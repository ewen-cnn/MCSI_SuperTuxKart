
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

SERIAL_PORT = 'COM6'                  # port serie a saisir dans MultiSense Serial
BAUDRATE= 115200
TIMEOUT=0.1

# ===========================================================================
# PARAMETRES DE CONTROLE DU KART (Configurables ici pour tout le projet)
# ===========================================================================
CAPTEURS = { 'vibrationSensor', 'MuscleSensor' }
SEUIL_CONTRACTION = 40      # a regler apres mesure
SEUIL_RELACHEMENT = 20      # plus bas que le precedent : hysteresis
SENSOR_TIMEOUT = 0.50       # sans message d'un capteur -> capteur eteint

EXPO           = 2.0       # 1.0 = lineaire ; 2.0 = doux au centre, franc aux extremes
SKID_KICKOFF   = 0.15 
SKID_INTO_MAX  = 0.7       # braquage maxi DANS le sens du virage pendant la glisse
LOOP_HZ        = 120     

# Dimensions standard de capture camera (16:9)
FRAME_WIDTH = 640
FRAME_HEIGHT = 360
GRAVITY = 9.81
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
# Distance en cm entre le visage et la camera
DEFAULT_Z_NEUTRAL = 75.0         # Distance neutre initiale (calibrable en jeu via la touche Z)
DEAD_ZONE_Z_CM = 7.0            # Zone morte neutre (+/- 7 cm autour de la position de repos)
DELTA_Z_MAX = 20.0              # Ecart en cm pour pleine acceleration / plein freinage
POS_Z_MIN = 60.0                # Seuil absolu min secours (cm)
POS_Z_MAX = 110.0               # Seuil absolu max secours (cm)
DEAD_ZONE_Z = 0.20              # Zone morte normalisee

# --- 3. Detection d'Objets Colores (Lancer d'objets / Fire) ---
COLOR_DETECTION_ENABLED = True
COLOR_PRESET = "red"            # Presets disponibles : 'red', 'green', 'blue', 'yellow', 'orange', 'custom'

# Plages HSV par defaut pour le mode personnalise ('custom')
COLOR_CUSTOM_LOWER = (0, 100, 70)
COLOR_CUSTOM_UPPER = (10, 255, 255)

# Filtres geometriques pour eliminer les faux positifs (murs, vetements, bruit)
COLOR_MIN_AREA = 300            # Superficie minimale en pixels (evite le bruit de fond)
COLOR_MAX_AREA = 45000          # Superficie maximale en pixels (evite tout l'arriere-plan)
COLOR_MAX_ASPECT_RATIO = 3.5    # Rapport longueur/largeur max (rejette les lignes fines)
COLOR_MIN_SOLIDITY = 0.65       # Compacite contour/enveloppe convexe (rejette formes creuses)
COLOR_MIN_EXTENT = 0.35         # Remplissage par rapport au rectangle englobant

# Filtrage temporel & Anti-rebond (Debounce)
COLOR_COOLDOWN_SECONDS = 1.6    # Delai anti-rafale entre deux tirs d'objets (1.6 secondes)
COLOR_PULSE_DURATION = 0.40     # Duree d'affichage visuel de la banniere FIRE (en secondes)
COLOR_CONFIRM_FRAMES = 3        # Nombre d'images consecutives requises pour valider la detection

TAP_MIN_DURATION = 0.08     # en dessous, c'est un rebond du pad, pas un tap
TAP_MAX_DURATION = 0.40     # au-dela, c'est un appui maintenu, pas un tap
DOUBLE_TAP_DELAY = 0.30     # ecart maxi entre les deux taps

JOYSTICK_RADIUS = 0.50  # deplacement (en unites pad) pour atteindre le maximum

CAMERA_X_SHAKE_THRESHOLD = 3 # Différence x min perçu par la caméra lors de la rotation de la tête 
CAMERA_SHAKE_MIN_SAMPLES = 2 # nb d'echantillons rapides dans la fenetre
CAMERA_SHAKE_MIN_REVERSALS   = 1     # nb d'inversions de sens : c'est le va-et-vient

SHAKE_WINDOW          = 0.60  # fenetre d'observation
SHAKE_MIN_SAMPLES     = 3     # nb d'echantillons rapides dans la fenetre
SHAKE_MIN_REVERSALS   = 2     # nb d'inversions de sens : c'est le va-et-vient
RESCUE_COOLDOWN       = 2.00  # une secousse = un seul RESCUE
SHAKE_LOCKOUT         = 1.00  # apres un shake, on ignore l'inclinaison

CONTINUOUS_PERIOD = 0.05   # duree d'un cycle pressed + released (s)

FIRE_HOLD        = 0.12     # maintien de la touche espace (s)
RESCUE_HOLD      = 0.12     # maintien de la touche retour arriere (s)
NITRO_HOLD       = 0.12     # maintien de la touche nitro (s)