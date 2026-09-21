import time
import cv2

try:
    from poseDetection.src.config import (
        CAMERA_ID,
        CAMERA_WIDTH,
        CAMERA_HEIGHT,
        CAMERA_FPS,
    )
except ImportError:
    from config import (
        CAMERA_ID,
        CAMERA_WIDTH,
        CAMERA_HEIGHT,
        CAMERA_FPS,
    )


class Camera:
    def __init__(
        self,
        device_id: int = CAMERA_ID,
        width: int = CAMERA_WIDTH,
        height: int = CAMERA_HEIGHT,
        fps: int = CAMERA_FPS,
    ):
        self.cap = cv2.VideoCapture(device_id)
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)

    def is_opened(self) -> bool:
        return self.cap.isOpened()

    def read(self):
        ret, frame = self.cap.read()
        if not ret:
            return False, None
        return True, cv2.flip(frame, 1)

    def release(self):
        self.cap.release()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


def main():
    cam = Camera()
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

        cv2.putText(frame, f"FPS: {fps:.1f}", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
        cv2.imshow("Capture Test", frame)

        if cv2.waitKey(1) & 0xFF in (ord('q'), 27):
            break

    cam.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
