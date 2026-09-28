import math
from classes.Config import (GRAVITY)

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
    """Amplitude de la consigne au-dela de la zone morte, ramenee dans [0, 1]."""
    magnitude = abs(value)
    if magnitude <= dead_zone or dead_zone >= 1.0:
        return 0.0
    return min(1.0, (magnitude - dead_zone) / (1.0 - dead_zone))


def gravity_deviation(ax, ay, az):
    """Ecart entre la norme de l'acceleration et la gravite (m/s2)."""
    return abs(math.sqrt(ax * ax + ay * ay + az * az) - GRAVITY)


def bind_all(osc, pad, acc, camera):
    """Associe les messages OSC de MultiSense Osc aux trois etats."""
    osc.bind(b'/multisense/pad/x', lambda *values: pad.set_x(values[0]))
    osc.bind(b'/multisense/pad/y', lambda *values: pad.set_y(values[0]))
    osc.bind(b'/multisense/pad/touchUP', lambda *values: pad.set_touch_up())
    
    osc.bind(b'/multisense/accelerometer/x', lambda *values: acc.set_x(values[0]))
    osc.bind(b'/multisense/accelerometer/y', lambda *values: acc.set_y(values[0]))
    osc.bind(b'/multisense/accelerometer/z', lambda *values: acc.set_z(values[0]))

    osc.bind(b'/tracker/head/pos_xyz', lambda *values: camera.pos_x(values[0]))
    osc.bind(b'/tracker/head/pos_xyz', lambda *values: camera.pos_y(values[1]))     
    osc.bind(b'/tracker/head/pos_xyz', lambda *values: camera.pos_z(values[2])) 