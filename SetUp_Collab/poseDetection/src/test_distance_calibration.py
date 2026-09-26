import unittest
from types import SimpleNamespace
from pose_types import Point3D, PlayerPose, CalibrationStatus
from config import CalibrationConfig, SteeringConfig
from calibration import CalibrationManager


def make_test_pose(shoulder_x=0.35, shoulder_y=0.42, wrist_in_chest=False, crossed_arms=False):
    def lm(x, y, z=0.0):
        return Point3D(x=x, y=y, z=z, visibility=0.99)

    l_sh = lm(shoulder_x + 0.10, shoulder_y)
    r_sh = lm(shoulder_x - 0.10, shoulder_y)
    l_hip = lm(shoulder_x + 0.08, shoulder_y + 0.30)
    r_hip = lm(shoulder_x - 0.08, shoulder_y + 0.30)

    if wrist_in_chest:
        # One wrist on chest/heart between shoulders
        l_wrist = lm(shoulder_x, shoulder_y + 0.08)
        r_wrist = lm(shoulder_x - 0.20, shoulder_y + 0.40)
    elif crossed_arms:
        # Left wrist crosses over right side, right wrist crosses over left side
        l_wrist = lm(shoulder_x - 0.03, shoulder_y + 0.15)
        r_wrist = lm(shoulder_x + 0.03, shoulder_y + 0.15)
    else:
        # Arms resting at hips (uncrossed)
        l_wrist = lm(shoulder_x + 0.15, shoulder_y + 0.30)
        r_wrist = lm(shoulder_x - 0.15, shoulder_y + 0.30)

    pts = [lm(shoulder_x, shoulder_y - 0.10)] * 33
    pts[11] = l_sh
    pts[12] = r_sh
    pts[15] = l_wrist
    pts[16] = r_wrist
    pts[23] = l_hip
    pts[24] = r_hip

    return PlayerPose(
        left_shoulder=l_sh,
        right_shoulder=r_sh,
        left_wrist=l_wrist,
        right_wrist=r_wrist,
        left_hip=l_hip,
        right_hip=r_hip,
        nose=pts[0],
        hip_x=shoulder_x,
        hip_y=shoulder_y + 0.30,
        shoulder_x=shoulder_x,
        shoulder_y=shoulder_y,
        torso_size=0.30,
        landmarks=tuple(pts),
    )


class TestDistanceCalibration(unittest.TestCase):
    def test_calibration_modifies_only_brake_line(self):
        calib_cfg = CalibrationConfig(
            default_p1_neutral_x=0.28,
            default_p2_neutral_x=0.72,
            default_p1_brake_y=0.50,
            crouch_brake_offset=0.10,
        )
        steer_cfg = SteeringConfig(deadzone=0.05)
        mgr = CalibrationManager(config=calib_cfg, steering_config=steer_cfg)

        initial_p1_nx = mgr.state.p1_neutral_x
        initial_p2_nx = mgr.state.p2_neutral_x
        initial_left_th = mgr.state.left_thresh
        initial_right_th = mgr.state.right_thresh

        # Seated player with shoulder at Y=0.38 (and shifted laterally at X=0.45)
        p1 = make_test_pose(shoulder_x=0.45, shoulder_y=0.38)
        success = mgr.calibrate(p1, None, timestamp=10.0)
        self.assertTrue(success)

        # Steering lines must be completely UNCHANGED!
        self.assertEqual(mgr.state.p1_neutral_x, initial_p1_nx)
        self.assertEqual(mgr.state.p2_neutral_x, initial_p2_nx)
        self.assertEqual(mgr.state.left_thresh, initial_left_th)
        self.assertEqual(mgr.state.right_thresh, initial_right_th)

        # ONLY the brake line must be updated!
        self.assertAlmostEqual(mgr.state.p1_standing_y, 0.38, places=3)
        self.assertAlmostEqual(mgr.state.p1_brake_y, 0.38 + 0.10, places=3)

    def test_distance_gesture_salute_detection(self):
        mgr = CalibrationManager()
        pose_salute = make_test_pose(wrist_in_chest=True)
        pose_rest = make_test_pose(wrist_in_chest=False)

        self.assertTrue(mgr.is_salute(pose_salute))
        self.assertTrue(mgr.is_calibration_pose(pose_salute))
        self.assertFalse(mgr.is_salute(pose_rest))
        self.assertFalse(mgr.is_calibration_pose(pose_rest))

    def test_distance_gesture_crossed_arms_detection(self):
        mgr = CalibrationManager()
        pose_crossed = make_test_pose(crossed_arms=True)
        self.assertTrue(mgr.is_crossed_arms(pose_crossed))
        self.assertTrue(mgr.is_calibration_pose(pose_crossed))

    def test_gesture_hold_triggers_distance_calibration(self):
        cfg = CalibrationConfig(gesture_hold_seconds=0.80, cooldown_seconds=2.0, crouch_brake_offset=0.12)
        mgr = CalibrationManager(config=cfg)

        pose = make_test_pose(shoulder_x=0.30, shoulder_y=0.35, wrist_in_chest=True)

        # t = 0.0s: Gesture begins
        st0 = mgr.update(pose, None, timestamp=0.0)
        self.assertEqual(st0.status, CalibrationStatus.CALIBRATING)
        self.assertFalse(mgr.just_calibrated)
        self.assertAlmostEqual(st0.calib_pose_progress, 0.0, places=2)

        # t = 0.4s: Halfway through hold
        st1 = mgr.update(pose, None, timestamp=0.4)
        self.assertEqual(st1.status, CalibrationStatus.CALIBRATING)
        self.assertFalse(mgr.just_calibrated)
        self.assertAlmostEqual(st1.calib_pose_progress, 0.5, places=2)

        # t = 0.85s: Hold completed -> Trigger calibration!
        st2 = mgr.update(pose, None, timestamp=0.85)
        self.assertTrue(mgr.just_calibrated)
        self.assertAlmostEqual(st2.p1_brake_y, 0.35 + 0.12, places=3)

        # t = 1.0s: In cooldown period
        st3 = mgr.update(pose, None, timestamp=1.0)
        self.assertEqual(st3.status, CalibrationStatus.COOLDOWN)
        self.assertFalse(mgr.just_calibrated)


if __name__ == "__main__":
    unittest.main()
