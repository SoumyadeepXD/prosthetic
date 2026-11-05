#!/usr/bin/env python3
"""Interactive AS5600 Magnetic Rotary Encoder Calibration Tool for VAPA Rev 2.

Calibrates joint position encoders via the TCA9548A multiplexer (address 0x71):
1. Verifies magnet presence and magnetic field health diagnostics (MD, ML, MH bits).
2. Sets mechanical zero-angle offsets at joint home posture.
3. Validates positive joint rotation direction (+1 or -1).
4. Saves zero_offset_deg and direction to config/hardware.yaml.
"""

import sys
import time
import argparse
import shutil
from pathlib import Path
from typing import Dict, Any, List
import yaml

CONFIG_PATH = Path("config/hardware.yaml")

def print_banner():
    print("=" * 72)
    print(" VAPA ENCODER TOOL: AS5600 JOINT CALIBRATION & MAGNET DIAGNOSTICS")
    print("=" * 72)
    print("PROCEDURE:")
    print("1. Ensure diametrically magnetized N52 disc magnets are installed with 1mm air gap.")
    print("2. The tool will check magnet field status for all joints.")
    print("3. Move joint to mechanical ZERO (home/neutral) position when prompted.")
    print("=" * 72)

def calibrate_joint(as5600: Any, joint_name: str, current_cfg: Dict[str, Any], is_mock: bool) -> Dict[str, Any]:
    print(f"\n--- Checking Joint Encoder: {joint_name.upper()} (Mux Channel {current_cfg.get('channel')}) ---")
    ch = int(current_cfg.get("channel", 0))

    if is_mock:
        print(f"[MOCK] Joint {joint_name}: Magnet Detected=OK, Strength=OK, Ticks=2048")
        zero_offset = float(current_cfg.get("zero_offset_deg", 0.0))
        direction = int(current_cfg.get("direction", 1))
        return {
            "channel": ch,
            "zero_offset_deg": zero_offset,
            "direction": direction,
            "calibrated": True,
        }

    status = as5600.read_joint_status(joint_name)
    print(f"Magnet Status:")
    print(f"  Magnet Detected:    {status.magnet_detected}")
    print(f"  Magnet Too Weak:    {status.magnet_too_weak}")
    print(f"  Magnet Too Strong:  {status.magnet_too_strong}")
    print(f"  Raw Angle Ticks:    {status.raw_angle_ticks} (0..4095)")

    if not status.magnet_detected:
        print(f"ERROR: Magnet NOT DETECTED on joint {joint_name}! Check magnet installation and air gap.")
        return current_cfg

    if status.magnet_too_weak or status.magnet_too_strong:
        print(f"WARNING: Magnet field out of optimal range! Check distance (0.5 - 1.5mm recommended).")

    input(f"Position {joint_name} at mechanical ZERO (home/neutral) and press Enter... ")

    # Sample zero angle
    readings = []
    for _ in range(20):
        st = as5600.read_joint_status(joint_name)
        readings.append(st.raw_angle_ticks / 4096.0 * 360.0)
        time.sleep(0.01)

    measured_zero = float(sum(readings) / len(readings))
    print(f"-> Set zero offset for {joint_name} to: {measured_zero:.2f}°")

    dir_input = input("Enter joint direction (+1 for normal, -1 for reversed) [1]: ").strip()
    direction = int(dir_input) if dir_input in ("1", "-1") else int(current_cfg.get("direction", 1))

    return {
        "channel": ch,
        "zero_offset_deg": round(measured_zero, 2),
        "direction": direction,
        "calibrated": True,
    }

def main():
    parser = argparse.ArgumentParser(description="VAPA Encoder Calibration Tool")
    parser.add_argument("--mock", action="store_true", help="Run with mock AS5600 backend")
    parser.add_argument("--joint", type=str, default=None, help="Calibrate a specific joint only")
    args = parser.parse_args()

    print_banner()

    if not CONFIG_PATH.exists():
        print(f"ERROR: {CONFIG_PATH} not found.")
        sys.exit(1)

    with open(CONFIG_PATH, "r") as f:
        data = yaml.safe_load(f) or {}

    as5600_cfg = data.get("jetson", {}).get("as5600", {})
    channels = as5600_cfg.get("channels", {})

    if args.mock:
        from vapa.hal import MockAS5600
        as5600 = MockAS5600(joint_config=channels)
    else:
        from vapa.hal import RealAS5600, RealTCA9548A
        mux = RealTCA9548A(bus_num=7, address=0x71)
        if not mux.initialize():
            print("ERROR: Failed to connect to TCA9548A multiplexer at 0x71.")
            sys.exit(1)
        as5600 = RealAS5600(mux=mux, bus_num=7, address=0x36, joint_config=channels)

    if not as5600.initialize():
        print("ERROR: Failed to initialize AS5600 array.")
        sys.exit(1)

    targets = [args.joint] if args.joint and args.joint in channels else list(channels.keys())

    for j_name in targets:
        channels[j_name] = calibrate_joint(as5600, j_name, channels[j_name], args.mock)

    as5600.close()

    # Backup & save
    shutil.copyfile(CONFIG_PATH, CONFIG_PATH.with_suffix(".yaml.bak"))
    data["jetson"]["as5600"]["channels"] = channels
    with open(CONFIG_PATH, "w") as f:
        yaml.safe_dump(data, f, sort_keys=False)

    print("\n" + "=" * 72)
    print(f"SUCCESS: Calibrated {len(targets)} joint encoders. Saved to {CONFIG_PATH}")
    print("=" * 72)

if __name__ == "__main__":
    main()
