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
- `0x40` (PCA9685)
- `0x71` (TCA9548A multiplexer)

### UART Configuration
Ensure the serial port `/dev/ttyTHS1` (or equivalent UART mapped to 40-pin header pins 8 and 10) is not allocated to a Linux serial login console:
```bash
sudo systemctl stop nvgetty
sudo systemctl disable nvgetty
sudo usermod -aG dialout $USER
```
