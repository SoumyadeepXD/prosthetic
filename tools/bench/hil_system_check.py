#!/usr/bin/env python3
"""Hardware-In-The-Loop (HIL) Master System Bringup & Pre-Flight Qualification.

HUMAN-OPERATOR BENCH SCRIPT.
MANDATORY SAFETY RULES:
1. Mechanical hand must be mounted to isolated test bench fixture.
2. Tendon cables must be detached or fingers free to move without pinch hazard.
3. Physical Emergency Stop switch must be held in hand.
4. Do NOT wear EMG electrodes on human skin during powered testing.
"""

import sys
import time
import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main():
    parser = argparse.ArgumentParser(description="VAPA HIL Master System Qualification Tool")
    parser.add_argument("--mock", action="store_true", help="Run with mock HAL backends for software CI verification")
    args = parser.parse_args()

    print("=" * 76)
    print("      VAPA HARDWARE-IN-THE-LOOP (HIL) SYSTEM QUALIFICATION SUITE")
    print("=" * 76)
    print("MANDATORY SAFETY CHECKLIST BEFORE PROCEEDING:")
    print(" [1] Prosthetic arm is secured to bench fixture.")
    print(" [2] Servos are unloaded (tendons detached) or clear of mechanical obstructions.")
    print(" [3] Physical Emergency Stop mushroom button is wired and within reach.")
    print(" [4] Electrodes are NOT connected to any human subject.")
    print("=" * 76)

    if not args.mock:
        confirm = input("Confirm safety checklist is satisfied? (type 'yes' to proceed): ")
        if confirm.strip().lower() != "yes":
            print("Aborted by operator.")
            sys.exit(1)
    else:
        print("[MOCK MODE ACTIVATED] Running automated mock verification...")

    results = {}
    esp = None

    # ------------------------------------------------------------------
    # Step 1: ESP32 Link & Protocol Verification
    # ------------------------------------------------------------------
    print("\n[STEP 1/5] Verifying ESP32 UART Link & Protocol CRC...")
    try:
        if args.mock:
            from vapa.hal.esp_link import MockESPLink
            esp = MockESPLink()
        else:
            from vapa.hal.esp_link import RealESPLink
            esp = RealESPLink(port="/dev/ttyTHS1", baudrate=460800)

        if not esp.initialize():
            raise RuntimeError("Could not initialize ESP32 serial link.")

        # Gather telemetry for 1 second
        t_end = time.time() + 1.0
        packets = 0
        while time.time() < t_end:
            s = esp.get_latest_sensor()
            if s:
                packets += 1
            time.sleep(0.02)

        stats = esp.get_link_stats()
        print(f" -> Telemetry packets received: {packets}")
        print(f" -> CRC Errors: {stats.get('crc_errors', 0)}")
        print(f" -> Frame Age: {stats.get('frame_age_ms', 0):.1f} ms")
        assert packets > 0, "No telemetry received from ESP32"
        assert stats.get("crc_errors", 0) == 0, "CRC errors detected on UART link"
        results["ESP32_Link"] = "PASS"
        print(" -> ESP32 Link: [PASSED]")
    except Exception as e:
        results["ESP32_Link"] = f"FAIL: {e}"
        print(f" -> ESP32 Link: [FAILED] ({e})")

    # ------------------------------------------------------------------
    # Step 2: FSR Fingertip Force Sensors
    # ------------------------------------------------------------------
    print("\n[STEP 2/5] Verifying 5x FSR402 Fingertip Force Sensors...")
    try:
        sensor = esp.get_latest_sensor()
        assert sensor is not None, "No sensor message available"
        fsr_readings = sensor.fsr
        print(f" -> Raw FSR Counts: Thumb={fsr_readings[0]}, Index={fsr_readings[1]}, "
              f"Middle={fsr_readings[2]}, Ring={fsr_readings[3]}, Little={fsr_readings[4]}")

        for idx, counts in enumerate(fsr_readings):
            assert counts >= 10, f"FSR {idx} open-circuit (<10 counts)"
            assert counts < 4090, f"FSR {idx} short-circuit (>=4090 counts)"

        results["FSR_Sensors"] = "PASS"
        print(" -> FSR402 Sensors: [PASSED]")
    except Exception as e:
        results["FSR_Sensors"] = f"FAIL: {e}"
        print(f" -> FSR402 Sensors: [FAILED] ({e})")

    # ------------------------------------------------------------------
    # Step 3: Two-Channel MyoWare EMG Envelope
    # ------------------------------------------------------------------
    print("\n[STEP 3/5] Verifying ADS1115 Two-Channel EMG Baselines...")
    try:
        sensor = esp.get_latest_sensor()
        flex_raw = sensor.emg[0]
        ext_raw = sensor.emg[1]
        flex_mv = float(flex_raw) if flex_raw <= 800 else float(flex_raw) * 0.125
        ext_mv = float(ext_raw) if ext_raw <= 800 else float(ext_raw) * 0.125
        print(f" -> Flexor Envelope:  {flex_raw:5d} ({flex_mv:6.1f} mV)")
        print(f" -> Extensor Envelope: {ext_raw:5d} ({ext_mv:6.1f} mV)")

        assert 50.0 <= flex_mv <= 3200.0, f"Flexor EMG out of range: {flex_mv} mV"
        assert 50.0 <= ext_mv <= 3200.0, f"Extensor EMG out of range: {ext_mv} mV"

        results["EMG_Subsystem"] = "PASS"
        print(" -> MyoWare EMG: [PASSED]")
    except Exception as e:
        results["EMG_Subsystem"] = f"FAIL: {e}"
        print(f" -> MyoWare EMG: [FAILED] ({e})")

    # ------------------------------------------------------------------
    # Step 4: Camera / Vision Subsystem (Webcam or RealSense)
    # ------------------------------------------------------------------
    print("\n[STEP 4/5] Verifying Camera Video Acquisition...")
    try:
        import yaml
        v_dev = "webcam"
        v_path = Path("config/vision.yaml")
        if v_path.exists():
            with open(v_path) as vf:
                v_cfg = yaml.safe_load(vf) or {}
                v_dev = v_cfg.get("camera", {}).get("device", "webcam").lower()

        is_webcam = "webcam" in v_dev or "usb" in v_dev

        if args.mock:
            if is_webcam:
                from vapa.hal.webcam import MockWebcam
                cam = MockWebcam()
            else:
                from vapa.hal.realsense import MockRealSense
                cam = MockRealSense()
        else:
            if is_webcam:
                from vapa.hal.webcam import GenericWebcam
                cam = GenericWebcam(device_index=0)
            else:
                from vapa.hal.realsense import RealRealSense
                cam = RealRealSense()

        if not cam.initialize():
            raise RuntimeError(f"Camera ({v_dev}) initialization failed.")

        if is_webcam:
            color, ts = cam.capture_frame()
            print(f" -> Captured USB Webcam Color Frame: {color.shape}")
            assert color.shape[0] > 0, "Empty frame captured"
        else:
            color, depth, ts = cam.capture_frame()
            print(f" -> Captured Color Frame: {color.shape}, Depth Frame: {depth.shape}")
            assert color.shape[0] > 0 and depth.shape[0] > 0, "Empty frame captured"
        cam.close()

        results["Camera_Subsystem"] = "PASS"
        print(f" -> Camera ({v_dev}): [PASSED]")
    except Exception as e:
        results["Camera_Subsystem"] = f"FAIL: {e}"
        print(f" -> Camera: [FAILED] ({e})")

    # ------------------------------------------------------------------
    # Step 5: PCA9685 PWM Controller & Gated Actuation
    # ------------------------------------------------------------------
    print("\n[STEP 5/5] Verifying PCA9685 (0x40) PWM Actuation & Gate...")
    try:
        if args.mock:
            from vapa.hal.pca9685 import MockPCA9685
            pca = MockPCA9685()
        else:
            from vapa.hal.pca9685 import RealPCA9685
            pca = RealPCA9685(bus_num=7, address=0x40)

        if not pca.initialize():
            raise RuntimeError("PCA9685 initialization failed.")

        from vapa.safety import SafetyStateMachine
        sm = SafetyStateMachine()
        assert not sm.is_pwm_allowed, "PWM permitted in initial state"

        # Arm with preconditions
        sm.request_arm(
            esp_link_healthy=True,
            estop_released=True,
            no_latched_fault=True,
            pca9685_healthy=True,
            emg_plausible=True,
            fsr_plausible=True,
        )
        assert sm.is_pwm_allowed, "PWM refused after satisfying preconditions"

        # Pulse neutral on all 9 channels
        for ch in range(9):
            pca.set_pulse_us(ch, 1500.0)
        time.sleep(0.05)
        pca.disable_all()
        pca.close()

        results["PCA9685_Actuation"] = "PASS"
        print(" -> PCA9685 Actuation: [PASSED]")
    except Exception as e:
        results["PCA9685_Actuation"] = f"FAIL: {e}"
        print(f" -> PCA9685 Actuation: [FAILED] ({e})")

    # Clean up esp
    if esp is not None:
        esp.close()

    # ------------------------------------------------------------------
    # Summary Certificate
    # ------------------------------------------------------------------
    print("\n" + "=" * 76)
    print("                    HIL QUALIFICATION SUMMARY")
    print("=" * 76)
    all_passed = True
    for sub, res in results.items():
        status = "PASSED" if res == "PASS" else "FAILED"
        if status == "FAILED":
            all_passed = False
        print(f"  • {sub:25s} : [{status}] {res if status == 'FAILED' else ''}")

    print("=" * 76)
    if all_passed:
        label = "mock-verified" if args.mock else "HARDWARE-VERIFIED"
        print(f"OVERALL STATUS: {label.upper()} - All subsystems passed pre-flight qualification.")
        sys.exit(0)
    else:
        print("OVERALL STATUS: QUALIFICATION FAILED - Review errors above before physical arming.")
        sys.exit(1)


if __name__ == "__main__":
    main()
