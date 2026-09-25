import unittest
import time
from pose_types import Point3D, PlayerPose
from config import AppConfig, SteeringConfig, GestureConfig, CalibrationConfig
from gestures import DuoGestureDetector, SteeringEngine, VerticalActionDetector


def make_test_pose(shoulder_x: float, shoulder_y: float = 0.40, nose_y: float = 0.25) -> PlayerPose:
    return PlayerPose(
        left_shoulder=Point3D(shoulder_x + 0.08, shoulder_y),
        right_shoulder=Point3D(shoulder_x - 0.08, shoulder_y),
        left_wrist=Point3D(shoulder_x + 0.05, shoulder_y + 0.3),
        right_wrist=Point3D(shoulder_x - 0.05, shoulder_y + 0.3),
        left_hip=Point3D(shoulder_x + 0.05, shoulder_y + 0.35),
        right_hip=Point3D(shoulder_x - 0.05, shoulder_y + 0.35),
        nose=Point3D(shoulder_x, nose_y),
        hip_x=shoulder_x,
        hip_y=shoulder_y + 0.35,
        shoulder_x=shoulder_x,
        shoulder_y=shoulder_y,
        torso_size=0.35,
        landmarks=(),
    )


class TestSoloSteeringAndBrake(unittest.TestCase):
    def test_brake_triggers_on_shoulder_height_not_nose(self):
        """
        Verify that ducking shoulders past the brake threshold triggers brake,
        even when the nose remains well above the threshold line.
        """
        cfg = GestureConfig(default_standing_y=0.40, crouch_threshold=0.10)
        detector = VerticalActionDetector(cfg)

        brake_threshold = 0.50

        # Standing upright: shoulders at 0.40, nose at 0.25 -> No brake
        p_standing = make_test_pose(shoulder_x=0.50, shoulder_y=0.40, nose_y=0.25)
        brake, jump, _, _ = detector.evaluate_player(p_standing, standing_y=0.40, brake_y=brake_threshold)
        self.assertFalse(brake)

        # Crouching: shoulders drop to 0.53 (> 0.50), but nose is at 0.38 (< 0.50)
        # Previous bug evaluated nose_y, so brake failed to trigger.
        # Now it evaluates shoulder_y, so brake triggers immediately!
        p_crouch = make_test_pose(shoulder_x=0.50, shoulder_y=0.53, nose_y=0.38)
        brake, jump, _, _ = detector.evaluate_player(p_crouch, standing_y=0.40, brake_y=brake_threshold)
        self.assertTrue(brake)

    def test_crouch_cuts_throttle_and_engages_brake_in_pipeline(self):
        """
        Verify that during cruise control, crouching suppresses ACCELERATE and outputs BRAKE.
        """
        detector = DuoGestureDetector()
        detector.cruise_control = True

        # Upright player
        p_standing = make_test_pose(shoulder_x=0.50, shoulder_y=0.40, nose_y=0.25)
        res_standing = detector.detect(p_standing, None, timestamp=1.0)
        self.assertTrue(res_standing.accelerate)
        self.assertFalse(res_standing.brake)

        # Crouching player
        p_crouch = make_test_pose(shoulder_x=0.50, shoulder_y=0.54, nose_y=0.38)
        res_crouch = detector.detect(p_crouch, None, timestamp=1.1)
        self.assertFalse(res_crouch.accelerate, "Throttle must cut out while braking")
        self.assertTrue(res_crouch.brake, "Brake must be active for SuperTuxKart down key / reverse")

    def test_solo_steering_tight_neutral_centered_at_desk(self):
        """
        Verify that a solo player in front of camera (x=0.50) has a tight neutral zone
        [0.46, 0.54] rather than spanning 54% of the screen.
        """
        cfg = SteeringConfig(
            time_based_position=True,
            solo_deadzone=0.04,
            p1_center_x=0.28,
            p2_center_x=0.72,
        )
        engine = SteeringEngine(cfg)

        # 1. Player centered at 0.50 -> STRAIGHT (inside [0.46, 0.54])
        p_mid = make_test_pose(shoulder_x=0.50)
        st_mid = engine.calculate(p_mid, None, left_thresh=0.23, right_thresh=0.77, p1_neutral_x=0.28, p2_neutral_x=0.72, timestamp=1.0)
        self.assertIsNone(st_mid.direction)
        self.assertEqual(st_mid.intensity, 0.0)
        self.assertAlmostEqual(st_mid.left_thresh, 0.46, places=2)
        self.assertAlmostEqual(st_mid.right_thresh, 0.54, places=2)

        # 2. Player takes a small step left to 0.44 (< 0.46) -> Turns LEFT immediately
        p_left = make_test_pose(shoulder_x=0.44)
        st_left = engine.calculate(p_left, None, left_thresh=0.23, right_thresh=0.77, p1_neutral_x=0.28, p2_neutral_x=0.72, timestamp=2.0)
        self.assertEqual(st_left.direction, "LEFT")
        self.assertGreater(st_left.intensity, 0.0)

        # 3. Player takes a small step right to 0.56 (> 0.54) -> Turns RIGHT immediately
        # (Previously, player had to step all the way past 0.77 to turn right!)
        p_right = make_test_pose(shoulder_x=0.56)
        st_right = engine.calculate(p_right, None, left_thresh=0.23, right_thresh=0.77, p1_neutral_x=0.28, p2_neutral_x=0.72, timestamp=3.0)
        self.assertEqual(st_right.direction, "RIGHT")
        self.assertGreater(st_right.intensity, 0.0)

        # 4. Returning to center (0.50) -> Resets instantly to STRAIGHT
        st_back = engine.calculate(p_mid, None, left_thresh=0.23, right_thresh=0.77, p1_neutral_x=0.28, p2_neutral_x=0.72, timestamp=4.0)
        self.assertIsNone(st_back.direction)
        self.assertEqual(st_back.intensity, 0.0)

    def test_solo_steering_at_p1_position(self):
        """
        Verify that if the solo player stands at the P1 spot (x=0.28),
        the neutral zone is centered around 0.28 ([0.24, 0.32]).
        """
        cfg = SteeringConfig(
            time_based_position=True,
            solo_deadzone=0.04,
            p1_center_x=0.28,
            p2_center_x=0.72,
        )
        engine = SteeringEngine(cfg)

        # Player stands at 0.28
        p_p1 = make_test_pose(shoulder_x=0.28)
        st_p1 = engine.calculate(p_p1, None, left_thresh=0.23, right_thresh=0.77, p1_neutral_x=0.28, p2_neutral_x=0.72, timestamp=1.0)
        self.assertIsNone(st_p1.direction)
        self.assertAlmostEqual(st_p1.left_thresh, 0.24, places=2)
        self.assertAlmostEqual(st_p1.right_thresh, 0.32, places=2)

        # Stepping left to 0.20 (< 0.24) -> Turns LEFT
        p_left = make_test_pose(shoulder_x=0.20)
        st_left = engine.calculate(p_left, None, left_thresh=0.23, right_thresh=0.77, p1_neutral_x=0.28, p2_neutral_x=0.72, timestamp=2.0)
        self.assertEqual(st_left.direction, "LEFT")

        # Stepping right to 0.35 (> 0.32) -> Turns RIGHT
        p_right = make_test_pose(shoulder_x=0.35)
        st_right = engine.calculate(p_right, None, left_thresh=0.23, right_thresh=0.77, p1_neutral_x=0.28, p2_neutral_x=0.72, timestamp=3.0)
        self.assertEqual(st_right.direction, "RIGHT")


if __name__ == "__main__":
    unittest.main()
