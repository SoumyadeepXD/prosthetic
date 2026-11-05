# Jetson Orin Nano Setup Guide (JetPack 6)

## 1. Operating System & Prerequisites
- **Target OS:** NVIDIA JetPack 6.x (Ubuntu 22.04 LTS / aarch64)
- **Python:** Python 3.10+ (standard system interpreter or venv)

### System Packages
```bash
sudo apt-get update && sudo apt-get install -y \
    python3-pip python3-dev python3-venv \
    i2c-tools git build-essential cmake \
    libssl-dev libusb-1.0-0-dev pkg-config \
    libgtk-3-dev libglfw3-dev libgl1-mesa-dev
```

## 2. RealSense D435i Setup (RSUSB Backend)
On NVIDIA JetPack 6, kernel patches for UVC can be complex. Building `librealsense` from source using the `RSUSB` backend (user-space libusb) provides the most reliable depth streaming:

```bash
git clone https://github.com/IntelRealSense/librealsense.git
cd librealsense
git checkout v2.55.1

mkdir build && cd build
cmake .. \
    -DCMAKE_BUILD_TYPE=Release \
    -DFORCE_RSUSB_BACKEND=ON \
    -DBUILD_PYTHON_BINDINGS=ON \
    -DPYTHON_EXECUTABLE=$(which python3) \
    -DBUILD_EXAMPLES=OFF \
    -DBUILD_GRAPHICAL_EXAMPLES=OFF

make -j$(nproc)
sudo make install
sudo ldconfig
```

Verify RealSense camera detection:
```bash
rs-enumerate-devices
```

## 3. Hardware Bus Configuration

### I2C Permissions & Setup
Add the current user to the `i2c` group:
```bash
sudo usermod -aG i2c $USER
```
Check I2C buses (typically `/dev/i2c-7` on Orin Nano dev kit 40-pin header):
```bash
i2cdetect -l
i2cdetect -y -r 7
```
Expected devices on bus 7:
- `0x40` (PCA9685 PWM Controller)
- `0x71` (TCA9548A I2C Multiplexer, A0 strapped to 3.3V)

### UART Configuration
Disable the default Linux serial login console on `/dev/ttyTHS1` (Pins 8 and 10 of 40-pin header):
```bash
sudo systemctl stop nvgetty
sudo systemctl disable nvgetty
sudo usermod -aG dialout $USER
```

---

## 4. Jetson Performance Tuning & Real-Time Setup

To ensure deterministic 100 Hz control loop execution and prevent CPU throttling:

1. **Set Max Performance Mode (15W MAXN)**:
   ```bash
   sudo nvpmodel -m 0
   sudo jetson_clocks
   ```
2. **Apply Hardware Udev Rules**:
   ```bash
   sudo ./scripts/setup_udev_rules.sh
   ```

---

## 5. Automated Installation & Build

Run the master installation script:
```bash
./scripts/install.sh
```
This script installs all system packages, builds Python dependencies inside `.venv`, sets up udev rules, and runs the pre-flight verification test suite (96 tests passing).

---

## 6. End-to-End Bringup Sequence

Follow this order when deploying physical hardware:

1. **Flash ESP32 Firmware**:
   ```bash
   ./scripts/flash_esp32.sh /dev/ttyUSB0
   ```
2. **Execute Master Bench Calibration**:
   ```bash
   python3 tools/calibration/calibrate_system.py
   ```
   Follow interactive wizard prompts for Servos, AS5600 Encoders, FSR402 Fingertips, MyoWare EMG, and RealSense D435i.
3. **Execute Hardware-In-The-Loop (HIL) Qualification**:
   ```bash
   python3 tools/bench/hil_system_check.py
   ```
   Ensures all 6 hardware subsystems are operational and verified before arming.
4. **Launch Main Controller**:
   ```bash
   # Physical hardware mode (interactive dashboard):
   ./scripts/run_vapa.sh

   # Or in offline simulation / mock mode:
   ./scripts/run_vapa.sh --mock
   ```

---

## 7. Production Systemd Service

To configure VAPA as a managed background system service on the prosthesis:

```bash
# Copy service definition
sudo cp scripts/systemd/vapa.service /etc/systemd/system/
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable vapa.service

# Start service immediately
sudo systemctl start vapa.service

# View live telemetry logs
journalctl -u vapa.service -f
```
