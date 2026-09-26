import math
import time
from typing import Optional, List

from config import FilterConfig
from pose_types import Point3D, PlayerPose, PlayerFace


class LowPassFilter:
    """Standard exponential moving average filter."""

    def __init__(self, alpha: float = 1.0):
        self.alpha = alpha
        self.prev: Optional[float] = None

    def filter(self, val: float, alpha: Optional[float] = None) -> float:
        if alpha is not None:
            self.alpha = alpha
        if self.prev is None:
            self.prev = val
            return val
        res = self.alpha * val + (1.0 - self.alpha) * self.prev
        self.prev = res
        return res

    def reset(self):
        self.prev = None


class OneEuroFilter:
    """Adaptive 1-Euro low-pass filter minimizing jitter at low speed and lag at high speed."""

    def __init__(
        self,
        min_cutoff: float = 1.2,
        beta: float = 0.05,
        d_cutoff: float = 1.0,
    ):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.x_filt = LowPassFilter()
        self.dx_filt = LowPassFilter()
        self.last_time: Optional[float] = None

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2.0 * math.pi * max(cutoff, 1e-4))
        return 1.0 / (1.0 + tau / max(dt, 1e-6))

    def filter(self, x: float, timestamp: Optional[float] = None) -> float:
        if math.isnan(x) or math.isinf(x):
            return self.x_filt.prev if self.x_filt.prev is not None else 0.0

        if timestamp is None:
            timestamp = time.time()

        if self.last_time is None:
            self.last_time = timestamp
            return self.x_filt.filter(x)

        dt = timestamp - self.last_time
        self.last_time = timestamp
        if dt <= 1e-6:
            dt = 1e-6

        # Avoid derivative explosion after dropped frames / stall
        if dt > 0.5:
            self.dx_filt.reset()
            self.x_filt.prev = x
            return x

        prev_x = self.x_filt.prev if self.x_filt.prev is not None else x
        dx = (x - prev_x) / dt
        edx = self.dx_filt.filter(dx, self._alpha(self.d_cutoff, dt))

        cutoff = self.min_cutoff + self.beta * abs(edx)
        return self.x_filt.filter(x, self._alpha(cutoff, dt))

    def reset(self):
        self.x_filt.reset()
        self.dx_filt.reset()
        self.last_time = None


class PointFilter:
    """Filters a Point3D instance using OneEuroFilter on spatial coordinates."""

    def __init__(
        self,
        min_cutoff: float = 1.2,
        beta: float = 0.05,
        d_cutoff: float = 1.0,
    ):
        self.x_filter = OneEuroFilter(min_cutoff, beta, d_cutoff)
        self.y_filter = OneEuroFilter(min_cutoff, beta, d_cutoff)

    def filter(self, pt: Point3D, timestamp: Optional[float] = None) -> Point3D:
        sx = self.x_filter.filter(pt.x, timestamp)
        sy = self.y_filter.filter(pt.y, timestamp)
        return Point3D(x=sx, y=sy, z=pt.z, visibility=pt.visibility)

    def reset(self):
        self.x_filter.reset()
        self.y_filter.reset()


class PoseSmoother:
    """Smoothes all landmarks of a PlayerPose to reduce jitter and latency."""

    def __init__(self, config: FilterConfig = FilterConfig()):
        self.config = config
        self.point_filters: List[PointFilter] = []
        self.last_seen: float = 0.0

    def smooth(
        self, pose: Optional[PlayerPose], timestamp: Optional[float] = None
    ) -> Optional[PlayerPose]:
        if pose is None:
            return None

        points = pose.landmarks
        if not points:
            return pose

        if timestamp is None:
            timestamp = time.time()

        if (timestamp - self.last_seen) > self.config.timeout_seconds:
            self.reset()
        self.last_seen = timestamp

        while len(self.point_filters) < len(points):
            self.point_filters.append(
                PointFilter(self.config.min_cutoff, self.config.beta, self.config.d_cutoff)
            )

        smoothed_points = [
            self.point_filters[i].filter(pt, timestamp) for i, pt in enumerate(points)
        ]
        return PlayerPose.from_landmarks(smoothed_points)

    def reset(self):
        for f in self.point_filters:
            f.reset()


class FaceSmoother:
    """Smoothes keypoints, center coordinates, and roll angle of a PlayerFace."""

    def __init__(self, config: FilterConfig = FilterConfig()):
        self.config = config
        self.nose_filter = PointFilter(config.min_cutoff, config.beta, config.d_cutoff)
        self.left_eye_filter = PointFilter(config.min_cutoff, config.beta, config.d_cutoff)
        self.right_eye_filter = PointFilter(config.min_cutoff, config.beta, config.d_cutoff)
        self.mouth_filter = PointFilter(config.min_cutoff, config.beta, config.d_cutoff)
        self.center_x_filter = OneEuroFilter(config.min_cutoff, config.beta, config.d_cutoff)
        self.center_y_filter = OneEuroFilter(config.min_cutoff, config.beta, config.d_cutoff)
        self.roll_filter = OneEuroFilter(config.min_cutoff, config.beta, config.d_cutoff)
        self.last_seen: float = 0.0

    def smooth(
        self, face: Optional[PlayerFace], timestamp: Optional[float] = None
    ) -> Optional[PlayerFace]:
        if face is None:
            return None

        if timestamp is None:
            timestamp = time.time()

        if (timestamp - self.last_seen) > self.config.timeout_seconds:
            self.reset()
        self.last_seen = timestamp

        s_nose = self.nose_filter.filter(face.nose, timestamp)
        s_left_eye = self.left_eye_filter.filter(face.left_eye, timestamp)
        s_right_eye = self.right_eye_filter.filter(face.right_eye, timestamp)
        s_mouth = self.mouth_filter.filter(face.mouth, timestamp)
        s_cx = self.center_x_filter.filter(face.center_x, timestamp)
        s_cy = self.center_y_filter.filter(face.center_y, timestamp)
        s_roll = self.roll_filter.filter(face.roll_angle, timestamp)

        return PlayerFace(
            nose=s_nose,
            left_eye=s_left_eye,
            right_eye=s_right_eye,
            mouth=s_mouth,
            right_ear=face.right_ear,
            left_ear=face.left_ear,
            center_x=s_cx,
            center_y=s_cy,
            bbox=face.bbox,
            roll_angle=s_roll,
            size=face.size,
            confidence=face.confidence,
            landmarks=face.landmarks,
        )

    def reset(self):
        self.nose_filter.reset()
        self.left_eye_filter.reset()
        self.right_eye_filter.reset()
        self.mouth_filter.reset()
        self.center_x_filter.reset()
        self.center_y_filter.reset()
        self.roll_filter.reset()
