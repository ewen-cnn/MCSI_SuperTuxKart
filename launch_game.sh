#!/usr/bin/env bash
# Starts the keyboard-injection server (UDP :6006) and SuperTuxKart.
# The `keyboard` module needs root on Linux, so only the server runs with sudo.
#
# Usage: STK_RUN=/path/to/run_game.sh ./launch_game.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$ROOT/.venv/bin/python"
STK_RUN="${STK_RUN:-supertuxkart}"

if [[ ! -x "$PYTHON" ]]; then
  echo "Virtual environment not found: run 'python3 -m venv .venv && .venv/bin/pip install -r requirements.txt'" >&2
  exit 1
fi

sudo -v  # ask for the password up front, before backgrounding the server
sudo "$PYTHON" "$ROOT/SetUp_Collab/STK_input_server.py" &
SERVER_PID=$!
trap 'sudo kill "$SERVER_PID" 2>/dev/null || true' EXIT

"$STK_RUN"
