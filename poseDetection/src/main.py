import time
import cv2

try:
    from poseDetection.src.capture import Camera
    from poseDetection.src.tracker import PoseTracker
    from poseDetection.src.gestures import DuoGestureDetector
    from poseDetection.src.network import STKClient
except ImportError:
    from capture import Camera
    from tracker import PoseTracker
    from gestures import DuoGestureDetector
    from network import STKClient


def main():
    cam = Camera()
    if not cam.is_opened():
        print("Error: could not open camera")
        return

    tracker = PoseTracker()
    detector = DuoGestureDetector()
    client = STKClient()

    COLOR_P1 = (255, 255, 0)
    COLOR_P2 = (255, 0, 255)

    prev = time.time()
    fps = 0.0

    try:
        while True:
            ret, frame = cam.read()
            if not ret:
                break

            p1, p2 = tracker.process(frame)
            gestures = detector.detect(p1, p2)

            actions = set()
            if gestures["accelerate"]:
                actions.add("ACCELERATE")
            if gestures["brake"]:
                actions.add("BRAKE")
            if gestures["rescue"]:
                actions.add("RESCUE")
            if gestures["steer_active"]:
                if gestures["steer"] == "LEFT":
                    actions.add("LEFT")
                elif gestures["steer"] == "RIGHT":
                    actions.add("RIGHT")

            client.update(actions)

            tracker.draw_player(frame, p1, COLOR_P1, "P1")
            tracker.draw_player(frame, p2, COLOR_P2, "P2")

            h, w, _ = frame.shape

            # Vertical action threshold lines and Neutral Zone
            lx = int(gestures["left_thresh"] * w)
            rx = int(gestures["right_thresh"] * w)
            cv2.line(frame, (lx, 0), (lx, h), (120, 120, 120), 1)
            cv2.line(frame, (rx, 0), (rx, h), (120, 120, 120), 1)

            nz_mid = (lx + rx) // 2
            cv2.putText(frame, "NEUTRAL ZONE", (nz_mid - 60, h - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 160, 160), 1)

            # Outer full-lock lines
            left_max_px = int(detector.steer_margin * w)
            right_max_px = int((1.0 - detector.steer_margin) * w)
            cv2.line(frame, (left_max_px, 0), (left_max_px, h), (40, 40, 120), 1)
            cv2.line(frame, (right_max_px, 0), (right_max_px, h), (40, 40, 120), 1)

            # Hip points & horizontal brake threshold lines
            if gestures["p1_hip"]:
                hx, hy = gestures["p1_hip"]
                col = (0, 0, 255) if gestures["p1_brake"] else (0, 255, 255)
                cv2.circle(frame, (int(hx * w), int(hy * h)), 7, col, -1)

                b_y = int(gestures["p1_brake_y"] * h)
                b_col = (0, 0, 255) if gestures["p1_brake"] else (70, 70, 70)
                cv2.line(frame, (0, b_y), (w // 2, b_y), b_col, 1)
                cv2.putText(frame, "P1 BRAKE", (10, b_y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.4, b_col, 1)

            if gestures["p2_hip"]:
                hx, hy = gestures["p2_hip"]
                col = (0, 0, 255) if gestures["p2_brake"] else (255, 0, 255)
                cv2.circle(frame, (int(hx * w), int(hy * h)), 7, col, -1)

                b_y = int(gestures["p2_brake_y"] * h)
                b_col = (0, 0, 255) if gestures["p2_brake"] else (70, 70, 70)
                cv2.line(frame, (w // 2, b_y), (w, b_y), b_col, 1)
                cv2.putText(frame, "P2 BRAKE", (w - 90, b_y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.4, b_col, 1)

            now = time.time()
            dt = now - prev
            prev = now
            if dt > 0:
                fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps > 0 else 1.0 / dt

            cv2.putText(frame, f"FPS: {fps:.1f}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)

            p1_pct = int(gestures["p1_power"] * 100)
            p2_pct = int(gestures["p2_power"] * 100)
            cv2.putText(frame, f"P1 Left: {p1_pct}%", (20, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.65, COLOR_P1, 2)
            cv2.putText(frame, f"P2 Right: {p2_pct}%", (w - 190, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.65, COLOR_P2, 2)

            if gestures["steer"]:
                net_pct = int(gestures["steer_intensity"] * 100)
                active_str = "●" if gestures["steer_active"] else "○"
                col = (0, 255, 0) if gestures["steer_active"] else (120, 200, 120)
                text = f"NET: {gestures['steer']} {net_pct}% {active_str}"
                cv2.putText(frame, text, (w // 2 - 110, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, col, 2)
            else:
                cv2.putText(frame, "NET: STRAIGHT", (w // 2 - 80, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (180, 180, 180), 2)

            if gestures["accelerate"]:
                cv2.putText(frame, "ACCEL: ON [CRUISE]", (20, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            elif gestures["cruise_control"] and gestures["brake"]:
                cv2.putText(frame, "ACCEL: PAUSED (BRAKE)", (20, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)
            else:
                cv2.putText(frame, "ACCEL: OFF [Raise Hand]", (20, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (80, 80, 80), 2)

            brake_col = (0, 0, 255) if "BRAKE" in actions else (80, 80, 80)
            cv2.putText(frame, "BRAKE", (20, 115), cv2.FONT_HERSHEY_SIMPLEX, 0.6, brake_col, 2)

            rescue_col = (0, 165, 255) if "RESCUE" in actions else (80, 80, 80)
            cv2.putText(frame, "RESCUE", (20, 145), cv2.FONT_HERSHEY_SIMPLEX, 0.6, rescue_col, 2)

            if gestures["t_pose_progress"] > 0:
                prog = int(gestures["t_pose_progress"] * 100)
                cv2.putText(frame, f"CALIBRATING: {prog}%", (w // 2 - 90, 70),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
            elif detector.calibrated:
                cv2.putText(frame, "CALIBRATED ('c' to reset)", (w // 2 - 100, 70),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)

            cv2.imshow("SuperTuxKart Vision Controller", frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), 27):
                break
            elif key in (ord('c'), ord('C')):
                detector.calibrate(p1, p2)
            elif key in (ord('a'), ord('A')):
                detector.cruise_control = not detector.cruise_control

    finally:
        client.close()
        cam.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
