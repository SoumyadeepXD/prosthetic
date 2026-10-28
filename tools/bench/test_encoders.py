#!/usr/bin/env python3
"""AS5600 Magnetic Encoder Diagnostic Tool (via TCA9548A Mux).

SAFETY & INSTRUCTION:
- Arm must be unpowered at 6V servo rail during encoder diagnosis.
- Verifies magnet detection (MD), magnet too weak (ML), and magnet too strong (MH).
- Monitors live angle across AS5600 encoders on Mux Channels 0, 1, 2, 3.
"""

import sys
import time

def main():
    print("=" * 60)
    print(" VAPA BENCH TOOL: AS5600 Encoder Diagnostic (via TCA9548A)")
    print("=" * 60)
    print("Pre-conditions:")
    print("1. 6V servo power rail is switched OFF (E-Stop active or relay open).")
    print("2. 3.3V logic connected to Jetson I2C bus (Pins 3 & 5).")
    print("3. TCA9548A address is 0x71 (A0 to 3.3V).")
    input("\nPress Enter to begin encoder diagnostics...")

    try:
        import yaml
        from vapa.hal.tca9548a import RealTCA9548A
        from vapa.hal.as5600 import RealAS5600
    except ImportError:
        print("ERROR: Run with project dependencies installed: pip install -e .")
        sys.exit(1)

    with open("config/hardware.yaml", "r") as f:
        cfg = yaml.safe_load(f)["jetson"]

    mux = RealTCA9548A(bus_num=cfg["i2c_bus"], address=cfg["tca9548a"]["address"])
    if not mux.initialize():
        print(f"ERROR: Failed to connect to TCA9548A multiplexer at 0x{cfg['tca9548a']['address']:02X}")
        sys.exit(1)

    encoders = RealAS5600(
        mux=mux,
        bus_num=cfg["i2c_bus"],
        address=cfg["as5600"]["address"],
        joint_config=cfg["as5600"]["channels"],
    )

    if not encoders.initialize():
        print("WARNING: One or more AS5600 encoders failed initial magnet check.")

    print("\nLive Joint Angles (Press Ctrl+C to exit):")
    print("-" * 65)
    print(f"{'Joint':<18} | {'Ch':<3} | {'Magnet':<8} | {'Raw Ticks':<10} | {'Angle (deg)':<12}")
    print("-" * 65)

    try:
        while True:
            lines = []
            for joint_name in ["finger_group", "wrist_flex", "wrist_rotate", "forearm_rotation"]:
                try:
                    st = encoders.read_joint_status(joint_name)
                    mag_str = "OK" if st.is_valid else ("WEAK" if st.magnet_too_weak else ("STRONG" if st.magnet_too_strong else "NO_MAG"))
                    lines.append(f"{joint_name:<18} | {st.channel:<3} | {mag_str:<8} | {st.raw_angle_ticks:<10} | {st.joint_angle_degrees:>9.1f}°")
                except Exception as e:
                    lines.append(f"{joint_name:<18} | ERR | {str(e)[:25]}")

            # Print status block
            sys.stdout.write("\033[H\033[J") # Clear screen
            print("AS5600 Encoder Live Readout (Move joints manually to observe):")
            print("-" * 65)
            print(f"{'Joint':<18} | {'Ch':<3} | {'Magnet':<8} | {'Raw Ticks':<10} | {'Angle (deg)':<12}")
            print("-" * 65)
            for line in lines:
                print(line)

            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        encoders.close()
        mux.close()
        print("\nDiagnostics complete.")

if __name__ == "__main__":
    main()
