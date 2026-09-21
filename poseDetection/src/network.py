import socket


class STKClient:
    def __init__(self, host="localhost", port=6006):
        self.address = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.active_actions = set()

    def send_command(self, cmd: str):
        try:
            self.sock.sendto(cmd.encode("utf-8"), self.address)
        except Exception as e:
            print(f"[UDP Warning] {e}")

    def update(self, current_actions: set):
        for action in current_actions - self.active_actions:
            self.send_command(f"P_{action}")

        for action in self.active_actions - current_actions:
            self.send_command(f"R_{action}")

        self.active_actions = set(current_actions)

    def release_all(self):
        for action in list(self.active_actions):
            self.send_command(f"R_{action}")
        self.active_actions.clear()

    def close(self):
        self.release_all()
        self.sock.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
