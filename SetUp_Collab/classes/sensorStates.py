import threading, time
from typing import Tuple

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
    """Stocke et consomme des evenements ponctuels (ex: lancer d'objet / FIRE)."""

    def __init__(self, cooldown: float = 1.4):
        self._lock = threading.Lock()
        self._triggered = False
        self._last_trigger_time = 0.0
        self._last_update = 0.0
        self._cooldown = cooldown

    def trigger(self, value=1):
        with self._lock:
            now = time.time()
            if value and (now - self._last_trigger_time >= self._cooldown):
                self._triggered = True
                self._last_trigger_time = now
                self._last_update = now

    def consume(self) -> bool:
        """Consomme l'evenement : renvoie True une seule fois puis se remet a False."""
        with self._lock:
            was = self._triggered
            self._triggered = False
            return was


class FloatState:
    """Stocke une valeur flottante scalaire reçue via OSC (ex: z_neutral)."""

    def __init__(self, default: float = 75.0):
        self._val = default
        self._last_update = time.time()
        self._lock = threading.Lock()

    def update(self, val, *args):
        with self._lock:
            try:
                self._val = float(val)
                self._last_update = time.time()
            except (ValueError, TypeError):
                pass

    def snapshot(self) -> Tuple[float, float]:
        with self._lock:
            return self._val, time.time() - self._last_update

