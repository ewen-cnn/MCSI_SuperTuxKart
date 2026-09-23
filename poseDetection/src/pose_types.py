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

    def distance_to(self, other: "Point3D") -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

    @classmethod
    def midpoint(cls, p1: "Point3D", p2: "Point3D") -> "Point3D":
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
    p1_neutral_x: float = 0.35
    p2_neutral_x: float = 0.65
    p1_standing_y: Optional[float] = None
    p2_standing_y: Optional[float] = None
    calib_pose_counter: int = 0
    calib_pose_progress: float = 0.0
    left_thresh: float = 0.29
    right_thresh: float = 0.71
    status: CalibrationStatus = CalibrationStatus.UNCALIBRATED
    cooldown_remaining: float = 0.0

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
    p1_brake_y: float = 0.39
    p2_brake_y: float = 0.39
    p1_jump: bool = False
    p2_jump: bool = False
    p1_jump_y: float = 0.29
    p2_jump_y: float = 0.29
    p1_shoulder: Optional[Tuple[float, float]] = None
    p2_shoulder: Optional[Tuple[float, float]] = None
    p1_hip: Optional[Tuple[float, float]] = None
    p2_hip: Optional[Tuple[float, float]] = None
    calibration: Optional[CalibrationState] = None
