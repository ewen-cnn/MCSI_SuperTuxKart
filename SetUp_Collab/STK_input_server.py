#!/usr/bin/env python3
# Michael ORTEGA - 09 jan 2018
# Upgraded for MCSI SuperTuxKart: Dual Backend (Keyboard & Analog Virtual Joystick)

###############################################################################
## Global libs
import sys
import time
import socket
import argparse

HAS_KEYBOARD = False
try:
    import keyboard
    HAS_KEYBOARD = True
except ImportError:
    pass

HAS_EVDEV = False
try:
    import evdev
    from evdev import UInput, ecodes as e, AbsInfo
    HAS_EVDEV = True
except ImportError:
    pass

###############################################################################
## Global vars
GREEN   = '\033[92m'
WHITE   = '\x1b[0m'
BLUE    = '\033[94m'
YELLOW  = '\033[93m'
RED     = '\033[91m'

address = ('localhost', 6006)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(address)

# Bindings clavier standards
keyboard_bindings = {}
if HAS_KEYBOARD:
    keyboard_bindings = {
        'UP':           ('up', keyboard.press_and_release),
        'DOWN':         ('down', keyboard.press_and_release),
        'LEFT':         ('left', keyboard.press_and_release),
        'RIGHT':        ('right', keyboard.press_and_release),
        'SELECT':       ('enter', keyboard.press_and_release),
        'CANCEL':       ('backspace', keyboard.press_and_release),
        'BACK':         ('backspace', keyboard.press_and_release),
        'FIRE':         ('space', keyboard.press_and_release),
        'P_FIRE':       ('space', keyboard.press),
        'R_FIRE':       ('space', keyboard.release),
        'NITRO':        ('n', keyboard.press_and_release),
        'P_NITRO':      ('n', keyboard.press),
        'R_NITRO':      ('n', keyboard.release),
        'P_SKIDDING':   ('v', keyboard.press),
        'R_SKIDDING':   ('v', keyboard.release),
        'P_LOOKBACK':   ('b', keyboard.press),
        'R_LOOKBACK':   ('b', keyboard.release),
        'RESCUE':       ('backspace', keyboard.press_and_release),
        'P_RESCUE':     ('backspace', keyboard.press),
        'R_RESCUE':     ('backspace', keyboard.release),
        'PAUSE':        ('escape', keyboard.press_and_release),
        'P_UP':         ('up', keyboard.press),
        'R_UP':         ('up', keyboard.release),
        'P_DOWN':       ('down', keyboard.press),
        'R_DOWN':       ('down', keyboard.release),
        'P_LEFT':       ('left', keyboard.press),
        'R_LEFT':       ('left', keyboard.release),
        'P_RIGHT':      ('right', keyboard.press),
        'R_RIGHT':      ('right', keyboard.release),
        'P_ACCELERATE': ('up', keyboard.press),
        'R_ACCELERATE': ('up', keyboard.release),
        'P_BRAKE':      ('down', keyboard.press),
        'R_BRAKE':      ('down', keyboard.release),
    }


def create_virtual_joystick():
    """Tente d'instancier un gamepad virtuel Linux via evdev /dev/uinput."""
    if not HAS_EVDEV:
        return None, "Module 'evdev' non disponible dans l'environnement."

    cap = {
        e.EV_KEY: [
            e.BTN_A,       # South button (Fire)
            e.BTN_B,       # East button (Nitro)
            e.BTN_X,       # West button (Skid / Drift)
            e.BTN_Y,       # North button (Rescue)
            e.BTN_START,   # Start / Pause
            e.BTN_SELECT,  # Select
            e.BTN_TL,      # Left shoulder
            e.BTN_TR,      # Right shoulder
        ],
        e.EV_ABS: [
            # Direction analogique (Stick gauche X) : [-32767 .. +32767]
            (e.ABS_X, AbsInfo(value=0, min=-32767, max=32767, fuzz=16, flat=128, resolution=0)),
            # Traction analogique (Stick gauche Y) : [-32767 .. +32767] (negatif=avant, positif=arriere)
            (e.ABS_Y, AbsInfo(value=0, min=-32767, max=32767, fuzz=16, flat=128, resolution=0)),
            # Gachette droite Acceleration : [0 .. 1023]
            (e.ABS_GAS, AbsInfo(value=0, min=0, max=1023, fuzz=4, flat=16, resolution=0)),
            (e.ABS_RZ, AbsInfo(value=0, min=0, max=1023, fuzz=4, flat=16, resolution=0)),
            # Gachette gauche Freinage : [0 .. 1023]
            (e.ABS_BRAKE, AbsInfo(value=0, min=0, max=1023, fuzz=4, flat=16, resolution=0)),
            (e.ABS_Z, AbsInfo(value=0, min=0, max=1023, fuzz=4, flat=16, resolution=0)),
        ],
    }
    try:
        ui = UInput(cap, name="SuperTuxKart Virtual Gamepad", version=0x3)
        return ui, None
    except Exception as ex:
        return None, str(ex)


def main():
    parser = argparse.ArgumentParser(description="STK Input Server (Keyboard & Analog Virtual Joystick)")
    parser.add_argument('-d', '--debug', action='store_true', help="Activer le mode debug")
    parser.add_argument(
        '-j', '--joystick', action='store_true',
        help="Activer l'emulation Gamepad/Joystick virtuel (axes analogiques continus)"
    )
    args, unknown = parser.parse_known_args()
    debug = args.debug
    want_joystick = args.joystick or ('-j' in sys.argv) or ('--joystick' in sys.argv)

    joystick = None
    if want_joystick:
        joystick, err = create_virtual_joystick()
        if joystick is not None:
            print(GREEN + "[STK Server] Joystick virtuel cree avec succes : 'SuperTuxKart Virtual Gamepad'" + WHITE)
        else:
            print(YELLOW + f"[STK Server] Impossible d'ouvrir le joystick ({err}). Repli sur le clavier." + WHITE)

    backend_str = "Joystick Virtuel (Analogique)" if joystick else "Clavier (Keystrokes)"
    print()
    print(f'STK input server started [Backend : {backend_str}] ', end='')
    if debug:
        print(GREEN + '(Debug mode)' + WHITE)
    else:
        print()

    stop = False
    try:
        while not stop:
            data, addr = sock.recvfrom(1024)
            if type(data) is bytes:
                data = data.decode("utf-8", errors="replace").replace(',', '').strip()

            if not data:
                continue

            if data == 'STOPSERVEUR':
                stop = True
                continue

            # --- 1. Commandes analogiques continues ---
            if data.startswith('STEER '):
                try:
                    val = float(data.split()[1])
                    clamped = max(-1.0, min(1.0, val))
                    if joystick:
                        axis_x = int(clamped * 32767)
                        joystick.write(e.EV_ABS, e.ABS_X, axis_x)
                        joystick.syn()
                    elif HAS_KEYBOARD:
                        if clamped < -0.20:
                            keyboard.press('left')
                            keyboard.release('right')
                        elif clamped > 0.20:
                            keyboard.press('right')
                            keyboard.release('left')
                        else:
                            keyboard.release('left')
                            keyboard.release('right')
                    if debug:
                        print(BLUE + f"\tSTEER analogique : {clamped:+.2f}" + WHITE)
                except Exception as ex:
                    if debug:
                        print(RED + f"\tErreur STEER : {ex}" + WHITE)
                continue

            if data.startswith('THROTTLE '):
                try:
                    val = float(data.split()[1])
                    clamped = max(-1.0, min(1.0, val))
                    if joystick:
                        if clamped > 0.0:
                            gas = int(clamped * 1023)
                            brake = 0
                        elif clamped < 0.0:
                            gas = 0
                            brake = int(-clamped * 1023)
                        else:
                            gas = 0
                            brake = 0
                        joystick.write(e.EV_ABS, e.ABS_GAS, gas)
                        joystick.write(e.EV_ABS, e.ABS_RZ, gas)
                        joystick.write(e.EV_ABS, e.ABS_BRAKE, brake)
                        joystick.write(e.EV_ABS, e.ABS_Z, brake)
                        # Axe Y (negatif=accel, positif=frein)
                        joystick.write(e.EV_ABS, e.ABS_Y, int(-clamped * 32767))
                        joystick.syn()
                    elif HAS_KEYBOARD:
                        if clamped > 0.15:
                            keyboard.press('up')
                            keyboard.release('down')
                        elif clamped < -0.15:
                            keyboard.press('down')
                            keyboard.release('up')
                        else:
                            keyboard.release('up')
                            keyboard.release('down')
                    if debug:
                        print(BLUE + f"\tTHROTTLE analogique : {clamped:+.2f}" + WHITE)
                except Exception as ex:
                    if debug:
                        print(RED + f"\tErreur THROTTLE : {ex}" + WHITE)
                continue

            # --- 2. Commandes discretes vers Joystick ou Clavier ---
            if joystick:
                # Mapping joystick pour les commandes discretes
                if data == 'P_ACCELERATE':
                    joystick.write(e.EV_ABS, e.ABS_GAS, 1023)
                    joystick.write(e.EV_ABS, e.ABS_Y, -32767)
                    joystick.syn()
                elif data == 'R_ACCELERATE':
                    joystick.write(e.EV_ABS, e.ABS_GAS, 0)
                    joystick.write(e.EV_ABS, e.ABS_Y, 0)
                    joystick.syn()
                elif data == 'P_BRAKE':
                    joystick.write(e.EV_ABS, e.ABS_BRAKE, 1023)
                    joystick.write(e.EV_ABS, e.ABS_Y, 32767)
                    joystick.syn()
                elif data == 'R_BRAKE':
                    joystick.write(e.EV_ABS, e.ABS_BRAKE, 0)
                    joystick.write(e.EV_ABS, e.ABS_Y, 0)
                    joystick.syn()
                elif data == 'P_LEFT':
                    joystick.write(e.EV_ABS, e.ABS_X, -32767)
                    joystick.syn()
                elif data == 'P_RIGHT':
                    joystick.write(e.EV_ABS, e.ABS_X, 32767)
                    joystick.syn()
                elif data in ('R_LEFT', 'R_RIGHT'):
                    joystick.write(e.EV_ABS, e.ABS_X, 0)
                    joystick.syn()
                elif data in ('FIRE', 'P_FIRE'):
                    joystick.write(e.EV_KEY, e.BTN_A, 1)
                    joystick.syn()
                    if data == 'FIRE':
                        time.sleep(0.04)
                        joystick.write(e.EV_KEY, e.BTN_A, 0)
                        joystick.syn()
                elif data == 'R_FIRE':
                    joystick.write(e.EV_KEY, e.BTN_A, 0)
                    joystick.syn()
                elif data in ('NITRO', 'P_NITRO'):
                    joystick.write(e.EV_KEY, e.BTN_B, 1)
                    joystick.syn()
                    if data == 'NITRO':
                        time.sleep(0.04)
                        joystick.write(e.EV_KEY, e.BTN_B, 0)
                        joystick.syn()
                elif data == 'R_NITRO':
                    joystick.write(e.EV_KEY, e.BTN_B, 0)
                    joystick.syn()
                elif data == 'P_SKIDDING':
                    joystick.write(e.EV_KEY, e.BTN_X, 1)
                    joystick.syn()
                elif data == 'R_SKIDDING':
                    joystick.write(e.EV_KEY, e.BTN_X, 0)
                    joystick.syn()
                elif data in ('RESCUE', 'P_RESCUE'):
                    joystick.write(e.EV_KEY, e.BTN_Y, 1)
                    joystick.syn()
                    if data == 'RESCUE':
                        time.sleep(0.04)
                        joystick.write(e.EV_KEY, e.BTN_Y, 0)
                        joystick.syn()
                elif data == 'R_RESCUE':
                    joystick.write(e.EV_KEY, e.BTN_Y, 0)
                    joystick.syn()
                elif data == 'PAUSE':
                    joystick.write(e.EV_KEY, e.BTN_START, 1)
                    joystick.syn()
                    time.sleep(0.04)
                    joystick.write(e.EV_KEY, e.BTN_START, 0)
                    joystick.syn()

                if debug:
                    print(YELLOW + f"\t[Joystick] {data}" + WHITE)

            elif HAS_KEYBOARD and data in keyboard_bindings:
                key_name, func = keyboard_bindings[data]
                func(key_name)
                if debug:
                    print(YELLOW + f"\t[Clavier] {data}" + WHITE)
            else:
                if debug:
                    print(RED + f"\t{data} (Inconnu)" + WHITE)

    finally:
        if joystick:
            try:
                joystick.close()
            except Exception:
                pass
        sock.close()
        print('STK input server stopped')


if __name__ == '__main__':
    main()
