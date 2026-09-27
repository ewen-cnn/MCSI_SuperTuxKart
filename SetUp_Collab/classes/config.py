import math

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


GRAVITY = 9.81


# ===========================================================================
# PARAMETRES DE CONTROLE DU KART (Configurables ici pour tout le projet)
# ===========================================================================

# Dimensions standard de capture camera (16:9)
FRAME_WIDTH = 640
FRAME_HEIGHT = 360

# --- 1. Direction (Steering) ---
ANGLE_TETE_MAX = 20.0        # Degres d'inclinaison max pour braquer a 100%
DEAD_ZONE_ANGLE_DEG = 5.0    # Zone neutre centrale en degres (+/- 5 degres)
DEAD_ZONE_X_FACE = DEAD_ZONE_ANGLE_DEG / ANGLE_TETE_MAX
INVERT_TETE = False          # Inverser si le kart tourne dans le mauvais sens

# Mode position horizontale ('position') :
DELTA_X_MAX = 8.0            # cm d'ecart lateral par rapport au repos pour braquer a 100%
DEAD_ZONE_X_POS = 0.25       # Ratio zone morte (+/- 2 cm de zone neutre)
TURN_SPAN_PX = 60.0          # Pixels au-dela de la ligne de seuil pour braquer a 100%

# Lignes de seuils visuels de direction pour le HUD (coordonnees normalisees [0.0 - 1.0]) :
SOLO_LEFT_THRESHOLD = 0.44
SOLO_RIGHT_THRESHOLD = 0.56
DUO_P1_LEFT_THRESHOLD = 0.19
DUO_P1_RIGHT_THRESHOLD = 0.31

# --- 2. Traction (Acceleration & Freinage) ---
# cz est la distance en cm entre le visage et la camera
POS_Z_MIN = 70.0             # Distance cm penche en avant (acceleration max)
POS_Z_MAX = 105.0            # Distance cm penche en arriere (freinage)
DEAD_ZONE_Z = 0.20           # Zone morte autour du point de repos



def gravity_deviation(ax, ay, az):
    """Ecart entre la norme de l'acceleration et la gravite (m/s2).

    Vaut ~0 des que le telephone est immobile, QUELLE QUE SOIT son inclinaison.
    C'est donc une mesure du mouvement propre, independante de l'orientation.
    """
    return abs(math.sqrt(ax * ax + ay * ay + az * az) - GRAVITY)


def bind_all(
    osc,
    gyr,
    eye1,
    eye2,
    camera,
    p1_eye1=None,
    p1_eye2=None,
    p1_camera=None,
    p2_camera=None,
):
    """Associe les messages OSC aux capteurs (compatible solo et duo)."""

    # Messages gyroscope smartphone
    osc.bind(b'/multisense/gyroscope/x', lambda *values: gyr.set_x(values[0]))
    osc.bind(b'/multisense/gyroscope/y', lambda *values: gyr.set_y(values[0]))
    osc.bind(b'/multisense/gyroscope/z', lambda *values: gyr.set_z(values[0]))

    # Messages standards (solo ou joueur principal)
    osc.bind(b'/tracker/eyes1/pos_xyz', lambda *values: eye1.pos_x(values[0]))
    osc.bind(b'/tracker/eyes1/pos_xyz', lambda *values: eye1.pos_y(values[1]))
    osc.bind(b'/tracker/eyes2/pos_xyz', lambda *values: eye2.pos_x(values[0]))
    osc.bind(b'/tracker/eyes2/pos_xyz', lambda *values: eye2.pos_y(values[1]))

    osc.bind(b'/tracker/head/pos_xyz', lambda *values: camera.pos_x(values[0]))
    osc.bind(b'/tracker/head/pos_xyz', lambda *values: camera.pos_y(values[1]))     
    osc.bind(b'/tracker/head/pos_xyz', lambda *values: camera.pos_z(values[2]))

    # Messages Duo - Joueur 1 (Direction)
    if p1_eye1 is not None:
        osc.bind(b'/tracker/p1/eyes1/pos_xyz', lambda *values: p1_eye1.pos_x(values[0]))
        osc.bind(b'/tracker/p1/eyes1/pos_xyz', lambda *values: p1_eye1.pos_y(values[1]))
    if p1_eye2 is not None:
        osc.bind(b'/tracker/p1/eyes2/pos_xyz', lambda *values: p1_eye2.pos_x(values[0]))
        osc.bind(b'/tracker/p1/eyes2/pos_xyz', lambda *values: p1_eye2.pos_y(values[1]))
    if p1_camera is not None:
        osc.bind(b'/tracker/p1/head/pos_xyz', lambda *values: p1_camera.pos_x(values[0]))
        osc.bind(b'/tracker/p1/head/pos_xyz', lambda *values: p1_camera.pos_y(values[1]))
        osc.bind(b'/tracker/p1/head/pos_xyz', lambda *values: p1_camera.pos_z(values[2]))

    # Messages Duo - Joueur 2 (Traction / Freinage)
    if p2_camera is not None:
        osc.bind(b'/tracker/p2/head/pos_xyz', lambda *values: p2_camera.pos_x(values[0]))
        osc.bind(b'/tracker/p2/head/pos_xyz', lambda *values: p2_camera.pos_y(values[1]))
        osc.bind(b'/tracker/p2/head/pos_xyz', lambda *values: p2_camera.pos_z(values[2]))
  