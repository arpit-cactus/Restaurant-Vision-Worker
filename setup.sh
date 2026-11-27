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

step() {
    echo -e "${BOLD}${BLUE}==>${RESET} ${BOLD}$1${RESET}"
}

ok() {
    echo -e "${GREEN}✓${RESET} $1"
}

warn() {
    echo -e "${YELLOW}!${RESET} $1"
}

fail() {
    echo -e "${RED}✗${RESET} $1" >&2
    exit 1
}

# ---------------------------------------------------------------------------
# 1. Python interpreter
# ---------------------------------------------------------------------------
step "Checking Python interpreter"
if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
else
    fail "python3 not found. Install Python 3.10+ and re-run this script."
fi
PY_VERSION="$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
ok "Found Python $PY_VERSION ($PYTHON_BIN)"

# ---------------------------------------------------------------------------
# 2. Virtual environment
# ---------------------------------------------------------------------------
if [ -f "$VENV_PYTHON" ]; then
    ok "Virtual environment already exists at .venv"
else
    step "Creating virtual environment (.venv)"
    "$PYTHON_BIN" -m venv "$VENV_DIR" || fail "Failed to create virtual environment"
    ok "Virtual environment created"
fi

# Sanity check: the venv python must actually run
if ! "$VENV_PYTHON" --version >/dev/null 2>&1; then
    warn "Existing .venv appears broken — recreating it"
    rm -rf "$VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR" || fail "Failed to recreate virtual environment"
fi

# ---------------------------------------------------------------------------
# 3. Dependencies
# ---------------------------------------------------------------------------
step "Installing dependencies from requirements.txt"
"$VENV_PYTHON" -m pip install --upgrade pip >/dev/null
"$VENV_PYTHON" -m pip install -r requirements.txt || fail "pip install failed"
ok "Dependencies installed"

# ---------------------------------------------------------------------------
# 4. Environment file
# ---------------------------------------------------------------------------
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        ok "Created .env from .env.example"
    else
        warn "No .env or .env.example found — worker will use built-in defaults"
    fi
else
    ok ".env already present"
fi

# ---------------------------------------------------------------------------
# 5. Unit tests
# ---------------------------------------------------------------------------
if [ -d "tests" ]; then
    step "Running unit tests"
    if "$VENV_PYTHON" -m pytest -q; then
        ok "All tests passed"
    else
        warn "Some tests failed — continuing anyway (worker can still start)"
    fi
else
    warn "No tests/ directory found — skipping test suite"
fi

# ---------------------------------------------------------------------------
# 6. Launch worker
# ---------------------------------------------------------------------------
if [ -f ".env" ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

echo -e "${BOLD}${BLUE}===================================================${RESET}"
echo -e "${BOLD}${BLUE}   Starting TableSense Computer Vision Worker      ${RESET}"
echo -e "${BOLD}${BLUE}   API Target: ${TS_API_URL:-http://127.0.0.1:8000}${RESET}"
echo -e "${BOLD}${BLUE}===================================================${RESET}"

exec "$VENV_PYTHON" -m app.main "$@"
