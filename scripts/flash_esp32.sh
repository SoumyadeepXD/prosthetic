#!/usr/bin/env bash
# VAPA ESP32 Safety Supervisor Firmware Build & Flash Script
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FIRMWARE_DIR="$REPO_ROOT/firmware/esp32"

echo "=========================================================="
echo "    VAPA ESP32 Safety Supervisor Build & Flash Tool       "
echo "=========================================================="

# Check for PlatformIO
if ! command -v pio &> /dev/null; then
    echo "PlatformIO (pio) not found in PATH."
    echo "Attempting to locate in virtual environment..."
    if [ -f "$REPO_ROOT/.venv/bin/pio" ]; then
        export PATH="$REPO_ROOT/.venv/bin:$PATH"
    else
        echo "Installing PlatformIO in current Python environment..."
        pip install platformio
    fi
fi

# Detect serial port
PORT="${1:-}"
if [ -z "$PORT" ]; then
    echo "Detecting connected ESP32 serial ports..."
    DETECTED_PORT=$(pio device list --serial 2>/dev/null | grep -E "(/dev/ttyUSB|/dev/ttyACM|/dev/cu.usbserial|/dev/cu.SLAB_USBtoUART|/dev/cu.wchusbserial)" | head -n 1 | awk '{print $1}' || true)
    if [ -n "$DETECTED_PORT" ]; then
        PORT="$DETECTED_PORT"
        echo "Found ESP32 on port: $PORT"
    else
        echo "No serial port automatically detected."
        echo "Usage: ./scripts/flash_esp32.sh [PORT]"
        echo "Example: ./scripts/flash_esp32.sh /dev/ttyUSB0"
        exit 1
    fi
fi

echo ""
echo "[Step 1/3] Running Native Supervisor Unit Tests on Host..."
pio test -d "$FIRMWARE_DIR" -e native || {
    echo "ERROR: Native firmware tests failed! Refusing to flash real hardware." >&2
    exit 1
}

echo ""
echo "[Step 2/3] Compiling ESP32 FreeRTOS Firmware (Target: esp32dev)..."
pio run -d "$FIRMWARE_DIR" -e esp32dev

echo ""
echo "[Step 3/3] Uploading Firmware to ESP32 on $PORT..."
pio run -d "$FIRMWARE_DIR" -e esp32dev -t upload --upload-port "$PORT"

echo ""
echo "=========================================================="
echo "SUCCESS: ESP32 Safety Supervisor flashed successfully!"
echo "Starting serial monitor at 460,800 baud (Ctrl+C to exit)..."
echo "=========================================================="
pio device monitor -d "$FIRMWARE_DIR" -b 460800 --port "$PORT"
