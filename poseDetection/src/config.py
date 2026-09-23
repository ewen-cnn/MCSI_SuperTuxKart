from dataclasses import dataclass, field
from typing import Tuple, Optional


@dataclass
class CameraConfig:
    device_id: int = 0
    width: int = 640
    height: int = 360
    fps: int = 30


@dataclass
class SteeringConfig:
    deadzone: float = 0.06
    margin: float = 0.10
    pwm_period: float = 0.15
    net_deadband: float = 0.01
    full_steer_intensity: float = 0.98


@dataclass
class GestureConfig:
    crouch_threshold: float = 0.045
    jump_threshold: float = 0.045
    default_standing_y: float = 0.34
    default_torso_height: float = 0.28
    default_brake_y: float = 0.39
    default_jump_y: float = 0.29
    rescue_mode: str = "color"


@dataclass
class ColorConfig:
    enabled: bool = True
    preset: str = "green"
    lower_hsv: Tuple[int, int, int] = (40, 80, 60)
    upper_hsv: Tuple[int, int, int] = (82, 255, 255)
    min_area: int = 180
    max_area: Optional[int] = 30000
    min_solidity: float = 0.70
    min_extent: float = 0.40
    max_aspect_ratio: float = 3.5
    cooldown_seconds: float = 1.5
    pulse_duration: float = 0.2


@dataclass

class CalibrationConfig:
    frames_required: int = 30
    cooldown_seconds: float = 3.0
    default_p1_neutral_x: float = 0.35
    default_p2_neutral_x: float = 0.65
    wrist_margin_y: float = 0.08
    hip_margin_y: float = 0.04
    shoulder_margin_x: float = 0.06
    cross_offset: float = 0.06
    prayer_max_distance: float = 0.10


@dataclass
class FilterConfig:
    min_cutoff: float = 1.2
    beta: float = 0.05
    d_cutoff: float = 1.0
    timeout_seconds: float = 0.6


@dataclass
class TrackerConfig:
    num_poses: int = 4
    min_player_size: float = 0.12
    min_detection_confidence: float = 0.5
    min_tracking_confidence: float = 0.5


@dataclass
class NetworkConfig:
    host: str = "localhost"
    port: int = 6006


@dataclass
class AppConfig:
    camera: CameraConfig = field(default_factory=CameraConfig)
    steering: SteeringConfig = field(default_factory=SteeringConfig)
    gestures: GestureConfig = field(default_factory=GestureConfig)
    calibration: CalibrationConfig = field(default_factory=CalibrationConfig)
    filter: FilterConfig = field(default_factory=FilterConfig)
    tracker: TrackerConfig = field(default_factory=TrackerConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    color: ColorConfig = field(default_factory=ColorConfig)


DEFAULT_CONFIG = AppConfig()

