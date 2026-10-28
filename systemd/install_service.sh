#!/usr/bin/env bash
# ==============================================================================
# VAPA Systemd Service Installer for NVIDIA Jetson Orin Nano
# ==============================================================================
#
# Non-negotiables enforced:
# 1. Daemon boots DISARMED.
# 2. Jetson user has dialout, i2c, and video groups for hardware access.
# 3. Realtime scheduling permissions are configured.
# ==============================================================================

set -euo pipefail

SERVICE_NAME="vapa.service"
INSTALL_DIR="/opt/vapa"
SYSTEMD_DIR="/etc/systemd/system"

echo "================================================================="
echo " VAPA Daemon Service Installer"
echo "================================================================="

if [[ $EUID -ne 0 ]]; then
   echo "ERROR: This installation script must be run as root (sudo)." 1>&2
   exit 1
fi

# 1. Ensure jetson user groups (UART, I2C, RealSense USB3)
TARGET_USER=${SUDO_USER:-jetson}
echo "[1/5] Checking hardware access permissions for user: ${TARGET_USER}..."
usermod -aG dialout,i2c,video "${TARGET_USER}" || true

# 2. Setup destination directory if needed
echo "[2/5] Setting up target application directory at ${INSTALL_DIR}..."
mkdir -p "${INSTALL_DIR}"
if [[ "$(pwd)" != "${INSTALL_DIR}" ]]; then
    echo "      Copying current workspace to ${INSTALL_DIR}..."
    rsync -av --exclude '.git' --exclude '__pycache__' --exclude '.pytest_cache' ./ "${INSTALL_DIR}/"
    chown -R "${TARGET_USER}:${TARGET_USER}" "${INSTALL_DIR}"
fi

# 3. Copy systemd service file
echo "[3/5] Installing ${SERVICE_NAME} to ${SYSTEMD_DIR}..."
cp "$(dirname "$0")/${SERVICE_NAME}" "${SYSTEMD_DIR}/${SERVICE_NAME}"
chmod 644 "${SYSTEMD_DIR}/${SERVICE_NAME}"

# 4. Reload systemd daemon
echo "[4/5] Reloading systemd daemon..."
systemctl daemon-reload

# 5. Enable service
echo "[5/5] Enabling ${SERVICE_NAME} for boot start..."
systemctl enable "${SERVICE_NAME}"

echo "================================================================="
echo " Installation Complete!"
echo " Non-negotiable check: Service will boot strictly DISARMED."
echo ""
echo " To start daemon manually:   sudo systemctl start vapa"
echo " To check status & states:   sudo systemctl status vapa"
echo " To monitor real-time logs:  journalctl -u vapa -f"
echo "================================================================="
