from typing import Optional, Tuple
import cv2
from mediapipe.tasks.python import vision

from pose_types import PlayerPose, GestureResult, CalibrationStatus

# Color palette (BGR)
COLOR_P1 = (255, 255, 0)         # Cyan
COLOR_P2 = (255, 0, 255)         # Magenta
COLOR_NEUTRAL_LINE = (200, 200, 200)
COLOR_NEUTRAL_BG = (35, 35, 35)
COLOR_MARGIN = (0, 165, 255)     # Orange
COLOR_ALERT = (0, 0, 255)        # Red
COLOR_OK = (0, 255, 0)           # Green
COLOR_WARN = (0, 215, 255)       # Yellow
COLOR_DIM = (100, 100, 100)      # Gray

COLOR_BRAKE_INACTIVE = (80, 80, 210)
COLOR_BRAKE_ACTIVE = (0, 0, 255)
COLOR_JUMP_INACTIVE = (0, 190, 240)
COLOR_JUMP_ACTIVE = (0, 255, 255)


class HUD:
    """Renders overlays, player skeletons, dynamic thresholds, and telemetry badges."""

    def __init__(self):
        self.banner_message: Optional[str] = None
        self.banner_expires: float = 0.0
        self.banner_color: Tuple[int, int, int] = COLOR_OK

    def show_message(
        self, text: str, duration: float = 3.0, color: Tuple[int, int, int] = COLOR_OK
    ):
        import time
        self.banner_message = text
        self.banner_expires = time.time() + duration
        self.banner_color = color

    @staticmethod
    def draw_badge(
        frame,
        text: str,
        pos: Tuple[int, int],
        text_color: Tuple[int, int, int],
        bg_color: Tuple[int, int, int] = (25, 25, 25),
        border_color: Optional[Tuple[int, int, int]] = (70, 70, 70),
        font_scale: float = 0.42,
        thickness: int = 1,
    ):
        x, y = pos
        (w_text, h_text), baseline = cv2.getTextSize(
            text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
        )
        pad_x, pad_y = 5, 4
        x1 = max(0, x - pad_x)
        y1 = max(0, y - h_text - pad_y)
        x2 = min(frame.shape[1] - 1, x + w_text + pad_x)
        y2 = min(frame.shape[0] - 1, y + baseline + pad_y)

        cv2.rectangle(frame, (x1, y1), (x2, y2), bg_color, -1)
        if border_color is not None:
            cv2.rectangle(frame, (x1, y1), (x2, y2), border_color, 1)
        cv2.putText(
            frame,
            text,
            (x, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            text_color,
            thickness,
            cv2.LINE_AA,
        )

    @staticmethod
    def draw_skeleton(
        frame, pose: Optional[PlayerPose], color: Tuple[int, int, int], label: str = ""
    ):
        if pose is None:
            return

        h, w, _ = frame.shape
        points = pose.landmarks

        for conn in vision.PoseLandmarksConnections.POSE_LANDMARKS:
            if conn.start < len(points) and conn.end < len(points):
                pt1 = (int(points[conn.start].x * w), int(points[conn.start].y * h))
                pt2 = (int(points[conn.end].x * w), int(points[conn.end].y * h))
                cv2.line(frame, pt1, pt2, color, 2, cv2.LINE_AA)

        for pt in points:
            cv2.circle(frame, (int(pt.x * w), int(pt.y * h)), 3, color, -1)

        if label:
            hx = int(pose.nose.x * w)
            hy = max(25, int(pose.nose.y * h) - 15)
            HUD.draw_badge(
                frame,
                label,
                (hx - 15, hy),
                color,
                bg_color=(20, 20, 20),
                font_scale=0.6,
                thickness=2,
            )

    @staticmethod
    def draw_zones(frame, left_thresh: float, right_thresh: float, steer_margin: float):
        h, w, _ = frame.shape
        lx = int(left_thresh * w)
        rx = int(right_thresh * w)

        overlay = frame.copy()
        cv2.rectangle(overlay, (lx, 0), (rx, h), COLOR_NEUTRAL_BG, -1)
        cv2.addWeighted(overlay, 0.25, frame, 0.75, 0, frame)

        cv2.line(frame, (lx, 0), (lx, h), COLOR_NEUTRAL_LINE, 2, cv2.LINE_AA)
        cv2.line(frame, (rx, 0), (rx, h), COLOR_NEUTRAL_LINE, 2, cv2.LINE_AA)

        nz_mid = (lx + rx) // 2
        HUD.draw_badge(
            frame, "◄ NEUTRAL ZONE ►", (nz_mid - 65, h - 15), (220, 220, 220), bg_color=(30, 30, 30)
        )

        left_max_px = int(steer_margin * w)
        right_max_px = int((1.0 - steer_margin) * w)
        cv2.line(frame, (left_max_px, 0), (left_max_px, h), COLOR_MARGIN, 2, cv2.LINE_AA)
        cv2.line(frame, (right_max_px, 0), (right_max_px, h), COLOR_MARGIN, 2, cv2.LINE_AA)
        HUD.draw_badge(frame, "MAX LEFT", (left_max_px + 4, h - 35), COLOR_MARGIN, font_scale=0.35)
        HUD.draw_badge(frame, "MAX RIGHT", (right_max_px - 65, h - 35), COLOR_MARGIN, font_scale=0.35)

    @staticmethod
    def draw_card(
        frame,
        bbox: Optional[Tuple[int, int, int, int]],
        triggered: bool = False,
    ):
        if bbox is None:
            return

        x, y, w, h = bbox
        color = COLOR_WARN if triggered else COLOR_OK
        thick = 3 if triggered else 2
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, thick)

        label = "RESCUE CARD [ACTIVE]" if triggered else "RESCUE CARD"
        HUD.draw_badge(
            frame,
            label,
            (x, max(20, y - 6)),
            (0, 0, 0) if triggered else (255, 255, 255),
            bg_color=(0, 215, 255) if triggered else (20, 20, 20),
            border_color=color,
            font_scale=0.45,
            thickness=2 if triggered else 1,
        )

    @staticmethod
    def draw_player_thresholds(
        frame,
        shoulder: Optional[Tuple[float, float]],
        brake_active: bool,
        brake_y: float,
        jump_active: bool,
        jump_y: float,
        is_p1: bool,
        show_jump_line: bool = True,
    ):
        h, w, _ = frame.shape
        start_x = 0 if is_p1 else w // 2
        end_x = w // 2 if is_p1 else w
        prefix = "P1" if is_p1 else "P2"
        badge_x = 10 if is_p1 else (w - 110)

        # Jump line (hidden if color rescue mode is enabled)
        if show_jump_line:
            j_y_px = int(jump_y * h)
            j_color = COLOR_JUMP_ACTIVE if jump_active else COLOR_JUMP_INACTIVE
            j_thick = 3 if jump_active else 2
            cv2.line(frame, (start_x, j_y_px), (end_x, j_y_px), j_color, j_thick, cv2.LINE_AA)

            j_bg = (0, 180, 220) if jump_active else (25, 25, 25)
            j_fg = (0, 0, 0) if jump_active else j_color
            HUD.draw_badge(
                frame,
                f"▲ {prefix} JUMP",
                (badge_x, j_y_px - 6),
                j_fg,
                bg_color=j_bg,
                border_color=j_color,
                font_scale=0.42,
                thickness=2 if jump_active else 1,
            )

        # Brake line
        b_y_px = int(brake_y * h)
        b_color = COLOR_BRAKE_ACTIVE if brake_active else COLOR_BRAKE_INACTIVE
        b_thick = 3 if brake_active else 2
        cv2.line(frame, (start_x, b_y_px), (end_x, b_y_px), b_color, b_thick, cv2.LINE_AA)

        b_bg = (0, 0, 220) if brake_active else (25, 25, 25)
        b_fg = (255, 255, 255) if brake_active else b_color
        HUD.draw_badge(
            frame,
            f"▼ {prefix} BRAKE",
            (badge_x, b_y_px - 6),
            b_fg,
            bg_color=b_bg,
            border_color=b_color,
            font_scale=0.42,
            thickness=2 if brake_active else 1,
        )

        # Shoulder centroid tracking dot
        if shoulder is not None:
            sx, sy = shoulder
            center = (int(sx * w), int(sy * h))
            if brake_active:
                dot_color = COLOR_ALERT
            elif jump_active and show_jump_line:
                dot_color = COLOR_JUMP_ACTIVE
            else:
                dot_color = COLOR_P1 if is_p1 else COLOR_P2

            cv2.circle(frame, center, 9, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.circle(frame, center, 7, dot_color, -1, cv2.LINE_AA)

    @staticmethod
    def draw_telemetry(frame, gestures: GestureResult, fps: float):
        h, w, _ = frame.shape

        HUD.draw_badge(frame, f"FPS: {fps:.1f}", (20, 25), COLOR_OK, font_scale=0.55, thickness=2)

        p1_pct = int(gestures.steering.p1_power * 100)
        p2_pct = int(gestures.steering.p2_power * 100)
        HUD.draw_badge(frame, f"P1 Left: {p1_pct}%", (20, 52), COLOR_P1, font_scale=0.55, thickness=2)
        HUD.draw_badge(frame, f"P2 Right: {p2_pct}%", (w - 180, 52), COLOR_P2, font_scale=0.55, thickness=2)

        # Steering direction and intensity percentage
        if gestures.steering.direction:
            net_pct = int(gestures.steering.intensity * 100)
            if gestures.steering.direction == "LEFT":
                net_label = f"◄◄ NET: LEFT {net_pct}%"
            else:
                net_label = f"NET: RIGHT {net_pct}% ►►"
            HUD.draw_badge(frame, net_label, (w // 2 - 95, 30), COLOR_OK, font_scale=0.6, thickness=2)
        else:
            HUD.draw_badge(frame, "NET: STRAIGHT", (w // 2 - 65, 30), (180, 180, 180), font_scale=0.6, thickness=2)

        # Acceleration and Cruise Control
        if gestures.accelerate:
            HUD.draw_badge(frame, "ACCEL: ON [CRUISE]", (20, 80), COLOR_OK, font_scale=0.5, thickness=2)
        elif gestures.cruise_control and gestures.brake:
            HUD.draw_badge(frame, "ACCEL: PAUSED (BRAKE)", (20, 80), COLOR_WARN, font_scale=0.5, thickness=2)
        else:
            HUD.draw_badge(frame, "ACCEL: OFF [Raise Hand]", (20, 80), COLOR_DIM, font_scale=0.5, thickness=1)

        # Brake badge
        brake_col = COLOR_ALERT if gestures.brake else COLOR_DIM
        HUD.draw_badge(
            frame,
            "BRAKE: ACTIVE" if gestures.brake else "BRAKE",
            (20, 105),
            brake_col,
            font_scale=0.5,
            thickness=2 if gestures.brake else 1,
        )

        # Rescue badge
        if gestures.rescue_mode == "color":
            if gestures.rescue:
                rescue_label = "RESCUE [CARD]: ACTIVE"
                rescue_col = COLOR_WARN
            elif gestures.card_detected:
                rescue_label = "RESCUE [CARD]: DETECTED"
                rescue_col = COLOR_OK
            else:
                rescue_label = "RESCUE [CARD]: IDLE"
                rescue_col = COLOR_DIM
        elif gestures.rescue_mode == "jump":
            rescue_label = "RESCUE [JUMP]: ACTIVE" if gestures.rescue else "RESCUE [JUMP]: IDLE"
            rescue_col = COLOR_WARN if gestures.rescue else COLOR_DIM
        else:
            rescue_label = "RESCUE: ACTIVE" if gestures.rescue else "RESCUE [BOTH]: IDLE"
            rescue_col = COLOR_WARN if gestures.rescue else COLOR_DIM

        HUD.draw_badge(
            frame,
            rescue_label,
            (20, 130),
            rescue_col,
            font_scale=0.5,
            thickness=2 if gestures.rescue else 1,
        )

        # Rescue mode indicator badge
        mode_str = gestures.rescue_mode.upper()
        HUD.draw_badge(
            frame,
            f"RESCUE: {mode_str} ('r')",
            (w - 180, 25),
            COLOR_OK if gestures.rescue_mode == "color" else COLOR_WARN,
            font_scale=0.45,
            thickness=1,
        )

        # Calibration progress or resting status
        calib = gestures.calibration
        if calib:
            progress = calib.calib_pose_progress
            if progress > 0:
                prog_pct = int(progress * 100)
                box_w, box_h = 280, 45
                bx = (w - box_w) // 2
                by = 60
                cv2.rectangle(frame, (bx, by), (bx + box_w, by + box_h), (20, 20, 20), -1)
                cv2.rectangle(frame, (bx, by), (bx + box_w, by + box_h), (0, 255, 255), 2)
                cv2.putText(
                    frame,
                    f"CALIBRATING GESTURE: {prog_pct}%",
                    (bx + 15, by + 20),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.48,
                    (0, 255, 255),
                    1,
                    cv2.LINE_AA,
                )
                bar_x = bx + 15
                bar_y = by + 28
                bar_w = box_w - 30
                bar_h = 8
                cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (60, 60, 60), -1)
                cv2.rectangle(
                    frame,
                    (bar_x, bar_y),
                    (bar_x + int(bar_w * progress), bar_y + bar_h),
                    (0, 255, 255),
                    -1,
                )
            elif calib.cooldown_remaining > 0:
                HUD.draw_badge(
                    frame,
                    f"CALIBRATED (RESTING {calib.cooldown_remaining:.1f}s)",
                    (w // 2 - 110, 65),
                    COLOR_OK,
                    font_scale=0.45,
                )
            elif calib.status == CalibrationStatus.CALIBRATED:
                HUD.draw_badge(
                    frame, "CALIBRATED ('c' to reset)", (w // 2 - 80, 65), COLOR_OK, font_scale=0.45
                )

    @staticmethod
    def draw_sample_reticle(frame, box_size: int = 80):

        h, w = frame.shape[:2]
        cx, cy = w // 2, h // 2
        half = box_size // 2
        x1, y1 = cx - half, cy - half
        x2, y2 = cx + half, cy + half
        arm = 14
        col = (180, 180, 180)

        # Corner brackets
        cv2.line(frame, (x1, y1), (x1 + arm, y1), col, 2, cv2.LINE_AA)
        cv2.line(frame, (x1, y1), (x1, y1 + arm), col, 2, cv2.LINE_AA)
        cv2.line(frame, (x2, y1), (x2 - arm, y1), col, 2, cv2.LINE_AA)
        cv2.line(frame, (x2, y1), (x2, y1 + arm), col, 2, cv2.LINE_AA)
        cv2.line(frame, (x1, y2), (x1 + arm, y2), col, 2, cv2.LINE_AA)
        cv2.line(frame, (x1, y2), (x1, y2 - arm), col, 2, cv2.LINE_AA)
        cv2.line(frame, (x2, y2), (x2 - arm, y2), col, 2, cv2.LINE_AA)
        cv2.line(frame, (x2, y2), (x2, y2 - arm), col, 2, cv2.LINE_AA)

        HUD.draw_badge(
            frame,
            "HOLD CARD & PRESS 'S'",
            (cx - 75, y2 + 16),
            (200, 200, 200),
            bg_color=(20, 20, 20),
            font_scale=0.38,
            thickness=1,
        )

    def render(
        self,
        frame,
        p1: Optional[PlayerPose],
        p2: Optional[PlayerPose],
        gestures: GestureResult,
        fps: float,
        steer_margin: float,
    ):
        self.draw_skeleton(frame, p1, COLOR_P1, "P1")
        self.draw_skeleton(frame, p2, COLOR_P2, "P2")

        left_thresh = gestures.calibration.left_thresh if gestures.calibration else 0.29
        right_thresh = gestures.calibration.right_thresh if gestures.calibration else 0.71
        self.draw_zones(frame, left_thresh, right_thresh, steer_margin)

        show_jump_line = gestures.rescue_mode != "color"

        self.draw_player_thresholds(
            frame=frame,
            shoulder=gestures.p1_shoulder,
            brake_active=gestures.p1_brake,
            brake_y=gestures.p1_brake_y,
            jump_active=gestures.p1_jump,
            jump_y=gestures.p1_jump_y,
            is_p1=True,
            show_jump_line=show_jump_line,
        )
        self.draw_player_thresholds(
            frame=frame,
            shoulder=gestures.p2_shoulder,
            brake_active=gestures.p2_brake,
            brake_y=gestures.p2_brake_y,
            jump_active=gestures.p2_jump,
            jump_y=gestures.p2_jump_y,
            is_p1=False,
            show_jump_line=show_jump_line,
        )

        if gestures.rescue_mode == "color" and not gestures.card_detected:
            self.draw_sample_reticle(frame)

        if gestures.card_detected and gestures.card_bbox:
            self.draw_card(frame, gestures.card_bbox, triggered=gestures.rescue)

        import time
        if self.banner_message and time.time() < self.banner_expires:
            HUD.draw_badge(
                frame,
                self.banner_message,
                (frame.shape[1] // 2 - 150, 60),
                self.banner_color,
                bg_color=(15, 15, 15),
                border_color=self.banner_color,
                font_scale=0.55,
                thickness=2,
            )

        self.draw_telemetry(frame, gestures, fps)


