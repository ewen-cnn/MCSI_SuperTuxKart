import time
from pathlib import Path
import urllib.request
import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

try:
    from poseDetection.src.capture import Camera
    from poseDetection.src.config import (
        NUM_POSES,
        MIN_DETECTION_CONFIDENCE,
        MIN_TRACKING_CONFIDENCE,
    )
except ImportError:
    from capture import Camera
    from config import (
        NUM_POSES,
        MIN_DETECTION_CONFIDENCE,
        MIN_TRACKING_CONFIDENCE,
    )


MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"


class PoseTracker:
    def __init__(self, model_path=None):
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
            num_poses=NUM_POSES,
            min_pose_detection_confidence=MIN_DETECTION_CONFIDENCE,
            min_pose_presence_confidence=MIN_DETECTION_CONFIDENCE,
            min_tracking_confidence=MIN_TRACKING_CONFIDENCE,
        )
        self.detector = vision.PoseLandmarker.create_from_options(options)

    def process(self, frame_bgr):
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
        result = self.detector.detect(mp_image)

        if not result.pose_landmarks:
            return None, None

        poses = result.pose_landmarks
        if len(poses) == 1:
            hip_x = (poses[0][23].x + poses[0][24].x) / 2.0
            return (poses[0], None) if hip_x < 0.5 else (None, poses[0])

        poses = sorted(poses[:2], key=lambda lm: (lm[23].x + lm[24].x) / 2.0)
        return poses[0], poses[1]

    @staticmethod
    def draw_player(frame, landmarks, color, label=""):
        if landmarks is None:
            return

        h, w, _ = frame.shape
        for conn in vision.PoseLandmarksConnections.POSE_LANDMARKS:
            pt1 = (int(landmarks[conn.start].x * w), int(landmarks[conn.start].y * h))
            pt2 = (int(landmarks[conn.end].x * w), int(landmarks[conn.end].y * h))
            cv2.line(frame, pt1, pt2, color, 2, cv2.LINE_AA)

        for lm in landmarks:
            cv2.circle(frame, (int(lm.x * w), int(lm.y * h)), 3, color, -1)

        if label:
            hx = int(landmarks[0].x * w)
            hy = max(25, int(landmarks[0].y * h) - 15)
            cv2.putText(frame, label, (hx - 20, hy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)


def main():
    cam = Camera()
    if not cam.is_opened():
        return

    tracker = PoseTracker()
    COLOR_P1 = (255, 255, 0)
    COLOR_P2 = (255, 0, 255)

    prev = time.time()
    fps = 0.0

    while True:
        ret, frame = cam.read()
        if not ret:
            break

        p1, p2 = tracker.process(frame)
        tracker.draw_player(frame, p1, COLOR_P1, "P1")
        tracker.draw_player(frame, p2, COLOR_P2, "P2")

        now = time.time()
        dt = now - prev
        prev = now
        if dt > 0:
            fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps > 0 else 1.0 / dt

        cv2.putText(frame, f"FPS: {fps:.1f}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(frame, "P1: OK" if p1 else "P1: --", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOR_P1, 2)
        cv2.putText(frame, "P2: OK" if p2 else "P2: --", (20, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOR_P2, 2)

        cv2.imshow("Tracker Test", frame)
        if cv2.waitKey(1) & 0xFF in (ord('q'), 27):
            break

    cam.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
