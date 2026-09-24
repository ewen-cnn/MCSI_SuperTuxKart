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

    def reset(self):
        self.p1_smoother.reset()
        self.p2_smoother.reset()
        self.prev_p1 = None
        self.prev_p2 = None

    def process(
        self, frame_bgr, timestamp: Optional[float] = None
    ) -> Tuple[Optional[PlayerPose], Optional[PlayerPose]]:
        if timestamp is None:
            timestamp = time.time()

        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
        result = self.detector.detect(mp_image)

        if not result.pose_landmarks:
            return None, None

        foreground_candidates: List[PlayerPose] = []
        for lm in result.pose_landmarks:
            pose = PlayerPose.from_landmarks(lm)
            if pose is None:
                continue

            # Check shoulder visibility
            sh_vis = min(pose.left_shoulder.visibility, pose.right_shoulder.visibility)
            if sh_vis < 0.35:
                continue

            # 1. Reject background people using shoulder span (visual scale)
            # Foreground players sitting in front have wide shoulders (>= min_shoulder_span)
            if pose.shoulder_span < self.config.min_shoulder_span:
                continue

            # 2. Reject background people using MediaPipe relative Z-depth
            # Foreground players have negative/small Z; people in the back have large Z
            if pose.depth_z > self.config.max_depth_z:
                continue

            foreground_candidates.append(pose)

        if not foreground_candidates:
            return None, None

        # Partition foreground candidates into P1 (Left side: shoulder_x < 0.50)
        # and P2 (Right side: shoulder_x >= 0.50)
        p1_candidates = [p for p in foreground_candidates if p.shoulder_x < 0.50]
        p2_candidates = [p for p in foreground_candidates if p.shoulder_x >= 0.50]

        raw_p1: Optional[PlayerPose] = None
        raw_p2: Optional[PlayerPose] = None

        if p1_candidates:
            if self.prev_p1 is not None:
                # Prefer candidate closest to previous P1 position with high foreground score
                raw_p1 = max(
                    p1_candidates,
                    key=lambda p: p.foreground_score - 1.5 * abs(p.shoulder_x - self.prev_p1.shoulder_x),
                )
            else:
                raw_p1 = max(p1_candidates, key=lambda p: p.foreground_score)

        if p2_candidates:
            if self.prev_p2 is not None:
                raw_p2 = max(
                    p2_candidates,
                    key=lambda p: p.foreground_score - 1.5 * abs(p.shoulder_x - self.prev_p2.shoulder_x),
                )
            else:
                raw_p2 = max(p2_candidates, key=lambda p: p.foreground_score)

        # Hysteresis for solo player leaning near center divider
        if len(foreground_candidates) == 1:
            only_player = foreground_candidates[0]
            if raw_p1 is None and raw_p2 is None:
                if only_player.shoulder_x < 0.50:
                    raw_p1 = only_player
                else:
                    raw_p2 = only_player
            elif raw_p1 is None and raw_p2 is not None:
                if self.prev_p2 is not None and abs(only_player.shoulder_x - self.prev_p2.shoulder_x) < 0.35:
                    raw_p2 = only_player
            elif raw_p2 is None and raw_p1 is not None:
                if self.prev_p1 is not None and abs(only_player.shoulder_x - self.prev_p1.shoulder_x) < 0.35:
                    raw_p1 = only_player

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
