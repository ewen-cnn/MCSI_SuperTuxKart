import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple, Sequence, Any


@dataclass(frozen=True)
class Point3D:
    x: float
    y: float
    z: float = 0.0
    visibility: float = 1.0

    def is_valid(self) -> bool:
        """Returns False if any coordinate is NaN or infinite."""
        return not (
            math.isnan(self.x) or math.isnan(self.y) or math.isnan(self.z)
            or math.isinf(self.x) or math.isinf(self.y) or math.isinf(self.z)
        )

    def distance_to(self, other: "Point3D") -> float:
        if not self.is_valid() or not other.is_valid():
            return 999.0
        return math.hypot(self.x - other.x, self.y - other.y)

    @classmethod
    def midpoint(cls, p1: "Point3D", p2: "Point3D") -> "Point3D":
        if not p1.is_valid():
            return p2
        if not p2.is_valid():
            return p1
        return cls(
            x=(p1.x + p2.x) / 2.0,
            y=(p1.y + p2.y) / 2.0,
            z=(p1.z + p2.z) / 2.0,
            visibility=min(p1.visibility, p2.visibility),
        )


NOSE_IDX = 0
LEFT_SHOULDER_IDX = 11
RIGHT_SHOULDER_IDX = 12
LEFT_WRIST_IDX = 15
RIGHT_WRIST_IDX = 16
LEFT_HIP_IDX = 23
RIGHT_HIP_IDX = 24


@dataclass
class PlayerFace:
    nose: Point3D
    left_eye: Point3D
    right_eye: Point3D
    mouth: Point3D
    right_ear: Point3D
    left_ear: Point3D
    center_x: float
    center_y: float
    bbox: Tuple[int, int, int, int]
    roll_angle: float = 0.0
    size: float = 0.1
    confidence: float = 1.0
    landmarks: Tuple[Point3D, ...] = ()

    @property
    def head_x(self) -> float:
        return self.center_x

    @property
    def head_y(self) -> float:
        return self.center_y

    @property
    def head(self) -> Tuple[float, float]:
        return self.center_x, self.center_y

    # Backward compatibility properties for pose consumers
    @property
    def hip_x(self) -> float:
        return self.center_x

    @property
    def hip_y(self) -> float:
        return self.center_y

    @property
    def shoulder_x(self) -> float:
        return self.center_x

    @property
    def shoulder_y(self) -> float:
        return self.center_y

    @property
    def shoulder(self) -> Tuple[float, float]:
        return self.center_x, self.center_y

    @property
    def hip(self) -> Tuple[float, float]:
        return self.center_x, self.center_y

    @property
    def torso_size(self) -> float:
        return self.size

    @property
    def torso_y(self) -> float:
        return self.center_y

    @property
    def shoulder_span(self) -> float:
        return abs(self.left_eye.x - self.right_eye.x) * 2.0

    @property
    def left_shoulder(self) -> Point3D:
        return Point3D(self.left_eye.x, self.center_y + 0.1)

    @property
    def right_shoulder(self) -> Point3D:
        return Point3D(self.right_eye.x, self.center_y + 0.1)

    @property
    def left_wrist(self) -> Point3D:
        return Point3D(self.center_x, self.center_y + 0.3)

    @property
    def right_wrist(self) -> Point3D:
        return Point3D(self.center_x, self.center_y + 0.3)

    @property
    def left_hip(self) -> Point3D:
        return Point3D(self.left_eye.x, self.center_y + 0.3)

    @property
    def right_hip(self) -> Point3D:
        return Point3D(self.right_eye.x, self.center_y + 0.3)


@dataclass
class PlayerPose:
    left_shoulder: Point3D
    right_shoulder: Point3D
    left_wrist: Point3D
    right_wrist: Point3D
    left_hip: Point3D
    right_hip: Point3D
    nose: Point3D

    hip_x: float
    hip_y: float
    shoulder_x: float
    shoulder_y: float
    torso_size: float
    landmarks: Tuple[Point3D, ...]

    @property
    def head_x(self) -> float:
        return self.nose.x

    @property
    def head_y(self) -> float:
        return self.nose.y

    @property
    def head(self) -> Tuple[float, float]:
        return self.nose.x, self.nose.y

    @property
    def hip(self) -> Tuple[float, float]:
        return self.hip_x, self.hip_y

    @property
    def shoulder(self) -> Tuple[float, float]:
        return self.shoulder_x, self.shoulder_y

    @property
    def torso_y(self) -> float:
        """Vertical midpoint between shoulders and hips."""
        return (self.shoulder_y + self.hip_y) / 2.0

    @property
    def shoulder_span(self) -> float:
        """Horizontal distance between left and right shoulders."""
        return abs(self.left_shoulder.x - self.right_shoulder.x)

    @property
    def depth_z(self) -> float:
        """Mean relative Z depth of upper body. Smaller/negative = closer to camera."""
        return (self.left_shoulder.z + self.right_shoulder.z + self.nose.z) / 3.0

    def is_valid_detection(self) -> bool:
        """Ensures core landmarks are valid numbers and visible."""
        return (
            self.left_shoulder.is_valid()
            and self.right_shoulder.is_valid()
            and not (math.isnan(self.shoulder_x) or math.isinf(self.shoulder_x))
            and not (math.isnan(self.shoulder_y) or math.isinf(self.shoulder_y))
            and self.shoulder_span > 0.01
        )

    @property
    def spine_lean_angle_deg(self) -> float:
        """
        Torso lean angle (degrees) computed from hip midpoint to shoulder midpoint vector.
        Negative = leaning left, Positive = leaning right.
        Immune to individual shoulder shrugs.
        """
        dx = self.shoulder_x - self.hip_x
        dy = self.hip_y - self.shoulder_y  # In image coords, shoulder_y < hip_y, so dy > 0
        if dy <= 1e-4:
            return self.shoulder_tilt_angle_deg
        angle_rad = math.atan2(dx, dy)
        return math.degrees(angle_rad)

    @property
    def shoulder_tilt_angle_deg(self) -> float:
        """
        Shoulder line tilt angle (degrees).
        Negative = tilting left, Positive = tilting right.
        """
        dx = self.left_shoulder.x - self.right_shoulder.x
        dy = self.left_shoulder.y - self.right_shoulder.y
        if abs(dx) <= 1e-4:
            return 0.0
        return math.degrees(math.atan2(dy, dx))

    @property
    def foreground_score(self) -> float:
        """Score favoring players in the front (wide shoulders, close Z depth)."""
        return self.shoulder_span - (self.depth_z * 0.2)

    @classmethod
    def from_landmarks(cls, raw_landmarks: Sequence[Any]) -> Optional["PlayerPose"]:
        if raw_landmarks is None or len(raw_landmarks) < 25:
            return None

        def to_point(pt: Any) -> Point3D:
            if isinstance(pt, Point3D):
                return pt
            return Point3D(
                x=float(pt.x),
                y=float(pt.y),
                z=float(getattr(pt, "z", 0.0)),
                visibility=float(getattr(pt, "visibility", 1.0)),
            )

        pts = tuple(to_point(lm) for lm in raw_landmarks)
        l_sh = pts[LEFT_SHOULDER_IDX]
        r_sh = pts[RIGHT_SHOULDER_IDX]
        l_hip = pts[LEFT_HIP_IDX]
        r_hip = pts[RIGHT_HIP_IDX]
        l_wrist = pts[LEFT_WRIST_IDX]
        r_wrist = pts[RIGHT_WRIST_IDX]
        nose = pts[NOSE_IDX]

        sh_mid = Point3D.midpoint(l_sh, r_sh)
        hip_mid = Point3D.midpoint(l_hip, r_hip)
        torso_size = abs(hip_mid.y - sh_mid.y)

        return cls(
            left_shoulder=l_sh,
            right_shoulder=r_sh,
            left_wrist=l_wrist,
            right_wrist=r_wrist,
            left_hip=l_hip,
            right_hip=r_hip,
            nose=nose,
            hip_x=hip_mid.x,
            hip_y=hip_mid.y,
            shoulder_x=sh_mid.x,
            shoulder_y=sh_mid.y,
            torso_size=torso_size,
            landmarks=pts,
        )


class CalibrationStatus(Enum):
    UNCALIBRATED = "UNCALIBRATED"
    CALIBRATING = "CALIBRATING"
    COOLDOWN = "COOLDOWN"
    CALIBRATED = "CALIBRATED"


@dataclass
class CalibrationState:
    p1_neutral_x: float = 0.28
    p2_neutral_x: float = 0.72
    p1_standing_y: Optional[float] = 0.40
    p2_standing_y: Optional[float] = 0.40
    calib_pose_counter: int = 0
    calib_pose_progress: float = 0.0
    left_thresh: float = 0.23
    right_thresh: float = 0.77
    status: CalibrationStatus = CalibrationStatus.CALIBRATED
    cooldown_remaining: float = 0.0
    fixed_mode: bool = True
    p1_brake_y: float = 0.52
    p2_brake_y: float = 0.52
    p1_jump_y: float = 0.28
    p2_jump_y: float = 0.28

    @property
    def is_calibrated(self) -> bool:
        return self.status in (CalibrationStatus.CALIBRATED, CalibrationStatus.COOLDOWN)


@dataclass
class SteeringState:
    direction: Optional[str] = None
    intensity: float = 0.0
    active: bool = False
    p1_power: float = 0.0
    p2_power: float = 0.0


@dataclass
class GestureResult:
    steering: SteeringState
    accelerate: bool = False
    cruise_control: bool = False
    brake: bool = False
    rescue: bool = False
    p1_brake: bool = False
    p2_brake: bool = False
    p1_brake_y: float = 0.52
    p2_brake_y: float = 0.52
    p1_jump: bool = False
    p2_jump: bool = False
    p1_jump_y: float = 0.28
    p2_jump_y: float = 0.28
    p1_shoulder: Optional[Tuple[float, float]] = None
    p2_shoulder: Optional[Tuple[float, float]] = None
    p1_hip: Optional[Tuple[float, float]] = None
    p2_hip: Optional[Tuple[float, float]] = None
    calibration: Optional[CalibrationState] = None
    card_detected: bool = False
    card_bbox: Optional[Tuple[int, int, int, int]] = None
    card_enabled: bool = True
    rescue_mode: str = "color"
    p1_face: Optional[PlayerFace] = None
    p2_face: Optional[PlayerFace] = None
