###############################################################################
## Global libs
import socket
import sys
import threading
import time
import serial
from collections import deque

from STK_Sender import *
from oscpy.server import OSCThreadServer
from KartState import *

from sensorStates import *
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

CAPTEURS = { 'vibrationSensor', 'MuscleSensor' }
SEUIL_CONTRACTION = 40      # a regler apres mesure
SEUIL_RELACHEMENT = 20      # plus bas que le precedent : hysteresis


def main():
    debug = '-d' in sys.argv or '--debug' in sys.argv

    sender = STKSender(STK_SERVER_ADDRESS, debug=debug)
    kart = KartState(sender, debug=debug)
    muscle_contracte = False

    with serial.Serial(SERIAL_PORT, BAUDRATE, timeout=TIMEOUT) as serialPort:
        serialPort.reset_input_buffer()
        print("Lecture de", SERIAL_PORT)

        try:
            while True:
                brut = serialPort.readline()
                if not brut.endswith(b'\n'):
                    continue                    # timeout : ligne incomplete

                nom = brut.decode('utf-8', errors='replace').strip()


                if nom == 'vibrationSensor':
                    kart.fire()
                    if debug:
                        print(GREEN + '\tchoc -> FIRE' + WHITE)

                elif nom == 'muscleSensor':
                    kart.set_nitro(True)
                    if debug:
                        print(RED + '\tchoc -> FIRE' + WHITE)

        except KeyboardInterrupt:
            pass
        finally:
            kart.release_all()
            print()
            print('STK collab input stopped')

if __name__ == '__main__':
    main()
