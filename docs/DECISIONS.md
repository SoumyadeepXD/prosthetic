# Architecture & Safety Decisions Log

This document records safety and architectural design choices, alternatives considered, and justifications.

---

### DEC-001: Independent ESP32 Output Enable (OE) Supervisor
- **Decision:** ESP32 owns PCA9685 Output Enable pin (GPIO25, active low). ESP32 sets OE HIGH (disabled) immediately on boot, on E-stop press, on heartbeat timeout (> 250 ms), or on sustained force fault (> 500 ms).
- **Alternatives Considered:** Jetson controlling OE via GPIO or I2C All-Call sleep bit.
- **Reason:** A software crash or kernel freeze on the Jetson must not be able to leave servos energized or moving. Hardware fail-safe requires an independent microcontroller with hardware watchdog directly gating power/signals.

---

### DEC-002: Fail-Closed Servo PWM Gating
- **Decision:** While in any state other than `ARMED_IDLE` or `ACTIVE`, the Jetson PWM layer suppresses all PWM signals (0% duty cycle / pulse output disabled). All servo commands pass through clamp -> slew limiter -> arm gate.
- **Alternatives Considered:** Sending neutral positions when disarmed.
- **Reason:** Driving servos to neutral on fault could crush trapped objects or pinch fingers. Disabling pulses allows the mechanical backdrive/slack to prevent sustained injury.

---

### DEC-003: 100 Hz Envelope Threshold Decoding as Primary EMG Mode
- **Decision:** Use two-site envelope threshold decoding (MyoWare ENV signals sampled at ~100 Hz via ADS1115) as the default control mechanism. ML-based EMG classification is disabled by default.
- **Alternatives Considered:** Enabling a pre-trained raw EMG classifier.
- **Reason:** ADS1115 round-robin sampling across 3 channels yields ~100-200 Hz max per channel. This cannot support 500+ Hz raw EMG feature extraction. Running raw classifiers on sub-Nyquist enveloped signals causes unpredictable output.

---

### DEC-004: Shared-Control Arbitration Safety Invariant
- **Decision:** Vision outputs (distance matrix, object classification, bounding boxes) are strictly limited to pre-shaping hand aperture, setting force targets/caps, and suggesting grip profiles. Vision is mathematically barred from commanding or increasing a closing motion. EMG open command unconditionally overrides any active motion.
- **Alternatives Considered:** Autonomous grasp triggering when camera detects object within threshold.
- **Reason:** Autonomous grasp without explicit user intent poses severe safety hazards (unintended clamping on people or hazards). Prosthetic control must maintain user agency.

---

### DEC-005: TCA9548A I2C Address Relocation to 0x71
- **Decision:** Configure TCA9548A hardware address to `0x71` by pulling A0 to 3.3V.
- **Alternatives Considered:** Leaving TCA9548A at default `0x70`.
- **Reason:** PCA9685 responds to the I2C All-Call broadcast address `0x70`. Placing the mux at `0x70` causes bus conflicts whenever the All-Call address is acknowledged.

---

### DEC-006: Servo Range Safety Clamping and Closed-Loop Mismatch Monitoring
- **Decision:** Any uncalibrated servo in `config/servos.yaml` is clamped to neutral (1500 us) to prevent mechanical overdrive. For joints with AS5600 encoders, closed-loop tracking trips a system fault if commanded-vs-measured position mismatch exceeds 12° for >0.35 s (stall/mechanical jamming) or uncommanded motion exceeds 20°/s for >0.25 s (slippage/external backdrive). In the finger force loop, exceeding the force cap triggers immediate positional backoff, while opening motions bypass the force controller unconditionally.
- **Alternatives Considered:** Open-loop commands only; or continuing to drive servos during joint stall.
- **Reason:** Tendon-driven fingers and high-torque digital servos will strip gears or burn motors if driven while jammed. Immediate detection and disarm protects the mechanics and patient.

---

### DEC-007: EMG Dwell Debouncing, Hysteresis, and EEG Isolation
- **Decision:** The two-site EMG decoder enforces a 100 ms dwell filter to reject transient electrode movement artifacts, an asymmetric hysteresis band (0.25 activate, 0.15 deactivate), and a 600 ms sustained co-contraction requirement to trigger profile cycling (`MODE_CYCLE`). Extensor (OPEN) intent unconditionally preempts any closing intent. The EEG subsystem is disabled by default behind an abstract mock interface; if enabled, it is strictly forbidden from commanding motion and may only issue mode switch cues.
- **Alternatives Considered:** Instantaneous threshold crossing without dwell; permitting EEG to initiate grasp.
- **Reason:** Motion artifacts from electrode tugging or minor involuntary muscle twitches must not cause accidental hand opening or closing. Single dry-channel EEG is too noisy for direct motor intent and must never compromise safety.

---

### DEC-008: Vision Central Zone Target Prioritization and 5-Frame Differentiation
- **Decision:** The 12x16 depth distance matrix isolates a central target tracking zone (rows 2-9, cols 3-12) directly aligned with the prosthetic palm line. Nearest surface distance and approach velocity are tracked strictly within this cone before falling back to peripheral bounds. Approach velocity is computed via linear regression over a 5-frame sliding window (with negative velocity indicating closing in). Edge-preserving spatial smoothing (delta 20 mm), temporal persistence, and hole filling are executed prior to matrix discretization.
- **Alternatives Considered:** Global nearest pixel search; single-frame backward difference.
- **Reason:** Peripheral objects (e.g. tabletops, user torso, or bystanders) would otherwise dominate the nearest distance metric, causing false aperture preshaping. A 5-frame regression window suppresses depth camera noise spikes.
