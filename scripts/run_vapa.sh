#!/usr/bin/env bash
# VAPA Master Application Startup Script
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

# Activate venv if present
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

MOCK_MODE=false
for arg in "$@"; do
    if [ "$arg" == "--mock" ]; then
        MOCK_MODE=true
    fi
done

echo "=========================================================="
echo "          VAPA PROSTHETIC ARM RUNTIME CONTROLLER          "
echo "=========================================================="

if [ "$MOCK_MODE" = false ]; then
    echo "OPERATING MODE: [PHYSICAL HARDWARE]"
    echo ""
    echo "Checking physical interfaces on Jetson Orin Nano..."

    # Check UART
    if [ ! -r "/dev/ttyTHS1" ] || [ ! -w "/dev/ttyTHS1" ]; then
        echo "WARNING: /dev/ttyTHS1 is not accessible or missing."
        echo "Check permissions or run: sudo ./scripts/setup_udev_rules.sh"
    else
        echo " -> UART1 (/dev/ttyTHS1): READY"
    fi

    # Check I2C Bus 7
    if [ ! -r "/dev/i2c-7" ] || [ ! -w "/dev/i2c-7" ]; then
        echo "WARNING: /dev/i2c-7 is not accessible or missing."
    else
        echo " -> I2C-7 (/dev/i2c-7): READY"
    fi

    echo ""
    echo "MANDATORY SAFETY REMINDER:"
    echo "1. Emergency Stop button must be in hand."
    echo "2. Wearer skin must be electrically isolated from servo battery power."
    echo "3. System boots strictly DISARMED. Press 'A' in UI to arm once verified."
    echo ""
    read -rp "Ready to launch physical controller? (type 'yes' to proceed): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        echo "Launch cancelled."
        exit 1
    fi

    # Elevate priority if possible (nice -n -10)
    if command -v nice &> /dev/null; then
        echo "Launching with elevated real-time priority (nice -n -10)..."
        exec nice -n -10 python3 -m vapa.app.main "$@"
    else
        exec python3 -m vapa.app.main "$@"
    fi
else
    echo "OPERATING MODE: [OFFLINE MOCK SIMULATION]"
    echo "Launching mock simulation dashboard..."
    exec python3 -m vapa.app.main "$@"
fi
