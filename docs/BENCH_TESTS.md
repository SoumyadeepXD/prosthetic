# Hardware Bench Testing Protocol (Rev 2)

**SAFETY WARNING:**
- Never connect the 6V servo rail while wearing electrodes on human skin.
- Keep the physical Emergency Stop button within hand reach during all bench procedures.
- Do not attach tendon cables or linkages to servos until individual zero and range limits are verified.

---

## Checkpoint 1: ESP32 Boot & Sensor Diagnostics
1. Flash firmware via PlatformIO: `pio run -d firmware/esp32 -t upload`
2. Open monitor: `pio device monitor -b 460800`
3. Verify ADS1115 detected at `0x48`.
4. Observe FSR counts: press each sensor individually and confirm raw ADC counts **rise** with pressure.

## Checkpoint 2: ESP32 <-> Jetson UART Link Integrity
1. Connect Jetson UART (Pin 8 TXD, Pin 10 RXD) cross-wired to ESP32 (GPIO16 RX2, GPIO17 TX2).
2. Run bench monitor: `python3 tools/bench/esp_link_monitor.py`
3. Verify frames arrive at ~100 Hz with 0 CRC error rate over 60 seconds.

## Checkpoint 3: Emergency Stop & Output Enable Hardware Interlock
1. Measure voltage at PCA9685 `OE` pin: must read 3.3V (HIGH / disabled).
2. Connect multimeter to 6V servo power rail.
3. Strike E-Stop button: verify 6V drops to 0V and `flags.estop_pressed` transitions to 1.
4. Release E-Stop: verify `OE` remains HIGH until an explicit arming cycle occurs.

## Checkpoint 4: Jetson I2C Scan
1. Run scan script: `python3 tools/bench/i2c_scan.py`
2. Confirm presence of `0x40` (PCA9685) and `0x71` (TCA9548A).

## Checkpoint 5: PCA9685 OE Gating Verification
1. Connect a single unloaded test servo to Channel 0.
2. Verify servo cannot be backdriven when OE is LOW (energized), and goes limp immediately when OE transitions to HIGH.

## Checkpoint 6: Servo Range Calibration
1. Run `python3 tools/bench/calibrate_servos.py`.
2. Step each servo in 10 µs increments to define physical mechanical limits.
3. Save resulting values to `config/servos.yaml`.

## Checkpoint 7: AS5600 Magnetic Encoder Bus Readout
1. Run `python3 tools/bench/test_encoders.py`.
2. Verify all 4 encoders report valid magnet status (`MD=1`, `ML=0`, `MH=0`).
3. Rotate joints by hand and observe continuous, monotonic angle changes across 360-degree unwrap.

## Checkpoint 8: EMG Baseline & Dynamic Calibration
1. Attach MyoWare electrodes to forearm muscles (flexor and extensor).
2. Run `python3 tools/bench/calibrate_emg.py` while arm is **off the body**.
3. Perform 5 s rest baseline, followed by 3 Maximum Voluntary Contractions (MVC).

## Checkpoint 9: RealSense Depth Matrix Bench Verification
1. Run `python3 tools/bench/test_realsense.py`.
2. Place a flat obstacle at 0.3m, 0.5m, and 1.0m. Compare median distance matrix cell readings against physical tape measure measurements.

## Checkpoint 10: Full Bench Integration
1. Run complete system in bench test mode.
2. Confirm shared-control rules: vision preshapes aperture as target approaches; hand does not close until flexor EMG exceeds threshold; extensor EMG immediately opens fingers.
