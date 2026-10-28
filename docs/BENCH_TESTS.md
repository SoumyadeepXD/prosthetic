# Hardware Bench Testing Protocol (Rev 2)

**Document Reference:** VAPA-TEST-REV2  
**Target Architecture:** NVIDIA Jetson Orin Nano + ESP32-WROOM-32 Supervisor + PCA9685 + TCA9548A + RealSense D435i  

---

## 1. Safety Rules & Precautions

> [!CAUTION]
> **MANDATORY SAFETY NON-NEGOTIABLES:**
> 1. **ELECTRODE ISOLATION:** Never connect the 6.0V servo power supply while electrodes are placed on human skin. All electrode calibration must be performed with the mechanical arm completely detached from the human body and placed on an isolated test bench.
> 2. **EMERGENCY STOP PROXIMITY:** The physical red mushroom Emergency Stop button must remain within immediate reach (< 30 cm) of the lead operator's hand at all times during bench testing.
> 3. **TENDON DISCONNECTION:** Do not string tendon cables or mechanical linkages through finger joints until individual servo zero, neutral (1500 µs), and physical mechanical travel limits are verified.
> 4. **BOOT DISARMED:** The system boots strictly in the `DISARMED` state. No PWM pulses are emitted while disarmed. Never bypass the safety state machine or arm gate.

---

## 2. Required Bench Equipment & Tools

| Equipment | Specification | Purpose |
| :--- | :--- | :--- |
| **Bench DC Power Supply** | 6.0 V, ≥ 10.0 A, adjustable current limit | Servo power rail (MG996R & DS3218MG servos) |
| **Logic Bench Power Supply** | 5.0 V / 3.3 V regulated | Logic rails and breadboard testing |
| **Digital Multimeter** | True-RMS, voltage, resistance, continuity | Rail voltage checks, OE logic level, ground continuity |
| **Logic Analyzer / Scope** | ≥ 2 channels, 24 MHz sampling | UART frame timing, I2C bus transactions, PWM jitter |
| **Emergency Stop Switch** | Industrial NC latching mushroom switch | Hardware interlock relay to 6V power rail & ESP32 GPIO27 |
| **Precision Tape Measure** | Metric 1 mm precision (or laser distance meter) | RealSense 12x16 depth matrix ground truth calibration |
| **Calibration Weights** | 50 g, 100 g, 200 g, 500 g brass/steel weights | FSR pressure-to-gram curve verification |
| **EMG Electrodes** | Single-use silver/silver chloride (Ag/AgCl) pads | MyoWare 2.0 muscle sensor interface |

---

## 3. Step-by-Step Bench Verification Checkpoints

```
[ Unboxing & Wiring ]
         │
         ▼
[ Checkpoint 1: ESP32 Firmware & ADS1115 FSRs ]
         │
         ▼
[ Checkpoint 2: 460800 Baud UART Link & CRC16 ]
         │
         ▼
[ Checkpoint 3: Hardware E-Stop & Relay Interlock ]
         │
         ▼
[ Checkpoint 4: Jetson I2C Scan (0x40 PCA9685, 0x71 TCA9548A) ]
         │
         ▼
[ Checkpoint 5: PCA9685 Hardware OE Gating ]
         │
         ▼
[ Checkpoint 6: Interactive Servo Range Calibration ]
         │
         ▼
[ Checkpoint 7: AS5600 Magnetic Encoder Bus ]
         │
         ▼
[ Checkpoint 8: MyoWare EMG Envelope & MVC Calibration ]
         │
         ▼
[ Checkpoint 9: RealSense Depth Matrix Ground Truth ]
         │
         ▼
[ Checkpoint 10: Full Shared-Control Integration & E-Stop Trip ]
```

---

### Checkpoint 1: ESP32 Boot & Sensor Diagnostics

- **Objective:** Flash FreeRTOS supervisor firmware, verify ADS1115 ADC communication over I2C (`0x48`), and check FSR sensor polarity.
- **Physical Wiring:**
  - ESP32 GPIO21 (SDA) -> ADS1115 SDA
  - ESP32 GPIO22 (SCL) -> ADS1115 SCL
  - ADS1115 ADDR pin -> GND (sets I2C address to `0x48`)
  - 5x FSRs wired in voltage divider (10 kΩ pull-down to GND, FSR to 3.3V).
- **Execution Command:**
  ```bash
  pio run -d firmware/esp32 -t upload
  pio device monitor -d firmware/esp32 -b 460800
  ```
- **Multimeter Checks:**
  - Verify ESP32 3.3V rail: **3.28 V to 3.33 V**.
  - Measure voltage across each FSR divider at rest: **0.05 V to 0.15 V**.
- **Pass/Fail Criteria:**
  - **PASS:** Monitor outputs `ADS1115 initialized at 0x48`. Pressing each fingertip FSR results in raw ADC counts monotonically increasing from ~400 counts to >12,000 counts.
  - **FAIL:** `ADS1115 not found` or FSR counts decrease with pressure (inverted divider wiring).

---

### Checkpoint 2: ESP32 <-> Jetson UART Link Integrity

- **Objective:** Verify high-speed bidirectional UART communication at 460,800 baud with 0 CRC errors over 60 seconds.
- **Physical Wiring:**
  - Jetson 40-Pin Header Pin 8 (UART1 TXD) -> ESP32 GPIO16 (RX2)
  - Jetson 40-Pin Header Pin 10 (UART1 RXD) -> ESP32 GPIO17 (TX2)
  - Jetson Pin 6 / Pin 9 (GND) -> ESP32 Common Ground
- **Execution Command:**
  ```bash
  python3 tools/bench/esp_link_monitor.py --port /dev/ttyTHS1 --baud 460800 --duration 60
  ```
- **Pass/Fail Criteria:**
  - **PASS:** 100 Hz frame delivery rate (5,950 to 6,050 frames in 60 s). CRC error rate = **0.00%** (0 bad frames). Jitter standard deviation < 1.0 ms.
  - **FAIL:** Frame rate < 95 Hz, framing errors, or any CRC16 checksum failures. Check common ground connection and line capacitance.

---

### Checkpoint 3: Emergency Stop & Hardware Interlock Relay

- **Objective:** Verify that the hardware E-Stop physically disconnects the 6.0V servo supply and forces PCA9685 `OE` HIGH (disabled) independently of Jetson software.
- **Physical Wiring:**
  - E-Stop switch NC contact in series with 6V DC solid-state relay control line.
  - Auxiliary NO contact connected to ESP32 GPIO27 with 10 kΩ pull-up to 3.3V.
  - ESP32 GPIO25 connected to PCA9685 `OE` (active low).
- **Multimeter Checks:**
  1. Measure PCA9685 `OE` pin on boot: Must read **3.3 V** (disabled).
  2. Measure 6.0V servo power bus: Must read **0.0 V** while E-Stop is depressed.
- **Execution Command:**
  ```bash
  python3 tools/bench/test_oe.py
  ```
- **Pass/Fail Criteria:**
  - **PASS:** 
    - In DISARMED state, `OE` voltage is strictly 3.3V (HIGH).
    - When E-Stop is pressed, 6V rail immediately drops to 0.0V in < 5 ms, ESP32 status flag `FLAG_ESTOP_PRESSED` transitions to `1`, and `OE` remains latched at 3.3V.
    - Releasing the E-Stop button does NOT auto-arm the system (`OE` remains HIGH until an explicit arming command is issued).
  - **FAIL:** `OE` drops LOW while disarmed, or servo rail stays energized when E-Stop is pressed.

---

### Checkpoint 4: Jetson I2C Bus Scan

- **Objective:** Confirm detection of PCA9685 at `0x40` and TCA9548A multiplexer at `0x71` on Jetson I2C Bus 1.
- **Physical Wiring:**
  - Jetson Pin 3 (I2C1 SDA) -> Level Shifter -> PCA9685 SDA & TCA9548A SDA
  - Jetson Pin 5 (I2C1 SCL) -> Level Shifter -> PCA9685 SCL & TCA9548A SCL
  - TCA9548A Address Pin A0 connected to 3.3V, A1/A2 to GND (`0x71`).
- **Execution Command:**
  ```bash
  python3 tools/bench/i2c_scan.py --bus 1
  ```
- **Pass/Fail Criteria:**
  - **PASS:** Scan outputs exactly:
    - Address `0x40`: PCA9685 16-Channel PWM Driver.
    - Address `0x71`: TCA9548A 8-Channel I2C Multiplexer.
    - Address `0x70` is NOT present or disabled (PCA9685 All-Call disabled).
  - **FAIL:** Missing `0x40` or `0x71`. Multiplexer appears at `0x70` (A0 pulled to ground instead of 3.3V).

---

### Checkpoint 5: PCA9685 OE Gating Verification

- **Objective:** Verify that servo torque is strictly controllable by the hardware `OE` line.
- **Physical Setup:** Connect an unloaded MG996R test servo to PCA9685 Channel 0.
- **Execution Command:**
  ```bash
  python3 tools/bench/test_oe.py --channel 0
  ```
- **Pass/Fail Criteria:**
  - **PASS:** 
    - When test prompts "OE DISABLED (3.3V)", the servo horn can be rotated easily by hand (completely limp / unenergized).
    - When test prompts "OE ENABLED (0.0V)", the servo locks firmly at 1500 µs neutral and resists manual backdriving.
    - When toggled back to DISABLED, servo immediately goes limp.
  - **FAIL:** Servo draws current or buzzes while OE is HIGH.

---

### Checkpoint 6: Interactive Servo Range Calibration

- **Objective:** Calibrate minimum pulse (`pulse_min_us`), maximum pulse (`pulse_max_us`), and neutral position (`pulse_neutral_us`) for each of the 6 servos.
- **Physical Setup:** 
  - Ensure mechanical tendon cables are UNTENSIONED or disconnected.
  - Wear protective safety glasses.
- **Execution Command:**
  ```bash
  python3 tools/bench/calibrate_servos.py
  ```
- **Procedure:**
  1. Select joint: `thumb`, `index`, `middle`, `ring`, `little`, `wrist_flex`, `wrist_rotate`, or `forearm_rotation`.
  2. Nudge pulse in +10 µs / -10 µs increments.
  3. Locate physical mechanical stop without forcing or stalling motor.
  4. Apply 30 µs safety backoff margin from physical hard stop.
  5. Save calibrated values directly to `config/servos.yaml`.
- **Pass/Fail Criteria:**
  - **PASS:** Every servo has verified safe pulse limits with zero buzzing at endpoints. All calibrated limits are saved in `config/servos.yaml`.
  - **FAIL:** Motor stalls, overheats, or pulls excessive current (> 1.2 A unloaded).

---

### Checkpoint 7: AS5600 Magnetic Encoder Bus Readout

- **Objective:** Verify magnetic field detection (`MD=1`, `ML=0`, `MH=0`) and 12-bit monotonic angle tracking across all 4 encoders connected to TCA9548A Channels 0, 1, 2, and 3.
- **Execution Command:**
  ```bash
  python3 tools/bench/test_encoders.py
  ```
- **Procedure:**
  - Manually rotate each joint through its full mechanical range.
  - Observe angle readouts across the 0° / 360° boundary.
- **Pass/Fail Criteria:**
  - **PASS:** All 4 encoders report `Magnet: OK`. Rotating joint increases angle smoothly without jumps or NaN errors. Read latency < 0.05 ms per channel.
  - **FAIL:** `Magnet: WEAK` (air gap > 2.0 mm), `Magnet: STRONG` (air gap < 0.5 mm), or `Magnet: NO_MAG`.

---

### Checkpoint 8: MyoWare EMG Baseline & MVC Calibration

- **Objective:** Measure user rest baseline voltage (5 seconds) and Maximum Voluntary Contraction (MVC, 3 repeats of 2 seconds) for forearm flexor and extensor muscles.
- **Physical Setup:**
  - Clean skin with alcohol swabs.
  - Attach MyoWare 2.0 electrodes:
    - Channel 1 (Flexor): Mid-belly of Flexor Carpi Radialis.
    - Channel 2 (Extensor): Mid-belly of Extensor Digitorum.
    - Reference: Olecranon bony process of the elbow.
  - **ARM MUST BE OFF THE BODY ON THE TEST BENCH.**
- **Execution Command:**
  ```bash
  python3 tools/bench/calibrate_emg.py
  ```
- **Pass/Fail Criteria:**
  - **PASS:**
    - Rest baseline: **150 mV to 400 mV** with noise ripple < 50 mV.
    - MVC contraction: **1,600 mV to 2,800 mV**.
    - Thresholds and normalization parameters successfully written to `config/emg.yaml`.
  - **FAIL:** Rest baseline > 800 mV (poor electrode contact), flatline at 0 mV (cable disconnected), or 60 Hz hum ripple > 300 mV.

---

### Checkpoint 9: RealSense Depth Matrix Ground Truth Validation

- **Objective:** Verify accuracy of the 12x16 central zone distance matrix against physical tape measure ground truth.
- **Physical Setup:** Secure camera rigidly on bench. Align flat 200x200 mm cardboard target perpendicular to camera optical axis.
- **Execution Command:**
  ```bash
  python3 tools/bench/test_realsense.py
  ```
- **Validation Measurements:**
  | Distance Benchmark | Allowable Error Tolerance | PASS / FAIL Criteria |
  | :--- | :--- | :--- |
  | **300 mm** (close grasp zone) | ± 15.0 mm | Measured median 285 mm to 315 mm |
  | **500 mm** (approach zone) | ± 25.0 mm | Measured median 475 mm to 525 mm |
  | **1000 mm** (search zone) | ± 50.0 mm | Measured median 950 mm to 1050 mm |
- **Pass/Fail Criteria:**
  - **PASS:** All 3 distances pass within error tolerance. Central tracking zone (rows 2-9, cols 3-12) reports valid depth with >95% pixel validity.
  - **FAIL:** Depth error > tolerance, or black holes (zero depth) in central target area.

---

### Checkpoint 10: Full Shared-Control Integration & Emergency Stop Trip

- **Objective:** Complete end-to-end integration test validating shared-control arbitration, proportional grasp, extensor rapid open override, and emergency stop shutdown.
- **Execution Command:**
  ```bash
  python3 -m vapa.app.main --headless
  ```
- **Procedure:**
  1. **Boot Check:** System starts in `DISARMED` state. Multimeter verifies `OE` is 3.3V.
  2. **Arm Request:** Operator enters command line prompt to request arming. Verify transition: `DISARMED -> ARMED_IDLE`. `OE` drops to 0.0V.
  3. **Visual Approach:** Bring target object toward camera. Observe:
     - Aperture preshapes wider as target enters < 0.50 m.
     - **INVARIANT VERIFICATION:** Hand DOES NOT close. Fingers remain stationary or preshaped.
  4. **Intent-Driven Closing:** Contract flexor muscle. Hand closes proportionally. FSRs contact object and force controller limits grip force to profile ceiling.
  5. **Immediate Override:** While closing, contract extensor muscle.
     - **INVARIANT VERIFICATION:** Closing stops immediately within the very first cycle (< 10 ms), and hand opens fully upon satisfying dwell.
  6. **Emergency Stop Strike:** Strike physical red E-Stop button.
     - **INVARIANT VERIFICATION:** 6V power relay opens immediately, ESP32 sets `OE` HIGH (< 5 ms), state transitions to `FAULT`, and servos go completely limp.
- **Pass/Fail Criteria:**
  - **PASS:** All 6 steps pass without deviation. 0 uncommanded motions. 0 safety violations.
  - **FAIL:** Any autonomous closing without flexor EMG, extensor override delay > 100 ms, or failure of E-Stop to cut power.

---

## 4. Sign-Off & Hardware Verification Record

| Checkpoint | Description | Operator Name | Date | Result (PASS / FAIL) |
| :--- | :--- | :--- | :--- | :--- |
| **CP-01** | ESP32 Firmware & ADS1115 FSRs | | | |
| **CP-02** | 460800 Baud UART Link & CRC16 | | | |
| **CP-03** | Hardware E-Stop & Relay Interlock | | | |
| **CP-04** | Jetson I2C Scan (0x40 & 0x71) | | | |
| **CP-05** | PCA9685 Hardware OE Gating | | | |
| **CP-06** | Interactive Servo Range Calibration | | | |
| **CP-07** | AS5600 Magnetic Encoders (Ch 0..3) | | | |
| **CP-08** | MyoWare EMG Baseline & MVC | | | |
| **CP-09** | RealSense Depth Matrix Calibration | | | |
| **CP-10** | Full Shared-Control Integration & E-Stop | | | |
