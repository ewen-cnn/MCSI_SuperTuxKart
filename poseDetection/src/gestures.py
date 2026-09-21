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

        # 1. Player 1: Dedicated Left Steerer (leans outward left)
        p1_left_power = 0.0
        if p1_hip:
            dx1 = self.p1_neutral_x - p1_hip[0]
            if dx1 > self.steer_deadzone:
                travel1 = (self.p1_neutral_x - self.steer_deadzone) - self.steer_margin
                if travel1 > 0:
                    p1_left_power = min(1.0, max(0.0, (dx1 - self.steer_deadzone) / travel1))

        # 2. Player 2: Dedicated Right Steerer (leans outward right)
        p2_right_power = 0.0
        if p2_hip:
            dx2 = p2_hip[0] - self.p2_neutral_x
            if dx2 > self.steer_deadzone:
                travel2 = (1.0 - self.steer_margin) - (self.p2_neutral_x + self.steer_deadzone)
                if travel2 > 0:
                    p2_right_power = min(1.0, max(0.0, (dx2 - self.steer_deadzone) / travel2))

        # Solo fallback if playing alone
        if p1_hip and not p2_hip:
            dx1_right = p1_hip[0] - self.p1_neutral_x
            if dx1_right > self.steer_deadzone:
                travel = (1.0 - self.steer_margin) - (self.p1_neutral_x + self.steer_deadzone)
                if travel > 0:
                    p2_right_power = min(1.0, max(0.0, (dx1_right - self.steer_deadzone) / travel))
        elif p2_hip and not p1_hip:
            dx2_left = self.p2_neutral_x - p2_hip[0]
            if dx2_left > self.steer_deadzone:
                travel = (self.p2_neutral_x - self.steer_deadzone) - self.steer_margin
                if travel > 0:
                    p1_left_power = min(1.0, max(0.0, (dx2_left - self.steer_deadzone) / travel))

        # 3. Differential Net Steering
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

        accelerate = self._hands_up(p1_landmarks) or self._hands_up(p2_landmarks)

        # 4. Crouch & Jump handling per player
        brake = False
        rescue = False

        if p1_hip:
            if self.p1_standing_y is None or p1_hip[1] < self.p1_standing_y:
                self.p1_standing_y = p1_hip[1]
            else:
                self.p1_standing_y += 0.001

            if p1_hip[1] > self.p1_standing_y + self.crouch_threshold:
                brake = True

            if self.p1_prev_y is not None and (self.p1_prev_y - p1_hip[1]) > self.jump_velocity:
                rescue = True
            self.p1_prev_y = p1_hip[1]
        else:
            self.p1_prev_y = None

        if p2_hip:
            if self.p2_standing_y is None or p2_hip[1] < self.p2_standing_y:
                self.p2_standing_y = p2_hip[1]
            else:
                self.p2_standing_y += 0.001

            if p2_hip[1] > self.p2_standing_y + self.crouch_threshold:
                brake = True

            if self.p2_prev_y is not None and (self.p2_prev_y - p2_hip[1]) > self.jump_velocity:
                rescue = True
            self.p2_prev_y = p2_hip[1]
        else:
            self.p2_prev_y = None

        return {
            "steer": steer,
            "steer_intensity": steer_intensity,
            "steer_active": steer_active,
            "p1_power": p1_left_power,
            "p2_power": p2_right_power,
            "accelerate": accelerate,
            "brake": brake,
            "rescue": rescue,
            "p1_neutral_x": self.p1_neutral_x,
            "p2_neutral_x": self.p2_neutral_x,
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

        # Draw P1 neutral and deadzone
        p1_cx = int(detector.p1_neutral_x * w)
        cv2.line(frame, (p1_cx, 0), (p1_cx, h), (100, 100, 100), 1)
        p1_dz_px = int((detector.p1_neutral_x - detector.steer_deadzone) * w)
        cv2.line(frame, (p1_dz_px, 0), (p1_dz_px, h), (70, 70, 70), 1)

        # Draw P2 neutral and deadzone
        p2_cx = int(detector.p2_neutral_x * w)
        cv2.line(frame, (p2_cx, 0), (p2_cx, h), (100, 100, 100), 1)
        p2_dz_px = int((detector.p2_neutral_x + detector.steer_deadzone) * w)
        cv2.line(frame, (p2_dz_px, 0), (p2_dz_px, h), (70, 70, 70), 1)

        # Draw outer full-lock margins
        left_max_px = int(detector.steer_margin * w)
        right_max_px = int((1.0 - detector.steer_margin) * w)
        cv2.line(frame, (left_max_px, 0), (left_max_px, h), (40, 40, 120), 1)
        cv2.line(frame, (right_max_px, 0), (right_max_px, h), (40, 40, 120), 1)

        # Dual power HUD
        p1_pct = int(gestures["p1_power"] * 100)
        p2_pct = int(gestures["p2_power"] * 100)
        cv2.putText(frame, f"P1 Left: {p1_pct}%", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, COLOR_P1, 2)
        cv2.putText(frame, f"P2 Right: {p2_pct}%", (w - 230, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, COLOR_P2, 2)

        # Net steering display in center
        if gestures["steer"]:
            net_pct = int(gestures["steer_intensity"] * 100)
            active_str = "●" if gestures["steer_active"] else "○"
            col = (0, 255, 0) if gestures["steer_active"] else (120, 200, 120)
            text = f"NET: {gestures['steer']} {net_pct}% {active_str}"
            cv2.putText(frame, text, (w // 2 - 120, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.75, col, 2)
        else:
            cv2.putText(frame, "NET: STRAIGHT", (w // 2 - 90, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (180, 180, 180), 2)

        cv2.putText(frame, "ACCEL", (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 255, 0) if gestures["accelerate"] else (80, 80, 80), 2)
        cv2.putText(frame, "BRAKE", (20, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 0, 255) if gestures["brake"] else (80, 80, 80), 2)
        cv2.putText(frame, "RESCUE", (20, 145), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 165, 255) if gestures["rescue"] else (80, 80, 80), 2)

        if gestures["t_pose_progress"] > 0:
            prog = int(gestures["t_pose_progress"] * 100)
            cv2.putText(frame, f"CALIBRATING: {prog}%", (w // 2 - 100, 80),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        elif detector.calibrated:
            cv2.putText(frame, "CALIBRATED ('c' to reset)", (w // 2 - 120, 80),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

        cv2.imshow("Gestures Test", frame)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord('q'), 27):
            break
        elif key in (ord('c'), ord('C')):
            detector.calibrate(p1, p2)

    cam.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
