#!/usr/bin/env bash
# Launcher for Aura Desktop on Linux / macOS.
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -x "venv/bin/python" ]; then
    python3 -m venv venv
fi

# shellcheck disable=SC1091
source venv/bin/activate

if ! python -c "import PyQt6" >/dev/null 2>&1; then
    pip install --upgrade pip
    pip install -r requirements-desktop.txt
fi

exec python aura_desktop.py "$@"
