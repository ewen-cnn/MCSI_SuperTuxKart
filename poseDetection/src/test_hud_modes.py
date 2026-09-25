import unittest
import numpy as np
from pose_types import Point3D, PlayerPose, SteeringState, GestureResult
from hud import HUD


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


class TestHudModes(unittest.TestCase):
    def test_clean_mode_and_debug_toggle(self):
        hud = HUD()
        self.assertFalse(hud.debug_mode, "Default HUD should be clean arcade view!")

        is_dbg = hud.toggle_debug()
        self.assertTrue(is_dbg)
        self.assertTrue(hud.debug_mode)

        is_clean = hud.toggle_debug()
        self.assertFalse(is_clean)
        self.assertFalse(hud.debug_mode)

    def test_hud_rendering_clean_and_debug(self):
        hud = HUD()
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        p1 = make_player(0.28)
        p2 = make_player(0.72)

        steering = SteeringState(direction="LEFT", intensity=0.5, active=True, p1_power=0.5, p2_power=0.0)
        gestures = GestureResult(steering=steering, accelerate=True, cruise_control=True)

        # Render in clean mode
        hud.debug_mode = False
        hud.render(frame, p1, p2, gestures, fps=30.0, steer_margin=0.08)
        self.assertEqual(frame.shape, (360, 640, 3))
        # Verify non-zero pixels near P1 shoulder center (x ~ 179, y ~ 144)
        sh_px_y, sh_px_x = int(0.4 * 360), int(0.28 * 640)
        self.assertTrue(np.any(frame[sh_px_y - 3:sh_px_y + 3, sh_px_x - 3:sh_px_x + 3] > 0),
                        "Shoulder midpoint dot must be rendered in clean HUD!")

        # Render in debug mode
        frame_dbg = np.zeros((360, 640, 3), dtype=np.uint8)
        hud.debug_mode = True
        hud.render(frame_dbg, p1, p2, gestures, fps=30.0, steer_margin=0.08)
        self.assertEqual(frame_dbg.shape, (360, 640, 3))

    def test_clean_hud_calibrating_progress(self):
        from pose_types import CalibrationState, CalibrationStatus
        hud = HUD(debug_mode=False)
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        p1 = make_player(0.28)
        calib = CalibrationState(status=CalibrationStatus.CALIBRATING, calib_pose_progress=0.60)
        steering = SteeringState()
        gestures = GestureResult(steering=steering, calibration=calib)

        hud.render(frame, p1, None, gestures, fps=30.0, steer_margin=0.08)
        # Center bar should have non-zero pixels
        self.assertTrue(np.any(frame[160:176, 250:390] > 0), "Calibration progress bar must be rendered!")


if __name__ == "__main__":
    unittest.main()
