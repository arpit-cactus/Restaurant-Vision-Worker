#!/usr/bin/env bash
set -e

# Change directory to the script's location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Color formatting
BOLD="\033[1m"
GREEN="\033[0;32m"
BLUE="\033[0;34m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
RESET="\033[0m"

echo -e "${BOLD}${BLUE}===================================================${RESET}"
echo -e "${BOLD}${BLUE}   TableSense / Camsense CV Worker Setup & Start   ${RESET}"
echo -e "${BOLD}${BLUE}===================================================${RESET}"

# 1. Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[ERROR] python3 could not be found. Please install Python 3.10+ first.${RESET}"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "${GREEN}✓ Found Python ${PYTHON_VERSION}${RESET}"

# 2. Virtual Environment Setup
VENV_DIR="$SCRIPT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python3"

if [ ! -d "$VENV_DIR" ] || [ ! -f "$VENV_PYTHON" ]; then
    echo -e "${YELLOW}→ Initializing virtual environment (.venv)...${RESET}"
    rm -rf "$VENV_DIR"
    python3 -m venv "$VENV_DIR"
    echo -e "${GREEN}✓ Virtual environment created.${RESET}"
fi

# 3. Install & Update Dependencies
echo -e "${YELLOW}→ Verifying dependencies from requirements.txt...${RESET}"
"$VENV_PYTHON" -m pip install -r requirements.txt --quiet
echo -e "${GREEN}✓ Dependencies verified.${RESET}"

# 4. Environment File Setup
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo -e "${YELLOW}→ Creating .env from .env.example...${RESET}"
        cp .env.example .env
        echo -e "${GREEN}✓ .env file created.${RESET}"
    else
        echo -e "${YELLOW}→ Creating default .env file...${RESET}"
        cat <<EOF > .env
TS_API_URL=http://127.0.0.1:8000
TS_WORKER_TOKEN=dev_worker_token_secret_12345
TS_HEARTBEAT_INTERVAL_SEC=15
TS_CONFIG_POLL_INTERVAL_SEC=30
TS_SQLITE_PATH=/tmp/tablesense_worker_queue.db
TS_SAMPLE_FPS=10.0
TS_SIMULATION_MODE=true
EOF
        echo -e "${GREEN}✓ Default .env file created.${RESET}"
    fi
fi

# 5. Run quick self-test suite
echo -e "${YELLOW}→ Running self-test suite...${RESET}"
"$VENV_PYTHON" -m pytest -q
echo -e "${GREEN}✓ All worker unit tests passed.${RESET}"

# 6. Start CV Worker Engine
echo -e "${BOLD}${GREEN}===================================================${RESET}"
echo -e "${BOLD}${GREEN}   Starting TableSense CV Worker Engine...         ${RESET}"
echo -e "${BOLD}${GREEN}===================================================${RESET}"
exec "$VENV_PYTHON" app/main.py
