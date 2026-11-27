#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

BOLD="\033[1m"
GREEN="\033[0;32m"
BLUE="\033[0;34m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
RESET="\033[0m"

VENV_DIR="$SCRIPT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python3"

# Ensure setup was run
if [ ! -d "$VENV_DIR" ] || [ ! -f "$VENV_PYTHON" ]; then
    echo -e "${YELLOW}Virtual environment not found. Running setup.sh...${RESET}"
    ./setup.sh
fi

# Load .env variables if present
if [ -f ".env" ]; then
    echo -e "${GREEN}✓ Loading environment from .env${RESET}"
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

echo -e "${BOLD}${BLUE}===================================================${RESET}"
echo -e "${BOLD}${BLUE}   Starting TableSense Computer Vision Worker      ${RESET}"
echo -e "${BOLD}${BLUE}   API Target: ${TS_API_URL:-http://127.0.0.1:8000}${RESET}"
echo -e "${BOLD}${BLUE}===================================================${RESET}"

# Execute CV Worker
exec "$VENV_PYTHON" -m app.main "$@"
