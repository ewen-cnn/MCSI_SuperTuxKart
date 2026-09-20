import cv2

try:
    from poseDetection.src.capture import Camera
    from poseDetection.src.tracker import PoseTracker
except ImportError:
    from capture import Camera
    from tracker import PoseTracker


class DuoGestureDetector:
    def __init__(self, steer_deadzone=0.07, crouch_threshold=0.08, jump_velocity=0.05):
        self.steer_deadzone = steer_deadzone
        self.crouch_threshold = crouch_threshold
        self.jump_velocity = jump_velocity
        self.prev_hip_y = None
        self.standing_hip_y = None

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

    def detect(self, p1_landmarks, p2_landmarks):
        p1_hip = self._hip_pos(p1_landmarks)
        p2_hip = self._hip_pos(p2_landmarks)

        # Lateral steering based on midpoint
        mid_x = None
        if p1_hip and p2_hip:
            mid_x = (p1_hip[0] + p2_hip[0]) / 2.0
        elif p1_hip:
            mid_x = p1_hip[0]
        elif p2_hip:
            mid_x = p2_hip[0]

        steer = None
        if mid_x is not None:
            dx = mid_x - 0.5
            if dx < -self.steer_deadzone:
                steer = "LEFT"
            elif dx > self.steer_deadzone:
                steer = "RIGHT"

        accelerate = self._hands_up(p1_landmarks) or self._hands_up(p2_landmarks)

        brake = False
        rescue = False

        current_hip_y = None
        if p1_hip and p2_hip:
            current_hip_y = (p1_hip[1] + p2_hip[1]) / 2.0
        elif p1_hip:
            current_hip_y = p1_hip[1]
        elif p2_hip:
            current_hip_y = p2_hip[1]

        if current_hip_y is not None:
            if self.standing_hip_y is None or current_hip_y < self.standing_hip_y:
                self.standing_hip_y = current_hip_y
            else:
                self.standing_hip_y += 0.001

            if current_hip_y > self.standing_hip_y + self.crouch_threshold:
                brake = True

            if self.prev_hip_y is not None:
                if (self.prev_hip_y - current_hip_y) > self.jump_velocity:
                    rescue = True

            self.prev_hip_y = current_hip_y
        else:
            self.prev_hip_y = None

        return {
            "steer": steer,
            "accelerate": accelerate,
            "brake": brake,
            "rescue": rescue,
            "mid_x": mid_x,
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

        tracker.draw_player(frame, p1, COLOR_P1, "P1")
        tracker.draw_player(frame, p2, COLOR_P2, "P2")

        h, w, _ = frame.shape
        cv2.line(frame, (w // 2, 0), (w // 2, h), (100, 100, 100), 1)
        dz_px = int(detector.steer_deadzone * w)
        cv2.line(frame, (w // 2 - dz_px, 0), (w // 2 - dz_px, h), (70, 70, 70), 1)
        cv2.line(frame, (w // 2 + dz_px, 0), (w // 2 + dz_px, h), (70, 70, 70), 1)

        if gestures["mid_x"] is not None:
            cx = int(gestures["mid_x"] * w)
            cv2.circle(frame, (cx, h - 35), 8, (0, 255, 255), -1)

        steer_str = gestures["steer"] or "CENTER"
        cv2.putText(frame, f"STEER: {steer_str}", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0) if gestures["steer"] else (180, 180, 180), 2)
        cv2.putText(frame, "ACCEL", (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 255, 0) if gestures["accelerate"] else (80, 80, 80), 2)
        cv2.putText(frame, "BRAKE", (20, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 0, 255) if gestures["brake"] else (80, 80, 80), 2)
        cv2.putText(frame, "RESCUE", (20, 145), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 165, 255) if gestures["rescue"] else (80, 80, 80), 2)

        cv2.imshow("Gestures Test", frame)
        if cv2.waitKey(1) & 0xFF in (ord('q'), 27):
            break

    cam.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
