#!/usr/bin/env python3
"""Interactive Human-Run Servo Calibration Tool.

SAFETY INSTRUCTIONS:
- Calibrate ONE servo at a time.
- Servos MUST be unloaded (mechanical tendons/linkages disconnected).
- Physical Emergency Stop button MUST be in reach.
- Never run this script autonomously.
"""

import sys
import time
import shutil
from pathlib import Path
import yaml

CONFIG_PATH = Path("config/servos.yaml")

def print_banner():
    print("=" * 65)
    print(" VAPA BENCH TOOL: Interactive Servo Calibration CLI")
    print("=" * 65)
    print("MANDATORY SAFETY RULES:")
    print("1. All mechanical linkages and tendon cables MUST BE DISCONNECTED.")
    print("2. The physical Emergency Stop button MUST BE IN YOUR HAND.")
    print("3. Calibrate only ONE servo at a time.")
    print("=" * 65)

def main():
    print_banner()

    confirm = input("Confirm: Are servos unloaded and E-Stop ready? (type 'yes'): ")
    if confirm.strip().lower() != "yes":
        print("Calibration cancelled.")
        sys.exit(1)

    try:
        from vapa.hal.pca9685 import RealPCA9685
    except ImportError:
        print("ERROR: Run with project dependencies installed: pip install -e .")
        sys.exit(1)

    if not CONFIG_PATH.exists():
        print(f"ERROR: {CONFIG_PATH} not found.")
        sys.exit(1)

    with open(CONFIG_PATH, "r") as f:
        data = yaml.safe_load(f)

    servos = data.get("servos", {})

    print("\nConnecting to PCA9685 at 0x40 on I2C bus 7...")
    pca = RealPCA9685(bus_num=7, address=0x40, frequency_hz=50)
    if not pca.initialize():
        print("ERROR: Failed to initialize PCA9685 at 0x40.")
        sys.exit(1)

    print("\nAvailable Servos:")
    for idx, name in enumerate(servos.keys()):
        ch = servos[name]["channel"]
        cal = "CALIBRATED" if servos[name].get("calibrated", False) else "UNVERIFIED"
        print(f"  [{idx + 1}] {name:<18} (Channel {ch:2d}) - {cal}")

    while True:
        choice = input("\nEnter servo number to calibrate (or 'q' to quit and save): ").strip()
        if choice.lower() == 'q':
            break

        try:
            choice_idx = int(choice) - 1
            servo_names = list(servos.keys())
            if not (0 <= choice_idx < len(servo_names)):
                print("Invalid servo number.")
                continue
            name = servo_names[choice_idx]
        except ValueError:
            print("Invalid input.")
            continue

        s = servos[name]
        ch = s["channel"]
        print(f"\n--- Calibrating Servo: {name} (Channel {ch}) ---")
        print("Commands:")
        print("  [+] Increase pulse by 10 us      [-] Decrease pulse by 10 us")
        print("  [++] Increase pulse by 50 us     [--] Decrease pulse by 50 us")
        print("  [min] Set current pulse as MIN")
        print("  [neu] Set current pulse as NEUTRAL")
        print("  [max] Set current pulse as MAX")
        print("  [done] Finish this servo and return to menu")
        print("  [abort] Discard changes for this servo")

        curr_pulse = float(s.get("pulse_neutral_us", 1500.0))
        min_pulse = float(s.get("pulse_min_us", 1000.0))
        neu_pulse = float(s.get("pulse_neutral_us", 1500.0))
        max_pulse = float(s.get("pulse_max_us", 2000.0))

        pca.set_pulse_us(ch, curr_pulse)

        while True:
            cmd = input(f"[{name} @ {curr_pulse:.0f} us | Min: {min_pulse:.0f}, Neu: {neu_pulse:.0f}, Max: {max_pulse:.0f}] > ").strip().lower()

            if cmd == "+":
                curr_pulse = min(2300.0, curr_pulse + 10.0)
            elif cmd == "-":
                curr_pulse = max(700.0, curr_pulse - 10.0)
            elif cmd in ("++", "50"):
                curr_pulse = min(2300.0, curr_pulse + 50.0)
            elif cmd in ("--", "-50"):
                curr_pulse = max(700.0, curr_pulse - 50.0)
            elif cmd == "min":
                min_pulse = curr_pulse
                print(f"Recorded MIN pulse: {min_pulse:.0f} us")
            elif cmd == "neu":
                neu_pulse = curr_pulse
                print(f"Recorded NEUTRAL pulse: {neu_pulse:.0f} us")
            elif cmd == "max":
                max_pulse = curr_pulse
                print(f"Recorded MAX pulse: {max_pulse:.0f} us")
            elif cmd == "done":
                s["pulse_min_us"] = min_pulse
                s["pulse_neutral_us"] = neu_pulse
                s["pulse_max_us"] = max_pulse
                s["calibrated"] = True
                print(f"Saved calibration for {name}: Min={min_pulse:.0f}, Neu={neu_pulse:.0f}, Max={max_pulse:.0f}")
                pca.disable_channel(ch)
                break
            elif cmd == "abort":
                print(f"Aborted changes for {name}.")
                pca.disable_channel(ch)
                break
            else:
                print("Unknown command. Use +, -, ++, --, min, neu, max, done, abort")

            pca.set_pulse_us(ch, curr_pulse)

    # Save to config/servos.yaml with backup
    pca.disable_all()
    pca.close()

    backup_path = CONFIG_PATH.with_suffix(".yaml.bak")
    shutil.copyfile(CONFIG_PATH, backup_path)
    print(f"\nCreated backup at {backup_path}")

    with open(CONFIG_PATH, "w") as f:
        yaml.safe_dump(data, f, sort_keys=False)
    print(f"Updated configuration saved to {CONFIG_PATH}!")

if __name__ == "__main__":
    main()
