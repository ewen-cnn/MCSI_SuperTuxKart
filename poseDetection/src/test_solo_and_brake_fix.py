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

    def test_solo_mode_two_threshold_lines_small_neutral_zone(self):
        """
        Verify Solo Mode with small neutral zone [0.40, 0.60]:
        Single player in center (0.50) goes straight.
        Leaning left (< 0.40) turns LEFT; leaning right (> 0.60) turns RIGHT.
        """
        cfg = SteeringConfig(
            left_threshold=0.40,
            right_threshold=0.60,
            time_based_position=True,
        )
        engine = SteeringEngine(cfg)

        # Player in center neutral zone (0.50) -> Straight
        p_center = make_test_pose(shoulder_x=0.50)
        st_center = engine.calculate(p_center, None, timestamp=1.0)
        self.assertIsNone(st_center.direction)
        self.assertEqual(st_center.intensity, 0.0)
        self.assertAlmostEqual(st_center.left_thresh, 0.40, places=2)
        self.assertAlmostEqual(st_center.right_thresh, 0.60, places=2)

        # Leaning left to 0.35 (< 0.40) -> Turns LEFT
        p_left = make_test_pose(shoulder_x=0.35)
        st_left = engine.calculate(p_left, None, timestamp=2.0)
        self.assertEqual(st_left.direction, "LEFT")
        self.assertGreater(st_left.intensity, 0.0)

        # Back to center neutral zone (0.50) -> Straight (instant reset)
        st_back = engine.calculate(p_center, None, timestamp=2.1)
        self.assertIsNone(st_back.direction)
        self.assertEqual(st_back.intensity, 0.0)

        # Leaning right to 0.65 (> 0.60) -> Turns RIGHT
        p_right = make_test_pose(shoulder_x=0.65)
        st_right = engine.calculate(p_right, None, timestamp=3.0)
        self.assertEqual(st_right.direction, "RIGHT")
        self.assertGreater(st_right.intensity, 0.0)

    def test_solo_mode_when_tracked_as_p2(self):
        """
        Verify that a solo player tracked as P2 also steers symmetrically.
        """
        cfg = SteeringConfig(
            left_threshold=0.40,
            right_threshold=0.60,
            time_based_position=True,
        )
        engine = SteeringEngine(cfg)

        # Center -> Straight
        p_center = make_test_pose(shoulder_x=0.50)
        st_center = engine.calculate(None, p_center, timestamp=1.0)
        self.assertIsNone(st_center.direction)

        # Leaning left -> Turns LEFT
        p_left = make_test_pose(shoulder_x=0.35)
        st_left = engine.calculate(None, p_left, timestamp=2.0)
        self.assertEqual(st_left.direction, "LEFT")

        # Leaning right -> Turns RIGHT
        p_right = make_test_pose(shoulder_x=0.65)
        st_right = engine.calculate(None, p_right, timestamp=3.0)
        self.assertEqual(st_right.direction, "RIGHT")

    def test_duo_mode_two_threshold_lines_big_neutral_zone(self):
        """
        Verify Duo Mode with big neutral zone [0.30, 0.70]:
        P1 can only activate LEFT (< 0.30).
        P2 can only activate RIGHT (> 0.70).
        Central space between 0.30 and 0.70 is neutral.
        """
        cfg = SteeringConfig(
            left_threshold=0.30,
            right_threshold=0.70,
            time_based_position=True,
        )
        engine = SteeringEngine(cfg)

        p1_neutral = make_test_pose(shoulder_x=0.35)
        p2_neutral = make_test_pose(shoulder_x=0.65)

        # Both inside neutral zone [0.30, 0.70] -> Straight
        st = engine.calculate(p1_neutral, p2_neutral, timestamp=1.0)
        self.assertIsNone(st.direction)

        # P1 leans left to 0.22 (< 0.30) -> Turns LEFT
        p1_steer = make_test_pose(shoulder_x=0.22)
        st_duo_l = engine.calculate(p1_steer, p2_neutral, timestamp=2.0)
        self.assertEqual(st_duo_l.direction, "LEFT")

        # P1 steps right to 0.45 (into neutral zone) -> Does NOT turn right
        p1_right_step = make_test_pose(shoulder_x=0.45)
        st_no_r = engine.calculate(p1_right_step, p2_neutral, timestamp=2.5)
        self.assertIsNone(st_no_r.direction)

        # P2 leans right to 0.78 (> 0.70) -> Turns RIGHT
        p2_steer = make_test_pose(shoulder_x=0.78)
        st_duo_r = engine.calculate(p1_neutral, p2_steer, timestamp=3.0)
        self.assertEqual(st_duo_r.direction, "RIGHT")

        # P2 steps left to 0.55 (into neutral zone) -> Does NOT turn left
        p2_left_step = make_test_pose(shoulder_x=0.55)
        st_no_l = engine.calculate(p1_neutral, p2_left_step, timestamp=3.5)
        self.assertIsNone(st_no_l.direction)

    def test_right_steering_starts_at_base_intensity_not_stuck_at_100(self):
        """
        Regression test: Verify that right steering does not get stuck at 100%
        from stale start timestamps across player switches or repeated leans.
        """
        cfg = SteeringConfig(
            left_threshold=0.40,
            right_threshold=0.60,
            time_based_position=True,
            time_steer_base_intensity=0.28,
            time_steer_ramp_seconds=0.70,
            enable_pwm=False,
        )
        engine = SteeringEngine(cfg)

        p_center = make_test_pose(shoulder_x=0.50)
        p_right = make_test_pose(shoulder_x=0.65)

        # 1. First right turn at t=10.0
        st1 = engine.calculate(p_right, None, timestamp=10.0)
        self.assertEqual(st1.direction, "RIGHT")
        self.assertAlmostEqual(st1.intensity, 0.28, places=2)

        # 2. Return to center at t=10.8
        st_center = engine.calculate(p_center, None, timestamp=10.8)
        self.assertIsNone(st_center.direction)

        # 3. Second right turn at t=25.0 (15 seconds later)
        # BUG REGRESSION: In the old code, this was 1.0 (100%) because start_time was stale!
        # Now, it must restart fresh at 0.28!
        st2 = engine.calculate(p_right, None, timestamp=25.0)
        self.assertEqual(st2.direction, "RIGHT")
        self.assertAlmostEqual(st2.intensity, 0.28, places=2)

    def test_solid_vs_pwm_actuation(self):
        """
        Verify that enable_pwm=False gives solid direct keypress (active=True),
        while enable_pwm=True pulses via PWM.
        """
        # Solid direct steering
        cfg_solid = SteeringConfig(enable_pwm=False, left_threshold=0.40, right_threshold=0.60)
        engine_solid = SteeringEngine(cfg_solid)
        p_left = make_test_pose(shoulder_x=0.35)
        p_right = make_test_pose(shoulder_x=0.65)

        st_l_solid = engine_solid.calculate(p_left, None, timestamp=1.0)
        self.assertTrue(st_l_solid.active, "Solid steering must hold key active without pulsing!")

        st_r_solid = engine_solid.calculate(p_right, None, timestamp=2.0)
        self.assertTrue(st_r_solid.active, "Solid steering must hold key active without pulsing!")

        # PWM pulsed steering
        cfg_pwm = SteeringConfig(enable_pwm=True, left_threshold=0.40, right_threshold=0.60, pwm_period=0.10)
        engine_pwm = SteeringEngine(cfg_pwm)
        st_l_pwm = engine_pwm.calculate(p_left, None, timestamp=1.0)
        self.assertIsNotNone(st_l_pwm.direction)


if __name__ == "__main__":
    unittest.main()
