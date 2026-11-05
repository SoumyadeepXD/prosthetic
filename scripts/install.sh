#!/usr/bin/env bash
# VAPA Master System Installer for NVIDIA Jetson Orin Nano (Ubuntu 22.04 / JetPack 6)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=========================================================="
echo "    VAPA System Installation: Jetson Orin Nano / Linux    "
echo "=========================================================="

echo "[1/5] Updating package lists & installing Linux system dependencies..."
sudo apt-get update -y
sudo apt-get install -y \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    cmake \
    git \
    pkg-config \
    libi2c-dev \
    i2c-tools \
    v4l-utils \
    libssl-dev \
    libusb-1.0-0-dev \
    libudev-dev \
    libgtk-3-dev \
    libglfw3-dev \
    libgl1-mesa-dev

echo "[2/5] Installing hardware udev rules..."
sudo "$SCRIPT_DIR/setup_udev_rules.sh"

echo "[3/5] Initializing Python 3.10+ virtual environment..."
cd "$REPO_ROOT"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

# Activate venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel

echo "[4/5] Installing VAPA Python package and dependencies..."
pip install -e ".[dev]"
pip install platformio

echo "[5/5] Executing pre-flight mock test suite..."
pytest

echo ""
echo "=========================================================="
echo "SUCCESS: VAPA Software Stack & Dependencies Installed!"
echo ""
echo "NEXT STEPS FOR OPERATOR:"
echo " 1. Reboot Jetson (or log out) for udev dialout/i2c group permissions to apply."
echo " 2. Flash ESP32:          ./scripts/flash_esp32.sh"
echo " 3. Calibrate Hardware:    python3 tools/calibration/calibrate_system.py"
echo " 4. Run HIL Qualification: python3 tools/bench/hil_system_check.py"
echo " 5. Start VAPA Controller: ./scripts/run_vapa.sh"
echo "=========================================================="
