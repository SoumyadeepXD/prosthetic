#!/usr/bin/env python3
"""Interactive Servo Calibration Utility for VAPA Rev 2.

Calibrates individual servo endpoints, neutral position, joint limits, and direction.
Supports both real hardware execution (with mandatory safety warnings) and --mock simulation.
Saves calibrated pulse parameters to config/servos.yaml.
"""

import sys
import time
import argparse
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
import yaml

CONFIG_PATH = Path("config/servos.yaml")

def print_safety_banner():
    print("=" * 72)
    print(" VAPA BENCH TOOL: 9-CHANNEL SERVO CALIBRATION WIZARD")
    print("=" * 72)
    print("MANDATORY SAFETY RULES:")
    print("1. All mechanical linkages and tendon cables MUST BE UNLOADED.")
    print("2. The physical Emergency Stop button MUST BE IN YOUR HAND.")
    print("3. Calibrate only ONE servo at a time.")
    print("4. Verify PCA9685 /OE line is properly pulled high by ESP32.")
    print("=" * 72)

def calibrate_channel(pca: Any, name: str, current_cfg: Dict[str, Any], is_mock: bool) -> Dict[str, Any]:
    print(f"\n--- Calibrating Servo: {name.upper()} (Channel {current_cfg.get('channel')}) ---")
    ch = int(current_cfg.get("channel", 0))
    min_us = float(current_cfg.get("pulse_min_us", current_cfg.get("min_pulse_us", 1000.0)))
    max_us = float(current_cfg.get("pulse_max_us", current_cfg.get("max_pulse_us", 2000.0)))
    neutral_us = float(current_cfg.get("pulse_neutral_us", current_cfg.get("neutral_pulse_us", 1500.0)))
    direction = int(current_cfg.get("direction", 1))

    updated_cfg = dict(current_cfg)
    if is_mock:
        print("[MOCK MODE] Simulating calibration step for channel", ch)
        updated_cfg.update({
            "pulse_min_us": int(min_us),
            "pulse_max_us": int(max_us),
            "pulse_neutral_us": int(neutral_us),
            "direction": direction,
            "calibrated": True,
        })
        return updated_cfg

    # Test neutral
    print(f"Setting channel {ch} to neutral: {neutral_us:.1f} us...")
    pca.set_pulse_us(ch, neutral_us)
    time.sleep(0.5)

    try:
        val = input(f"Enter neutral pulse in microseconds [{neutral_us:.0f}]: ").strip()
        if val:
            neutral_us = float(val)

        val = input(f"Enter minimum pulse (full open/retracted) in microseconds [{min_us:.0f}]: ").strip()
        if val:
            min_us = float(val)

        val = input(f"Enter maximum pulse (full close/extended) in microseconds [{max_us:.0f}]: ").strip()
        if val:
            max_us = float(val)

        val = input(f"Enter direction (1 for normal, -1 for reversed) [{direction}]: ").strip()
        if val:
            direction = int(val)
    except (ValueError, EOFError):
        print("Using current defaults.")

    pca.disable_channel(ch)
    print(f"Channel {ch} calibrated: min={min_us:.0f}us, max={max_us:.0f}us, neutral={neutral_us:.0f}us, dir={direction}")

    updated_cfg.update({
        "pulse_min_us": int(min_us),
        "pulse_max_us": int(max_us),
        "pulse_neutral_us": int(neutral_us),
        "direction": direction,
        "calibrated": True,
    })
    return updated_cfg

def main():
    parser = argparse.ArgumentParser(description="VAPA Servo Calibration Tool")
    parser.add_argument("--mock", action="store_true", help="Run with mock PCA9685 backend for testing")
    parser.add_argument("--servo", type=str, default=None, help="Calibrate a specific servo only")
    args = parser.parse_args()

    print_safety_banner()

    if not args.mock:
        try:
            confirm = input("Confirm: Are servos unloaded and E-Stop ready? (type 'yes'): ")
            if confirm.strip().lower() != "yes":
                print("Calibration cancelled.")
                sys.exit(1)
        except EOFError:
            print("Cannot read stdin; aborting.")
            sys.exit(1)

    if not CONFIG_PATH.exists():
        print(f"ERROR: {CONFIG_PATH} not found.")
        sys.exit(1)

    with open(CONFIG_PATH, "r") as f:
        data = yaml.safe_load(f) or {}

    servos = data.get("servos", {})

    if args.mock:
        from vapa.hal import MockPCA9685
        pca = MockPCA9685()
    else:
        from vapa.hal import RealPCA9685
        pca = RealPCA9685(bus_num=7, address=0x40, frequency_hz=50)

    if not pca.initialize():
        print("ERROR: Failed to initialize PCA9685.")
        sys.exit(1)

    # Backup configuration
    backup_path = CONFIG_PATH.with_suffix(".yaml.bak")
    shutil.copyfile(CONFIG_PATH, backup_path)
    print(f"Created configuration backup at: {backup_path}")

    targets = [args.servo] if args.servo and args.servo in servos else list(servos.keys())

    for s_name in targets:
        servos[s_name] = calibrate_channel(pca, s_name, servos[s_name], args.mock)

    pca.disable_all()
    pca.close()

    # Save updated YAML
    data["servos"] = servos
    with open(CONFIG_PATH, "w") as f:
        yaml.safe_dump(data, f, sort_keys=False)

    print("\n" + "=" * 72)
    print(f"SUCCESS: Calibrated {len(targets)} servos. Updated {CONFIG_PATH}.")
    print("=" * 72)

if __name__ == "__main__":
    main()
