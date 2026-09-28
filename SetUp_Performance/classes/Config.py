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
ACC_X_MIN, ACC_X_MAX = -3, 3    # pencher a gauche / a droite
ACC_Y_MIN, ACC_Y_MAX = -7,-3    # pencher en avant / en arriere
INVERT_ACC_Y = True
    
# --- Reglages de l'interaction ----------------------------------------------
# Zone morte autour du centre, dans [0, 1] apres normalisation.
DEAD_ZONE_X = 0.20
DEAD_ZONE_Y = 0.20

TOUCH_TIMEOUT  = 0.40   # sans message pad pendant ce delai -> doigt leve
SENSOR_TIMEOUT = 0.50   # sans message d'un capteur -> capteur eteint

# --- Source de la direction -------------------------------------------------
STEERING_SOURCE = 'tilt'

# ---  double-tap -> FIRE -----------------------------------------
FIRE_HOLD        = 0.12     # maintien de la touche espace (s)
RESCUE_HOLD      = 0.12     # maintien de la touche retour arriere (s)
NITRO_HOLD       = 0.12     # maintien de la touche nitro (s)
TAP_MIN_DURATION = 0.03     # en dessous, c'est un rebond du pad, pas un tap
TAP_MAX_DURATION = 0.25     # au-dela, c'est un appui maintenu, pas un tap
DOUBLE_TAP_DELAY = 0.30     # ecart maxi entre les deux taps

# --- Mouvement tête -> RESCUE -----------------------------
CAMERA_X_SHAKE_THRESHOLD = 3 # Différence x min perçu par la caméra lors de la rotation de la tête 
CAMERA_SHAKE_MIN_SAMPLES = 2 # nb d'echantillons rapides dans la fenetre
CAMERA_SHAKE_MIN_REVERSALS   = 1     # nb d'inversions de sens : c'est le va-et-vient

SHAKE_WINDOW          = 0.60  # fenetre d'observation
SHAKE_MIN_SAMPLES     = 3     # nb d'echantillons rapides dans la fenetre
SHAKE_MIN_REVERSALS   = 2     # nb d'inversions de sens : c'est le va-et-vient
RESCUE_COOLDOWN       = 2.00  # une secousse = un seul RESCUE
SHAKE_LOCKOUT         = 1.00  # apres un shake, on ignore l'inclinaiso

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


JOYSTICK_RADIUS = 0.50  # deplacement (en unites pad) pour atteindre le maximum


