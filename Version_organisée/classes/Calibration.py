from classes.SensorState import PadState, Vector3State
from oscpy.server import OSCThreadServer
import socket
import threading
import time


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

TOUCH_TIMEOUT  = 0.05   # sans message pad pendant ce delai -> doigt leve

###############################################################################
########################## Mode calibration ###################################  
###############################################################################
#         
def run_calibration():
    """Affiche en direct les valeurs brutes des trois capteurs."""
    pad = PadState()
    acc = Vector3State()
    gyr = Vector3State()
    bounds = {'xmin': float('inf'), 'xmax': float('-inf'),
              'ymin': float('inf'), 'ymax': float('-inf'),
              'gyr': 0.0}

    osc = OSCThreadServer()
    osc.listen(address=OSC_LISTEN_IP, port=OSC_LISTEN_PORT, default=True)
    bind_all(osc, pad, acc, gyr)

    print()
    print('Mode calibration - Ctrl+C pour arreter')
    print('  1. touche les 4 coins du pad')
    print('  2. penche le telephone a droite : verifie que acc x devient positif')
    print('  3. incline vivement pour piloter : note le pic de gyr x (a NE PAS depasser)')
    print('  4. secoue le telephone : note le pic de gyr x (a depasser largement)')
    print('Ecoute OSC sur {}:{}'.format(OSC_LISTEN_IP, OSC_LISTEN_PORT))
    print()
    try:
        while True:
            x, y, page = pad.snapshot()
            ax, ay, az, aage = acc.snapshot()
            gx, gy, gz, gage = gyr.snapshot()

            ligne = ''
            if x is not None:
                bounds['xmin'] = min(bounds['xmin'], x)
                bounds['xmax'] = max(bounds['xmax'], x)
                bounds['ymin'] = min(bounds['ymin'], y)
                bounds['ymax'] = max(bounds['ymax'], y)
                ligne += 'pad {:+.2f} {:+.2f} [{:+.2f},{:+.2f}]x[{:+.2f},{:+.2f}] {} | '.format(
                    x, y, bounds['xmin'], bounds['xmax'],
                    bounds['ymin'], bounds['ymax'],
                    'touche ' if page < TOUCH_TIMEOUT else 'relache')
            if ax is not None:
                ligne += 'acc {:+.2f} {:+.2f} {:+.2f} | '.format(ax, ay, az)
            if gx is not None:
                bounds['gyr'] = max(bounds['gyr'], abs(gx))
                ligne += 'gyr x {:+6.2f} rad/s  pic |x| {:5.2f}'.format(gx, bounds['gyr'])
            if ligne:
                print('\r' + ligne + '   ', end='')

            time.sleep(1.0 / 30)
    except KeyboardInterrupt:
        print()
        print()
        print('Recopie ces valeurs dans le script :')
        print('    PAD_X_MIN, PAD_X_MAX  = {:.3f}, {:.3f}'.format(
            bounds['xmin'], bounds['xmax']))
        print('    PAD_Y_MIN, PAD_Y_MAX  = {:.3f}, {:.3f}'.format(
            bounds['ymin'], bounds['ymax']))
        print('    GYR_X_SHAKE_THRESHOLD = {:.1f}   (~70 % du pic observe : {:.2f} rad/s)'.format(
            bounds['gyr'] * 0.7, bounds['gyr']))
    finally:
        osc.stop()
