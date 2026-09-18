###############################################################################
## Global libs
import math
import socket
import sys
import threading
import time
from collections import deque

from oscpy.server import OSCThreadServer

from classes.SensorState import *
from classes.KartState import *
from classes.ActionDetector import *
from classes.Calibration import run_calibration

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


# --- Calibration du pad -----------------------------------------------------
PAD_X_MIN, PAD_X_MAX = -1.0, 1.0
PAD_Y_MIN, PAD_Y_MAX = -1.0, 1.0
INVERT_Y = True     # True si y=0 correspond au HAUT de l'ecran (cas habituel)

# --- Calibration de l'accelerometre (en m/s2, gravite = 9.81) ---------------
ACC_X_MIN, ACC_X_MAX = -1.5, 1.5    # pencher a gauche / a droite
ACC_Y_MIN, ACC_Y_MAX = -7,-3    # pencher en avant / en arriere
INVERT_ACC_Y = True
    
# --- Reglages de l'interaction ----------------------------------------------
DEAD_ZONE_X = 0.20
DEAD_ZONE_Y = 0.20

TOUCH_TIMEOUT  = 0.05   # sans message pad pendant ce delai -> doigt leve
SENSOR_TIMEOUT = 0.50   # sans message d'un capteur -> capteur eteint

# --- Source de la direction -------------------------------------------------
STEERING_SOURCE = 'tilt'

# --- le pad comme joystick (press & drag) -----------------------
TOUCH_MODE      = 'joystick'


# ---  double-tap -> FIRE -----------------------------------------
FIRE_HOLD        = 0.12     # maintien de la touche espace (s)
RESCUE_HOLD      = 0.12     # maintien de la touche retour arriere (s)
NITRO_HOLD       = 0.12     # maintien de la touche nitro (s)

# --- secousse autour de X -> RESCUE -----------------------------
CAMERA_X_SHAKE_THRESHOLD = 3 # Différence x min perçu par la caméra lors de la rotation de la tête 
CAMERA_SHAKE_MIN_SAMPLES = 2 # nb d'echantillons rapides dans la fenetre
CAMERA_SHAKE_MIN_REVERSALS   = 1     # nb d'inversions de sens : c'est le va-et-vient
GYR_X_SHAKE_THRESHOLD = 4.0   # rad/s (~230 deg/s)
SHAKE_WINDOW          = 0.60  # fenetre d'observation
SHAKE_MIN_SAMPLES     = 3     # nb d'echantillons rapides dans la fenetre
SHAKE_MIN_REVERSALS   = 2     # nb d'inversions de sens : c'est le va-et-vient
RESCUE_COOLDOWN       = 2.00  # une secousse = un seul RESCUE
SHAKE_LOCKOUT         = 1.00  # apres un shake, on ignore l'inclinaison

GRAVITY          = 9.81
MOTION_TOLERANCE = 3.00

# ---  envoi continu des commandes de direction --------------------
SKID_KICKOFF = 0.15 
SKID_LEVEL_MIN = 0.3    # plancher : en dessous, la glisse retombe
SKID_LEVEL_MAX = 0.7    # plafond : au-dessus, la courbe se referme trop
LOOP_HZ = 120       # frequence de la boucle principale
# A 120 Hz avec une periode de 0.10 s, on dispose de 12 crans d'intensite.
# Baisser LOOP_HZ ou CONTINUOUS_PERIOD rend le dosage plus grossier.

###############################################################################
## Outils
def normalize(value, vmin, vmax):
    """Ramene value de [vmin, vmax] vers [-1, 1] (0 = centre)."""
    if vmax == vmin:
        return 0.0
    ratio = (value - vmin) / (vmax - vmin)      # -> [0, 1]
    centered = ratio * 2.0 - 1.0                # -> [-1, 1]
    return max(-1.0, min(1.0, centered))


def zone(value, dead_zone, negative_label, positive_label):
    """Traduit une valeur de [-1, 1] en etat discret, avec zone morte."""
    if value > dead_zone:
        return positive_label
    if value < -dead_zone:
        return negative_label
    return 'NONE'


def intensity(value, dead_zone):
    """Amplitude de la consigne au-dela de la zone morte, ramenee dans [0, 1].

    C'est la valeur continue demandee par la partie 4 : 0 juste apres la zone
    morte, 1 a fond de course.
    """
    magnitude = abs(value)
    if magnitude <= dead_zone or dead_zone >= 1.0:
        return 0.0
    return min(1.0, (magnitude - dead_zone) / (1.0 - dead_zone))


def gravity_deviation(ax, ay, az):
    """Ecart entre la norme de l'acceleration et la gravite (m/s2).

    Vaut ~0 des que le telephone est immobile, QUELLE QUE SOIT son inclinaison.
    C'est donc une mesure du mouvement propre, independante de l'orientation.
    """
    return abs(math.sqrt(ax * ax + ay * ay + az * az) - GRAVITY)


def bind_all(osc, pad, acc, gyr, camera):
    """Associe les messages OSC de MultiSense Osc aux trois etats."""
    osc.bind(b'/multisense/pad/x', lambda *values: pad.set_x(values[0]))
    osc.bind(b'/multisense/pad/y', lambda *values: pad.set_y(values[0]))

    osc.bind(b'/multisense/accelerometer/x', lambda *values: acc.set_x(values[0]))
    osc.bind(b'/multisense/accelerometer/y', lambda *values: acc.set_y(values[0]))
    osc.bind(b'/multisense/accelerometer/z', lambda *values: acc.set_z(values[0]))

    osc.bind(b'/multisense/gyroscope/x', lambda *values: gyr.set_x(values[0]))
    osc.bind(b'/multisense/gyroscope/y', lambda *values: gyr.set_y(values[0]))
    osc.bind(b'/multisense/gyroscope/z', lambda *values: gyr.set_z(values[0]))

    osc.bind(b'/tracker/head/pos_xyz', lambda *values: camera.pos_x(values[0]))
    osc.bind(b'/tracker/head/pos_xyz', lambda *values: camera.pos_y(values[1]))     
    osc.bind(b'/tracker/head/pos_xyz', lambda *values: camera.pos_z(values[2]))  # age is not used, but we can bind it if needed


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

    if '--calib' in sys.argv:
        run_calibration()
        return

    sender = STKSender(STK_SERVER_ADDRESS, debug=debug)
    kart = KartState(sender, debug=debug)
    pad = PadState()
    acc = Vector3State()
    gyr = Vector3State()
    camera = CameraState()
    tap_detector = TapDetector()
    shake_detector = ShakeDetector()
    drag = DragTracker()
    steering_pwm = ContinuousCommand()
    skidding_button = HoldCommand(sender, 'P_SKIDDING', 'R_SKIDDING', RESCUE_HOLD)
    fire_button = HoldCommand(sender, 'P_FIRE', 'R_FIRE', FIRE_HOLD)
    rescue_button = HoldCommand(sender, 'P_RESCUE', 'R_RESCUE', RESCUE_HOLD)
    nitro_button = HoldCommand(sender, 'P_NITRO', 'R_NITRO', NITRO_HOLD)

    # Le serveur OSC tourne dans son propre thread et remplit les trois etats.
    osc = OSCThreadServer()
    osc.listen(address=OSC_LISTEN_IP, port=OSC_LISTEN_PORT, default=True)
    bind_all(osc, pad, acc, gyr, camera)

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
    shake_lock_until = 0.0
    skid_started_at = 0.0
    try:
        while True:
            now = time.time()
            px, py, page = pad.snapshot()
            ax, ay, az, aage = acc.snapshot()
            gx, gy, gz, gage = gyr.snapshot()
            cx, cy, cz, cage = camera.snapshot() #Données liées à la caméra

            touching = px is not None and page <= TOUCH_TIMEOUT
            acc_ok   = ax is not None and aage <= SENSOR_TIMEOUT
            gyr_ok   = gx is not None and gage <= SENSOR_TIMEOUT
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
            
            # --- Secousse -> sauvetage ---------------------------
            gyro_shake = gyr_ok and shake_detector.updategyr(gx, now)
            camera_shake = camera_ok and shake_detector.updatecamera(cx, now)
            if gyro_shake or camera_shake:
                rescue_button.trigger(now)
                shake_lock_until = now + SHAKE_LOCKOUT
                if debug:
                    print(GREEN + '\tsecousse -> RESCUE' + WHITE)
            rescue_button.update(now)

            # --- Consigne continue nx, ny dans [-1, 1] -----------------------
            if touching:
                px_n = normalize(px, PAD_X_MIN, PAD_X_MAX)
                py_n = normalize(py, PAD_Y_MIN, PAD_Y_MAX)
            else:
                px_n = py_n = 0.0
            # Appele a chaque iteration, meme doigt leve : c'est lui qui detecte
            # le front montant et fixe l'origine du joystick.
            dx, dy = drag.update(touching, px_n, py_n)

            if now < shake_lock_until:
                # Pendant et juste apres une secousse, l'inclinaison n'a aucun
                # sens : on met le kart au neutre plutot que de lire du bruit.
                nx = ny = 0.0
            elif STEERING_SOURCE == 'pad' and touching:
                # Le pad pilote, et lui seul.
                if TOUCH_MODE == 'joystick':
                    nx, ny = dx, dy
                else:
                    nx, ny = px_n, py_n
                if INVERT_Y:
                    ny = -ny
            elif STEERING_SOURCE == 'tilt' and acc_calme:
                # Inclinaison pilote, meme si un doigt touche le
                # pad. C'est ce qui rend le double-tap inoffensif pour la
                # trajectoire.
                nx = normalize(ax, ACC_X_MIN, ACC_X_MAX)
                ny = normalize(ay, ACC_Y_MIN, ACC_Y_MAX)
                if INVERT_ACC_Y:
                    ny = -ny
            else:
                # Source indisponible (capteur eteint, telephone secoue, ou
                # doigt leve en mode 'pad') -> neutre.
                nx = ny = 0.0

            # --- La direction est dosee, pas tout ou rien ---------
            direction = zone(nx, DEAD_ZONE_X, 'LEFT', 'RIGHT')
            niveau = intensity(nx, DEAD_ZONE_X)

            # Pendant la glisse : jamais tout droit (la glisse retomberait),
            # jamais a fond (la courbe se refermerait). La course du telephone
            # ne sert plus qu'a ajuster la trajectoire dans cette bande.
            if kart.skidding_on:
                niveau = SKID_LEVEL_MIN + niveau * (SKID_LEVEL_MAX - SKID_LEVEL_MIN)

            # A l'amorce seulement, on court-circuite la MLI pour garantir que
            # la fleche est enfoncee quand P_SKIDDING part.
            amorce = kart.skidding_on and (now - skid_started_at) < SKID_KICKOFF

            if amorce or steering_pwm.pressed(niveau, now):
                kart.set_steering(direction)
            else:
                kart.set_steering('NONE')

            # La traction reste tout ou rien : en course on veut le pied au
            # plancher ou le frein, pas 40 % d'accelerateur. ContinuousCommand
            # est reutilisable telle quelle si tu veux la doser aussi.
            kart.set_throttle(zone(ny, DEAD_ZONE_Y, 'BRAKE', 'ACCELERATE'))

            time.sleep(period)

    except KeyboardInterrupt:
        pass
    finally:
        # Indispensable : sans ca, les touches restent enfoncees dans le jeu.
        kart.release_all()          # relache aussi le derapage
        fire_button.release_now()
        rescue_button.release_now()
        osc.stop()
        print()
        print('STK client v2 stopped')


if __name__ == '__main__':
    main()
