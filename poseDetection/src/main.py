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

    left_th = getattr(cfg.steering, "left_threshold", 0.40)
    right_th = getattr(cfg.steering, "right_threshold", 0.60)
    is_narrow = abs((right_th - left_th) - 0.20) < 0.08
    mode_str = "SOLO (Narrow Neutral Zone)" if is_narrow else "DUO (Wide Neutral Zone)"
    print(f"Steering Setup: {mode_str} [Left: {left_th:.2f}, Right: {right_th:.2f}]")
    print("Controls:")
    print("  'c' / 'C' : Calibrate brake line to current shoulder height")
    print("  'a' / 'A' : Toggle cruise control (acceleration) [or raise hand]")
    print("  'd' / 'D' : Toggle clean arcade HUD vs debug telemetry view")
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

                if getattr(gestures, "just_calibrated", False):
                    hud.show_message("Brake line calibrated!", duration=2.5, color=(0, 255, 120))

                client.update(actions)

                hud.render(frame, p1, p2, gestures, fps, detector.steer_margin)
                cv2.imshow("SuperTuxKart Vision Controller", frame)

                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break
                elif key in (ord("c"), ord("C")):
                    detector.calibrate(p1, p2, timestamp=now)
                    hud.show_message("Brake line calibrated!", duration=2.5, color=(0, 255, 120))
                elif key in (ord("a"), ord("A")):
                    detector.cruise_control = not detector.cruise_control
                elif key in (ord("d"), ord("D")):
                    is_dbg = hud.toggle_debug()
                    status = "DEBUG TELEMETRY" if is_dbg else "CLEAN VIEW"
                    print(f"[HUD] Presentation mode: {status}")
                    hud.show_message(
                        f"HUD: {status}",
                        duration=1.8,
                        color=(0, 255, 255) if is_dbg else (0, 255, 120),
                    )

        finally:
            cv2.destroyAllWindows()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="MCSI SuperTuxKart Vision Controller")
    parser.add_argument(
        "--steering",
        choices=["position", "inclination"],
        default=None,
        help="Steering strategy: 'position' (time-based threshold) or 'inclination' (spine torso tilt)",
    )
    parser.add_argument(
        "--mode",
        choices=["solo", "duo"],
        default=None,
        help="Optional preset override: 'solo' (narrow neutral zone [0.40, 0.60]) or 'duo' (wide neutral zone [0.30, 0.70])",
    )
    args = parser.parse_args()

    cfg = AppConfig()
    if args.steering:
        cfg.steering.strategy = args.steering
    if args.mode == "solo":
        cfg.steering.left_threshold = 0.40
        cfg.steering.right_threshold = 0.60
    elif args.mode == "duo":
        cfg.steering.left_threshold = 0.30
        cfg.steering.right_threshold = 0.70

    run_controller(config=cfg)


if __name__ == "__main__":
    main()
