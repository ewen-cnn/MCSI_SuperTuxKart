import unittest
from pose_types import Point3D, PlayerPose
from config import SteeringConfig
from gestures import SteeringEngine


def make_torso_pose(cx: float, shoulder_dx: float = 0.0, l_sh_y: float = 0.3, r_sh_y: float = 0.3) -> PlayerPose:
    # Hip at cx, 0.6. Shoulder at cx + shoulder_dx, 0.3
    sh_cx = cx + shoulder_dx
    return PlayerPose(
        left_shoulder=Point3D(sh_cx + 0.08, l_sh_y),
        right_shoulder=Point3D(sh_cx - 0.08, r_sh_y),
        left_wrist=Point3D(sh_cx + 0.05, 0.5),
        right_wrist=Point3D(sh_cx - 0.05, 0.5),
        left_hip=Point3D(cx + 0.05, 0.6),
        right_hip=Point3D(cx - 0.05, 0.6),
        nose=Point3D(sh_cx, 0.2),
        hip_x=cx, hip_y=0.6,
        shoulder_x=sh_cx, shoulder_y=(l_sh_y + r_sh_y) / 2.0,
        torso_size=0.3, landmarks=(),
    )


class TestInclinationSpine(unittest.TestCase):
    def setUp(self):
        self.cfg = SteeringConfig(
            strategy="inclination",
            inclination_mode="spine",
            lean_deadzone_deg=3.5,
            lean_max_deg=16.0,
        )
        self.engine = SteeringEngine(self.cfg)

    def test_upright_neutral(self):
        p1 = make_torso_pose(0.5, shoulder_dx=0.0)
        state = self.engine.calculate(p1, None, 0.3, 0.7, 0.5, 0.5, timestamp=1.0)
        self.assertIsNone(state.direction)
        self.assertEqual(state.intensity, 0.0)

    def test_torso_lean_left_and_right(self):
        # Lean Left: shoulder_x is 0.42 while hip is 0.50 (dx = -0.08, dy = 0.3)
        # angle ≈ atan2(-0.08, 0.3) ≈ -14.9 deg > deadzone (3.5 deg)
        p_left = make_torso_pose(0.5, shoulder_dx=-0.08)
        state_left = self.engine.calculate(p_left, None, 0.3, 0.7, 0.5, 0.5, timestamp=1.0)
        self.assertEqual(state_left.direction, "LEFT")
        self.assertGreater(state_left.intensity, 0.7)

        # Lean Right: shoulder_x is 0.58 while hip is 0.50 (dx = +0.08)
        p_right = make_torso_pose(0.5, shoulder_dx=0.08)
        state_right = self.engine.calculate(p_right, None, 0.3, 0.7, 0.5, 0.5, timestamp=1.1)
        self.assertEqual(state_right.direction, "RIGHT")
        self.assertGreater(state_right.intensity, 0.7)

    def test_shoulder_shrug_immunity(self):
        # Vertical spine: hip at 0.5, shoulder center at 0.5
        # But left shoulder lifted (shrug): l_sh_y = 0.26 instead of 0.30
        p_shrug = make_torso_pose(0.5, shoulder_dx=0.0, l_sh_y=0.26, r_sh_y=0.30)
        # Spine vector is perfectly vertical (dx = 0)
        state = self.engine.calculate(p_shrug, None, 0.3, 0.7, 0.5, 0.5, timestamp=1.0)
        self.assertIsNone(state.direction, "Spine inclination should be immune to shoulder shrugs!")


if __name__ == "__main__":
    unittest.main()
