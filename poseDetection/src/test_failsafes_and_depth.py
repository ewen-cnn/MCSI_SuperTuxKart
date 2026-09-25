import unittest
import math
from pose_types import Point3D, PlayerPose
from config import TrackerConfig
from filters import OneEuroFilter


class TestFailsafesAndDepth(unittest.TestCase):
    def test_point3d_failsafes(self):
        p_valid = Point3D(0.5, 0.5)
        p_nan = Point3D(float("nan"), 0.5)
        p_inf = Point3D(0.5, float("inf"))

        self.assertTrue(p_valid.is_valid())
        self.assertFalse(p_nan.is_valid())
        self.assertFalse(p_inf.is_valid())

        # distance_to safe fallback
        self.assertEqual(p_valid.distance_to(p_nan), 999.0)

        # midpoint safe fallback
        mid = Point3D.midpoint(p_valid, p_nan)
        self.assertEqual(mid, p_valid)

    def test_one_euro_filter_nan_and_jump_resilience(self):
        oef = OneEuroFilter()
        v1 = oef.filter(10.0, timestamp=1.0)
        self.assertEqual(v1, 10.0)

        # NaN input should not corrupt filter state
        v_nan = oef.filter(float("nan"), timestamp=1.033)
        self.assertEqual(v_nan, 10.0)

        # Huge timestamp gap (e.g. dropped frames or sleep) resets velocity
        v_gap = oef.filter(20.0, timestamp=3.0)
        self.assertEqual(v_gap, 20.0)

    def test_player_pose_spine_angle(self):
        # Mirrored: left shoulder has higher x, right shoulder lower x
        l_sh = Point3D(0.58, 0.3)
        r_sh = Point3D(0.42, 0.3)
        l_hip = Point3D(0.58, 0.6)
        r_hip = Point3D(0.42, 0.6)

        pose_upright = PlayerPose(
            left_shoulder=l_sh, right_shoulder=r_sh,
            left_wrist=Point3D(0.5, 0.5), right_wrist=Point3D(0.5, 0.5),
            left_hip=l_hip, right_hip=r_hip,
            nose=Point3D(0.5, 0.2),
            hip_x=0.5, hip_y=0.6,
            shoulder_x=0.5, shoulder_y=0.3,
            torso_size=0.3, landmarks=(),
        )
        self.assertTrue(pose_upright.is_valid_detection())
        self.assertAlmostEqual(pose_upright.spine_lean_angle_deg, 0.0, places=1)

        # Lean torso Left (shoulders move left towards x=0.40)
        pose_left = PlayerPose(
            left_shoulder=Point3D(0.48, 0.3), right_shoulder=Point3D(0.32, 0.3),
            left_wrist=Point3D(0.4, 0.5), right_wrist=Point3D(0.4, 0.5),
            left_hip=l_hip, right_hip=r_hip,
            nose=Point3D(0.4, 0.2),
            hip_x=0.5, hip_y=0.6,
            shoulder_x=0.4, shoulder_y=0.3,
            torso_size=0.3, landmarks=(),
        )
        # dx = 0.4 - 0.5 = -0.1, dy = 0.6 - 0.3 = 0.3 -> angle < 0 (left)
        self.assertLess(pose_left.spine_lean_angle_deg, -10.0)


if __name__ == "__main__":
    unittest.main()
