#!/usr/bin/env bash
# VAPA udev rules configuration script for NVIDIA Jetson Orin Nano / Ubuntu 22.04
set -euo pipefail

echo "=========================================================="
echo "    VAPA Hardware Udev Rules & Device Permission Setup    "
echo "=========================================================="

if [ "$EUID" -ne 0 ]; then
  echo "Error: This script must be run as root (use sudo)." >&2
  exit 1
fi

CURRENT_USER="${SUDO_USER:-$USER}"

echo "[1/4] Adding user '$CURRENT_USER' to dialout, i2c, and video groups..."
usermod -aG dialout "$CURRENT_USER" || true
usermod -aG i2c "$CURRENT_USER" || true
usermod -aG video "$CURRENT_USER" || true

echo "[2/4] Installing UART and ESP32 udev rules..."
cat << 'EOF' > /etc/udev/rules.d/99-vapa-uart.rules
# NVIDIA Jetson Orin Nano 40-Pin Header UART1 (ttyTHS1)
KERNEL=="ttyTHS1", MODE="0666", GROUP="dialout"

# Silicon Labs CP2102 USB-to-UART (ESP32-WROOM-32)
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", MODE="0666", GROUP="dialout", SYMLINK+="vapa_esp32"

# WCH CH340 USB-to-UART (ESP32 clones)
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", MODE="0666", GROUP="dialout", SYMLINK+="vapa_esp32_ch340"
EOF

echo "[3/4] Installing I2C bus udev rules..."
cat << 'EOF' > /etc/udev/rules.d/99-vapa-i2c.rules
# Jetson Orin Nano I2C Buses (including I2C-7 on 40-pin header)
KERNEL=="i2c-[0-9]*", MODE="0666", GROUP="i2c"
EOF

echo "[4/4] Installing Intel RealSense D435i udev rules..."
cat << 'EOF' > /etc/udev/rules.d/99-realsense-libusb.rules
# Intel RealSense D435i Camera
SUBSYSTEMS=="usb", ATTRS{idVendor}=="8086", ATTRS{idProduct}=="0b3a", MODE="0666", GROUP="video"
SUBSYSTEMS=="usb", ATTRS{idVendor}=="8086", ATTRS{idProduct}=="0b07", MODE="0666", GROUP="video"
SUBSYSTEMS=="usb", ATTRS{idVendor}=="8086", ATTRS{idProduct}=="0b35", MODE="0666", GROUP="video"
EOF

echo "Reloading udev rules..."
udevadm control --reload-rules
udevadm trigger

echo "=========================================================="
echo "SUCCESS: VAPA udev rules installed."
echo "NOTE: Log out and log back in (or reboot) for group additions to take effect."
echo "=========================================================="
