######################################################################################
# This python script implements a 3D face tracking which uses a webcam               #
# to achieve face detection. This face detection is done with MediaPipe:             #
#                                                                                    #
# The script then streams the 3D position through OSC                                #
#                                                                                    #
# date: December 2019 / Updated September 2026 for Collaborative STK                 #
# authors: Cedric Fleury / MCSI SuperTuxKart Collab Team                             #
# affiliation: IMT Atlantique, Lab-STICC (Brest)                                     #
#                                                                                    #
# usage: python face_tracking.py [--mode {auto,duo,solo}] [ipd]                      #
# where ipd is an optional value to tune the interpupillary distance of the          #
# tracked subject (by default, the interpupillary distance is set at 6cm).           #
######################################################################################

import sys
import os
import time
import math
import argparse
import numpy as np
from typing import Tuple, Union, Optional, List

# import oscpy for OSC streaming
from oscpy.client import OSCClient

# import opencv for image processing
import cv2

# import mediapipe for face detection
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# Import project configuration parameters
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from classes.config import (
    ANGLE_TETE_MAX,
    DEAD_ZONE_ANGLE_DEG,
    POS_Z_MIN,
    POS_Z_MAX,
    MOUTH_OPEN_THRESHOLD,
)

# Focal length in pixels
fl = 654.0

# Screen height in cm
screen_height = 21.0

# Frame dimensions
FRAME_WIDTH = 640
FRAME_HEIGHT = 360


def parse_arguments():
    parser = argparse.ArgumentParser(description="3D Multi-Face Tracking & STK Controller")
    parser.add_argument(
        "ipd",
        nargs="?",
        type=float,
        default=3.0,
        help="Demi-distance interpupillaire en cm (defaut: 3.0 cm, soit 6 cm au total)",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "duo", "solo"],
        default="auto",
        help="Mode de suivi: 'auto' (adapte 1 ou 2 visages), 'duo' (P1 tourne, P2 accelere), 'solo' (1 joueur fait tout)",
    )
    parser.add_argument("--port", type=int, default=8000, help="Port OSC de streaming (defaut: 8000)")
    parser.add_argument("--host", type=str, default="localhost", help="Hote OSC (defaut: localhost)")
    parser.add_argument("--no-gui", action="store_true", help="Desactiver la fenetre d'affichage OpenCV")
    return parser.parse_args()


def compute3DPos(ibe_x: float, ibe_y: float, rec_ipd: float, user_ipd: float = 3.0) -> Tuple[float, float, float]:
    """Convertit la position 2D (pixels) et l'ecart des yeux en coordonnees 3D (cm)."""
    z = (fl * user_ipd * 2.0) / max(1.0, rec_ipd)

    cx = FRAME_WIDTH / 2.0
    cy = FRAME_HEIGHT / 2.0

    x = ((ibe_x - cx) * z) / fl
    y = ((ibe_y - cy) * z) / fl

    if screen_height > 0:
        y = y - (screen_height / 2.0)

    return (x, y, z)


def _normalized_to_pixel_coordinates(
    normalized_x: float, normalized_y: float, image_width: int, image_height: int
) -> Union[None, Tuple[int, int]]:
    """Converts normalized value pair to pixel coordinates."""
    def is_valid_normalized_value(value: float) -> bool:
        return (value > 0 or math.isclose(0, value)) and (value < 1 or math.isclose(1, value))

    if not (is_valid_normalized_value(normalized_x) and is_valid_normalized_value(normalized_y)):
        return None
    x_px = min(math.floor(normalized_x * image_width), image_width - 1)
    y_px = min(math.floor(normalized_y * image_height), image_height - 1)
    return x_px, y_px


class FaceData:
    """Structure contenant toutes les metriques extraites pour un visage detecte."""

    def __init__(self, det, width: int, height: int, user_ipd: float = 3.0):
        self.bbox = det.bounding_box
        self.origin_x = self.bbox.origin_x
        self.origin_y = self.bbox.origin_y
        self.width = self.bbox.width
        self.height = self.bbox.height
        self.center_x_px = self.origin_x + self.width // 2
        self.center_y_px = self.origin_y + self.height // 2

        # Keypoints: 0=oeil droit, 1=oeil gauche, 2=nez, 3=bouche
        kps = det.keypoints
        self.eye1_px = _normalized_to_pixel_coordinates(kps[0].x, kps[0].y, width, height) if len(kps) > 0 else None
        self.eye2_px = _normalized_to_pixel_coordinates(kps[1].x, kps[1].y, width, height) if len(kps) > 1 else None
        self.nose_px = _normalized_to_pixel_coordinates(kps[2].x, kps[2].y, width, height) if len(kps) > 2 else None
        self.mouth_px = _normalized_to_pixel_coordinates(kps[3].x, kps[3].y, width, height) if len(kps) > 3 else None

        if self.eye1_px and self.eye2_px:
            self.ipd_px = math.hypot(self.eye2_px[0] - self.eye1_px[0], self.eye2_px[1] - self.eye1_px[1])
            self.eye_center_x = (self.eye1_px[0] + self.eye2_px[0]) / 2.0
            self.eye_center_y = (self.eye1_px[1] + self.eye2_px[1]) / 2.0
            self.pos_x, self.pos_y, self.pos_z = compute3DPos(
                self.eye_center_x, self.eye_center_y, max(1.0, self.ipd_px), user_ipd
            )
            self.angle = math.degrees(
                math.atan2(self.eye2_px[1] - self.eye1_px[1], self.eye2_px[0] - self.eye1_px[0])
            )
        else:
            self.ipd_px = 0.0
            self.pos_x, self.pos_y, self.pos_z = 0.0, 0.0, 85.0
            self.angle = 0.0

        # Detection ouverture de la bouche pour le sauvetage (Rescue)
        if self.nose_px and self.mouth_px and self.ipd_px > 0:
            mouth_dist = math.hypot(self.mouth_px[0] - self.nose_px[0], self.mouth_px[1] - self.nose_px[1])
            self.mouth_ratio = mouth_dist / self.ipd_px
        else:
            self.mouth_ratio = 0.0

        self.mouth_open = self.mouth_ratio >= MOUTH_OPEN_THRESHOLD

    @property
    def is_valid(self) -> bool:
        return self.eye1_px is not None and self.eye2_px is not None and self.ipd_px > 10.0


class TrackingResults:
    def __init__(self):
        self.tracking_results = None

    def get_result(self, result: vision.FaceDetectorResult, output_image: mp.Image, timestamp_ms: int):
        self.tracking_results = result


def draw_hud(
    frame: np.ndarray,
    p1: Optional[FaceData],
    p2: Optional[FaceData],
    active_mode: str,
    is_rescue: bool,
    fps: float,
):
    """Dessine le HUD moderne avec zone de direction (P1) et zone de traction (P2)."""
    h, w, _ = frame.shape

    # 1. En-tete superieur (Mode & FPS)
    cv2.rectangle(frame, (0, 0), (w, 32), (18, 18, 18), -1)
    mode_text = "MODE: DUO (P1: Direction | P2: Vitesse)" if active_mode == "duo" else "MODE: SOLO (Direction + Vitesse)"
    mode_color = (0, 255, 200) if active_mode == "duo" else (0, 255, 120)
    cv2.putText(frame, mode_text, (15, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, mode_color, 2, cv2.LINE_AA)
    cv2.putText(frame, f"FPS: {fps:.0f}", (w - 95, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1, cv2.LINE_AA)

    # 2. Ligne de separation centrale en mode Duo
    if active_mode == "duo":
        for y_dot in range(35, h - 35, 16):
            cv2.line(frame, (w // 2, y_dot), (w // 2, y_dot + 8), (70, 70, 70), 1, cv2.LINE_AA)

    # 3. Affichage Joueur 1 (Direction)
    if p1 is not None and p1.is_valid:
        # Bounding box cyan
        bx, by, bw, bh = p1.origin_x, p1.origin_y, p1.width, p1.height
        cv2.rectangle(frame, (bx, by), (bx + bw, by + bh), (255, 200, 0), 2)
        cv2.putText(frame, "P1: DIRECTION" if active_mode == "duo" else "SOLO", (bx, max(45, by - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 200, 0), 1, cv2.LINE_AA)

        # Yeux et inclinaison
        cv2.circle(frame, p1.eye1_px, 3, (0, 255, 255), -1)
        cv2.circle(frame, p1.eye2_px, 3, (0, 255, 255), -1)
        cv2.line(frame, p1.eye1_px, p1.eye2_px, (0, 255, 200), 2, cv2.LINE_AA)

        # Etat de direction
        if p1.angle < -DEAD_ZONE_ANGLE_DEG:
            steer_lbl = f"<-- GAUCHE ({p1.angle:+.1f} deg)"
            steer_clr = (0, 255, 120)
        elif p1.angle > DEAD_ZONE_ANGLE_DEG:
            steer_lbl = f"DROITE --> ({p1.angle:+.1f} deg)"
            steer_clr = (0, 255, 120)
        else:
            steer_lbl = f"NEUTRE ({p1.angle:+.1f} deg)"
            steer_clr = (180, 180, 180)

        cv2.putText(frame, steer_lbl, (bx, by + bh + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, steer_clr, 2, cv2.LINE_AA)

    # 4. Affichage Joueur 2 (Traction) en mode Duo
    if active_mode == "duo" and p2 is not None and p2.is_valid:
        bx, by, bw, bh = p2.origin_x, p2.origin_y, p2.width, p2.height
        cv2.rectangle(frame, (bx, by), (bx + bw, by + bh), (0, 165, 255), 2)
        cv2.putText(frame, "P2: VITESSE", (bx, max(45, by - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 165, 255), 1, cv2.LINE_AA)

        # Points yeux et nez/bouche
        cv2.circle(frame, p2.eye1_px, 3, (0, 200, 255), -1)
        cv2.circle(frame, p2.eye2_px, 3, (0, 200, 255), -1)
        if p2.nose_px:
            cv2.circle(frame, p2.nose_px, 3, (255, 255, 0), -1)
        if p2.mouth_px:
            m_clr = (0, 0, 255) if p2.mouth_open else (0, 255, 0)
            cv2.circle(frame, p2.mouth_px, 4 if p2.mouth_open else 2, m_clr, -1)

        # Etat de vitesse
        if p2.pos_z < (POS_Z_MIN + 5.0):
            spd_lbl = f"ACCELERER ^ ({p2.pos_z:.0f} cm)"
            spd_clr = (0, 255, 120)
        elif p2.pos_z > (POS_Z_MAX - 5.0):
            spd_lbl = f"FREINER v ({p2.pos_z:.0f} cm)"
            spd_clr = (0, 0, 255)
        else:
            spd_lbl = f"ROUE LIBRE ({p2.pos_z:.0f} cm)"
            spd_clr = (180, 180, 180)

        cv2.putText(frame, spd_lbl, (bx, by + bh + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, spd_clr, 2, cv2.LINE_AA)

    # 5. Affichage distance en mode Solo
    elif active_mode == "solo" and p1 is not None and p1.is_valid:
        if p1.pos_z < (POS_Z_MIN + 5.0):
            spd_lbl = f"ACCEL ({p1.pos_z:.0f} cm)"
            spd_clr = (0, 255, 120)
        elif p1.pos_z > (POS_Z_MAX - 5.0):
            spd_lbl = f"FREIN ({p1.pos_z:.0f} cm)"
            spd_clr = (0, 0, 255)
        else:
            spd_lbl = f"COAST ({p1.pos_z:.0f} cm)"
            spd_clr = (180, 180, 180)

        cv2.putText(frame, spd_lbl, (p1.origin_x, p1.origin_y + p1.height + 36),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, spd_clr, 2, cv2.LINE_AA)

    # 6. Banniere Sauvetage (Rescue)
    if is_rescue:
        banner_y = h // 2 - 20
        cv2.rectangle(frame, (w // 2 - 190, banner_y), (w // 2 + 190, banner_y + 45), (0, 0, 200), -1)
        cv2.rectangle(frame, (w // 2 - 190, banner_y), (w // 2 + 190, banner_y + 45), (0, 255, 255), 2)
        cv2.putText(frame, "RESCUE ACTIVE ! (Bouche)", (w // 2 - 170, banner_y + 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)

    # 7. Barre d'aide inferieure
    cv2.putText(
        frame,
        "ESC: Quitter | Incliner tete: Tourner | Avancer/Reculer: Vitesse | Ouvrir bouche: Rescue",
        (15, h - 10),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.36,
        (160, 160, 160),
        1,
        cv2.LINE_AA,
    )


def runtracking():
    args = parse_arguments()
    user_ipd = args.ipd
    mode = args.mode
    osc_host = args.host
    osc_port = args.port
    no_gui = args.no_gui

    print("\n" + "=" * 65)
    print("  MCSI SuperTuxKart - Face Tracking Collaboratif & Solo")
    print(f"  Mode configure : {mode.upper()}")
    print(f"  Distance interpupillaire : {user_ipd * 2.0:.1f} cm (demi-ecart: {user_ipd} cm)")
    print(f"  Streaming OSC vers {osc_host}:{osc_port}")
    print("=" * 65 + "\n")

    clientOSC = OSCClient(osc_host, osc_port)

    # Initialisation camera
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    if not cap.isOpened():
        print("Erreur : Impossible d'ouvrir le flux webcam.")
        return

    # Initialisation detecteur MediaPipe
    res = TrackingResults()
    model_asset_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blaze_face_short_range.tflite")
    base_options = python.BaseOptions(model_asset_path=model_asset_path)
    options = vision.FaceDetectorOptions(
        base_options=base_options,
        running_mode=vision.RunningMode.LIVE_STREAM,
        result_callback=res.get_result,
    )
    detector = vision.FaceDetector.create_from_options(options)

    first_time = time.time() * 1000.0
    prev_time = time.time()
    fps = 30.0

    print("Tracking demarre ! Appuyez sur ESC pour quitter...\n")

    try:
        while True:
            ret, img_bgr = cap.read()
            if not ret or img_bgr is None:
                time.sleep(0.01)
                continue

            now = time.time()
            dt = now - prev_time
            prev_time = now
            if dt > 0:
                fps = 0.9 * fps + 0.1 * (1.0 / dt)

            frame_timestamp_ms = int(now * 1000 - first_time)

            # Conversion MediaPipe
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)
            detector.detect_async(mp_image, frame_timestamp_ms)

            # Traitement des visages detectes
            valid_faces: List[FaceData] = []
            if res.tracking_results is not None and res.tracking_results.detections:
                for det in res.tracking_results.detections:
                    face = FaceData(det, FRAME_WIDTH, FRAME_HEIGHT, user_ipd)
                    if face.is_valid:
                        valid_faces.append(face)

            # Tri des visages horizontalement (gauche vers droite)
            valid_faces.sort(key=lambda f: f.center_x_px)

            # Determination du mode (Duo vs Solo)
            p1: Optional[FaceData] = None
            p2: Optional[FaceData] = None
            is_rescue = False

            if mode == "duo" or (mode == "auto" and len(valid_faces) >= 2):
                active_mode = "duo"
                if len(valid_faces) >= 2:
                    p1 = valid_faces[0]  # Visage gauche : Joueur 1 (Direction)
                    p2 = valid_faces[1]  # Visage droit : Joueur 2 (Vitesse)
                elif len(valid_faces) == 1:
                    p1 = valid_faces[0]  # Un seul visage present en attente du second
            else:
                active_mode = "solo"
                if len(valid_faces) >= 1:
                    p1 = valid_faces[0]  # Joueur unique : fait tout

            # Sauvetage si la bouche est ouverte
            if p1 and p1.mouth_open:
                is_rescue = True
            if p2 and p2.mouth_open:
                is_rescue = True

            # Envoi des messages OSC
            if active_mode == "duo" and p1 and p2:
                # Joueur 1 : Direction (yeux + tete)
                clientOSC.send_message(b"/tracker/p1/eyes1/pos_xyz", [p1.eye1_px[0], p1.eye1_px[1]])
                clientOSC.send_message(b"/tracker/p1/eyes2/pos_xyz", [p1.eye2_px[0], p1.eye2_px[1]])
                clientOSC.send_message(b"/tracker/p1/head/pos_xyz", [p1.pos_x, p1.pos_y, p1.pos_z])

                # Joueur 2 : Vitesse (tete distance z + yeux)
                clientOSC.send_message(b"/tracker/p2/head/pos_xyz", [p2.pos_x, p2.pos_y, p2.pos_z])
                clientOSC.send_message(b"/tracker/p2/eyes1/pos_xyz", [p2.eye1_px[0], p2.eye1_px[1]])
                clientOSC.send_message(b"/tracker/p2/eyes2/pos_xyz", [p2.eye2_px[0], p2.eye2_px[1]])

                # Messages de retro-compatibilite directe
                clientOSC.send_message(b"/tracker/eyes1/pos_xyz", [p1.eye1_px[0], p1.eye1_px[1]])
                clientOSC.send_message(b"/tracker/eyes2/pos_xyz", [p1.eye2_px[0], p1.eye2_px[1]])
                clientOSC.send_message(b"/tracker/head/pos_xyz", [p2.pos_x, p2.pos_y, p2.pos_z])

            elif p1 is not None:
                # Mode Solo (ou P1 seul)
                clientOSC.send_message(b"/tracker/eyes1/pos_xyz", [p1.eye1_px[0], p1.eye1_px[1]])
                clientOSC.send_message(b"/tracker/eyes2/pos_xyz", [p1.eye2_px[0], p1.eye2_px[1]])
                clientOSC.send_message(b"/tracker/head/pos_xyz", [p1.pos_x, p1.pos_y, p1.pos_z])

                clientOSC.send_message(b"/tracker/p1/eyes1/pos_xyz", [p1.eye1_px[0], p1.eye1_px[1]])
                clientOSC.send_message(b"/tracker/p1/eyes2/pos_xyz", [p1.eye2_px[0], p1.eye2_px[1]])
                clientOSC.send_message(b"/tracker/p1/head/pos_xyz", [p1.pos_x, p1.pos_y, p1.pos_z])
                clientOSC.send_message(b"/tracker/p2/head/pos_xyz", [p1.pos_x, p1.pos_y, p1.pos_z])

            # Sauvetage OSC
            clientOSC.send_message(b"/tracker/rescue", [1 if is_rescue else 0])

            # Affichage graphique
            if not no_gui:
                draw_hud(img_bgr, p1, p2, active_mode, is_rescue, fps)
                cv2.imshow("SuperTuxKart - Face Tracking Collaboratif", img_bgr)

                key = cv2.waitKey(1) & 0xFF
                if key == 27:  # ESC
                    break

    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("\nFace tracking arrete.")


if __name__ == "__main__":
    runtracking()