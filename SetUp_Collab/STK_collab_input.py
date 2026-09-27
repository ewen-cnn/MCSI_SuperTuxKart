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
from serial.tools import list_ports       

from classes.sensorStates import *
from classes.KartState import *
from classes.actionDetector import *
from classes.config import *
from collections import deque
from STK_Sender import *
from oscpy.server import OSCThreadServer

###############################################################################
## Global vars
GREEN   = '\033[92m'
WHITE   = '\x1b[0m'
BLUE    = '\033[94m'
YELLOW  = '\033[93m'
RED     = '\033[91m'

# --- Reseau -----------------------------------------------------------------
STK_SERVER_ADDRESS = ('localhost', 6006)    # STK_input_server.py
OSC_LISTEN_IP      = '0.0.0.0'              # 0.0.0.0 = toutes les interfaces
OSC_LISTEN_PORT    = 8000                   # port a saisir dans MultiSense Osc

SERIAL_PORT = 'COM6'                  # port serie a saisir dans MultiSense Serial
BAUDRATE= 115200
TIMEOUT=0.1

CAPTEURS = { 'vibrationSensor', 'MuscleSensor' }
SEUIL_CONTRACTION = 40      # a regler apres mesure
SEUIL_RELACHEMENT = 20      # plus bas que le precedent : hysteresis
SENSOR_TIMEOUT = 0.50       # sans message d'un capteur -> capteur eteint

ANGLE_TETE_MAX = 20.0      # degres d'inclinaison pour braquer a fond
EXPO           = 2.0       # 1.0 = lineaire ; 2.0 = doux au centre, franc aux extremes
INVERT_TETE    = False     # a basculer si le kart tourne a l'envers

DEAD_ZONE_X = 10.0 / ANGLE_TETE_MAX
DEAD_ZONE_Y = 0.20
DEAD_ZONE_Z = 0.25

POS_X_MIN, POS_X_MAX = -23.0 , 23.0
POS_Y_MIN, POS_Y_MAX = -23.0 , 23.0
POS_Z_MIN, POS_Z_MAX = 80.0, 100.0    # cm : a mesurer avec --calib

SKID_KICKOFF = 0.15 
SKID_INTO_MAX = 0.7     # braquage maxi DANS le sens du virage pendant la glisse
LOOP_HZ = 120      

def main():
    debug = '-d' in sys.argv or '--debug' in sys.argv

    sender = STKSender(STK_SERVER_ADDRESS, debug=debug)
    kart = KartState(sender, debug=debug)
    gyr = Vector3State()
    shake_detector = ShakeDetector()
    camera = CameraState()
    eye1 = EyesValues()
    eye2 = EyesValues()
    osc = OSCThreadServer()
    steering_pwm = ContinuousCommand()
    
    osc.listen(address=OSC_LISTEN_IP, port=OSC_LISTEN_PORT, default=True)

    bind_all(osc, gyr, eye1, eye2, camera)
    print()
    print('STK client v2 started ', end='')

    # Lance le serveur et le face tracking, chacun dans sa propre console.
    ici = os.path.dirname(os.path.abspath(__file__))
    serveur = subprocess.Popen(
        [sys.executable, os.path.join(ici, 'STK_input_server.py'), '-d'],
        cwd=ici, creationflags=subprocess.CREATE_NEW_CONSOLE)
    time.sleep(1.0)          # laisse le serveur prendre le port 6006
    tracking = subprocess.Popen(
        [sys.executable, os.path.join(ici, 'face_tracking.py')],
        cwd=ici, creationflags=subprocess.CREATE_NEW_CONSOLE)
    
    muscle_contracte = False
    angle_repos = None          # neutre mesure au demarrage
    debut_calib = None
    echantillons = []
    nitro_jusqua = None
    skid_started_at = 0.0
    skid_direction = 'NONE'

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

            gx, gy, gz, gage = gyr.snapshot()
            if gx is not None and gage <= SENSOR_TIMEOUT:
                if shake_detector.updategyr(gx, now):
                    kart.rescue()

            # --- 2. Direction : angle de la droite entre les deux yeux --
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
                        print("Calibration : garde la tete droite 2 secondes...")
                    echantillons.append(angle)
                    if now - debut_calib >= 2.0 and echantillons:
                        angle_repos = sum(echantillons) / len(echantillons)
                        print("Angle de repos : {:+.1f} deg".format(angle_repos))
                    kart.set_steering('NONE')
                else:
                    nx = normalize(angle - angle_repos, -ANGLE_TETE_MAX, ANGLE_TETE_MAX)
                    direction = zone(-nx, DEAD_ZONE_X, 'LEFT', 'RIGHT')
                    niveau = intensity(-nx, DEAD_ZONE_X) ** EXPO
                    if steering_pwm.pressed(niveau, now):
                        kart.set_steering(direction)
                    else:
                        kart.set_steering('NONE')
            else:
                kart.set_steering('NONE')      # visage perdu : on relache
                
            # --- 3. Traction : distance de la tete a la camera ---------
            cx, cy, cz, cage = camera.snapshot()
            if cz is not None and cage <= SENSOR_TIMEOUT:
                nz = normalize(cz, POS_Z_MIN, POS_Z_MAX)
                # se rapprocher (cz petit) -> nz vaut -1 -> on accelere
                kart.set_throttle(zone(-nz, DEAD_ZONE_Z, 'BRAKE', 'ACCELERATE'))
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
        serveur.terminate()
        tracking.terminate()
        print()
        print('STK collab input stopped')

if __name__ == '__main__':
    main()
