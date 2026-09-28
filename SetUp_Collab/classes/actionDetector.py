from collections import deque
from classes.config import *

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
######################### Detection de la secousse ############################
###############################################################################

class ShakeDetector:

    def __init__(self):
        self._history = deque()
        self._last_rescue = 0.0
        self._previous_cx = None

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
