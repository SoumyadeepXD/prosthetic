#!/usr/bin/env python3
"""Interactive Human-Run EMG Baseline & MVC Calibration Tool.

SAFETY INSTRUCTIONS:
- The prosthetic arm MUST BE DISARMED and OFF THE BODY during calibration.
- Physical Emergency Stop button MUST be in reach.
- MyoWare electrodes must be properly placed:
    * Channel A0: Flexor muscle belly (e.g. flexor digitorum superficialis)
    * Channel A1: Extensor muscle belly (e.g. extensor digitorum communis)
    * Reference ground on bony protrusion (e.g. elbow olecranon)
- Never run this script autonomously.
"""

import sys
import time
import shutil
import argparse
from pathlib import Path
from typing import List, Tuple
import yaml
import numpy as np

CONFIG_PATH = Path("config/emg.yaml")
ADS1115_MV_PER_LSB = 0.125

def print_banner():
    print("=" * 65)
    print(" VAPA BENCH TOOL: Interactive EMG Calibration CLI")
    print("=" * 65)
    print("MANDATORY SAFETY RULES:")
    print("1. Prosthetic arm MUST BE DISARMED and OFF THE BODY.")
    print("2. The physical Emergency Stop button MUST BE IN YOUR HAND.")
    print("3. MyoWare electrodes: A0 = Flexor, A1 = Extensor, Ref = Elbow.")
    print("=" * 65)

def collect_samples(link, duration_s: float, label: str) -> Tuple[np.ndarray, np.ndarray]:
    """Collect flexor and extensor samples for duration_s seconds."""
    flex_samples: List[float] = []
    ext_samples: List[float] = []

    start_time = time.time()
    next_print = start_time
    total_samples = int(duration_s * 100)

    while (time.time() - start_time) < duration_s:
        # Check for incoming sensor frames
        msg = link.get_latest_sensor()
        if msg is not None:
            raw_flex = float(msg.emg[0]) * ADS1115_MV_PER_LSB
            raw_ext = float(msg.emg[1]) * ADS1115_MV_PER_LSB
            flex_samples.append(raw_flex)
            ext_samples.append(raw_ext)

        now = time.time()
        if now >= next_print:
            elapsed = now - start_time
            remaining = max(0.0, duration_s - elapsed)
            print(f"  [{label}] Time remaining: {remaining:4.1f}s | Collected: {len(flex_samples)} samples", end="\r")
            next_print = now + 0.2
        time.sleep(0.005)

    print(f"\n  [{label}] Completed: {len(flex_samples)} samples collected.")
    if len(flex_samples) == 0:
        # Fallback for synthetic/disconnected runs
        print("  WARNING: No packets received from link. Using nominal test values.")
        return np.array([250.0]), np.array([250.0])

    return np.array(flex_samples), np.array(ext_samples)

def main():
    parser = argparse.ArgumentParser(description="Calibrate EMG baseline and MVC thresholds.")
    parser.add_argument("--port", type=str, default="/dev/ttyTHS1", help="Jetson UART device")
    parser.add_argument("--baud", type=int, default=460800, help="UART baud rate")
    parser.add_argument("--mock", action="store_true", help="Use virtual mock ESP link for dry run")
    args = parser.parse_args()

    print_banner()

    confirm = input("Confirm: Is arm safely off the body and E-Stop in reach? (type 'yes'): ")
    if confirm.strip().lower() != "yes":
        print("Calibration cancelled.")
        sys.exit(1)

    # Initialize Link
    if args.mock:
        print("\nConnecting to Mock ESP32 Link...")
        from vapa.hal.esp_link import MockESPLink
        link = MockESPLink()
        link.initialize()
    else:
        print(f"\nConnecting to Real ESP32 Link on {args.port} @ {args.baud} baud...")
        from vapa.hal.esp_link import RealESPLink
        link = RealESPLink(port=args.port, baudrate=args.baud)
        if not link.initialize():
            print(f"ERROR: Failed to connect to ESP32 on {args.port}")
            sys.exit(1)

    try:
        # --- Step 1: Rest Baseline Measurement ---
        print("\n" + "=" * 50)
        print(" STEP 1: Rest Baseline Measurement (Noise Floor)")
        print("=" * 50)
        print("Instructions: Keep forearm muscles COMPLETELY RELAXED.")
        print("Do not move fingers, clench jaw, or tense muscles.")
        input("Press [Enter] to start 5-second rest measurement...")

        flex_rest, ext_rest = collect_samples(link, 5.0, "REST BASELINE")

        flex_base = float(np.mean(flex_rest))
        flex_base_std = float(np.std(flex_rest))
        ext_base = float(np.mean(ext_rest))
        ext_base_std = float(np.std(ext_rest))

        print(f"\nRest Baseline Results:")
        print(f"  Flexor  (A0): {flex_base:6.1f} mV  (± {flex_base_std:.1f} mV)")
        print(f"  Extensor (A1): {ext_base:6.1f} mV  (± {ext_base_std:.1f} mV)")

        # --- Step 2: Flexor MVC (Maximum Voluntary Contraction) ---
        print("\n" + "=" * 50)
        print(" STEP 2: Flexor MVC (Fist Clench / Close)")
        print("=" * 50)
        print("Instructions: You will perform 3 contractions of 2 seconds each.")
        print("Squeeze your fist firmly (close intent) when prompted.")
        input("Press [Enter] to begin Flexor MVC protocol...")

        flex_mvc_peaks: List[float] = []
        for rep in range(1, 4):
            print(f"\n--- Flexor Repetition {rep} of 3 ---")
            for countdown in range(3, 0, -1):
                print(f"  Get ready in {countdown}...", end="\r")
                time.sleep(1.0)
            print("  >>> SQUEEZE NOW (HOLD FIRM)! <<<          ")
            f_samples, _ = collect_samples(link, 2.0, f"FLEX MVC REP {rep}")
            peak = float(np.percentile(f_samples, 95))
            flex_mvc_peaks.append(peak)
            print(f"  Rep {rep} 95th Percentile Peak: {peak:6.1f} mV")
            if rep < 3:
                print("  Relax muscles for 3 seconds...")
                time.sleep(3.0)

        flex_mvc = float(np.mean(flex_mvc_peaks))
        print(f"\nCalculated Flexor MVC: {flex_mvc:6.1f} mV")

        # --- Step 3: Extensor MVC (Hand Open) ---
        print("\n" + "=" * 50)
        print(" STEP 3: Extensor MVC (Hand Open / Extend)")
        print("=" * 50)
        print("Instructions: You will perform 3 contractions of 2 seconds each.")
        print("Extend your fingers and hand backwards (open intent) when prompted.")
        input("Press [Enter] to begin Extensor MVC protocol...")

        ext_mvc_peaks: List[float] = []
        for rep in range(1, 4):
            print(f"\n--- Extensor Repetition {rep} of 3 ---")
            for countdown in range(3, 0, -1):
                print(f"  Get ready in {countdown}...", end="\r")
                time.sleep(1.0)
            print("  >>> OPEN / EXTEND NOW (HOLD FIRM)! <<<    ")
            _, e_samples = collect_samples(link, 2.0, f"EXT MVC REP {rep}")
            peak = float(np.percentile(e_samples, 95))
            ext_mvc_peaks.append(peak)
            print(f"  Rep {rep} 95th Percentile Peak: {peak:6.1f} mV")
            if rep < 3:
                print("  Relax muscles for 3 seconds...")
                time.sleep(3.0)

        ext_mvc = float(np.mean(ext_mvc_peaks))
        print(f"\nCalculated Extensor MVC: {ext_mvc:6.1f} mV")

        # --- Step 4: Validation & Threshold Calculation ---
        print("\n" + "=" * 50)
        print(" CALIBRATION SUMMARY & VALIDATION")
        print("=" * 50)

        flex_snr = flex_mvc / max(1.0, flex_base)
        ext_snr = ext_mvc / max(1.0, ext_base)

        print(f"Flexor  SNR: {flex_snr:.2f}x (Baseline: {flex_base:.1f} mV, MVC: {flex_mvc:.1f} mV)")
        print(f"Extensor SNR: {ext_snr:.2f}x (Baseline: {ext_base:.1f} mV, MVC: {ext_mvc:.1f} mV)")

        if flex_snr < 1.8:
            print("WARNING: Flexor dynamic range is low (<1.8x). Consider reapplying electrode with gel.")
        if ext_snr < 1.8:
            print("WARNING: Extensor dynamic range is low (<1.8x). Consider reapplying electrode with gel.")

        # Update config/emg.yaml
        if not CONFIG_PATH.exists():
            print(f"ERROR: {CONFIG_PATH} not found.")
            sys.exit(1)

        with open(CONFIG_PATH, "r") as f:
            emg_data = yaml.safe_load(f)

        emg_data["thresholds"]["flexor"]["baseline_mv"] = round(flex_base, 1)
        emg_data["thresholds"]["flexor"]["mvc_mv"] = round(flex_mvc, 1)
        emg_data["thresholds"]["extensor"]["baseline_mv"] = round(ext_base, 1)
        emg_data["thresholds"]["extensor"]["mvc_mv"] = round(ext_mvc, 1)

        # Backup existing config
        backup_path = CONFIG_PATH.with_suffix(".yaml.bak")
        shutil.copyfile(CONFIG_PATH, backup_path)
        print(f"\nCreated backup at {backup_path}")

        with open(CONFIG_PATH, "w") as f:
            yaml.safe_dump(emg_data, f, sort_keys=False)

        print(f"Updated EMG thresholds written to {CONFIG_PATH} successfully!")

    finally:
        link.close()

if __name__ == "__main__":
    main()
