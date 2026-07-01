#!/usr/bin/env bash
# =============================================================================
# initiate.sh — mycoSupervised environment setup
# =============================================================================
#
# PURPOSE
#   One-time (idempotent, safe to re-run) setup so that experiment.sh / build.sh
#   and the Arduino serial logger have everything they need, on either Fedora
#   Linux or Windows (via Git Bash / WSL — this is a bash script, so it needs
#   one of those to run on Windows in the first place).
#
#   Checks / installs:
#     1. python3 (Fedora: dnf install; Windows: prints a manual install link,
#        since installing system software on Windows from bash is unreliable)
#     2. pip, inside a project-local virtual environment at .venv/ so nothing
#        is installed into the system Python (avoids Fedora's PEP 668
#        "externally-managed-environment" pip error)
#     3. pyserial, inside that same .venv — required by the Arduino logging
#        scripts in user_provided/arduino/01_stepper_motor/ (NOT required by
#        experiment.sh/build.sh themselves, which use only the Python standard
#        library)
#     4. On Fedora: checks whether the current user is in the group that owns
#        /dev/ttyUSB* / /dev/ttyACM* (usually "dialout"), since without that,
#        the logger cannot open the Arduino serial port without sudo
#     5. Prints a manual checklist for the Arduino IDE side (board support +
#        libraries), which cannot be installed from a shell script
#
# USAGE
#   From the repo root:
#     bash user_provided/makefile/initiate.sh
#
# AFTER RUNNING
#   Use the venv's Python for the logger:
#     .venv/bin/python user_provided/arduino/01_stepper_motor/logging_sht30_bme688_bme688_as7341.py   (Linux/Git Bash)
#     .venv/Scripts/python.exe ...                                                                     (Windows, cmd/PowerShell)
#   experiment.sh / build.sh can keep using system python3 (stdlib only), or:
#     PYTHON=.venv/bin/python bash user_provided/makefile/experiment.sh
# =============================================================================

set -euo pipefail

# ── Resolve paths relative to this script's location ─────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV_DIR="$REPO_ROOT/.venv"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║     mycoSupervised  —  initiate          ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "  Repo: $REPO_ROOT"
echo ""

# ── Detect platform ────────────────────────────────────────────────────────────
UNAME_S="$(uname -s 2>/dev/null || echo unknown)"
case "$UNAME_S" in
    Linux*)                         PLATFORM="linux" ;;
    MINGW*|MSYS*|CYGWIN*)           PLATFORM="windows" ;;
    Darwin*)                        PLATFORM="macos" ;;
    *)                              PLATFORM="unknown" ;;
esac
echo "  Detected platform: $PLATFORM ($UNAME_S)"
echo ""

# ── Step 1: ensure a python3 interpreter exists ───────────────────────────────
echo "[ 1 / 4 ]  Checking for Python 3 …"

find_python() {
    for cand in python3 python; do
        if command -v "$cand" &>/dev/null; then
            if "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' &>/dev/null; then
                echo "$cand"
                return 0
            fi
        fi
    done
    return 1
}

if SYSTEM_PYTHON="$(find_python)"; then
    echo "           Found: $SYSTEM_PYTHON ($("$SYSTEM_PYTHON" --version 2>&1))"
else
    echo "           No suitable Python 3 (>=3.8) found."
    if [ "$PLATFORM" = "linux" ]; then
        if command -v dnf &>/dev/null; then
            echo "           Installing via dnf (requires sudo) …"
            sudo dnf install -y python3 python3-pip
            SYSTEM_PYTHON="$(find_python)" || { echo "           dnf install did not produce a usable python3. Aborting."; exit 1; }
            echo "           Installed: $SYSTEM_PYTHON ($("$SYSTEM_PYTHON" --version 2>&1))"
        else
            echo "           dnf not found — install Python 3 manually for your distro, then re-run."
            exit 1
        fi
    elif [ "$PLATFORM" = "windows" ]; then
        echo "           Install Python 3 manually on Windows, then re-run this script:"
        echo "             - https://www.python.org/downloads/windows/  (check \"Add python.exe to PATH\")"
        echo "             - or: winget install Python.Python.3"
        exit 1
    else
        echo "           Install Python 3 manually for your platform, then re-run."
        exit 1
    fi
fi
echo ""

# ── Step 2: create/refresh a project-local virtual environment ───────────────
echo "[ 2 / 4 ]  Setting up virtual environment at $VENV_DIR …"
if [ ! -d "$VENV_DIR" ]; then
    "$SYSTEM_PYTHON" -m venv "$VENV_DIR"
    echo "           Created."
else
    echo "           Already exists — reusing."
fi

if [ -x "$VENV_DIR/bin/python" ]; then
    VENV_PYTHON="$VENV_DIR/bin/python"
elif [ -x "$VENV_DIR/Scripts/python.exe" ]; then
    VENV_PYTHON="$VENV_DIR/Scripts/python.exe"
else
    echo "           Could not find a python executable inside the venv. Aborting."
    exit 1
fi
echo "           venv Python: $VENV_PYTHON ($("$VENV_PYTHON" --version 2>&1))"
echo ""

# ── Step 3: install Python dependencies into the venv ─────────────────────────
echo "[ 3 / 4 ]  Installing Python dependencies (pyserial) into the venv …"
"$VENV_PYTHON" -m pip install --upgrade pip --quiet
"$VENV_PYTHON" -m pip install --upgrade pyserial --quiet
echo "           $("$VENV_PYTHON" -m pip show pyserial | grep -E '^(Name|Version):' | tr '\n' ' ')"
echo ""
echo "           Note: experiment.sh / build.sh only need the Python standard"
echo "           library and can keep using system Python. pyserial is only"
echo "           needed to run the Arduino logging scripts."
echo ""

# ── Step 4: platform-specific serial port access checks ──────────────────────
echo "[ 4 / 4 ]  Serial port access …"
if [ "$PLATFORM" = "linux" ]; then
    SERIAL_GROUP=""
    for g in dialout uucp; do
        if getent group "$g" &>/dev/null; then SERIAL_GROUP="$g"; break; fi
    done
    if [ -n "$SERIAL_GROUP" ]; then
        if id -nG "$USER" | grep -qw "$SERIAL_GROUP"; then
            echo "           $USER is already in the '$SERIAL_GROUP' group — serial ports should be accessible."
        else
            echo "           $USER is NOT in the '$SERIAL_GROUP' group, which usually owns /dev/ttyUSB*/ttyACM*."
            echo "           Run this once, then log out and back in:"
            echo "             sudo usermod -aG $SERIAL_GROUP $USER"
        fi
    else
        echo "           Could not detect the serial-port group (dialout/uucp) on this system — check"
        echo "           'ls -l /dev/ttyUSB0' (or ttyACM0) permissions manually once the Arduino is plugged in."
    fi
elif [ "$PLATFORM" = "windows" ]; then
    echo "           On Windows, plug in the Arduino and confirm its COM port number in Device"
    echo "           Manager (Ports (COM & LPT)) — no driver/group setup is normally required."
fi
echo ""

# ── Manual checklist: Arduino IDE side ────────────────────────────────────────
echo "  Arduino IDE checklist (manual — not scriptable from here):"
echo "    [ ] Arduino IDE installed"
echo "    [ ] Required libraries installed via Library Manager:"
echo "          - Adafruit SHT31 Library"
echo "          - Adafruit BME680 Library"
echo "          - DFRobot AS7341 Library"
echo "          - Wire (built-in, no install needed)"
echo "    [ ] user_provided/arduino/01_stepper_motor/01_stepper_motor.ino uploaded to the board"
echo ""

echo "  ✓  Initiate complete."
echo ""
