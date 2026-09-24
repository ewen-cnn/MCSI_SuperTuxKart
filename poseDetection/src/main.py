import time
from typing import Optional
import cv2

from config import AppConfig, DEFAULT_CONFIG
from capture import Camera
from tracker import PoseTracker
from gestures import DuoGestureDetector
from network import STKClient
from hud import HUD


def run_controller(config: Optional[AppConfig] = None):
    cfg = config or DEFAULT_CONFIG

    print("Starting SuperTuxKart Vision Controller...")
    print("Controls:")
    print("  'c' / 'C' : Force immediate baseline calibration")
    print("  'a' / 'A' : Toggle cruise control (acceleration)")
    print("  'r' / 'R' : Toggle rescue mode (color card vs physical jump)")
    print("  's' / 'S' : Calibrate/sample card color in center box")
    print("  'q' / ESC : Exit application\n")

    with Camera(cfg.camera) as cam, STKClient(cfg.network) as client:
        if not cam.is_opened():
            print("Error: Could not open camera device.")
            return

        tracker = PoseTracker(config=cfg.tracker, filter_config=cfg.filter)
        detector = DuoGestureDetector(config=cfg)
        hud = HUD()

        prev_time = time.time()
        fps = 0.0

        try:
            while True:
                ret, frame = cam.read()
                if not ret:
                    break

                now = time.time()
                dt = now - prev_time
                prev_time = now
                if dt > 0:
                    fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps > 0 else 1.0 / dt

                p1, p2 = tracker.process(frame, timestamp=now)
                gestures = detector.detect(p1, p2, frame=frame, timestamp=now)

                # Map gestures to SuperTuxKart actions
                actions = set()
                if gestures.accelerate:
                    actions.add("ACCELERATE")
                if gestures.brake:
                    actions.add("BRAKE")
                if gestures.rescue:
                    actions.add("RESCUE")
                if gestures.steering.active and gestures.steering.direction:
                    actions.add(gestures.steering.direction)

                client.update(actions)

                hud.render(frame, p1, p2, gestures, fps, detector.steer_margin)
                cv2.imshow("SuperTuxKart Vision Controller", frame)

                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break
                elif key in (ord("c"), ord("C")):
                    detector.calibrate(p1, p2, timestamp=now)
                elif key in (ord("a"), ord("A")):
                    detector.cruise_control = not detector.cruise_control
                elif key in (ord("r"), ord("R")):
                    new_mode = detector.toggle_rescue_mode()
                    print(f"Rescue mode toggled to: {new_mode.upper()}")
                elif key in (ord("s"), ord("S")):
                    success, msg = detector.sample_card_color(frame)
                    print(f"[Color Calibration] {msg}")
                    hud.show_message(
                        msg,
                        duration=3.0,
                        color=(0, 255, 0) if success else (0, 0, 255),
                    )

        finally:
            cv2.destroyAllWindows()


def main():
    run_controller()


if __name__ == "__main__":
    main()
