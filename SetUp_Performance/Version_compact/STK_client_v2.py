###############################################################################
## Global libs
import math
import socket
import sys
import threading
import time
import subprocess
import os
from collections import deque

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

# --- Calibration du pad -----------------------------------------------------
PAD_X_MIN, PAD_X_MAX = -1.0, 1.0
PAD_Y_MIN, PAD_Y_MAX = -1.0, 1.0
INVERT_Y = True     # True si y=0 correspond au HAUT de l'ecran (cas habituel)

# --- Calibration de l'accelerometre (en m/s2, gravite = 9.81) ---------------
ACC_X_MIN, ACC_X_MAX = -2, 2    # pencher a gauche / a droite
ACC_Y_MIN, ACC_Y_MAX = -7,-3    # pencher en avant / en arriere
INVERT_ACC_Y = True
    
# --- Reglages de l'interaction ----------------------------------------------
# Zone morte autour du centre, dans [0, 1] apres normalisation. Elle fixe le
# seuil de DECLENCHEMENT, la borne ACC_* ci-dessus fixe le plein braquage.
# A 0.20 avec ACC_X_MAX = 3.0, le kart commence a tourner vers 3.5 degres
# d'inclinaison et braque a fond a 18 degres.
DEAD_ZONE_X = 0.20
DEAD_ZONE_Y = 0.20

TOUCH_TIMEOUT  = 0.40   # sans message pad pendant ce delai -> doigt leve
SENSOR_TIMEOUT = 0.50   # sans message d'un capteur -> capteur eteint

# --- Source de la direction -------------------------------------------------
STEERING_SOURCE = 'tilt'

# --- le pad comme joystick (press & drag) -----------------------
# Ne s'applique que si STEERING_SOURCE == 'pad'.
# 'joystick' : la consigne vient du DEPLACEMENT depuis le point de poser.
#              Revenir a l'origine ou lever le doigt = point neutre.
# 'absolu'   : la consigne vient de la POSITION touchee (partie 1).
TOUCH_MODE      = 'joystick'
JOYSTICK_RADIUS = 0.50  # deplacement (en unites pad) pour atteindre le maximum

# ---  double-tap -> FIRE -----------------------------------------
# Attention : le doigt leve n'est detecte qu'apres TOUCH_TIMEOUT, donc la duree
# de contact mesuree est surestimee d'autant. Ces seuils en tiennent compte ;
# si tu changes TOUCH_TIMEOUT, reverifie-les.
# Duree de maintien des touches d'action. Il faut couvrir plusieurs images
# de jeu : a 60 fps une image dure 16 ms et STK relit l'etat du clavier une
# fois par image. Une impulsion plus courte passe entre deux lectures.
FIRE_HOLD        = 0.12     # maintien de la touche espace (s)
RESCUE_HOLD      = 0.12     # maintien de la touche retour arriere (s)
NITRO_HOLD       = 0.12     # maintien de la touche nitro (s)
TAP_MIN_DURATION = 0.03     # en dessous, c'est un rebond du pad, pas un tap
TAP_MAX_DURATION = 0.25     # au-dela, c'est un appui maintenu, pas un tap
DOUBLE_TAP_DELAY = 0.30     # ecart maxi entre les deux taps

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
# Contrainte : SHAKE_MIN_SAMPLES doit rester > SHAKE_MIN_REVERSALS, sinon la
# condition est impossible a satisfaire (n signes contiennent au plus n-1
# inversions).

# L'ACCELEROMETRE, lui, ne mesure l'inclinaison que si le telephone est quasi
# immobile : au-dela de cet ecart a la gravite, la mesure est dominee par le
# mouvement du bras et ne veut plus rien dire.
GRAVITY          = 9.81
MOTION_TOLERANCE = 3.00

# ---  envoi continu des commandes de direction --------------------
# On ne peut pas dire au jeu "tourne a 40 %". On lui envoie donc la meme
# commande en rafale en dosant le rapport cyclique. Sur une periode :
#     t1 = intensite * CONTINUOUS_PERIOD        -> touche enfoncee
#     t2 = (1 - intensite) * CONTINUOUS_PERIOD  -> touche relachee
CONTINUOUS_PERIOD = 0.05   # duree d'un cycle pressed + released (s)
SKID_KICKOFF = 0.15 
SKID_INTO_MAX = 0.7     # braquage maxi DANS le sens du virage pendant la glisse
LOOP_HZ = 120       # frequence de la boucle principale
# A 120 Hz avec une periode de 0.10 s, on dispose de 12 crans d'intensite.
# Baisser LOOP_HZ ou CONTINUOUS_PERIOD rend le dosage plus grossier.


###############################################################################
## Envoi des commandes vers STK_input_server.py
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
## Representation de l'etat du kart
class KartState:

    # etat -> (commande "pressed", commande "released")
    STEERING_COMMANDS = {
        'LEFT':  ('P_LEFT',  'R_LEFT'),
        'RIGHT': ('P_RIGHT', 'R_RIGHT'),
        'NONE':  (None,      None),
    }
    THROTTLE_COMMANDS = {
        'ACCELERATE': ('P_ACCELERATE', 'R_ACCELERATE'),
        'BRAKE':      ('P_BRAKE',      'R_BRAKE'),
        'NONE':       (None,           None),
    }

    def __init__(self, sender, debug=False):
        self.sender = sender
        self.debug = debug
        self.steering = 'NONE'
        self.throttle = 'NONE'
        self.skidding_on = False
        self.nitro_on = False

    def _switch(self, table, current, target):
        """Relache l'ancienne touche puis appuie sur la nouvelle."""
        if target == current:
            return current
        release_old = table[current][1]
        if release_old:
            self.sender.send(release_old)
        press_new = table[target][0]
        if press_new:
            self.sender.send(press_new)
        if self.debug:
            print(BLUE + '\tetat : {} -> {}'.format(current, target) + WHITE)
        return target

    def set_steering(self, target):
        self.steering = self._switch(self.STEERING_COMMANDS, self.steering, target)

    def set_throttle(self, target):
        self.throttle = self._switch(self.THROTTLE_COMMANDS, self.throttle, target)

    def release_all(self):
        """Retour au point neutre : roues droites, ni accelerateur ni frein."""
        self.set_steering('NONE')
        self.set_throttle('NONE')

    # --- Actions ponctuelles (le serveur fait press_and_release) -------------
    def fire(self):
        """Lance un objet."""
        self.sender.send('FIRE')

    def rescue(self):
        """Sauvetage par l'oiseau : replace le kart sur la piste."""
        self.sender.send('RESCUE')

    def set_skidding(self, active):
        """Maintient la touche de derapage tant que active est vrai."""
        if active == self.skidding_on:
            return                          # pas de changement : rien a envoyer
        self.sender.send('P_SKIDDING' if active else 'R_SKIDDING')
        self.skidding_on = active
        if self.debug:
            print(BLUE + '\tderapage : {}'.format('ON' if active else 'OFF') + WHITE)

    def set_nitro(self, active):
        """Maintient la touche nitro tant que active est vrai."""
        if active == self.nitro_on:
            return
        self.sender.send('P_NITRO' if active else 'R_NITRO')
        self.nitro_on = active
        if self.debug:
            print(GREEN + '\tdouble-tap -> NITRO' + WHITE)

    def release_all(self):
        """Retour au point neutre : roues droites, ni accelerateur ni frein."""
        self.set_steering('NONE')
        self.set_throttle('NONE')
        self.set_skidding(False)

    def __str__(self):
        if self.steering == 'NONE' and self.throttle == 'NONE':
            return 'immobile'
        return '{} + {}'.format(self.steering, self.throttle)


###############################################################################
## Etats des capteurs (ecrits par le thread OSC, lus par la boucle principale)
class PadState:
    """Derniere position connue du doigt sur le pad, protegee par un verrou."""

    def __init__(self):
        self._lock = threading.Lock()
        self._x = None
        self._y = None
        self._pressed = False
        self._last_update = 0.0

    def set_x(self, value):
        with self._lock:
            self._x = value
            self._pressed = True          # un message x ou y = le doigt est pose
            self._last_update = time.time()

    def set_y(self, value):
        with self._lock:
            self._y = value
            self._pressed = True          # un message x ou y = le doigt est pose
            self._last_update = time.time()

    def set_touch_up(self):
        with self._lock:
            self._pressed = False         # annonce explicite du lever

    def snapshot(self):
        """Retourne (x, y, pressed, age du dernier message)."""
        with self._lock:
            if self._x is None or self._y is None:
                return None, None, False, float('inf')
            return self._x, self._y, self._pressed, time.time() - self._last_update

class Vector3State:

    def __init__(self):
        self._lock = threading.Lock()
        self._x = None
        self._y = None
        self._z = None
        self._last_update = 0.0

    def set_x(self, value):
        with self._lock:
            self._x = value
            self._last_update = time.time()

    def set_y(self, value):
        with self._lock:
            self._y = value
            self._last_update = time.time()

    def set_z(self, value):
        with self._lock:
            self._z = value
            self._last_update = time.time()

    def snapshot(self):
        """Retourne (x, y, z, age du dernier message recu)."""
        with self._lock:
            if self._x is None or self._y is None or self._z is None:
                return None, None, None, float('inf')
            return self._x, self._y, self._z, time.time() - self._last_update


class CameraState:

    def __init__(self):
            self._lock = threading.Lock()
            self._x = None
            self._y = None
            self._z = None
            self._last_update = 0.0
    
    def pos_x(self, value):
        with self._lock:
            self._x = value
            self._last_update = time.time()

    def pos_y(self, value):
        with self._lock:
            self._y = value
            self._last_update = time.time()

    def pos_z(self, value):
        with self._lock:
            self._z = value
            self._last_update = time.time()

    def snapshot(self):
        """Retourne (x, y, z, age du dernier message recu)."""
        with self._lock:
            if self._x is None or self._y is None or self._z is None:
                return None, None, None, float('inf')
            return self._x, self._y, self._z, time.time() - self._last_update



###############################################################################
##detection du double-tap
class TapDetector:

    """
    Reconnait deux gestes sur le pad a partir d'un SEUL decompte.

    Au front montant, on lance le decompte. Ensuite :
    - si le doigt reste pose au-dela de TAP_MAX_DURATION -> MAINTIEN (etat)
    - si le doigt est leve avant                         -> c'est un TAP
    - si ce tap a commence peu apres un tap precedent    -> DOUBLE-TAP (evenement)

    Un contact est donc soit un tap, soit un maintien, jamais les deux.
    """

    def __init__(self):
        self._touching = False
        self._touch_start = 0.0
        self._last_tap_end = None   # instant du lever du dernier tap valide
        self._second_tap = False    # le contact en cours peut-il etre le 2e tap ?

    def update(self, touching, now):
        """A appeler a chaque iteration. Retourne (double_tap, maintien)."""
        double_tap = False

        if touching and not self._touching:
            # Front montant : on lance le decompte.
            self._touch_start = now
            # Est-ce le 2e appui d'un double-tap ? On le sait des la pose :
            # il faut que le 1er tap se soit termine il y a MOINS de DOUBLE_TAP_DELAY.
            self._second_tap = (self._last_tap_end is not None
                                and now - self._last_tap_end <= DOUBLE_TAP_DELAY)

        elif not touching and self._touching:
            # Front descendant : on arrete le decompte et on classe le contact.
            duration = now - self._touch_start
            if TAP_MIN_DURATION <= duration <= TAP_MAX_DURATION:
                if self._second_tap:
                    double_tap = True
                    self._last_tap_end = None    # consomme : evite le triple-tap
                else:
                    self._last_tap_end = now     # 1er tap : on attend le 2e
            else:
                # Trop court (parasite) ou trop long (c'etait un maintien) :
                # ce contact ne peut pas servir de 1er tap.
                self._last_tap_end = None
            self._second_tap = False

        self._touching = touching

        # Maintien : un ETAT, vrai tant que le decompte a depasse le seuil.
        maintien = touching and (now - self._touch_start) > TAP_MAX_DURATION
        return double_tap, maintien


###############################################################################
## detection de la secousse
class ShakeDetector:

    def __init__(self):
        self._history = deque()
        self._last_rescue = 0.0
        self._previous_cx = None

    def updategyr(self, gx, now):
        """A appeler une fois par iteration. Retourne True sur une secousse."""
        if gx is None:
            return False
        
        self._history.append((now, gx))

        # On ne garde que la fenetre glissante.
        while self._history and now - self._history[0][0] > SHAKE_WINDOW:
            self._history.popleft()

        # Periode refractaire : une secousse dure ~1 s et produirait sinon
        # une rafale de RESCUE.
        if now - self._last_rescue < RESCUE_COOLDOWN:
            return False

        # Criteres 1 et 2 : des rotations rapides, et en nombre.
        signes = [1 if v >= 0 else -1
                for _, v in self._history
                if v is not None and abs(v) > GYR_X_SHAKE_THRESHOLD]
        if len(signes) < SHAKE_MIN_SAMPLES:
            return False

        # Critere 3 : le sens doit s'inverser (va-et-vient).
        inversions = sum(1 for a, b in zip(signes, signes[1:]) if a != b)
        if inversions < SHAKE_MIN_REVERSALS:
            return False

        self._last_rescue = now
        self._history.clear()
        return True

    def updatecamera(self, cx, now):
        """Retourne True lorsqu'une secousse rapide gauche-droite est détectée."""

        # Première mesure
        if self._previous_cx is None:
            self._previous_cx = cx
            return False

        # Variation de position entre deux images
        dx = cx - self._previous_cx
        self._previous_cx = cx

        self._history.append((now, dx))

        # Fenêtre glissante
        while self._history and now - self._history[0][0] > SHAKE_WINDOW:
            self._history.popleft()

        # Cooldown
        if now - self._last_rescue < RESCUE_COOLDOWN:
            return False

        # On garde les mouvements rapides
        signes = [
            1 if v > 0 else -1
            for _, v in self._history
            if abs(v) > CAMERA_X_SHAKE_THRESHOLD
        ]

        # Nombre minimal de mouvements
        if len(signes) < CAMERA_SHAKE_MIN_SAMPLES:
            return False

        # Recherche des changements de direction
        inversions = sum(
            1 for a, b in zip(signes, signes[1:])
            if a != b
        )

        if inversions < CAMERA_SHAKE_MIN_REVERSALS:
            return False

        # SECousse détectée
        self._last_rescue = now
        self._history.clear()

        return True


###############################################################################
## le pad comme joystick relatif
class DragTracker:

    def __init__(self):
        self._touching = False
        self._origin_x = 0.0
        self._origin_y = 0.0

    def update(self, touching, px, py):
        """Retourne (dx, dy) dans [-1, 1] ; (0, 0) si le doigt est leve."""
        if touching and not self._touching:
            # Front montant : ce point devient le centre du joystick.
            self._origin_x, self._origin_y = px, py
        self._touching = touching

        if not touching:
            return 0.0, 0.0

        dx = (px - self._origin_x) / JOYSTICK_RADIUS
        dy = (py - self._origin_y) / JOYSTICK_RADIUS
        return (max(-1.0, min(1.0, dx)), max(-1.0, min(1.0, dy)))


###############################################################################
## Appui bref mais tenu (pour FIRE)
class HoldCommand:

    def __init__(self, sender, press_cmd, release_cmd, hold):
        self.sender = sender
        self.press_cmd = press_cmd
        self.release_cmd = release_cmd
        self.hold = hold
        self._release_at = None     # None = touche relachee

    def trigger(self, now):
        """Declenche l'appui."""
        # Si la touche est encore enfoncee (declenchements rapproches), il faut
        # la relacher d'abord : reappuyer sur une touche deja enfoncee ne
        # produit aucun nouveau front, donc aucune action dans le jeu.
        if self._release_at is not None:
            self.sender.send(self.release_cmd)
        self.sender.send(self.press_cmd)
        self._release_at = now + self.hold

    def update(self, now):
        """A appeler a chaque iteration : relache la touche le moment venu."""
        if self._release_at is None:
            return                  # touche deja relachee, rien a faire
        if now < self._release_at:
            return                  # encore dans la duree de maintien
        self.sender.send(self.release_cmd)
        self._release_at = None     # sans ca : un released par iteration

    def release_now(self):
        """Relachement force, a la fermeture du client."""
        if self._release_at is not None:
            self.sender.send(self.release_cmd)
            self._release_at = None


###############################################################################
class ContinuousCommand:

    def __init__(self):
        self._phase = 0.0
        self._last_time = None

    def pressed(self, level, now):
        """Retourne True si la touche doit etre enfoncee a cet instant."""
        if self._last_time is None:
            self._last_time = now
        dt = now - self._last_time
        self._last_time = now

        if level <= 0.0:
            self._phase = 0.0
            return False
        if level >= 1.0:
            return True

        self._phase = (self._phase + dt) % CONTINUOUS_PERIOD
        return self._phase < level * CONTINUOUS_PERIOD


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
    osc.bind(b'/multisense/pad/touchUP', lambda *values: pad.set_touch_up())

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
## Mode calibration
def run_calibration():
    """Affiche en direct les valeurs brutes des trois capteurs."""
    pad = PadState()
    acc = Vector3State()
    gyr = Vector3State()
    bounds = {'xmin': float('inf'), 'xmax': float('-inf'),
              'ymin': float('inf'), 'ymax': float('-inf'),
              'gyr': 0.0}

    osc = OSCThreadServer()
    osc.listen(address=OSC_LISTEN_IP, port=OSC_LISTEN_PORT, default=True)
    bind_all(osc, pad, acc, gyr)

    print()
    print('Mode calibration - Ctrl+C pour arreter')
    print('  1. touche les 4 coins du pad')
    print('  2. penche le telephone a droite : verifie que acc x devient positif')
    print('  3. incline vivement pour piloter : note le pic de gyr x (a NE PAS depasser)')
    print('  4. secoue le telephone : note le pic de gyr x (a depasser largement)')
    print('Ecoute OSC sur {}:{}'.format(OSC_LISTEN_IP, OSC_LISTEN_PORT))
    print()
    try:
        while True:
            x, y, page = pad.snapshot()
            ax, ay, az, aage = acc.snapshot()
            gx, gy, gz, gage = gyr.snapshot()

            ligne = ''
            if x is not None:
                bounds['xmin'] = min(bounds['xmin'], x)
                bounds['xmax'] = max(bounds['xmax'], x)
                bounds['ymin'] = min(bounds['ymin'], y)
                bounds['ymax'] = max(bounds['ymax'], y)
                ligne += 'pad {:+.2f} {:+.2f} [{:+.2f},{:+.2f}]x[{:+.2f},{:+.2f}] {} | '.format(
                    x, y, bounds['xmin'], bounds['xmax'],
                    bounds['ymin'], bounds['ymax'],
                    'touche ' if page < TOUCH_TIMEOUT else 'relache')
            if ax is not None:
                ligne += 'acc {:+.2f} {:+.2f} {:+.2f} | '.format(ax, ay, az)
            if gx is not None:
                bounds['gyr'] = max(bounds['gyr'], abs(gx))
                ligne += 'gyr x {:+6.2f} rad/s  pic |x| {:5.2f}'.format(gx, bounds['gyr'])
            if ligne:
                print('\r' + ligne + '   ', end='')

            time.sleep(1.0 / 30)
    except KeyboardInterrupt:
        print()
        print()
        print('Recopie ces valeurs dans le script :')
        print('    PAD_X_MIN, PAD_X_MAX  = {:.3f}, {:.3f}'.format(
            bounds['xmin'], bounds['xmax']))
        print('    PAD_Y_MIN, PAD_Y_MAX  = {:.3f}, {:.3f}'.format(
            bounds['ymin'], bounds['ymax']))
        print('    GYR_X_SHAKE_THRESHOLD = {:.1f}   (~70 % du pic observe : {:.2f} rad/s)'.format(
            bounds['gyr'] * 0.7, bounds['gyr']))
    finally:
        osc.stop()


###############################################################################
## Lancement des programmes serveur et face tracking



###############################################################################
## Main
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

    # Lance le serveur et le face tracking, chacun dans sa propre console.
    ici = os.path.dirname(os.path.abspath(__file__))
    serveur = subprocess.Popen(
        [sys.executable, os.path.join(ici, 'STK_input_server.py'), '-d'],
        cwd=ici, creationflags=subprocess.CREATE_NEW_CONSOLE)
    time.sleep(1.0)          # laisse le serveur prendre le port 6006
    tracking = subprocess.Popen(
        [sys.executable, os.path.join(ici, 'face_tracking.py')],
        cwd=ici, creationflags=subprocess.CREATE_NEW_CONSOLE)
    
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
    skid_direction = 'NONE'
    try:
        while True:
            now = time.time()
            px, py, pressed, page = pad.snapshot()
            ax, ay, az, aage = acc.snapshot()
            gx, gy, gz, gage = gyr.snapshot()
            cx, cy, cz, cage = camera.snapshot() #Données liées à la caméra

            touching = pressed and page <= TOUCH_TIMEOUT
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
            camera_shake = camera_ok and shake_detector.updatecamera(cx, now) and cz > -90
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

            # A l'amorce, on court-circuite la MLI : le jeu fige le sens du
            # derapage a l'instant ou P_SKIDDING part, et il faut qu'une
            # fleche soit enfoncee a ce moment-la.
            amorce = kart.skidding_on and (now - skid_started_at) < SKID_KICKOFF
            if amorce and direction != 'NONE':
                skid_direction = direction

            # Pendant la glisse, le jeu remappe le braquage [-1, 1] vers
            # [0.2, 0.8] : dans le virage -> 0.8 (serre), rien -> 0.5,
            # contre le virage -> 0.2 (large). On ne plafonne donc que le
            # sens du virage, pour eviter la courbe la plus serree.
            if kart.skidding_on and direction == skid_direction:
                niveau = min(niveau, SKID_INTO_MAX)

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
        serveur.terminate()         # <-- ajout
        tracking.terminate()        # <-- ajout
        print()
        print('STK client v2 stopped')


if __name__ == '__main__':
    main()
