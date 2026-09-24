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
        self.state = CalibrationState(
            p1_neutral_x=p1_nx,
            p2_neutral_x=p2_nx,
            p1_standing_y=self.config.default_p1_standing_y,
            p2_standing_y=self.config.default_p2_standing_y,
            calib_pose_counter=0,
            calib_pose_progress=0.0,
            left_thresh=p1_nx - deadzone,
            right_thresh=p2_nx + deadzone,
            status=CalibrationStatus.CALIBRATED,
            cooldown_remaining=0.0,
            fixed_mode=True,
            p1_brake_y=self.config.default_p1_brake_y,
            p2_brake_y=self.config.default_p2_brake_y,
            p1_jump_y=self.config.default_p1_jump_y,
            p2_jump_y=self.config.default_p2_jump_y,
        )

    def is_calibration_pose(self, pose: Optional[Union[PlayerPose, PlayerFace]]) -> bool:
        """Gesture calibration is disabled in favor of fixed lines / keyboard recentering ('c')."""
        return False

    def calibrate(
        self,
        p1: Optional[Union[PlayerPose, PlayerFace]],
        p2: Optional[Union[PlayerPose, PlayerFace]],
        timestamp: Optional[float] = None,
    ) -> bool:
        """Instantly snaps neutral centers to current seated player positions upon pressing 'c'."""
        deadzone = self.steering_config.deadzone

        if p1 is not None and p2 is not None:
            self.state.p1_neutral_x = p1.shoulder_x
            self.state.p2_neutral_x = p2.shoulder_x
            self.state.p1_standing_y = p1.shoulder_y
            self.state.p2_standing_y = p2.shoulder_y
            self.state.left_thresh = self.state.p1_neutral_x - deadzone
            self.state.right_thresh = self.state.p2_neutral_x + deadzone
        elif p1 is not None:
            self.state.p1_neutral_x = p1.shoulder_x
            self.state.p1_standing_y = p1.shoulder_y
            self.state.left_thresh = p1.shoulder_x - deadzone
        elif p2 is not None:
            self.state.p2_neutral_x = p2.shoulder_x
            self.state.p2_standing_y = p2.shoulder_y
            self.state.right_thresh = p2.shoulder_x + deadzone
        else:
            return False

        self.state.status = CalibrationStatus.CALIBRATED
        current_time = timestamp if timestamp is not None else time.time()
        self.last_calibrated_time = current_time
        return True

    def reset_cooldown(self):
        self.last_calibrated_time = -999.0
        self.state.cooldown_remaining = 0.0

    def update(
        self,
        p1: Optional[Union[PlayerPose, PlayerFace]],
        p2: Optional[Union[PlayerPose, PlayerFace]],
        timestamp: Optional[float] = None,
    ) -> CalibrationState:
        """Returns the fixed calibration state. Gestures never move the lines."""
        self.state.status = CalibrationStatus.CALIBRATED
        self.state.calib_pose_progress = 0.0
        return self.state
