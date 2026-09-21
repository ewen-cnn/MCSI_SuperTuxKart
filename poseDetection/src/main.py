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
            if gestures["steer"] == "LEFT":
                actions.add("LEFT")
            elif gestures["steer"] == "RIGHT":
                actions.add("RIGHT")

            client.update(actions)

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

            now = time.time()
            dt = now - prev
            prev = now
            if dt > 0:
                fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps > 0 else 1.0 / dt

            cv2.putText(frame, f"FPS: {fps:.1f}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            steer_lbl = f"STEER: {gestures['steer'] or 'CENTER'}"
            cv2.putText(frame, steer_lbl, (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (0, 255, 0) if gestures["steer"] else (180, 180, 180), 2)

            accel_col = (0, 255, 0) if "ACCELERATE" in actions else (80, 80, 80)
            cv2.putText(frame, "ACCEL", (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.65, accel_col, 2)

            brake_col = (0, 0, 255) if "BRAKE" in actions else (80, 80, 80)
            cv2.putText(frame, "BRAKE", (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.65, brake_col, 2)

            rescue_col = (0, 165, 255) if "RESCUE" in actions else (80, 80, 80)
            cv2.putText(frame, "RESCUE", (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.65, rescue_col, 2)

            cv2.imshow("SuperTuxKart Vision Controller", frame)
            if cv2.waitKey(1) & 0xFF in (ord('q'), 27):
                break

    finally:
        client.close()
        cam.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
