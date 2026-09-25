import time
from typing import Optional, Tuple, Union
import numpy as np

from config import AppConfig, SteeringConfig, GestureConfig, CalibrationConfig
from pose_types import PlayerPose, PlayerFace, SteeringState, GestureResult, CalibrationStatus
from calibration import CalibrationManager
from capture import Camera
from tracker import PoseTracker
from hud import HUD


class PWMModulator:
    """Translates continuous steering intensity into periodic binary pulses."""

    def __init__(self, period: float = 0.15, full_steer_threshold: float = 0.98):
        self.period = period
        self.full_steer_threshold = full_steer_threshold
        self.pulse_start_time: Optional[float] = None
        self.last_direction: Optional[str] = None

    def update(
        self, direction: Optional[str], intensity: float, timestamp: Optional[float] = None
    ) -> bool:
        if not direction or intensity <= 0.0:
            self.pulse_start_time = None
            self.last_direction = None
            return False

        if timestamp is None:
            timestamp = time.time()

        if self.last_direction != direction or self.pulse_start_time is None:
            self.pulse_start_time = timestamp
            self.last_direction = direction

        if intensity >= self.full_steer_threshold:
            return True

        elapsed = (timestamp - self.pulse_start_time) % self.period
        cycle_pos = elapsed / self.period
        return cycle_pos < intensity

    def reset(self):
        self.pulse_start_time = None
        self.last_direction = None


class SteeringEngine:
    """Calculates normalized steering power for duo and solo modes using time-based threshold ramps."""

    def __init__(self, config: SteeringConfig = SteeringConfig()):
        self.config = config
        self.modulator = PWMModulator(
            period=self.config.pwm_period,
            full_steer_threshold=self.config.full_steer_intensity,
        )
        # Hold timestamps for time-based threshold steering
        self.p1_left_start: Optional[float] = None
        self.p1_right_start: Optional[float] = None
        self.p2_left_start: Optional[float] = None
        self.p2_right_start: Optional[float] = None

    def reset(self):
        self.p1_left_start = None
        self.p1_right_start = None
        self.p2_left_start = None
        self.p2_right_start = None
        self.modulator.reset()

    def _calc_time_power(
        self, is_active: bool, start_time: Optional[float], now: float
    ) -> Tuple[float, Optional[float]]:
        if not is_active:
            return 0.0, None

        if start_time is None:
            start_time = now

        duration = max(0.0, now - start_time)
        ramp_time = getattr(self.config, "time_steer_ramp_seconds", 0.70)
        base_int = getattr(self.config, "time_steer_base_intensity", 0.25)

        progress = min(1.0, duration / max(1e-4, ramp_time))
        power = base_int + (1.0 - base_int) * progress
        return float(min(1.0, power)), start_time

    @staticmethod
    def _calc_distance_power(val: float, limit: float, margin: float, direction: str) -> float:
        if direction == "LEFT":
            travel = max(1e-4, limit - margin)
            return min(1.0, max(0.0, (limit - val) / travel))
        else:
            travel = max(1e-4, (1.0 - margin) - limit)
            return min(1.0, max(0.0, (val - limit) / travel))

    def _calc_inclination_powers(
        self, p1: Optional[PlayerPose], p2: Optional[PlayerPose]
    ) -> Tuple[float, float]:
        """
        Computes Left and Right steering powers from torso spine lean angle.
        Uses shoulder-to-hip vector.
        """
        deadzone = getattr(self.config, "lean_deadzone_deg", 3.5)
        max_deg = getattr(self.config, "lean_max_deg", 16.0)
        use_spine = getattr(self.config, "inclination_mode", "spine") == "spine"

        def get_angle(p: PlayerPose) -> float:
            return p.spine_lean_angle_deg if use_spine else p.shoulder_tilt_angle_deg

        def angle_to_power(ang: float) -> float:
            if ang <= deadzone:
                return 0.0
            span = max(1e-4, max_deg - deadzone)
            return float(min(1.0, (ang - deadzone) / span))

        p1_left = 0.0
        p2_right = 0.0

        if p1 is not None and p2 is not None:
            # Duo mode: P1 controls left (negative angle = lean left), P2 controls right (positive angle = lean right)
            ang1 = get_angle(p1)
            ang2 = get_angle(p2)
            if ang1 < -deadzone:
                p1_left = angle_to_power(abs(ang1))
            if ang2 > deadzone:
                p2_right = angle_to_power(ang2)

        elif p1 is not None:
            # Solo mode (P1)
            ang = get_angle(p1)
            if ang < -deadzone:
                p1_left = angle_to_power(abs(ang))
            elif ang > deadzone:
                p2_right = angle_to_power(ang)

        elif p2 is not None:
            # Solo mode (P2)
            ang = get_angle(p2)
            if ang < -deadzone:
                p1_left = angle_to_power(abs(ang))
            elif ang > deadzone:
                p2_right = angle_to_power(ang)

        return p1_left, p2_right

    def calculate(
        self,
        p1: Optional[PlayerPose],
        p2: Optional[PlayerPose],
        left_thresh: float,
        right_thresh: float,
        p1_neutral_x: float,
        p2_neutral_x: float,
        timestamp: Optional[float] = None,
    ) -> SteeringState:
        if timestamp is None:
            timestamp = time.time()

        p1_left_power = 0.0
        p2_right_power = 0.0
        margin = self.config.margin
        use_time_steering = getattr(self.config, "time_based_position", True)
        strategy = getattr(self.config, "strategy", "position").lower()

        if strategy in ("inclination", "lean", "spine"):
            p1_left_power, p2_right_power = self._calc_inclination_powers(p1, p2)
        elif p1 is not None and p2 is not None:
            # Duo mode: P1 controls left, P2 controls right
            if use_time_steering:
                p1_left_power, self.p1_left_start = self._calc_time_power(
                    p1.shoulder_x < left_thresh, self.p1_left_start, timestamp
                )
                p2_right_power, self.p2_right_start = self._calc_time_power(
                    p2.shoulder_x > right_thresh, self.p2_right_start, timestamp
                )
            else:
                if p1.shoulder_x < left_thresh:
                    p1_left_power = self._calc_distance_power(p1.shoulder_x, left_thresh, margin, "LEFT")
                if p2.shoulder_x > right_thresh:
                    p2_right_power = self._calc_distance_power(p2.shoulder_x, right_thresh, margin, "RIGHT")

        elif p1 is not None:
            # Solo mode (P1)
            if use_time_steering:
                p1_left_power, self.p1_left_start = self._calc_time_power(
                    p1.shoulder_x < left_thresh, self.p1_left_start, timestamp
                )
                p2_right_power, self.p1_right_start = self._calc_time_power(
                    p1.shoulder_x > right_thresh, self.p1_right_start, timestamp
                )
            else:
                if p1.shoulder_x < left_thresh:
                    p1_left_power = self._calc_distance_power(p1.shoulder_x, left_thresh, margin, "LEFT")
                elif p1.shoulder_x > right_thresh:
                    p2_right_power = self._calc_distance_power(p1.shoulder_x, right_thresh, margin, "RIGHT")

        elif p2 is not None:
            # Solo mode (P2)
            if use_time_steering:
                p1_left_power, self.p2_left_start = self._calc_time_power(
                    p2.shoulder_x < left_thresh, self.p2_left_start, timestamp
                )
                p2_right_power, self.p2_right_start = self._calc_time_power(
                    p2.shoulder_x > right_thresh, self.p2_right_start, timestamp
                )
            else:
                if p2.shoulder_x < left_thresh:
                    p1_left_power = self._calc_distance_power(p2.shoulder_x, left_thresh, margin, "LEFT")
                elif p2.shoulder_x > right_thresh:
                    p2_right_power = self._calc_distance_power(p2.shoulder_x, right_thresh, margin, "RIGHT")

        else:
            self.reset()

        net = p1_left_power - p2_right_power
        direction = None
        intensity = 0.0

        if net > self.config.net_deadband:
            direction = "LEFT"
            intensity = net
        elif net < -self.config.net_deadband:
            direction = "RIGHT"
            intensity = abs(net)

        active = self.modulator.update(direction, intensity, timestamp=timestamp)

        return SteeringState(
            direction=direction,
            intensity=intensity,
            active=active,
            p1_power=p1_left_power,
            p2_power=p2_right_power,
        )


class VerticalActionDetector:
    """Evaluates jumping and crouching relative to calibrated baselines."""

    def __init__(self, config: GestureConfig = GestureConfig()):
        self.config = config

    def evaluate_player(
        self,
        pose: Optional[Union[PlayerPose, PlayerFace]],
        standing_y: Optional[float],
        is_calibrating: bool = False,
    ) -> Tuple[bool, bool, float, float]:
        """Calculates (brake_active, jump_active, brake_y, jump_y) for a player."""
        base_y = standing_y if standing_y is not None else self.config.default_standing_y
        brake_y = getattr(self.config, "default_brake_y", base_y + self.config.crouch_threshold)
        jump_y = getattr(self.config, "default_jump_y", base_y - self.config.jump_threshold)

        brake = False
        jump = False
        if pose is not None and not is_calibrating:
            pos_y = pose.head_y if hasattr(pose, "head_y") else pose.shoulder_y
            if pos_y > brake_y:
                brake = True
            elif pos_y < jump_y:
                jump = True

        return brake, jump, brake_y, jump_y


class DuoGestureDetector:
    """Coordinates dual-player gestures, steering, calibration, and cruise control."""

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        steering_config: Optional[SteeringConfig] = None,
        gesture_config: Optional[GestureConfig] = None,
        calibration_config: Optional[CalibrationConfig] = None,
    ):
        base_cfg = config or AppConfig()
        st_cfg = steering_config or base_cfg.steering
        ge_cfg = gesture_config or base_cfg.gestures
        cal_cfg = calibration_config or base_cfg.calibration

        self.config = base_cfg
        self.steering_engine = SteeringEngine(config=st_cfg)
        self.vertical_detector = VerticalActionDetector(config=ge_cfg)
        self.calibrator = CalibrationManager(
            config=cal_cfg,
            steering_config=st_cfg,
        )
        self.rescue_mode: str = ge_cfg.rescue_mode

        self.cruise_control: bool = False
        self.prev_hands_up: bool = False
        self.turn_start_time: Optional[float] = None


    @property
    def steer_margin(self) -> float:
        return self.steering_engine.config.margin

    @property
    def is_calibrated(self) -> bool:
        return self.calibrator.state.is_calibrated

    @property
    def p1_neutral_x(self) -> float:
        return self.calibrator.state.p1_neutral_x

    @property
    def p2_neutral_x(self) -> float:
        return self.calibrator.state.p2_neutral_x

    @staticmethod
    def is_hands_up(pose: Optional[PlayerPose]) -> bool:
        """Checks if player has either hand raised above their shoulder."""
        if pose is None:
            return False
        return (pose.left_wrist.y < pose.left_shoulder.y) or (
            pose.right_wrist.y < pose.right_shoulder.y
        )

    def calibrate(
        self,
        p1: Optional[PlayerPose] = None,
        p2: Optional[PlayerPose] = None,
        timestamp: Optional[float] = None,
    ) -> bool:
        return self.calibrator.calibrate(p1, p2, timestamp=timestamp)

    def calculate_steering(
        self,
        p1: Optional[PlayerPose],
        p2: Optional[PlayerPose],
        left_thresh: float,
        right_thresh: float,
        timestamp: Optional[float] = None,
    ) -> SteeringState:
        return self.steering_engine.calculate(
            p1=p1,
            p2=p2,
            left_thresh=left_thresh,
            right_thresh=right_thresh,
            p1_neutral_x=self.p1_neutral_x,
            p2_neutral_x=self.p2_neutral_x,
            timestamp=timestamp,
        )

    def detect(
        self,
        p1: Optional[PlayerPose] = None,
        p2: Optional[PlayerPose] = None,
        frame: Optional[np.ndarray] = None,
        timestamp: Optional[float] = None,
    ) -> GestureResult:
        if timestamp is None:
            timestamp = time.time()

        calib = self.calibrator.update(p1, p2, timestamp=timestamp)

        steering = self.calculate_steering(
            p1,
            p2,
            left_thresh=calib.left_thresh,
            right_thresh=calib.right_thresh,
            timestamp=timestamp,
        )

        hands_up = self.is_hands_up(p1) or self.is_hands_up(p2)
        if hands_up and not self.prev_hands_up:
            self.cruise_control = not self.cruise_control
        self.prev_hands_up = hands_up

        p1_is_calib = (
            calib.status == CalibrationStatus.CALIBRATING
            or self.calibrator.is_calibration_pose(p1)
        )
        p2_is_calib = (
            calib.status == CalibrationStatus.CALIBRATING
            or self.calibrator.is_calibration_pose(p2)
        )

        p1_brake, p1_jump, p1_brake_y, p1_jump_y = self.vertical_detector.evaluate_player(
            p1, calib.p1_standing_y, is_calibrating=p1_is_calib
        )
        p2_brake, p2_jump, p2_brake_y, p2_jump_y = self.vertical_detector.evaluate_player(
            p2, calib.p2_standing_y, is_calibrating=p2_is_calib
        )

        brake = p1_brake or p2_brake
        rescue = p1_jump or p2_jump

        accelerate = self.cruise_control and not brake

        corner_lift = False
        if accelerate and getattr(self.config.gestures, "cornering_lift_enabled", True):
            threshold = getattr(self.config.gestures, "cornering_lift_steer_threshold", 0.45)
            max_dur = getattr(self.config.gestures, "corner_lift_max_duration_s", 0.65)
            if steering.intensity >= threshold:
                if self.turn_start_time is None:
                    self.turn_start_time = timestamp
                # Temporarily lift off throttle during initial turn entry (< 0.65s) to carve corner
                if (timestamp - self.turn_start_time) < max_dur:
                    corner_lift = True
                    accelerate = False
            else:
                self.turn_start_time = None
        else:
            self.turn_start_time = None

        return GestureResult(
            steering=steering,
            accelerate=accelerate,
            corner_lift=corner_lift,
            cruise_control=self.cruise_control,
            brake=brake,
            rescue=rescue,
            p1_brake=p1_brake,
            p2_brake=p2_brake,
            p1_brake_y=p1_brake_y,
            p2_brake_y=p2_brake_y,
            p1_jump=p1_jump,
            p2_jump=p2_jump,
            p1_jump_y=p1_jump_y,
            p2_jump_y=p2_jump_y,
            p1_shoulder=p1.shoulder if p1 else None,
            p2_shoulder=p2.shoulder if p2 else None,
            p1_hip=p1.hip if p1 else None,
            p2_hip=p2.hip if p2 else None,
            calibration=calib,
            card_detected=False,
            card_bbox=None,
            card_enabled=False,
            rescue_mode=self.rescue_mode,
            p1_face=p1 if isinstance(p1, PlayerFace) else None,
            p2_face=p2 if isinstance(p2, PlayerFace) else None,
        )



def main():
    import cv2

    with Camera() as cam:
        if not cam.is_opened():
            return

        tracker = PoseTracker()
        detector = DuoGestureDetector()
        hud = HUD()

        prev = time.time()
        fps = 0.0

        while True:
            ret, frame = cam.read()
            if not ret:
                break

            now = time.time()
            dt = now - prev
            prev = now
            if dt > 0:
                fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps > 0 else 1.0 / dt

            p1, p2 = tracker.process(frame, timestamp=now)
            gestures = detector.detect(p1, p2, frame=frame, timestamp=now)

            hud.render(frame, p1, p2, gestures, fps, detector.steer_margin)

            cv2.imshow("Gestures Test", frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            elif key in (ord("c"), ord("C")):
                detector.calibrate(p1, p2, timestamp=now)
            elif key in (ord("a"), ord("A")):
                detector.cruise_control = not detector.cruise_control
            elif key in (ord("r"), ord("R")):
                detector.toggle_rescue_mode()

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
