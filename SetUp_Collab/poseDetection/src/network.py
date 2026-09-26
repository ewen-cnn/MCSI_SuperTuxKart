import socket
from typing import Set

from config import NetworkConfig


class STKClient:
    """Sends UDP press/release commands to SuperTuxKart."""

    def __init__(self, config: NetworkConfig = NetworkConfig()):
        self.config = config
        self.address = (self.config.host, self.config.port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.active_actions: Set[str] = set()

    def send_command(self, cmd: str):
        try:
            self.sock.sendto(cmd.encode("utf-8"), self.address)
        except Exception as e:
            print(f"[UDP Warning] Failed to send {cmd}: {e}")

    def update(self, current_actions: Set[str]):
        """Diffs new actions with active actions, sending press (P_) and release (R_) commands."""
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


def main():
    import time

    cfg = NetworkConfig()
    print(f"Testing STKClient on {cfg.host}:{cfg.port}...")
    with STKClient(cfg) as client:
        client.update({"ACCELERATE"})
        time.sleep(0.5)
        client.update({"ACCELERATE", "LEFT"})
        time.sleep(0.5)
        client.update(set())
    print("Network test complete.")


if __name__ == "__main__":
    main()
