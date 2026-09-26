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