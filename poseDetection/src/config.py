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
    deadzone: float = 0.05
    margin: float = 0.08
    p1_center_x: float = 0.28
    p2_center_x: float = 0.72
    fixed_lines: bool = True
    pwm_period: float = 0.15
    net_deadband: float = 0.01
    full_steer_intensity: float = 0.98

    # Steering strategy: 'position' (time-based threshold) or 'inclination' (torso tilt)
    strategy: str = "position"

    # Time-based position steering (starts turning on threshold, ramps over time)
    time_based_position: bool = True
    time_steer_base_intensity: float = 0.25   # Initial PWM power on crossing threshold
    time_steer_ramp_seconds: float = 0.70     # Duration of continuous hold to reach 100% full lock

    # Inclination steering settings (spine torso tilt from hip midpoint to shoulder midpoint)
    inclination_mode: str = "spine"           # 'spine' (hip to shoulder vector) or 'shoulders' (shoulder line tilt)
    lean_deadzone_deg: float = 3.5            # Deadzone degrees to ignore natural micro-wobbles
    lean_max_deg: float = 16.0                # Degrees for 100% full steering lock


@dataclass
class GestureConfig:
    crouch_threshold: float = 0.08
    jump_threshold: float = 0.08
    default_standing_y: float = 0.40
    default_torso_height: float = 0.28
    default_brake_y: float = 0.50
    default_jump_y: float = 0.30
    rescue_mode: str = "disabled"

    # Max Acceleration Modulation
    # Disabled by default on keyboard: pulsing keyboard UP key causes engine jerk/stutter in SuperTuxKart
    max_accel_intensity: float = 0.80           # 0.80 = 80% throttle duty cycle
    accel_pwm_period: float = 0.15              # PWM period in seconds for throttle pulsing
    modulate_accel: bool = False                # False = solid continuous keyboard UP (prevents stutter/dropouts)

    # Cornering Throttle Reduction (relative acceleration: drops throttle while turning)
    cornering_lift_enabled: bool = True
    cornering_lift_steer_threshold: float = 0.45
    corner_lift_max_duration_s: float = 0.65


@dataclass
class ColorConfig:
    enabled: bool = True  # Set to False to disable card detection and all card overlays
    show_reticle: bool = False  # Set to False to hide the center 'HOLD CARD' reticle box
    preset: str = "orange"
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
    fixed_mode: bool = True
    default_p1_neutral_x: float = 0.28
    default_p2_neutral_x: float = 0.72
    default_p1_standing_y: float = 0.40
    default_p2_standing_y: float = 0.40
    default_p1_brake_y: float = 0.50
    default_p2_brake_y: float = 0.50
    default_p1_jump_y: float = 0.30
    default_p2_jump_y: float = 0.30
    crouch_brake_offset: float = 0.10          # Distance shoulders drop below resting height to trigger brake
    enable_gesture_calibration: bool = True     # Hands-free distance calibration gesture (salute or crossed arms)
    gesture_hold_seconds: float = 0.80          # Continuous hold duration required to calibrate
    cooldown_seconds: float = 2.0               # Refractory period after calibration


@dataclass
class FilterConfig:
    min_cutoff: float = 1.2
    beta: float = 0.05
    d_cutoff: float = 1.0
    timeout_seconds: float = 0.6


@dataclass
class TrackerConfig:
    num_poses: int = 4
    min_shoulder_span: float = 0.14
    max_depth_z: float = 0.40
    min_detection_confidence: float = 0.5
    min_tracking_confidence: float = 0.5
    min_player_size: float = 0.10

    # Multi-layer Depth Bystander Rejection
    max_relative_depth_diff: float = 0.15     # Relative Z-depth gap behind primary player
    min_shoulder_scale_ratio: float = 0.55    # Bystander rejection ratio based on shoulder width
    distance_jump_rejection: float = 0.22     # Distance jump hysteresis threshold


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

