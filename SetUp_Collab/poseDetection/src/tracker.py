from pathlib import Path
import time
import urllib.request
from typing import Tuple, Optional, List
import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from config import TrackerConfig, FilterConfig
from pose_types import PlayerPose
from capture import Camera
from hud import HUD, COLOR_P1, COLOR_P2
from filters import PoseSmoother

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"


class PoseTracker:
    """
    Detects multi-person poses via MediaPipe PoseLandmarker with Z-depth and
    visual scale foreground filtering to eliminate background people.
    """

    def __init__(
        self,
        config: TrackerConfig = TrackerConfig(),
        filter_config: FilterConfig = FilterConfig(),
        model_path: Optional[Path] = None,
    ):
        self.config = config
        self.filter_config = filter_config

        if model_path is None:
            model_path = Path(__file__).resolve().parent.parent / "models" / "pose_landmarker_lite.task"
        model_path = Path(model_path)

        if not model_path.exists():
            model_path.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(MODEL_URL, str(model_path))

        base_options = python.BaseOptions(model_asset_path=str(model_path))
        options = vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.IMAGE,
            num_poses=self.config.num_poses,
            min_pose_detection_confidence=self.config.min_detection_confidence,
            min_pose_presence_confidence=self.config.min_detection_confidence,
            min_tracking_confidence=self.config.min_tracking_confidence,
        )
        self.detector = vision.PoseLandmarker.create_from_options(options)
        self.p1_smoother = PoseSmoother(config=self.filter_config)
        self.p2_smoother = PoseSmoother(config=self.filter_config)
        self.prev_p1: Optional[PlayerPose] = None
        self.prev_p2: Optional[PlayerPose] = None

        # Tracking continuity and depth jump hysteresis
        self.last_p1_x: float = 0.28
        self.last_p2_x: float = 0.72
        self.last_p1_span: Optional[float] = None
        self.last_p2_span: Optional[float] = None
        self.p1_lost_time: Optional[float] = None
        self.p2_lost_time: Optional[float] = None

    def reset(self):
        self.p1_smoother.reset()
        self.p2_smoother.reset()
        self.prev_p1 = None
        self.prev_p2 = None
        self.last_p1_span = None
        self.last_p2_span = None
        self.p1_lost_time = None
        self.p2_lost_time = None

    def _handle_loss(self, timestamp: float):
        timeout = getattr(self.filter_config, "timeout_seconds", 0.6)
        if self.p1_lost_time is None:
            self.p1_lost_time = timestamp
        elif (timestamp - self.p1_lost_time) > timeout:
            self.last_p1_span = None
            self.last_p1_x = 0.28

        if self.p2_lost_time is None:
            self.p2_lost_time = timestamp
        elif (timestamp - self.p2_lost_time) > timeout:
            self.last_p2_span = None
            self.last_p2_x = 0.72

    def process(
        self, frame_bgr, timestamp: Optional[float] = None
    ) -> Tuple[Optional[PlayerPose], Optional[PlayerPose]]:
        if frame_bgr is None or not hasattr(frame_bgr, "shape") or frame_bgr.size == 0 or len(frame_bgr.shape) != 3:
            return None, None

        if timestamp is None:
            timestamp = time.time()

        try:
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
            result = self.detector.detect(mp_image)
        except Exception:
            return None, None

        if not result.pose_landmarks:
            self._handle_loss(timestamp)
            return None, None

        raw_candidates: List[PlayerPose] = []
        for lm in result.pose_landmarks:
            pose = PlayerPose.from_landmarks(lm)
            if pose is None or not pose.is_valid_detection():
                continue

            # Check shoulder visibility
            sh_vis = min(pose.left_shoulder.visibility, pose.right_shoulder.visibility)
            if sh_vis < 0.35:
                continue

            # 1. Reject background people using shoulder span (visual scale)
            if pose.shoulder_span < self.config.min_shoulder_span:
                continue

            # 2. Reject background people using MediaPipe relative Z-depth
            if pose.depth_z > self.config.max_depth_z:
                continue

            raw_candidates.append(pose)

        if not raw_candidates:
            self._handle_loss(timestamp)
            return None, None

        # 3. Dynamic Depth Clustering & Visual Scale Ratio
        # Sort candidates by foreground score (closest Z-depth & widest span)
        raw_candidates.sort(key=lambda p: p.foreground_score, reverse=True)
        primary = raw_candidates[0]
        foreground_candidates: List[PlayerPose] = [primary]

        max_depth_gap = getattr(self.config, "max_relative_depth_diff", 0.15)
        min_scale_ratio = getattr(self.config, "min_shoulder_scale_ratio", 0.55)

        for cand in raw_candidates[1:]:
            # Dynamic Relative Depth Gap: Reject if standing significantly behind primary player
            if (cand.depth_z - primary.depth_z) > max_depth_gap:
                continue
            # Visual Scale Ratio: Reject if perspective width is too small relative to front player
            if primary.shoulder_span > 0.05 and (cand.shoulder_span / primary.shoulder_span) < min_scale_ratio:
                continue
            foreground_candidates.append(cand)
            if len(foreground_candidates) >= 2:
                break

        # 4. Partition into P1 (Left territory <= 0.55) and P2 (Right territory >= 0.45)
        # with distance jump hysteresis to prevent spectators from hijacking when ducking
        def is_depth_jump(cand: PlayerPose, last_span: Optional[float]) -> bool:
            if last_span is None:
                return False
            return (cand.shoulder_span / last_span) < 0.60

        p1_candidates = [
            p for p in foreground_candidates
            if p.shoulder_x <= 0.55 and not is_depth_jump(p, self.last_p1_span)
        ]
        p2_candidates = [
            p for p in foreground_candidates
            if p.shoulder_x >= 0.45 and not is_depth_jump(p, self.last_p2_span)
        ]

        raw_p1: Optional[PlayerPose] = None
        raw_p2: Optional[PlayerPose] = None

        if p1_candidates:
            raw_p1 = max(
                p1_candidates,
                key=lambda p: p.foreground_score - 1.5 * abs(p.shoulder_x - self.last_p1_x),
            )

        if p2_candidates:
            # Avoid picking the same person for both P1 and P2
            remaining_p2 = [p for p in p2_candidates if p is not raw_p1]
            if remaining_p2:
                raw_p2 = max(
                    remaining_p2,
                    key=lambda p: p.foreground_score - 1.5 * abs(p.shoulder_x - self.last_p2_x),
                )

        # Hysteresis for solo player leaning near center divider
        if len(foreground_candidates) == 1:
            only_player = foreground_candidates[0]
            if raw_p1 is None and raw_p2 is None:
                if only_player.shoulder_x < 0.50:
                    raw_p1 = only_player
                else:
                    raw_p2 = only_player
            elif raw_p1 is None and raw_p2 is not None:
                if abs(only_player.shoulder_x - self.last_p2_x) < 0.35:
                    raw_p2 = only_player
            elif raw_p2 is None and raw_p1 is not None:
                if abs(only_player.shoulder_x - self.last_p1_x) < 0.35:
                    raw_p1 = only_player

        # Update P1 tracking state
        if raw_p1 is not None:
            self.last_p1_x = raw_p1.shoulder_x
            self.last_p1_span = raw_p1.shoulder_span
            self.p1_lost_time = None
        else:
            if self.p1_lost_time is None:
                self.p1_lost_time = timestamp
            elif (timestamp - self.p1_lost_time) > getattr(self.filter_config, "timeout_seconds", 0.6):
                self.last_p1_span = None
                self.last_p1_x = 0.28

        # Update P2 tracking state
        if raw_p2 is not None:
            self.last_p2_x = raw_p2.shoulder_x
            self.last_p2_span = raw_p2.shoulder_span
            self.p2_lost_time = None
        else:
            if self.p2_lost_time is None:
                self.p2_lost_time = timestamp
            elif (timestamp - self.p2_lost_time) > getattr(self.filter_config, "timeout_seconds", 0.6):
                self.last_p2_span = None
                self.last_p2_x = 0.72

        p1 = self.p1_smoother.smooth(raw_p1, timestamp) if raw_p1 else None
        p2 = self.p2_smoother.smooth(raw_p2, timestamp) if raw_p2 else None

        self.prev_p1 = p1
        self.prev_p2 = p2
        return p1, p2

    @staticmethod
    def draw_player(frame, pose: Optional[PlayerPose], color, label=""):
        if pose is None:
            return
        HUD.draw_skeleton(frame, pose, color, label)


def main():
    with Camera() as cam:
        if not cam.is_opened():
            return

        tracker = PoseTracker()
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
            if p1:
                HUD.draw_skeleton(frame, p1, COLOR_P1, "P1")
            if p2:
                HUD.draw_skeleton(frame, p2, COLOR_P2, "P2")

            cv2.putText(
                frame, f"FPS: {fps:.1f}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2
            )
            cv2.putText(
                frame, "P1: OK" if p1 else "P1: --", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOR_P1, 2
            )
            cv2.putText(
                frame, "P2: OK" if p2 else "P2: --", (20, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOR_P2, 2
            )

            cv2.imshow("Z-Depth Filtered Pose Tracker", frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
