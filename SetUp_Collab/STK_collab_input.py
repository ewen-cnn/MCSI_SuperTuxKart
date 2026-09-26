###############################################################################
## Global libs
import socket
import sys
import threading
import time
import serial
import os
import subprocess

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

DEAD_ZONE_X = 0.20
DEAD_ZONE_Y = 0.20
DEAD_ZONE_Z = 50

POS_X_MIN, POS_X_MAX = -23.0 , 23.0

CONTINUOUS_PERIOD = 0.05   # duree d'un cycle pressed + released (s)
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
    osc = OSCThreadServer()
    steering_pwm = ContinuousCommand()
    
    osc.listen(address=OSC_LISTEN_IP, port=OSC_LISTEN_PORT, default=True)

    bind_all(osc, gyr, camera)
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
    nitro_jusqua = None
    skid_started_at = 0.0
    skid_direction = 'NONE'

    with serial.Serial(SERIAL_PORT, BAUDRATE, timeout=0.01) as serialPort:
        serialPort.reset_input_buffer()
        print("Lecture de", SERIAL_PORT)

        try:
            while True:
                now = time.time()
                
                # Direction du kart
                cx, cy, cz, gage = camera.snapshot()
            
                nx = normalize(cx, POS_X_MIN, POS_X_MAX)

                                # --- La direction est dosee, pas tout ou rien ---------
                direction = zone(-nx, DEAD_ZONE_X, 'LEFT', 'RIGHT')
               # niveau = intensity(nx, DEAD_ZONE_X)

                
                if direction == 'LEFT':
                    kart.set_throttle('ACCELERATE')
                    kart.set_steering(direction)

                elif direction == 'RIGHT':
                    kart.set_throttle('ACCELERATE')
                    kart.set_steering(direction)

                else:
                    None

                ligne = serialPort.readline()
                if not ligne.endswith(b'\n'):
                    continue

                nom = ligne.decode('utf-8', errors='replace').strip()

                if nom == 'vibrationSensor':
                    kart.set_nitro(True)
                    nitro_jusqua = time.time() + 0.15      # impulsion

                elif nom == 'Contraction':
                    if not muscle_contracte:
                        muscle_contracte = True
                        kart.set_skidding(True)
                    elif muscle_contracte:
                        muscle_contracte = False
                        kart.set_skidding(False)

                skid = muscle_contracte and nx > 0.25
                if skid and not kart.skidding_on:
                    skid_started_at = now
                    
                # Fin de l'impulsion nitro
                if nitro_jusqua and now >= nitro_jusqua:
                    kart.set_nitro(False)
                    nitro_jusqua = None                

                # Secousse du telephone -> sauvetage, evaluee a CHAQUE tour
                gx, gy, gz, gage = gyr.snapshot()
                if gx is not None and gage <= SENSOR_TIMEOUT:
                    if shake_detector.updategyr(gx, now):
                        kart.rescue()

                kart.set_throttle(zone(cz, DEAD_ZONE_Z, 'BRAKE', 'ACCELERATE'))
                
                time.sleep(1 / 120)

        except KeyboardInterrupt:
            pass
        finally:
            kart.release_all()
            osc.stop()
            serveur.terminate()         
            tracking.terminate()
            print()
            print('STK collab input stopped')

if __name__ == '__main__':
    main()
