import unittest
from pose_types import Point3D, PlayerPose
from config import SteeringConfig
from gestures import SteeringEngine


def make_pose(cx: float) -> PlayerPose:
    return PlayerPose(
        left_shoulder=Point3D(cx + 0.08, 0.3),
        right_shoulder=Point3D(cx - 0.08, 0.3),
        left_wrist=Point3D(cx + 0.05, 0.5),
        right_wrist=Point3D(cx - 0.05, 0.5),
        left_hip=Point3D(cx + 0.05, 0.6),
        right_hip=Point3D(cx - 0.05, 0.6),
        nose=Point3D(cx, 0.2),
        hip_x=cx, hip_y=0.6,
        shoulder_x=cx, shoulder_y=0.3,
        torso_size=0.3, landmarks=(),
    )


class TestTimeSteering(unittest.TestCase):
    def test_time_based_threshold_ramp_and_instant_reset(self):
        cfg = SteeringConfig(
            time_based_position=True,
            time_steer_base_intensity=0.25,
            time_steer_ramp_seconds=0.70,
            deadzone=0.05,
        )
        engine = SteeringEngine(cfg)

        left_thresh = 0.23  # (0.28 - 0.05)
        right_thresh = 0.77 # (0.72 + 0.05)

        # 1. P1 in neutral (shoulder_x = 0.28) -> No steering
        p1 = make_pose(0.28)
        state_neutral = engine.calculate(p1, None, left_thresh, right_thresh, 0.28, 0.72, timestamp=1.0)
        self.assertIsNone(state_neutral.direction)
        self.assertEqual(state_neutral.intensity, 0.0)

        # 2. P1 steps across threshold (shoulder_x = 0.20 < 0.23) at t=2.0
        # Immediately turns at base intensity (0.25)
        p1_steer = make_pose(0.20)
        state_start = engine.calculate(p1_steer, None, left_thresh, right_thresh, 0.28, 0.72, timestamp=2.0)
        self.assertEqual(state_start.direction, "LEFT")
        self.assertAlmostEqual(state_start.intensity, 0.25, places=2)

        # 3. Holding across threshold at t=2.35 (halfway = 0.35s)
        # Power should be base (0.25) + 0.75 * 0.5 = 0.625
        state_half = engine.calculate(p1_steer, None, left_thresh, right_thresh, 0.28, 0.72, timestamp=2.35)
        self.assertEqual(state_half.direction, "LEFT")
        self.assertAlmostEqual(state_half.intensity, 0.625, places=2)

        # 4. Holding across threshold at t=2.70 (full ramp = 0.70s)
        # Power reaches 1.0 (100% full lock)
        state_full = engine.calculate(p1_steer, None, left_thresh, right_thresh, 0.28, 0.72, timestamp=2.70)
        self.assertEqual(state_full.direction, "LEFT")
        self.assertAlmostEqual(state_full.intensity, 1.0, places=2)

        # 5. Instantly steps back inside threshold (shoulder_x = 0.28) at t=2.71
        # ZERO LAG: Resets immediately to straight (0.0)
        state_reset = engine.calculate(p1, None, left_thresh, right_thresh, 0.28, 0.72, timestamp=2.71)
        self.assertIsNone(state_reset.direction)
        self.assertEqual(state_reset.intensity, 0.0)


if __name__ == "__main__":
    unittest.main()
