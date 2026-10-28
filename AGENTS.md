# AGENTS.md — Rules for AI and Human Engineers on VAPA

This repository contains the software and firmware stack for the Vision-Assisted Prosthetic Arm (VAPA) matching **Hardware Connection Guide Rev 2**.

## 0. Hard Rules for Agents

1. **Safety Defaults Beat Convenience**: Always fail closed. System boots disarmed. When unsure, choose the safer behavior and document it in `docs/DECISIONS.md`.
2. **Never Command Real Hardware**: Never run code that drives real servos in tests, CI, or automated scripts. All PWM-emitting code must pass through a Hardware Abstraction Layer (HAL) with a mock backend.
3. **Hardware Scripts are Human-Run**: Real hardware scripts live strictly in `tools/bench/`. Agents must never execute them. They must print clear safety warnings and instructions before prompting human confirmation.
4. **Honest Verification**: Label test results `mock-verified` until verified on real hardware by human operators. Never claim "tested on hardware" autonomously.
5. **Shared-Control Principle**:
   - EMG supplies intent (close, open, hold, mode switch).
   - Vision supplies context (preshape aperture, grip profile, force ceiling).
   - **Vision can NEVER start or increase a closing motion.** EMG open always overrides everything.
6. **No Invented Hardware Facts**: If a pulse width, FSR voltage curve, or sensor parameter is unverified, assign a conservative default with a `# TODO: verify` annotation.
7. **Complete Files**: Output complete files, not fragments. Maintain strict typing, docstrings, and unit tests.
8. **Independent ESP32 Supervisor**: The ESP32 controls PCA9685 Output Enable (`OE`, GPIO25). It disables all servo outputs immediately on E-stop, heartbeat timeout (250 ms default), or persistent force fault. The Jetson cannot override the ESP32 supervisor.
9. **No ROS 2 Dependency**: Keep architecture as clean Python 3.10+ (asyncio/multiprocessing) on Jetson and C++/PlatformIO/FreeRTOS on ESP32. Keep module boundaries clean for future wrappers.

## 7. Non-Negotiables Checklist

- [ ] Boot disarmed. Never auto-arm. Arming requires explicit operator command + all pre-conditions satisfied.
- [ ] No PWM emitted while disarmed or faulted.
- [ ] Every servo command passes through: limits clamp -> slew rate limiter -> arm-state gate -> PCA9685.
- [ ] Heartbeat 50 Hz from dedicated thread; stops if control loop stalls.
- [ ] Global exception handlers and `atexit` drop arm request and halt heartbeats.
- [ ] Protocol frames use CRC16-CCITT-FALSE (poly `0x1021`, init `0xFFFF`) over `LEN, TYPE, SEQ, PAYLOAD`.
- [ ] TCA9548A mux address is `0x71` (A0 to 3.3V). PCA9685 is `0x40` with `ALLCALL` disabled at init.
