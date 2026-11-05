# VAPA — Vision-Assisted Prosthetic Arm (Rev 2)

VAPA is an advanced multi-modal robotic prosthetic arm featuring dual-processor shared control. Intent is governed strictly by electromyography (EMG) signals, while context (grip geometry, preshaping aperture, force ceilings) is derived in real time via an Intel RealSense depth camera.

## Hardware Reference Summary

- **Primary Controller:** NVIDIA Jetson Orin Nano (JetPack 6)
- **Safety Supervisor:** ESP32-WROOM-32 (FreeRTOS)
- **Actuation:** PCA9685 16-channel 12-bit PWM driver, 9 servos (5 finger tendons, 3 wrist, 1 forearm)
- **Sensors:** 4x AS5600 magnetic encoders via TCA9548A multiplexer (`0x71`), 5x FSR402 force sensors, 2x MyoWare 2.0 EMG envelopes via ADS1115 (`0x48`), Intel RealSense D435i.

## Documentation Index

- [Audit &amp; Spec Compliance](docs/AUDIT.md)
- [Architectural Design &amp; Pinouts](docs/ARCHITECTURE.md)
- [Safety &amp; Engineering Decisions](docs/DECISIONS.md)
- [UART Communication Protocol](docs/PROTOCOL.md)
- [Jetson Environment Setup](docs/SETUP_JETSON.md)
- [Bench Testing Guide](docs/BENCH_TESTS.md)
- [Agent &amp; Contributor Rules](AGENTS.md)

## Quick Start (Mock Environment)

```bash
# Set up Python virtual environment
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .

# Run full test suite
pytest

# Run VAPA Orchestrator in mock mode (terminal status dashboard)
python -m vapa --mock --headless

# Run VAPA Orchestrator with graphical status window (requires display)
python -m vapa --mock
```
