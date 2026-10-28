#!/usr/bin/env python3
"""PCA9685 Output Enable (OE) Gating Verification Script.

SAFETY INSTRUCTIONS:
- Connect EXACTLY ONE unloaded servo to PCA9685 Channel 0.
- Ensure all linkages and tendon cables are disconnected.
- Keep Emergency Stop button within immediate reach.
"""

import sys
import time

def main():
    print("=" * 65)
    print(" VAPA BENCH TOOL: PCA9685 Output Enable (OE) Gating Check")
    print("=" * 65)
    print("SAFETY WARNING:")
    print("This procedure tests PWM signal emission and physical OE gating.")
    print("1. Connect ONLY ONE unloaded servo to Channel 0.")
    print("2. Do NOT wear electrodes on human skin.")
    print("3. Keep hands clear of mechanical pinch points.")
    print("=" * 65)

    confirm = input("Are mechanical cables disconnected and E-Stop in hand? (type 'yes' to proceed): ")
    if confirm.strip().lower() != "yes":
        print("Aborted.")
        sys.exit(1)

    try:
        from vapa.hal.pca9685 import RealPCA9685
    except ImportError:
        print("ERROR: Run with project dependencies installed: pip install -e .")
        sys.exit(1)

    pca = RealPCA9685(bus_num=7, address=0x40, frequency_hz=50)
    if not pca.initialize():
        print("ERROR: Failed to connect to PCA9685 at 0x40.")
        sys.exit(1)

    print("\n[Step 1] Initializing Channel 0 to 1500 us (Neutral Pulse)...")
    pca.set_pulse_us(0, 1500.0)

    print("\nCheck 1: ESP32 OE is held HIGH by default (or jumpered to 3.3V).")
    print("==> Verify the test servo is completely DEAD / inert / back-drivable by hand.")
    input("Press Enter once verified that the servo is limp...")

    print("\nCheck 2: ESP32 OE line pulled LOW (Enabled).")
    print("==> If ESP32 is running, arm the system via esp_link_monitor or jumper OE to GND.")
    print("==> Verify the servo snaps to neutral (1500 us) and resists back-driving.")
    input("Press Enter once verified that the servo is energized...")

    print("\nCheck 3: Strike E-Stop or disconnect OE.")
    print("==> Verify the servo goes dead immediately.")
    input("Press Enter once verified that the servo immediately loses torque...")

    pca.disable_all()
    pca.close()
    print("\nPCA9685 OE gating test complete.")

if __name__ == "__main__":
    main()
