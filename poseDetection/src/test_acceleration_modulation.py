import unittest
from pose_types import Point3D, PlayerPose
from config import AppConfig
from gestures import DuoGestureDetector


def make_player(cx: float = 0.28) -> PlayerPose:
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


class TestAccelerationModulation(unittest.TestCase):
    def test_accel_modulation_duty_cycle(self):
        cfg = AppConfig()
        cfg.gestures.max_accel_intensity = 0.80
        cfg.gestures.accel_pwm_period = 0.10
        cfg.gestures.modulate_accel = True

        detector = DuoGestureDetector(config=cfg)
        detector.cruise_control = True
        p = make_player()

        # At t=0.00s: cycle start -> pulse ON
        r0 = detector.detect(p1=p, timestamp=0.00)
        self.assertTrue(r0.raw_accelerate)
        self.assertTrue(r0.accelerate)
        self.assertEqual(r0.accel_intensity, 0.80)

        # At t=0.05s: 50% into 0.10s cycle (< 80%) -> pulse ON
        r1 = detector.detect(p1=p, timestamp=0.05)
        self.assertTrue(r1.raw_accelerate)
        self.assertTrue(r1.accelerate)

        # At t=0.09s: 90% into 0.10s cycle (>= 80%) -> pulse OFF
        r2 = detector.detect(p1=p, timestamp=0.09)
        self.assertTrue(r2.raw_accelerate)
        self.assertFalse(r2.accelerate, "Throttle should be pulsed off during the 20% release window")

        # At t=0.11s: into next cycle (10% of next 0.10s cycle) -> pulse ON
        r3 = detector.detect(p1=p, timestamp=0.11)
        self.assertTrue(r3.raw_accelerate)
        self.assertTrue(r3.accelerate)

    def test_full_throttle_when_intensity_1_0(self):
        cfg = AppConfig()
        cfg.gestures.max_accel_intensity = 1.0
        cfg.gestures.accel_pwm_period = 0.10

        detector = DuoGestureDetector(config=cfg)
        detector.cruise_control = True
        p = make_player()

        for t in (0.00, 0.05, 0.09, 0.11):
            r = detector.detect(p1=p, timestamp=t)
            self.assertTrue(r.accelerate)

    def test_disabled_modulation(self):
        cfg = AppConfig()
        cfg.gestures.modulate_accel = False
        cfg.gestures.max_accel_intensity = 0.70

        detector = DuoGestureDetector(config=cfg)
        detector.cruise_control = True
        p = make_player()

        r = detector.detect(p1=p, timestamp=0.09)
        self.assertTrue(r.accelerate, "When modulation is disabled, acceleration should stay continuously on")


if __name__ == "__main__":
    unittest.main()
