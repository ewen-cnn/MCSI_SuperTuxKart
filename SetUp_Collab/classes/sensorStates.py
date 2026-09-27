import threading, time

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
            self._x = 0.0
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
                return 0.0, None, None, float('inf')
            return self._x, self._y, self._z, time.time() - self._last_update

    
class EyesValues():
    def __init__(self):
            self._lock = threading.Lock()
            self._x = 0.0
            self._y = None
            self._last_update = 0.0
        
    def pos_x(self, value):
        with self._lock:
            self._x = value
            self._last_update = time.time()

    def pos_y(self, value):
        with self._lock:
            self._y = value
            self._last_update = time.time()

    def snapshot(self):
        """Retourne (x, y, age du dernier message recu)."""
        with self._lock:
            if self._x is None or self._y is None:
                return None, None, float('inf')
            return self._x, self._y, time.time() - self._last_update


class TriggerState:
    """Conteneur thread-safe pour les declencheurs d'evenements (ex: RESCUE)."""
    def __init__(self):
        self._lock = threading.Lock()
        self._active = False
        self._last_update = 0.0

    def trigger(self, value=1):
        with self._lock:
            self._active = bool(value and float(value) > 0.0)
            if self._active:
                self._last_update = time.time()

    def snapshot(self):
        """Retourne (est_actif, age_depuis_declenchement)."""
        with self._lock:
            return self._active, time.time() - self._last_update

    def pop_trigger(self, max_age=0.6):
        """Consomme le declencheur une seule fois s'il est recent."""
        with self._lock:
            if self._active and (time.time() - self._last_update <= max_age):
                self._active = False
                return True
            return False

