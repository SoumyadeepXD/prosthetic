# VAPA Repository Audit (Phase 0)

## 1. Baseline Assessment
- **Date:** October 2026
- **Status:** Greenfield initialization.
- **Pre-existing Codebase:** None found in workspace `/Users/soumyadeepxd/Developer/napa2main`.
- **Pre-existing Hardware Scripts / Teammate Models:** None present.

## 2. Specification Alignment (Hardware Connection Guide Rev 2)
Since the repository is initialized clean:
- **No legacy conflicts exist** with previous revisions.
- **I2C Architecture:** TCA9548A mux configured at `0x71` (avoiding the `0x70` PCA9685 All-Call clash), PCA9685 at `0x40` (All-Call disabled at initialization).
- **ESP32 Pins:**
  - GPIO25: PCA9685 `OE` active-low (default HIGH / disabled via hardware 1k pull-up; initialized HIGH immediately on ESP32 boot).
  - GPIO27: E-stop NC/NO to GND (`INPUT_PULLUP`, LOW = pressed).
  - GPIO32-36: FSR 1-5 (ADC1 with 11dB attenuation). Higher count indicates higher force.
  - GPIO21/22: I2C (ADS1115 at `0x48`).
  - GPIO16/17: UART2 (460800 baud).
- **Control & Safety Model:**
  - Independent FreeRTOS supervisor on ESP32.
  - Fail-closed Jetson state machine (`BOOT -> DISARMED -> ARMED_IDLE -> ACTIVE -> FAULT`).
  - Strict EMG-priority arbitration (vision provides preshape and force bounds only; cannot command closing).
  - High-rate raw EMG classifiers disabled by default; 100 Hz envelope threshold decoder enabled by default.

## 3. Reconciliation Plan
All modules will be scaffolded from scratch directly conforming to Rev 2:
1. `config/*.yaml` with Rev 2 pinouts, addresses, and conservative pulse/force limits.
2. `vapa/` package hierarchy with typed abstract interfaces and mock backends.
3. ESP32 PlatformIO project in `firmware/esp32/` with native unit testing for supervisor logic.
4. Comprehensive mock test suite in `tests/`.
