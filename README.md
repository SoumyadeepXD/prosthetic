# VAPA — Vision-Assisted Prosthetic Arm
**Full Product Development & Physical Prototype Architecture**

[![CI / Pre-Flight Tests](https://img.shields.io/badge/tests-96%20passed%20%28100%25%29-brightgreen)]()
[![Safety Architecture](https://img.shields.io/badge/safety-ISO%2013849%20PL%20d%20%7C%20IEC%2060601--1%20Type%20BF-blue)]()
[![Platform](https://img.shields.io/badge/compute-NVIDIA%20Jetson%20Orin%20Nano%20%2B%20ESP32-orange)]()
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![Hardware](https://img.shields.io/badge/status-physical--prototype--ready-success)]()

VAPA is an advanced multi-modal active transradial robotic prosthetic arm combining dual-processor shared control, biological muscular intent (two-site surface electromyography), closed-loop force and magnetic encoder feedback, and real-time computer vision (RGB-D object classification and distance tracking).

> [!IMPORTANT]
> **SHARED-CONTROL SAFETY NON-NEGOTIABLES:**
> 1. **User Intent Supremacy**: EMG supplies intentional motor control (close, open, hold, mode switch).
> 2. **Vision Context Only**: Vision provides passive contextual assistance (preshape aperture, grip profile, force ceiling). **Vision can NEVER initiate or increase a closing motion.**
> 3. **Instantaneous Open Override**: An intentional EMG OPEN command unconditionally aborts any closing trajectory or grip hold within ≤ 15 ms.
> 4. **Independent ESP32 Supervisor**: The ESP32 supervisor controls PCA9685 `/OE` (GPIO25) and enforces a 250 ms heartbeat timeout, independent of Jetson operating system health.
> 5. **Dual-Layer Power Disconnection**: Physical E-stop switch trips an automotive PROFET high-side switch, disconnecting 6V battery power to all 9 servos in < 1 ms.
> 6. **Biomedical Isolation (IEC 60601-1 Type BF)**: Human skin electrodes and analog ADC circuitry are galvanically isolated by 1.5 kV DC-DC converter and digital I2C isolators.

---

## 1. Hardware & System Architecture

```
                                [ HUMAN OPERATOR ]
                                  |            |
                  (Surface EMG)   |            | (Physical Contact)
                                  v            v
                       +-------------------+  +-------------------+
                       | MyoWare 2.0 (x2)  |  | FSR402 Force (x5) |
                       +-------------------+  +-------------------+
                                  |                      |
             [1.5kV Galvanic]     v (ADS1115 ADC)        v (Analog Pins)
            =============================================================
                       |       ESP32-WROOM-32 SAFETY SUPERVISOR        |
                       | - FreeRTOS Independent Watchdog (350 ms)      |
                       | - Active-Low Hardware OE Control (GPIO25)     |
                       | - Dual-Layer PROFET E-Stop Loop Interlock     |
                       +-----------------------------------------------+
                                          ^          |
                 (50 Hz Heartbeat / CRC)  |          | (100 Hz Sensor Frames)
                                          |          v
            =============================================================
                       |           NVIDIA JETSON ORIN NANO             |
                       | - 100 Hz Deterministic Control Loop           |
                       | - Envelope Normalization & Threshold Decoder  |
                       | - Closed-Loop AS5600 Encoder Monitor          |
                       | - 30 Hz Multiprocess Vision Worker (RealSense)|
                       | - Shared-Control Arbitrator & Slew Limiter    |
                       +-----------------------------------------------+
                                  |                      |
               (I2C-7, Addr 0x40) v                      v (I2C-7, Addr 0x71 Mux)
                       +-------------------+  +-------------------+
                       |  PCA9685 16-Ch    |  | TCA9548A Mux      |
                       |  12-bit PWM Driver|  | 4x AS5600 Encoders|
                       +-------------------+  +-------------------+
                                  |
                                  v (9x Guarded PWM Channels)
            +-----------------------------------------------------------+
            | 5x MG996R Fingers | 3x DS3225 Wrist | 1x DS3218 Forearm   |
            +-----------------------------------------------------------+
```

---

## 2. Master Documentation Index

| Document | Description |
| :--- | :--- |
| **[`docs/FINAL_AUDIT.md`](docs/FINAL_AUDIT.md)** | Comprehensive 9-discipline engineering audit with classified findings (Critical/High/Med/Low). |
| **[`docs/SAFETY_ARCHITECTURE.md`](docs/SAFETY_ARCHITECTURE.md)** | Formal 8-state finite state machine, 14-point fault reaction matrix, and dual-layer cutoff. |
| **[`docs/MECHANICAL_DESIGN.md`](docs/MECHANICAL_DESIGN.md)** | Kinematics, 40mm tendon stroke math, capstan spools, wrist gimbal, and 1,284g mass budget. |
| **[`docs/DECISIONS.md`](docs/DECISIONS.md)** | Architectural Decision Records (ADRs DEC-001 through DEC-016). |
| **[`docs/BENCH_TESTS.md`](docs/BENCH_TESTS.md)** | 10-checkpoint bench bringup protocol for human test operators. |
| **[`docs/SETUP_JETSON.md`](docs/SETUP_JETSON.md)** | JetPack 6 installation, real-time tuning, udev rules, and systemd daemon setup. |
| **[`docs/PROTOCOL.md`](docs/PROTOCOL.md)** | Binary framing specification with CRC16-CCITT-FALSE lookup table. |
| **[`AGENTS.md`](AGENTS.md)** | Hard engineering non-negotiables for AI agents and human contributors. |

---

## 3. Electrical Schematics & BOM

Deliverables located in [`hardware/`](hardware/):
- **Schematics (`hardware/schematics/`)**:
  - `vapa_main.kicad_sch` (Master hierarchical schematic)
  - `power_distribution.kicad_sch` (XT60, 30A fuse, PROFET BTS50015, dual 6V/15A bucks, AP2112K LDO)
  - `esp32_controller.kicad_sch` (ESP32-WROOM-32E, GPIO25 OE pullup, PC817 E-stop, UART2)
  - `servo_controller.kicad_sch` (PCA9685 at 0x40, dual servo power split rails)
  - `emg_interface.kicad_sch` (IEC 60601-1 Type BF isolation barrier, Mornsun B0505S, ISO1540 isolator)
  - `fsr_interface.kicad_sch` (5x 10k 0.1% dividers, 0.1uF filter caps, SP3002 TVS diodes)
  - `encoder_interface.kicad_sch` (TCA9548A at 0x71, 4x AS5600 headers)
- **Wiring Diagrams (`hardware/diagrams/`)**:
  - `complete_wiring_diagram.svg` and high-res `complete_wiring_diagram.png` (2048px)
  - `power_distribution.svg` and `signal_flow.svg`
- **Bill of Materials (`hardware/bom/` & `hardware/mechanical/`)**:
  - `hardware/bom/bill_of_materials.csv` (Electrical BOM with part numbers and specs)
  - `hardware/mechanical/bill_of_materials_mechanical.csv` (Mechanical BOM: inserts, bearings, line)

---

## 4. Software Quick Start & Testing

### Python Environment Setup
```bash
# Clone repository
git clone https://github.com/SoumyadeepXD/prosthetic.git
cd prosthetic

# Create Python 3.10+ virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Run Test Suite (96 Tests Passing)
```bash
# Full test suite (including 21 fault injection and fuzzing tests)
pytest

# Fault injection test suite alone
pytest tests/fault_injection/
```

### Automated Master Calibration Wizard
```bash
# Mock mode (automated simulation verification):
python3 tools/calibration/calibrate_system.py --mock

# Real hardware mode (guided interactive calibration for bench technician):
python3 tools/calibration/calibrate_system.py
```

### Hardware-In-The-Loop (HIL) Qualification Tool
```bash
# Verify all 6 hardware subsystems in mock mode:
python3 tools/bench/hil_system_check.py --mock

# Physical hardware qualification check (requires technician confirmation):
python3 tools/bench/hil_system_check.py
```

### Launch VAPA Controller
```bash
# Run controller in mock mode with terminal ASCII dashboard:
./scripts/run_vapa.sh --mock --headless

# Run controller on real physical Jetson Orin Nano hardware:
./scripts/run_vapa.sh
```

---

## 5. Physical Deployment on Jetson Orin Nano

Follow the automated installation workflow on Ubuntu 22.04 / JetPack 6:

```bash
# 1. Run master system installer (sets up Linux packages, udev rules, Python venv)
./scripts/install.sh

# 2. Flash ESP32 supervisor firmware via USB-UART
./scripts/flash_esp32.sh /dev/ttyUSB0

# 3. Enable production systemd daemon
sudo cp scripts/systemd/vapa.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable vapa.service
sudo systemctl start vapa.service
```

---

## 6. Safety Verification Status

| Subsystem | Test Status | Standard Alignment |
| :--- | :---: | :--- |
| **8-State Safety Machine** | `mock-verified` | ISO 13849-1 Cat 3 / PL d |
| **Dual-Layer Actuator Cutoff** | `mock-verified` | Hardware /OE + PROFET switch |
| **Closed-Loop Joint Tracking** | `mock-verified` | AS5600 Stall / Runaway detection |
| **Piecewise FSR Calibration** | `mock-verified` | Open-circuit (<10) / Short-circuit (≥4090) faults |
| **Two-Site EMG Normalization**| `mock-verified` | Dwell debouncing, rail saturation, open override |
| **Optical Distance Matrix** | `mock-verified` | Central tracking cone, N-of-M temporal voting |
| **Fault Injection Suite** | `mock-verified` | 21 adversarial failure mode tests passing |
| **Physical Hardware Actuation**| `bench-pending` | Requires technician sign-off per Checkpoints 1–10 |

*Disclaimer: VAPA is an open-architecture engineering research prototype. Autonomous software test verification does not constitute clinical regulatory approval (FDA / CE mark). Physical human attachment requires independent institutional review board (IRB) approval, medical supervision, and isolated battery operation.*
