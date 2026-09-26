import time
from typing import Optional, Union

from config import CalibrationConfig, SteeringConfig
from pose_types import PlayerPose, PlayerFace, CalibrationState, CalibrationStatus


class CalibrationManager:
    """Manages fixed baseline calibration with optional manual one-key recentering ('c')."""

    def __init__(
        self,
        config: CalibrationConfig = CalibrationConfig(),
        steering_config: SteeringConfig = SteeringConfig(),
    ):
        self.config = config
        self.steering_config = steering_config

        deadzone = self.steering_config.deadzone
        p1_nx = self.config.default_p1_neutral_x
        p2_nx = self.config.default_p2_neutral_x

        self.last_calibrated_time: float = -999.0
        self.calib_hold_start: Optional[float] = None
        self.just_calibrated: bool = False
        self.cooldown_seconds: float = getattr(config, "cooldown_seconds", 2.0)
        self.hold_seconds: float = getattr(config, "gesture_hold_seconds", 0.80)

        left_th = getattr(self.steering_config, "left_threshold", p1_nx - deadzone)
        right_th = getattr(self.steering_config, "right_threshold", p2_nx + deadzone)

        self.state = CalibrationState(
            p1_neutral_x=p1_nx,
            p2_neutral_x=p2_nx,
            p1_standing_y=self.config.default_p1_standing_y,
            p2_standing_y=self.config.default_p2_standing_y,
            calib_pose_counter=0,
            calib_pose_progress=0.0,
            left_thresh=left_th,
            right_thresh=right_th,
            status=CalibrationStatus.CALIBRATED,
            cooldown_remaining=0.0,
            fixed_mode=True,
            p1_brake_y=self.config.default_p1_brake_y,
            p2_brake_y=self.config.default_p2_brake_y,
            p1_jump_y=self.config.default_p1_jump_y,
            p2_jump_y=self.config.default_p2_jump_y,
        )

    def is_salute(self, pose: PlayerPose) -> bool:
        """Detects 'Sasageyo' (heart salute): one hand/wrist over chest/heart."""
        ls, rs = pose.left_shoulder, pose.right_shoulder
        sw = abs(rs.x - ls.x)
        if sw < 1e-4:
            return False
        mid_y = (ls.y + rs.y) / 2.0
        chest_min_x = min(ls.x, rs.x) - 0.15 * sw
        chest_max_x = max(ls.x, rs.x) + 0.15 * sw
        chest_min_y = mid_y - 0.20 * sw
        chest_max_y = mid_y + 0.90 * sw
        lw_in = (chest_min_x <= pose.left_wrist.x <= chest_max_x) and (chest_min_y <= pose.left_wrist.y <= chest_max_y)
        rw_in = (chest_min_x <= pose.right_wrist.x <= chest_max_x) and (chest_min_y <= pose.right_wrist.y <= chest_max_y)
        return lw_in or rw_in

    def is_crossed_arms(self, pose: PlayerPose) -> bool:
        """Detects crossed arms across chest (wrists crossed relative to shoulder sides)."""
        sh_y = (pose.left_shoulder.y + pose.right_shoulder.y) / 2.0
        hip_y = (pose.left_hip.y + pose.right_hip.y) / 2.0
        w1 = (sh_y - 0.06) < pose.left_wrist.y < (hip_y + 0.06)
        w2 = (sh_y - 0.06) < pose.right_wrist.y < (hip_y + 0.06)
        if not (w1 and w2):
            return False
        min_x = min(pose.left_shoulder.x, pose.right_shoulder.x) - 0.06
        max_x = max(pose.left_shoulder.x, pose.right_shoulder.x) + 0.06
        if not ((min_x <= pose.left_wrist.x <= max_x) and (min_x <= pose.right_wrist.x <= max_x)):
            return False
        wrist_dx = pose.left_wrist.x - pose.right_wrist.x
        shoulder_dx = pose.left_shoulder.x - pose.right_shoulder.x
        return (wrist_dx * shoulder_dx) <= 0.001

    def is_calibration_pose(self, pose: Optional[Union[PlayerPose, PlayerFace]]) -> bool:
        """Evaluates whether the player is executing a distance calibration gesture."""
        if not getattr(self.config, "enable_gesture_calibration", True):
            return False
        if pose is None or not isinstance(pose, PlayerPose):
            return False
        return self.is_salute(pose) or self.is_crossed_arms(pose)

    def calibrate(
        self,
        p1: Optional[Union[PlayerPose, PlayerFace]],
        p2: Optional[Union[PlayerPose, PlayerFace]],
        timestamp: Optional[float] = None,
    ) -> bool:
        """
        Calibrates ONLY the vertical brake line based on current shoulder height.
        Steering neutral and threshold lines remain strictly fixed and untouched.
        """
        brake_offset = getattr(self.config, "crouch_brake_offset", 0.10)
        calibrated_any = False

        if p1 is not None and isinstance(p1, PlayerPose):
            self.state.p1_standing_y = p1.shoulder_y
            self.state.p1_brake_y = p1.shoulder_y + brake_offset
            calibrated_any = True

        if p2 is not None and isinstance(p2, PlayerPose):
            self.state.p2_standing_y = p2.shoulder_y
            self.state.p2_brake_y = p2.shoulder_y + brake_offset
            calibrated_any = True

        if not calibrated_any:
            return False

        self.state.status = CalibrationStatus.CALIBRATED
        current_time = timestamp if timestamp is not None else time.time()
        self.last_calibrated_time = current_time
        return True

    def reset_cooldown(self):
        self.last_calibrated_time = -999.0
        self.calib_hold_start = None
        self.state.cooldown_remaining = 0.0

    def update(
        self,
        p1: Optional[Union[PlayerPose, PlayerFace]],
        p2: Optional[Union[PlayerPose, PlayerFace]],
        timestamp: Optional[float] = None,
    ) -> CalibrationState:
        """Updates gesture-based distance calibration and manages cooldown."""
        current_time = timestamp if timestamp is not None else time.time()
        self.just_calibrated = False

        # 1. Cooldown period after calibration
        elapsed_cd = current_time - self.last_calibrated_time
        if elapsed_cd < self.cooldown_seconds:
            self.state.status = CalibrationStatus.COOLDOWN
            self.state.cooldown_remaining = max(0.0, self.cooldown_seconds - elapsed_cd)
            self.state.calib_pose_progress = 0.0
            self.calib_hold_start = None
            return self.state

        self.state.cooldown_remaining = 0.0

        # 2. Check for distance calibration gesture
        p1_calib = self.is_calibration_pose(p1)
        p2_calib = self.is_calibration_pose(p2)
        is_gesturing = p1_calib or p2_calib

        if is_gesturing:
            if self.calib_hold_start is None:
                self.calib_hold_start = current_time

            hold_dur = current_time - self.calib_hold_start
            progress = min(1.0, hold_dur / max(1e-4, self.hold_seconds))
            self.state.calib_pose_progress = progress
            self.state.status = CalibrationStatus.CALIBRATING

            # Trigger calibration when gesture held continuously for required duration
            if progress >= 1.0:
                success = self.calibrate(p1, p2, timestamp=current_time)
                if success:
                    self.just_calibrated = True
                self.calib_hold_start = None
                self.state.calib_pose_progress = 1.0
                self.state.status = CalibrationStatus.CALIBRATED
        else:
            self.calib_hold_start = None
            self.state.calib_pose_progress = 0.0
            self.state.status = CalibrationStatus.CALIBRATED

        return self.state
