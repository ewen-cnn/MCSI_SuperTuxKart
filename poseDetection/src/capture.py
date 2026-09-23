import time
from typing import Tuple, Optional
import numpy as np
import cv2

from config import CameraConfig


class Camera:
    """Manages OpenCV video capture device with configurable format and mirror flip."""

    def __init__(self, config: CameraConfig = CameraConfig()):
        self.config = config
        self.cap = cv2.VideoCapture(self.config.device_id)
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.config.fps)

    def is_opened(self) -> bool:
        return self.cap.isOpened()

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        ret, frame = self.cap.read()
        if not ret or frame is None:
            return False, None
        return True, cv2.flip(frame, 1)

    def release(self):
        if self.cap.isOpened():
            self.cap.release()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


def main():
    with Camera() as cam:
        if not cam.is_opened():
            print("Error: could not open camera")
            return

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

            cv2.putText(
                frame, f"FPS: {fps:.1f}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2
            )
            cv2.imshow("Capture Test", frame)

            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
