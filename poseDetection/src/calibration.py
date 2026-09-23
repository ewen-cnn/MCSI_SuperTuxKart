import time
from typing import Optional

from config import CalibrationConfig, SteeringConfig
from pose_types import PlayerPose, CalibrationState, CalibrationStatus


class CalibrationManager:
    """Manages player resting baseline calibration, compact poses, and resting cooldown."""

    def __init__(
        self,
        config: CalibrationConfig = CalibrationConfig(),
        steering_config: SteeringConfig = SteeringConfig(),
    ):
        self.config = config
        self.steering_config = steering_config

        self.last_calibrated_time: float = -999.0
        self.state = CalibrationState(
            p1_neutral_x=self.config.default_p1_neutral_x,
            p2_neutral_x=self.config.default_p2_neutral_x,
            p1_standing_y=None,
            p2_standing_y=None,
            calib_pose_counter=0,
            calib_pose_progress=0.0,
            left_thresh=self.config.default_p1_neutral_x - self.steering_config.deadzone,
            right_thresh=self.config.default_p2_neutral_x + self.steering_config.deadzone,
            status=CalibrationStatus.UNCALIBRATED,
            cooldown_remaining=0.0,
        )

    def is_crossed_arms(self, pose: Optional[PlayerPose]) -> bool:
        """Detects crossed-arms gesture in front of chest (wrist crossing)."""
        if pose is None:
            return False

        sh_y = (pose.left_shoulder.y + pose.right_shoulder.y) / 2.0
        hip_y = (pose.left_hip.y + pose.right_hip.y) / 2.0

        # Wrists must be vertically between shoulders and hips
        w1_chest = (sh_y - self.config.wrist_margin_y) < pose.left_wrist.y < (hip_y + self.config.hip_margin_y)
        w2_chest = (sh_y - self.config.wrist_margin_y) < pose.right_wrist.y < (hip_y + self.config.hip_margin_y)
        if not (w1_chest and w2_chest):
            return False

        # Wrists within horizontal torso span
        min_sh_x = min(pose.left_shoulder.x, pose.right_shoulder.x) - self.config.shoulder_margin_x
        max_sh_x = max(pose.left_shoulder.x, pose.right_shoulder.x) + self.config.shoulder_margin_x
        within_torso = (min_sh_x <= pose.left_wrist.x <= max_sh_x) and (
            min_sh_x <= pose.right_wrist.x <= max_sh_x
        )
        if not within_torso:
            return False

        # In mirrored frame: left wrist starts at higher X than right wrist.
        # When crossed, left wrist moves across to lower X (<= right wrist X + offset)
        return pose.left_wrist.x <= (pose.right_wrist.x + self.config.cross_offset)

    def is_prayer_pose(self, pose: Optional[PlayerPose]) -> bool:
        """Detects compact prayer pose (wrists together in front of chest)."""
        if pose is None:
            return False

        sh_y = (pose.left_shoulder.y + pose.right_shoulder.y) / 2.0
        hip_y = (pose.left_hip.y + pose.right_hip.y) / 2.0

        w1_chest = (sh_y - self.config.wrist_margin_y) < pose.left_wrist.y < (hip_y + self.config.hip_margin_y)
        w2_chest = (sh_y - self.config.wrist_margin_y) < pose.right_wrist.y < (hip_y + self.config.hip_margin_y)
        if not (w1_chest and w2_chest):
            return False

        dx = abs(pose.left_wrist.x - pose.right_wrist.x)
        dy = abs(pose.left_wrist.y - pose.right_wrist.y)
        return (dx < self.config.prayer_max_distance) and (dy < self.config.prayer_max_distance)

    def is_calibration_pose(self, pose: Optional[PlayerPose]) -> bool:
        """Evaluates whether the player is executing crossed arms or prayer pose."""
        return self.is_crossed_arms(pose) or self.is_prayer_pose(pose)

    def calibrate(
        self,
        p1: Optional[PlayerPose],
        p2: Optional[PlayerPose],
        timestamp: Optional[float] = None,
    ) -> bool:
        deadzone = self.steering_config.deadzone
        if p1 is not None and p2 is not None:
            self.state.p1_neutral_x = p1.hip_x
            self.state.p2_neutral_x = p2.hip_x
            self.state.p1_standing_y = p1.shoulder_y
            self.state.p2_standing_y = p2.shoulder_y
            self.state.left_thresh = self.state.p1_neutral_x - deadzone
            self.state.right_thresh = self.state.p2_neutral_x + deadzone
        elif p1 is not None:
            self.state.p1_neutral_x = p1.hip_x
            self.state.p1_standing_y = p1.shoulder_y
            self.state.left_thresh = p1.hip_x - deadzone
            self.state.right_thresh = p1.hip_x + deadzone
        elif p2 is not None:
            self.state.p2_neutral_x = p2.hip_x
            self.state.p2_standing_y = p2.shoulder_y
            self.state.left_thresh = p2.hip_x - deadzone
            self.state.right_thresh = p2.hip_x + deadzone
        else:
            return False

        self.state.status = CalibrationStatus.CALIBRATED

        current_time = timestamp if timestamp is not None else time.time()
        self.last_calibrated_time = current_time
        return True

    def reset_cooldown(self):
        """Allows immediate re-calibration by resetting resting timer."""
        self.last_calibrated_time = -999.0
        self.state.cooldown_remaining = 0.0

    def update(
        self,
        p1: Optional[PlayerPose],
        p2: Optional[PlayerPose],
        timestamp: Optional[float] = None,
    ) -> CalibrationState:
        """Updates calibration progress, handles resting cooldown, and triggers calibration."""
        current_time = timestamp if timestamp is not None else time.time()

        # Resting cooldown
        elapsed = current_time - self.last_calibrated_time
        if elapsed < self.config.cooldown_seconds:
            self.state.status = CalibrationStatus.COOLDOWN
            self.state.cooldown_remaining = self.config.cooldown_seconds - elapsed
            self.state.calib_pose_counter = 0
            self.state.calib_pose_progress = 0.0
            return self.state

        self.state.cooldown_remaining = 0.0

        p1_calib = self.is_calibration_pose(p1)
        p2_calib = self.is_calibration_pose(p2)

        if p1 is not None and p2 is not None:
            calib_active = p1_calib and p2_calib
        else:
            calib_active = p1_calib or p2_calib

        if calib_active:
            self.state.calib_pose_counter += 1
            self.state.status = CalibrationStatus.CALIBRATING
            if self.state.calib_pose_counter >= self.config.frames_required:
                self.calibrate(p1, p2, timestamp=current_time)
                self.state.calib_pose_counter = 0
        else:
            self.state.calib_pose_counter = max(0, self.state.calib_pose_counter - 1)
            if self.state.calib_pose_counter == 0 and not self.state.is_calibrated:
                self.state.status = CalibrationStatus.UNCALIBRATED

        self.state.calib_pose_progress = min(
            1.0, self.state.calib_pose_counter / float(self.config.frames_required)
        )
        return self.state
