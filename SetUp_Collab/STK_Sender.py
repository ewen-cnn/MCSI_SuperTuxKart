import socket

class STKSender:
    """Envoie les commandes texte (P_LEFT, R_LEFT, ...) en UDP au serveur STK."""

    def __init__(self, address, debug=False):
        self.address = address
        self.debug = debug
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, command):
        self.socket.sendto(command.encode('utf-8'), self.address)
        if self.debug:
            print('\t' + command)