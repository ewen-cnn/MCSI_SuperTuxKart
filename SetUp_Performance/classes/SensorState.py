import threading, time

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
