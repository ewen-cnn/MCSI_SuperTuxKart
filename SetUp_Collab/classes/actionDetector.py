from collections import deque

TAP_MIN_DURATION = 0.08     # en dessous, c'est un rebond du pad, pas un tap
TAP_MAX_DURATION = 0.40     # au-dela, c'est un appui maintenu, pas un tap
DOUBLE_TAP_DELAY = 0.30     # ecart maxi entre les deux taps

JOYSTICK_RADIUS = 0.50  # deplacement (en unites pad) pour atteindre le maximum

CAMERA_X_SHAKE_THRESHOLD = 3 # Différence x min perçu par la caméra lors de la rotation de la tête 
CAMERA_SHAKE_MIN_SAMPLES = 2 # nb d'echantillons rapides dans la fenetre
CAMERA_SHAKE_MIN_REVERSALS   = 1     # nb d'inversions de sens : c'est le va-et-vient
GYR_X_SHAKE_THRESHOLD = 4.0   # rad/s (~230 deg/s)
SHAKE_WINDOW          = 0.60  # fenetre d'observation
SHAKE_MIN_SAMPLES     = 3     # nb d'echantillons rapides dans la fenetre
SHAKE_MIN_REVERSALS   = 2     # nb d'inversions de sens : c'est le va-et-vient
RESCUE_COOLDOWN       = 2.00  # une secousse = un seul RESCUE
SHAKE_LOCKOUT         = 1.00  # apres un shake, on ignore l'inclinaison

CONTINUOUS_PERIOD = 0.05   # duree d'un cycle pressed + released (s)

###############################################################################
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
############################# Double-Tap ######################################
###############################################################################
class TapDetector:
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
######################### detection de la secousse ############################
###############################################################################

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
##################### Appui bref mais tenu (pour FIRE) ########################
###############################################################################

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
###################### le pad comme joystick relatif ##########################
###############################################################################

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