import time
from typing import Optional, Tuple, List
import cv2
import numpy as np

from config import ColorConfig


class ColorCardDetector:
    """Detects colored objects/cards in the video frame to trigger game actions."""

    PRESETS = {
        "green": [((40, 80, 60), (82, 255, 255))],
        "red": [((0, 90, 70), (10, 255, 255)), ((170, 90, 70), (180, 255, 255))],
        "blue": [((100, 90, 60), (130, 255, 255))],
        "yellow": [((22, 100, 80), (36, 255, 255))],
        "orange": [((10, 110, 80), (22, 255, 255))],
        "purple": [((130, 90, 60), (160, 255, 255))],
        "pink": [((140, 100, 80), (170, 255, 255))],
        "magenta": [((140, 100, 80), (170, 255, 255))],
    }

    def __init__(self, config: Optional[ColorConfig] = None):
        self.config = config or ColorConfig()
        self._kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))

        self.last_trigger_time: float = -999.0
        self.trigger_until: float = -999.0
        self.was_detected: bool = False
        self.custom_ranges: Optional[List[Tuple[Tuple[int, int, int], Tuple[int, int, int]]]] = None

    def get_hsv_ranges(self) -> List[Tuple[Tuple[int, int, int], Tuple[int, int, int]]]:
        preset_key = self.config.preset.lower()
        if preset_key == "custom" and self.custom_ranges is not None:
            return self.custom_ranges
        if preset_key in self.PRESETS:
            return self.PRESETS[preset_key]
        return [(self.config.lower_hsv, self.config.upper_hsv)]

    def set_preset(self, preset: str):
        self.config.preset = preset

    def set_custom_range(self, lower: Tuple[int, int, int], upper: Tuple[int, int, int]):
        self.config.preset = "custom"
        self.config.lower_hsv = lower
        self.config.upper_hsv = upper
        self.custom_ranges = [(lower, upper)]

    def sample_from_frame(
        self,
        frame: Optional[np.ndarray],
        box_size: int = 80,
    ) -> Tuple[bool, str]:
        """
        Samples the card color from the center of the frame to dynamically calibrate HSV bounds.
        """
        if frame is None:
            return False, "No camera frame available"

        h, w = frame.shape[:2]
        cx, cy = w // 2, h // 2
        half = box_size // 2
        y1, y2 = max(0, cy - half), min(h, cy + half)
        x1, x2 = max(0, cx - half), min(w, cx + half)

        patch = frame[y1:y2, x1:x2]
        if patch.size == 0:
            return False, "Sample area is empty"

        patch_hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
        # Select pixels with sufficient saturation and brightness
        valid = patch_hsv[(patch_hsv[:, :, 1] >= 50) & (patch_hsv[:, :, 2] >= 40)]
        if len(valid) < 50:
            return False, "Card not detected in center. Hold card closer to center box."

        med_h = int(np.median(valid[:, 0]))
        med_s = int(np.median(valid[:, 1]))
        med_v = int(np.median(valid[:, 2]))

        s_min = max(75, int(med_s - 45))
        v_min = max(50, int(med_v - 60))
        h_tol = 16

        ranges = []
        h_low = med_h - h_tol
        h_high = med_h + h_tol
        if h_low < 0:
            ranges.append(((0, s_min, v_min), (h_high, 255, 255)))
            ranges.append(((180 + h_low, s_min, v_min), (180, 255, 255)))
        elif h_high > 180:
            ranges.append(((h_low, s_min, v_min), (180, 255, 255)))
            ranges.append(((0, s_min, v_min), (h_high - 180, 255, 255)))
        else:
            ranges.append(((h_low, s_min, v_min), (h_high, 255, 255)))

        self.custom_ranges = ranges
        self.config.preset = "custom"
        self.config.lower_hsv = ranges[0][0]
        self.config.upper_hsv = ranges[0][1]

        return True, f"Card calibrated! (H:{med_h}, S:{med_s}, V:{med_v})"

    def reset(self):
        self.last_trigger_time = -999.0
        self.trigger_until = -999.0
        self.was_detected = False

    def detect(
        self, frame: Optional[np.ndarray], timestamp: Optional[float] = None
    ) -> Tuple[bool, bool, Optional[Tuple[int, int, int, int]]]:
        """
        Evaluates frame for colored card with shape, aspect ratio, and convexity filters.

        Returns:
            (triggered, detected, bounding_box)
            - triggered: True if rescue pulse is active on this frame
            - detected: True if card is currently detected in frame
            - bounding_box: (x, y, w, h) in pixels, or None
        """
        if frame is None or not self.config.enabled:
            return False, False, None

        now = timestamp if timestamp is not None else time.time()

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        ranges = self.get_hsv_ranges()

        combined_mask = None
        for lower, upper in ranges:
            lower_np = np.array(lower, dtype=np.uint8)
            upper_np = np.array(upper, dtype=np.uint8)
            mask = cv2.inRange(hsv, lower_np, upper_np)
            combined_mask = (
                mask if combined_mask is None else cv2.bitwise_or(combined_mask, mask)
            )

        if combined_mask is None:
            return False, False, None

        # Clean noise with morphological opening and closing
        cleaned = cv2.morphologyEx(combined_mask, cv2.MORPH_OPEN, self._kernel, iterations=1)
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, self._kernel, iterations=1)

        contours, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        detected = False
        bbox: Optional[Tuple[int, int, int, int]] = None

        valid_candidates = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < self.config.min_area:
                continue
            if self.config.max_area is not None and area > self.config.max_area:
                continue

            x, y, w, h = cv2.boundingRect(c)
            aspect = max(w, h) / max(1, min(w, h))
            if aspect > self.config.max_aspect_ratio:
                continue

            extent = area / max(1e-4, w * h)
            if extent < self.config.min_extent:
                continue

            hull = cv2.convexHull(c)
            hull_area = cv2.contourArea(hull)
            solidity = area / max(1e-4, hull_area)
            if solidity < self.config.min_solidity:
                continue

            # Score candidates favoring compact, solid rectangular shapes
            score = solidity * extent
            valid_candidates.append({
                "area": area,
                "bbox": (int(x), int(y), int(w), int(h)),
                "score": score,
            })

        if valid_candidates:
            best = max(valid_candidates, key=lambda item: item["score"])
            detected = True
            bbox = best["bbox"]

        # Pulse and cooldown logic
        cooldown_passed = (now - self.last_trigger_time) >= self.config.cooldown_seconds

        if detected:
            if not self.was_detected and cooldown_passed:
                self.last_trigger_time = now
                self.trigger_until = now + self.config.pulse_duration
            self.was_detected = True
        else:
            self.was_detected = False

        triggered = now < self.trigger_until

        return triggered, detected, bbox
