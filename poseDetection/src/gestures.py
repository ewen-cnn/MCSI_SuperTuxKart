import time
import cv2

try:
    from poseDetection.src.capture import Camera
    from poseDetection.src.tracker import PoseTracker
    from poseDetection.src.config import (
        STEER_DEADZONE,
        STEER_MARGIN,
        PWM_PERIOD,
        CROUCH_THRESHOLD,
        JUMP_VELOCITY,
    )
except ImportError:
    from capture import Camera
    from tracker import PoseTracker
    from config import (
        STEER_DEADZONE,
        STEER_MARGIN,
        PWM_PERIOD,
        CROUCH_THRESHOLD,
        JUMP_VELOCITY,
    )


class DuoGestureDetector:
    def __init__(
        self,
        steer_deadzone: float = STEER_DEADZONE,
        steer_margin: float = STEER_MARGIN,
        pwm_period: float = PWM_PERIOD,
        crouch_threshold: float = CROUCH_THRESHOLD,
        jump_velocity: float = JUMP_VELOCITY,
    ):
        self.steer_deadzone = steer_deadzone
        self.steer_margin = steer_margin
        self.pwm_period = pwm_period
        self.crouch_threshold = crouch_threshold
        self.jump_velocity = jump_velocity

        self.p1_neutral_x = 0.35
        self.p2_neutral_x = 0.65
        self.p1_standing_y = None
        self.p2_standing_y = None
        self.p1_prev_y = None
        self.p2_prev_y = None

        self.calibrated = False
        self.t_pose_counter = 0

        self.cruise_control = False
        self.prev_hands_up = False

    @staticmethod
    def _hip_pos(landmarks):
        if landmarks is None:
            return None
        hx = (landmarks[23].x + landmarks[24].x) / 2.0
        hy = (landmarks[23].y + landmarks[24].y) / 2.0
        return hx, hy

    @staticmethod
    def _hands_up(landmarks):
        if landmarks is None:
            return False
        return (landmarks[15].y < landmarks[11].y) or (landmarks[16].y < landmarks[12].y)

    @staticmethod
    def _is_t_pose(landmarks):
        if landmarks is None:
            return False
        left_arm = (abs(landmarks[15].y - landmarks[11].y) < 0.12) and (abs(landmarks[15].x - landmarks[11].x) > 0.15)
        right_arm = (abs(landmarks[16].y - landmarks[12].y) < 0.12) and (abs(landmarks[16].x - landmarks[12].x) > 0.15)
        return left_arm and right_arm

    def calibrate(self, p1_landmarks, p2_landmarks):
        p1_hip = self._hip_pos(p1_landmarks)
        p2_hip = self._hip_pos(p2_landmarks)

        if p1_hip and p2_hip:
            self.p1_neutral_x = p1_hip[0]
            self.p2_neutral_x = p2_hip[0]
            self.p1_standing_y = p1_hip[1]
            self.p2_standing_y = p2_hip[1]
            self.calibrated = True
            return True
        elif p1_hip:
            self.p1_neutral_x = p1_hip[0]
            self.p1_standing_y = p1_hip[1]
            self.calibrated = True
            return True
        elif p2_hip:
            self.p2_neutral_x = p2_hip[0]
            self.p2_standing_y = p2_hip[1]
            self.calibrated = True
            return True
        return False

    def detect(self, p1_landmarks, p2_landmarks):
        p1_hip = self._hip_pos(p1_landmarks)
        p2_hip = self._hip_pos(p2_landmarks)

        p1_t = self._is_t_pose(p1_landmarks)
        p2_t = self._is_t_pose(p2_landmarks)
        t_pose_active = (p1_t and p2_t) if (p1_landmarks and p2_landmarks) else (p1_t or p2_t)

        just_calibrated = False
        if t_pose_active:
            self.t_pose_counter += 1
            if self.t_pose_counter >= 30:
                just_calibrated = self.calibrate(p1_landmarks, p2_landmarks)
                self.t_pose_counter = 0
        else:
            self.t_pose_counter = max(0, self.t_pose_counter - 1)

        left_thresh = self.p1_neutral_x - self.steer_deadzone
        right_thresh = self.p2_neutral_x + self.steer_deadzone

        p1_left_power = 0.0
        if p1_hip:
            if p1_hip[0] < left_thresh:
                travel1 = left_thresh - self.steer_margin
                if travel1 > 0:
                    p1_left_power = min(1.0, max(0.0, (left_thresh - p1_hip[0]) / travel1))

        p2_right_power = 0.0
        if p2_hip:
            if p2_hip[0] > right_thresh:
                travel2 = (1.0 - self.steer_margin) - right_thresh
                if travel2 > 0:
                    p2_right_power = min(1.0, max(0.0, (p2_hip[0] - right_thresh) / travel2))

        # Solo fallback if playing alone
        if p1_hip and not p2_hip:
            if p1_hip[0] > (self.p1_neutral_x + self.steer_deadzone):
                travel = (1.0 - self.steer_margin) - (self.p1_neutral_x + self.steer_deadzone)
                if travel > 0:
                    p2_right_power = min(1.0, max(0.0, (p1_hip[0] - (self.p1_neutral_x + self.steer_deadzone)) / travel))
        elif p2_hip and not p1_hip:
            if p2_hip[0] < (self.p2_neutral_x - self.steer_deadzone):
                travel = (self.p2_neutral_x - self.steer_deadzone) - self.steer_margin
                if travel > 0:
                    p1_left_power = min(1.0, max(0.0, ((self.p2_neutral_x - self.steer_deadzone) - p2_hip[0]) / travel))

        net = p1_left_power - p2_right_power
        steer = None
        steer_intensity = 0.0

        if net > 0.01:
            steer = "LEFT"
            steer_intensity = net
        elif net < -0.01:
            steer = "RIGHT"
            steer_intensity = abs(net)

        if steer_intensity >= 0.98:
            steer_active = True
        elif steer_intensity > 0.0:
            cycle_pos = (time.time() % self.pwm_period) / self.pwm_period
            steer_active = cycle_pos < steer_intensity
        else:
            steer_active = False

        hands_up = self._hands_up(p1_landmarks) or self._hands_up(p2_landmarks)
        if hands_up and not self.prev_hands_up:
            self.cruise_control = not self.cruise_control
        self.prev_hands_up = hands_up

        p1_brake_y = (self.p1_standing_y + self.crouch_threshold) if self.p1_standing_y is not None else 0.58
        p2_brake_y = (self.p2_standing_y + self.crouch_threshold) if self.p2_standing_y is not None else 0.58

        p1_brake = False
        p2_brake = False
        rescue = False

        if p1_hip:
            if self.p1_standing_y is None:
                self.p1_standing_y = p1_hip[1]
                p1_brake_y = self.p1_standing_y + self.crouch_threshold

            if p1_hip[1] > p1_brake_y:
                p1_brake = True

            if self.p1_prev_y is not None and (self.p1_prev_y - p1_hip[1]) > self.jump_velocity:
                rescue = True
            self.p1_prev_y = p1_hip[1]
        else:
            self.p1_prev_y = None

        if p2_hip:
            if self.p2_standing_y is None:
                self.p2_standing_y = p2_hip[1]
                p2_brake_y = self.p2_standing_y + self.crouch_threshold

            if p2_hip[1] > p2_brake_y:
                p2_brake = True

            if self.p2_prev_y is not None and (self.p2_prev_y - p2_hip[1]) > self.jump_velocity:
                rescue = True
            self.p2_prev_y = p2_hip[1]
        else:
            self.p2_prev_y = None

        brake = p1_brake or p2_brake
        accelerate = self.cruise_control and not brake

        return {
            "steer": steer,
            "steer_intensity": steer_intensity,
            "steer_active": steer_active,
            "p1_power": p1_left_power,
            "p2_power": p2_right_power,
            "accelerate": accelerate,
            "cruise_control": self.cruise_control,
            "brake": brake,
            "rescue": rescue,
            "p1_hip": p1_hip,
            "p2_hip": p2_hip,
            "p1_brake": p1_brake,
            "p2_brake": p2_brake,
            "p1_brake_y": p1_brake_y,
            "p2_brake_y": p2_brake_y,
            "left_thresh": left_thresh,
            "right_thresh": right_thresh,
            "calibrated": self.calibrated,
            "just_calibrated": just_calibrated,
            "t_pose_progress": min(1.0, self.t_pose_counter / 30.0),
        }


def main():
    cam = Camera()
    if not cam.is_opened():
        return

    tracker = PoseTracker()
    detector = DuoGestureDetector()

    COLOR_P1 = (255, 255, 0)
    COLOR_P2 = (255, 0, 255)

    while True:
        ret, frame = cam.read()
        if not ret:
            break

        p1, p2 = tracker.process(frame)
        gestures = detector.detect(p1, p2)

        tracker.draw_player(frame, p1, COLOR_P1, "P1 (Left Steer)")
        tracker.draw_player(frame, p2, COLOR_P2, "P2 (Right Steer)")

        h, w, _ = frame.shape

        # Vertical action boundary lines & Neutral Zone
        lx = int(gestures["left_thresh"] * w)
        rx = int(gestures["right_thresh"] * w)
        cv2.line(frame, (lx, 0), (lx, h), (120, 120, 120), 1)
        cv2.line(frame, (rx, 0), (rx, h), (120, 120, 120), 1)

        nz_mid = (lx + rx) // 2
        cv2.putText(frame, "NEUTRAL ZONE", (nz_mid - 65, h - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (160, 160, 160), 1)

        # Full-lock margin lines
        left_max_px = int(detector.steer_margin * w)
        right_max_px = int((1.0 - detector.steer_margin) * w)
        cv2.line(frame, (left_max_px, 0), (left_max_px, h), (40, 40, 120), 1)
        cv2.line(frame, (right_max_px, 0), (right_max_px, h), (40, 40, 120), 1)

        # Hip points & horizontal brake lines
        if gestures["p1_hip"]:
            hx, hy = gestures["p1_hip"]
            h_px = (int(hx * w), int(hy * w if hy * w < h else hy * h))
            h_px = (int(hx * w), int(hy * h))
            col = (0, 0, 255) if gestures["p1_brake"] else (0, 255, 255)
            cv2.circle(frame, h_px, 7, col, -1)

            b_y = int(gestures["p1_brake_y"] * h)
            b_col = (0, 0, 255) if gestures["p1_brake"] else (80, 80, 80)
            cv2.line(frame, (0, b_y), (w // 2, b_y), b_col, 1)
            cv2.putText(frame, "P1 BRAKE", (10, b_y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.4, b_col, 1)

        if gestures["p2_hip"]:
            hx, hy = gestures["p2_hip"]
            h_px = (int(hx * w), int(hy * h))
            col = (0, 0, 255) if gestures["p2_brake"] else (255, 0, 255)
            cv2.circle(frame, h_px, 7, col, -1)

            b_y = int(gestures["p2_brake_y"] * h)
            b_col = (0, 0, 255) if gestures["p2_brake"] else (80, 80, 80)
            cv2.line(frame, (w // 2, b_y), (w, b_y), b_col, 1)
            cv2.putText(frame, "P2 BRAKE", (w - 90, b_y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.4, b_col, 1)

        p1_pct = int(gestures["p1_power"] * 100)
        p2_pct = int(gestures["p2_power"] * 100)
        cv2.putText(frame, f"P1 Left: {p1_pct}%", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.65, COLOR_P1, 2)
        cv2.putText(frame, f"P2 Right: {p2_pct}%", (w - 200, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.65, COLOR_P2, 2)

        if gestures["steer"]:
            net_pct = int(gestures["steer_intensity"] * 100)
            active_str = "●" if gestures["steer_active"] else "○"
            col = (0, 255, 0) if gestures["steer_active"] else (120, 200, 120)
            text = f"NET: {gestures['steer']} {net_pct}% {active_str}"
            cv2.putText(frame, text, (w // 2 - 110, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, col, 2)
        else:
            cv2.putText(frame, "NET: STRAIGHT", (w // 2 - 80, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (180, 180, 180), 2)

        if gestures["accelerate"]:
            cv2.putText(frame, "ACCEL: ON [CRUISE]", (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        elif gestures["cruise_control"] and gestures["brake"]:
            cv2.putText(frame, "ACCEL: PAUSED (BRAKE)", (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)
        else:
            cv2.putText(frame, "ACCEL: OFF [Raise Hand]", (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (80, 80, 80), 2)

        cv2.putText(frame, "BRAKE", (20, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (0, 0, 255) if gestures["brake"] else (80, 80, 80), 2)
        cv2.putText(frame, "RESCUE", (20, 125), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (0, 165, 255) if gestures["rescue"] else (80, 80, 80), 2)

        if gestures["t_pose_progress"] > 0:
            prog = int(gestures["t_pose_progress"] * 100)
            cv2.putText(frame, f"CALIBRATING: {prog}%", (w // 2 - 90, 70),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
        elif detector.calibrated:
            cv2.putText(frame, "CALIBRATED ('c' to reset)", (w // 2 - 100, 70),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)

        cv2.imshow("Gestures Test", frame)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord('q'), 27):
            break
        elif key in (ord('c'), ord('C')):
            detector.calibrate(p1, p2)
        elif key in (ord('a'), ord('A')):
            detector.cruise_control = not detector.cruise_control

    cam.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
