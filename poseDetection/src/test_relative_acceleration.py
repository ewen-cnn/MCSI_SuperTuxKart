import unittest
from pose_types import Point3D, PlayerPose
from config import AppConfig, GestureConfig, SteeringConfig
from gestures import DuoGestureDetector


def make_player(cx: float) -> PlayerPose:
    return PlayerPose(
        left_shoulder=Point3D(cx + 0.08, 0.4),
        right_shoulder=Point3D(cx - 0.08, 0.4),
        left_wrist=Point3D(cx + 0.05, 0.6),
        right_wrist=Point3D(cx - 0.05, 0.6),
        left_hip=Point3D(cx + 0.05, 0.7),
        right_hip=Point3D(cx - 0.05, 0.7),
        nose=Point3D(cx, 0.3),
        hip_x=cx, hip_y=0.7,
        shoulder_x=cx, shoulder_y=0.4,
        torso_size=0.3, landmarks=(),
    )


class TestRelativeAcceleration(unittest.TestCase):
    def test_cornering_throttle_reduction_and_recovery(self):
        cfg = AppConfig()
        cfg.gestures.cornering_lift_enabled = True
        cfg.gestures.cornering_lift_steer_threshold = 0.45
        cfg.gestures.corner_lift_max_duration_s = 0.65

        detector = DuoGestureDetector(config=cfg)
        detector.cruise_control = True  # Auto-acceleration active

        # Case 1: Going straight -> Full throttle
        p_straight = make_player(0.28)  # inside neutral
        res1 = detector.detect(p1=p_straight, timestamp=1.0)
        self.assertTrue(res1.accelerate)
        self.assertFalse(res1.corner_lift)

        # Case 2: Enter hard turn (shoulder_x = 0.15) -> Cornering throttle lift-off!
        p_turn = make_player(0.15)
        # Force a hard steer in steering engine
        res2 = detector.detect(p1=p_turn, timestamp=2.0)
        # Even with time ramp, at t=2.0 base power is 0.25 < 0.45.
        # At t=2.40 (0.40s hold), power > 0.45 -> corner_lift activates!
        res3 = detector.detect(p1=p_turn, timestamp=2.40)
        self.assertTrue(res3.corner_lift, "Throttle should be lifted during initial hard cornering entry!")
        self.assertFalse(res3.accelerate)

        # Case 3: Prolonged turn (> 0.65s, t=3.15) -> Drive recovery restores acceleration
        res4 = detector.detect(p1=p_turn, timestamp=3.15)
        self.assertFalse(res4.corner_lift, "Corner lift should expire to prevent getting stuck!")
        self.assertTrue(res4.accelerate, "Drive recovery should restore momentum!")


if __name__ == "__main__":
    unittest.main()
