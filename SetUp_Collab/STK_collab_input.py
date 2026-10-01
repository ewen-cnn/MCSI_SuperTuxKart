###############################################################################
## Global libs
import math
import socket
import sys
import threading
import time
import serial
import os
import subprocess
import argparse
from serial.tools import list_ports       

from classes.outils import *
from classes.config import *
from classes.sensorStates import *
from classes.KartState import *
from classes.actionDetector import *
from classes.config import *
from collections import deque
from STK_Sender import *
from oscpy.server import OSCThreadServer

import math 

def main():
    parser = argparse.ArgumentParser(description="STK Collab Input Controller")
    parser.add_argument('-d', '--debug', action='store_true', help="Activer le mode debug")
    parser.add_argument(
        '--steering',
        choices=['face', 'position'],
        default='face',
        help="Mode de direction : 'face' (inclinaison de la tete via angle des yeux, defaut) ou 'position' (position horizontale cx)",
    )
    parser.add_argument(
        '--mode',
        choices=['auto', 'duo', 'solo'],
        default='auto',
        help="Mode de jeu : 'auto' (1 ou 2 joueurs selon visages), 'duo' (P1 tourne, P2 vitesse), 'solo' (1 joueur fait tout)",
    )
    parser.add_argument(
        '--color',
        choices=['red', 'green', 'blue', 'yellow', 'orange', 'custom', 'off'],
        default=COLOR_PRESET,
        help="Couleur de l'objet/carte pour lancer les objets ('FIRE') (defaut: red, ou 'off' pour desactiver)",
    )
    args = parser.parse_args()
    debug = args.debug
    steering_mode = args.steering
    play_mode = args.mode
    color_mode = args.color

    sender = STKSender(STK_SERVER_ADDRESS, debug=debug)
    kart = KartState(sender, debug=debug)
    gyr = Vector3State()
    shake_detector = ShakeDetector()
    camera = CameraState()
    eye1 = EyesValues()
    eye2 = EyesValues()
    p1_eye1 = EyesValues()
    p1_eye2 = EyesValues()
    p1_camera = CameraState()
    p2_camera = CameraState()
    fire_event = TriggerState(cooldown=COLOR_COOLDOWN_SECONDS)       # rempli par le thread OSC
    fire_key = HoldCommand(sender, 'P_FIRE', 'R_FIRE', FIRE_HOLD) 
    rescue_button = HoldCommand(sender, 'P_RESCUE', 'R_RESCUE', RESCUE_HOLD)
    z_neutral_state = FloatState(default=DEFAULT_Z_NEUTRAL)
    osc = OSCThreadServer()
    steering_pwm = ContinuousCommand()
    
    osc.listen(address=OSC_LISTEN_IP, port=OSC_LISTEN_PORT, default=True)

    bind_all(
        osc,
        gyr,
        eye1,
        eye2,
        camera,
        p1_eye1=p1_eye1,
        p1_eye2=p1_eye2,
        p1_camera=p1_camera,
        p2_camera=p2_camera,
        fire_trigger=fire_event,
        z_neutral=z_neutral_state,
    )
    print()
    color_tag = f", Objet: {color_mode.upper()}" if color_mode != "off" else ""
    print(f'STK client v2 started (Mode jeu: {play_mode.upper()}, Direction: {steering_mode.upper()}{color_tag})')

    # Lance le serveur et le face tracking avec compatibilite multi-plateforme.
    ici = os.path.dirname(os.path.abspath(__file__))
    extra_flags = {}
    if sys.platform == 'win32' and hasattr(subprocess, 'CREATE_NEW_CONSOLE'):
        extra_flags['creationflags'] = subprocess.CREATE_NEW_CONSOLE

    serveur = None
    # Verifie si le serveur d'entrees est deja actif sur le port 6006 (ex: lance par launch_game.sh)
    test_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    serveur_deja_actif = False
    try:
        test_sock.bind(STK_SERVER_ADDRESS)
        test_sock.close()
    except OSError:
        serveur_deja_actif = True

    if not serveur_deja_actif:
        cmd_serveur = [sys.executable, os.path.join(ici, 'STK_input_server.py')]
        if debug:
            cmd_serveur.append('-d')
        serveur = subprocess.Popen(cmd_serveur, cwd=ici, **extra_flags)
        time.sleep(1.0)          # laisse le serveur prendre le port 6006
    else:
        print("Serveur STK d'entrees deja actif sur le port 6006.")

    cmd_tracking = [
        sys.executable,
        os.path.join(ici, 'face_tracking.py'),
        '--mode', play_mode,
        '--steering', steering_mode,
        '--color', color_mode,
    ]
    tracking = subprocess.Popen(cmd_tracking, cwd=ici, **extra_flags)
    
    muscle_contracte = False
    angle_repos = None          # neutre mesure au demarrage
    debut_calib = None
    echantillons = []
    nitro_jusqua = None

    # --- Port serie : optionnel ---
    serialPort = None
    port_detecte = None
    for p in list_ports.comports():
        if p.vid == 0x2341:                 # identifiant fabricant Arduino
            port_detecte = p.device
            break

    if port_detecte is None:
        print(YELLOW + "Aucune carte Arduino detectee : on continue sans." + WHITE)
    else:
        try:
            serialPort = serial.Serial(port_detecte, BAUDRATE, timeout=0.01)
            serialPort.reset_input_buffer()
            print("Lecture de", port_detecte)
        except serial.SerialException as e:
            print(YELLOW + "Port {} inutilisable ({}) : on continue sans.".format(
                port_detecte, e) + WHITE)
            serialPort = None
    ############# DEBUT DE LA BOUCLE ##################    
    try:
        while True:
            now = time.time()

            # --- 1. Ce qui ne depend pas du port serie ----------------
            if nitro_jusqua and now >= nitro_jusqua:
                kart.set_nitro(False)
                nitro_jusqua = None

            # --- 0. Lancer d'objet (FIRE) : carte / objet colore detecte ---
            if fire_event.consume():
                fire_key.trigger(now)
            fire_key.update(now)          # à chaque tour, sinon la touche ne se relâche jamais

            # dans le finally, à côté de kart.release_all()
            fire_key.release_now()

            # --- 1. Sauvetage (Rescue) : secousse gyro (carte Arduino) ---
            gx, gy, gz, gage = gyr.snapshot()
            if shake_detector.updategyr(gx, now):
                rescue_button.trigger(now)
                if debug:
                    print(GREEN + '\tsecousse -> RESCUE' + WHITE)
            rescue_button.update(now)
            
                

            # --- 2. Resolution du mode actif (Duo vs Solo) ------------------
            p1_e1x, p1_e1y, p1_age1 = p1_eye1.snapshot()
            p1_e2x, p1_e2y, p1_age2 = p1_eye2.snapshot()
            p2_cx, p2_cy, p2_cz, p2_cage = p2_camera.snapshot()

            is_duo_actif = (play_mode == 'duo') or (
                play_mode == 'auto' and p2_cz is not None and p2_cage <= SENSOR_TIMEOUT
            )

            # --- 3. Direction : Joueur 1 en Duo, ou Joueur Solo -------------
            if steering_mode == 'face':
                if is_duo_actif and p1_e1x is not None and max(p1_age1, p1_age2) <= SENSOR_TIMEOUT:
                    e_x1, e_y1 = p1_e1x, p1_e1y
                    e_x2, e_y2 = p1_e2x, p1_e2y
                    yeux_ok = True
                else:
                    e_x1, e_y1, age1 = eye1.snapshot()
                    e_x2, e_y2, age2 = eye2.snapshot()
                    yeux_ok = (e_x1 is not None and e_x2 is not None
                                and max(age1, age2) <= SENSOR_TIMEOUT)

                if yeux_ok:
                    angle = math.degrees(math.atan2(e_y2 - e_y1, e_x2 - e_x1))
                    if INVERT_TETE:
                        angle = -angle
                    if angle_repos is None:
                        # Calibration : 2 s de tete immobile pour mesurer le neutre.
                        if debut_calib is None:
                            debut_calib = now
                            role_str = "Joueur 1 (Direction)" if is_duo_actif else "Joueur Solo"
                            print(f"Calibration : {role_str}, garde la tete droite 2 secondes...")
                        echantillons.append(angle)
                        if now - debut_calib >= 2.0 and echantillons:
                            angle_repos = sum(echantillons) / len(echantillons)
                            print("Angle de repos calibre : {:+.1f} deg".format(angle_repos))
                        kart.set_steering('NONE')
                    else:
                        nx = normalize(angle - angle_repos, -ANGLE_TETE_MAX, ANGLE_TETE_MAX)
                        direction = zone(nx, DEAD_ZONE_X_FACE, 'LEFT', 'RIGHT')
                        niveau = intensity(nx, DEAD_ZONE_X_FACE) ** EXPO
                        if steering_pwm.pressed(niveau, now):
                            kart.set_steering(direction)
                        else:
                            kart.set_steering('NONE')
                else:
                    kart.set_steering('NONE')      # visage perdu : on relache
            else:
                # Mode position : deplacement horizontal du visage par rapport aux lignes de seuils
                if is_duo_actif:
                    left_thresh_ratio = DUO_P1_LEFT_THRESHOLD
                    right_thresh_ratio = DUO_P1_RIGHT_THRESHOLD
                    e1x, e1y, a1 = p1_e1x, p1_e1y, p1_age1
                    e2x, e2y, a2 = p1_e2x, p1_e2y, p1_age2
                    c_x, c_y, c_z, c_age = p1_camera.snapshot()
                else:
                    left_thresh_ratio = SOLO_LEFT_THRESHOLD
                    right_thresh_ratio = SOLO_RIGHT_THRESHOLD
                    e1x, e1y, a1 = eye1.snapshot()
                    e2x, e2y, a2 = eye2.snapshot()
                    c_x, c_y, c_z, c_age = camera.snapshot()

                left_thresh_px = left_thresh_ratio * FRAME_WIDTH
                right_thresh_px = right_thresh_ratio * FRAME_WIDTH

                head_x = None
                if e1x is not None and e2x is not None and max(a1, a2) <= SENSOR_TIMEOUT:
                    head_x = (e1x + e2x) / 2.0
                elif c_x is not None and c_age <= SENSOR_TIMEOUT and c_z is not None and c_z > 0:
                    head_x = (FRAME_WIDTH / 2.0) + (c_x * 654.0 / c_z)

                if head_x is not None:
                    if head_x < left_thresh_px:
                        delta = left_thresh_px - head_x
                        niveau = min(1.0, max(0.0, delta / max(1.0, TURN_SPAN_PX))) ** EXPO
                        if steering_pwm.pressed(niveau, now):
                            kart.set_steering('LEFT')
                        else:
                            kart.set_steering('NONE')
                    elif head_x > right_thresh_px:
                        delta = head_x - right_thresh_px
                        niveau = min(1.0, max(0.0, delta / max(1.0, TURN_SPAN_PX))) ** EXPO
                        if steering_pwm.pressed(niveau, now):
                            kart.set_steering('RIGHT')
                        else:
                            kart.set_steering('NONE')
                    else:
                        kart.set_steering('NONE')
                else:
                    kart.set_steering('NONE')
                
            # --- 4. Traction : Joueur 2 en Duo, ou Joueur Solo --------------
            if is_duo_actif and p2_cz is not None and p2_cage <= SENSOR_TIMEOUT:
                cz = p2_cz
                cage = p2_cage
            else:
                cx, cy, cz, cage = camera.snapshot()

            if cz is not None and cage <= SENSOR_TIMEOUT:
                current_zn, _ = z_neutral_state.snapshot()
                delta_z = cz - current_zn
                # Se rapprocher (delta_z negatif < -DEAD_ZONE_Z_CM) -> on accelere
                # S'eloigner (delta_z positif > +DEAD_ZONE_Z_CM) -> on freine
                if delta_z < -DEAD_ZONE_Z_CM:
                    kart.set_throttle('ACCELERATE')
                elif delta_z > DEAD_ZONE_Z_CM:
                    kart.set_throttle('BRAKE')
                else:
                    kart.set_throttle('NONE')
            else:
                kart.set_throttle('NONE')

            # --- 4. Lignes de l'Arduino, sans bloquer le reste ---------
            if serialPort is not None:
                ligne = serialPort.readline()
                if ligne.endswith(b'\n'):
                    nom = ligne.decode('utf-8', errors='replace').strip()
                    if nom == 'vibrationSensor':
                        kart.set_nitro(True)
                        nitro_jusqua = now + 0.15
                    elif nom == 'Contraction':
                        muscle_contracte = not muscle_contracte
                        kart.set_skidding(muscle_contracte)

            time.sleep(1.0 / LOOP_HZ)

    except KeyboardInterrupt:
        pass
    finally:
        kart.release_all()
        osc.stop()
        if serialPort is not None:
            serialPort.close()
        if serveur is not None:
            serveur.terminate()
        if tracking is not None:
            tracking.terminate()
        print()
        print('STK collab input stopped')

if __name__ == '__main__':
    main()
