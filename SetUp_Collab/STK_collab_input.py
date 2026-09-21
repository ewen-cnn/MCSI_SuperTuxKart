###############################################################################
## Global libs
import math
import socket
import sys
import threading
import time
import serial
from collections import deque

from oscpy.server import OSCThreadServer


from sensorStates import vibrationSensor, MuscleSensor
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

SERIAL_PORT = '/dev/ttyUSB0'                  # port serie a saisir dans MultiSense Serial
BAUDRATE= 115200
TIMEOUT=1

CAPTEURS = { 'vibrationSensor', 'MuscleSensor' }

def main():
    vs= vibrationSensor()
    ms= MuscleSensor()

    debug = '-d' in sys.argv or '--debug' in sys.argv
    # --- MultiSense Serial ----------------------------------------------------
    serialPort = serial.Serial(SERIAL_PORT, BAUDRATE, TIMEOUT, debug=debug)
    
    brut = serialPort.readline()
    print("Serial port opened: ")
    if brut.endswith(b'\n'):
        line = brut.decode('utf-8', errors='replace').strip()
        nom, sep, valeur = line.partition(':')
        if not sep:
            return None, None
        return nom.strip(), valeur.strip()    
    elif nom == 'vibrationSensor':
        if valeur == 1:
            if vs.state == 1:
                print("Double vibration detected")
                return None
            else :
                vs.state == 1
                print("Nouvelle vibration detected")
            
                
        else:
            print("No vibration detected")

    elif nom == 'MuscleSensor':
        ms.state1, ms.state2 = map(int, valeur.split(','))
    serial.close()