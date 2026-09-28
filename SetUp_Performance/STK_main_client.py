###############################################################################
## Global libs
import math
import socket
import sys
import threading
import time
import subprocess
import os

from classes.Config import *
from classes.Outils import *
from collections import deque

from oscpy.server import OSCThreadServer

from classes.SensorState import *
from classes.KartState import *
from classes.ActionDetector import *


###############################################################################
################# Envoi des commandes vers STK_input_server.py ################
###############################################################################

class STKSender:
    """Envoie les commandes texte (P_LEFT, R_LEFT, ...) en UDP au serveur STK."""

    def __init__(self, address, debug=False):
        self.address = address
        self.debug = debug
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, command):
        self.socket.sendto(command.encode('utf-8'), self.address)
        if self.debug:
            print(YELLOW + '\t' + command + WHITE)

############################################################################### 
##############################      Main       ################################        
###############################################################################

def main():
    debug = '-d' in sys.argv or '--debug' in sys.argv
    
    # Lance le serveur et le face tracking, chacun dans sa propre console.
    ici = os.path.dirname(os.path.abspath(__file__))
    serveur = subprocess.Popen([sys.executable, os.path.join(ici, 'STK_input_server.py'), '-d'], cwd=ici, creationflags=subprocess.CREATE_NEW_CONSOLE)
    time.sleep(1.0) 
    tracking = subprocess.Popen([sys.executable, os.path.join(ici, 'face_tracking.py')], cwd=ici, creationflags=subprocess.CREATE_NEW_CONSOLE)

    
    sender = STKSender(STK_SERVER_ADDRESS, debug=debug)
    kart = KartState(sender, debug=debug)
    pad = PadState()
    acc = Vector3State()
    camera = CameraState()
    tap_detector = TapDetector()
    shake_detector = ShakeDetector()
    steering_pwm = ContinuousCommand()
    fire_button = HoldCommand(sender, 'P_FIRE', 'R_FIRE', FIRE_HOLD)
    rescue_button = HoldCommand(sender, 'P_RESCUE', 'R_RESCUE', RESCUE_HOLD)
    osc = OSCThreadServer()

    osc.listen(address=OSC_LISTEN_IP, port=OSC_LISTEN_PORT, default=True)
    bind_all(osc, pad, acc, camera)
    print()
    print('STK client v2 started ', end='')
    
    if debug:   print(GREEN + '(Debug mode)' + WHITE)
    else:       print()
    print('  OSC : ecoute sur {}:{}  (a saisir dans MultiSense Osc)'.format(
        OSC_LISTEN_IP, OSC_LISTEN_PORT))
    print('  STK : envoi vers {}:{}'.format(*STK_SERVER_ADDRESS))
    print('  Activer PAD + Accelerometre + Gyroscope dans MultiSense Osc')
    print('  Ctrl+C pour arreter')
    print()

    period = 1.0 / LOOP_HZ
    skid_started_at = 0.0
    skid_direction = 'NONE'

    try:
        while True:
            now = time.time()
            px, py, pressed, page = pad.snapshot()
            ax, ay, az, aage = acc.snapshot()
            cx, cy, cz, cage = camera.snapshot() #Données liées à la caméra

            touching = pressed and page <= TOUCH_TIMEOUT
            acc_ok   = ax is not None and aage <= SENSOR_TIMEOUT
            camera_ok = cx is not None and cage <= SENSOR_TIMEOUT
            double_tap, maintien = tap_detector.update(touching, now)

            # Le telephone bouge-t-il trop pour qu'on y lise une inclinaison ?
            acc_calme = acc_ok and gravity_deviation(ax, ay, az) <= MOTION_TOLERANCE

            # --- Double-tap -> lancer un objet ou nitro -------------------
            if double_tap and px > 0:
                    fire_button.trigger(now)
                    if debug:
                        print(GREEN + '\tdouble-tap -> FIRE' + WHITE)

            # Front montant du derapage : on note l'instant de l'amorce.
            skid = maintien and px > 0
            if skid and not kart.skidding_on:
                skid_started_at = now
            kart.set_skidding(skid)
            kart.set_nitro(maintien and px < 0)

            fire_button.update(now)
            
            # --- Tourner la tête -> sauvetage ---------------------------
            camera_shake = camera_ok and shake_detector.updatecamera(cx, now) and cz > -90
            if camera_shake:
                rescue_button.trigger(now)
                if debug:
                    print(GREEN + '\tsecousse -> RESCUE' + WHITE)
            rescue_button.update(now)

            if STEERING_SOURCE == 'tilt' and acc_calme:
                nx = normalize(ax, ACC_X_MIN, ACC_X_MAX)
                ny = normalize(ay, ACC_Y_MIN, ACC_Y_MAX)
                if INVERT_ACC_Y:
                    ny = -ny
            else:
                nx = ny = 0.0

            # --- La direction est dosee, pas tout ou rien ---------
            direction = zone(nx, DEAD_ZONE_X, 'LEFT', 'RIGHT')
            niveau = intensity(nx, DEAD_ZONE_X)

            amorce = kart.skidding_on and (now - skid_started_at) < SKID_KICKOFF
            if amorce and direction != 'NONE':
                skid_direction = direction

            if kart.skidding_on and direction == skid_direction:
                niveau = min(niveau, SKID_INTO_MAX)

            if amorce or steering_pwm.pressed(niveau, now):
                kart.set_steering(direction)
            else:
                kart.set_steering('NONE')

            kart.set_throttle(zone(ny, DEAD_ZONE_Y, 'BRAKE', 'ACCELERATE'))

            time.sleep(period)

    except KeyboardInterrupt:
        pass
    finally:
        # Indispensable : sans ca, les touches restent enfoncees dans le jeu.
        kart.release_all()          
        fire_button.release_now()
        rescue_button.release_now()
        osc.stop()
        serveur.terminate()         
        tracking.terminate()        
        print()
        print('STK client v2 stopped')

if __name__ == '__main__':
    main()
