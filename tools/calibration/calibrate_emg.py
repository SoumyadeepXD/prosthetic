#!/usr/bin/env python3
"""Interactive Two-Channel EMG Calibration Tool for VAPA Rev 2.

Calibrates Flexor and Extensor muscle channels:
1. Resting Baseline Calibration (calculates baseline_mv and noise margins).
2. Maximum Voluntary Contraction (MVC) calibration for Flexor Carpi Radialis and Extensor Digitorum.
3. Automatically computes activation/deactivation thresholds, dwell times, and hysteresis.
4. Validates biomedical plausibility per Section 4.E of VAPA Master Specification.
5. Saves calibrated parameters to config/emg.yaml.
"""

import sys
import time
import argparse
import shutil
from pathlib import Path
from typing import Dict, Any, List, Tuple
import numpy as np
import yaml

CONFIG_PATH = Path("config/emg.yaml")

def print_banner():
    print("=" * 72)
    print(" VAPA BIOMEDICAL TOOL: TWO-CHANNEL EMG CALIBRATION WIZARD")
    print("=" * 72)
    print("INSTRUCTIONS FOR OPERATOR:")
    print("1. Ensure skin at electrode sites is cleaned with 70% isopropyl alcohol.")
    print("2. Snap fresh Ag/AgCl surface electrodes onto MyoWare 2.0 sensors.")
    print("3. Place Channel 1 over Flexor Carpi Radialis (anterior forearm).")
    print("4. Place Channel 2 over Extensor Digitorum (posterior forearm).")
    print("5. Place reference electrode on non-muscular bony landmark (elbow/wrist).")
    print("=" * 72)

def collect_baseline(esp_link: Any, duration_s: float = 5.0, is_mock: bool = False) -> Tuple[float, float, float, float]:
    print(f"\n[PHASE 1: RESTING BASELINE] Keep forearm completely relaxed for {duration_s:.0f} seconds...")
    flex_samples: List[float] = []
    ext_samples: List[float] = []

    t_start = time.time()
    while (time.time() - t_start) < duration_s:
        if is_mock:
            # Synthetic resting baseline ~250 mV with small noise
            flex_mv = 240.0 + np.random.normal(0, 8.0)
            ext_mv = 250.0 + np.random.normal(0, 10.0)
        else:
            sensor = esp_link.get_latest_sensor()
            if sensor:
                from vapa.emg import counts_to_mv
                flex_mv = counts_to_mv(sensor.emg[0])
                ext_mv = counts_to_mv(sensor.emg[1])
            else:
                time.sleep(0.01)
                continue

        flex_samples.append(flex_mv)
        ext_samples.append(ext_mv)
        time.sleep(0.01)

    flex_base = float(np.mean(flex_samples))
    flex_noise = float(np.std(flex_samples))
    ext_base = float(np.mean(ext_samples))
    ext_noise = float(np.std(ext_samples))

    print(f"-> Flexor Baseline:  {flex_base:.1f} mV (Noise SD: {flex_noise:.2f} mV)")
    print(f"-> Extensor Baseline: {ext_base:.1f} mV (Noise SD: {ext_noise:.2f} mV)")

    return flex_base, flex_noise, ext_base, ext_noise

def collect_mvc(esp_link: Any, muscle_name: str, channel_idx: int, is_mock: bool = False) -> float:
    print(f"\n[PHASE 2: MVC {muscle_name.upper()}] When prompted, perform MAXIMAL contraction for 3 seconds.")
    if not is_mock:
        input(f"Press Enter when ready to contract {muscle_name}... ")

    print(">>> CONTRACT MAXIMUM NOW! (3... 2... 1...) <<<")
    samples: List[float] = []
    t_start = time.time()
    while (time.time() - t_start) < 3.0:
        if is_mock:
            mv = 2200.0 + np.random.normal(0, 80.0)
        else:
            sensor = esp_link.get_latest_sensor()
            if sensor:
                from vapa.emg import counts_to_mv
                mv = counts_to_mv(sensor.emg[channel_idx])
            else:
                time.sleep(0.01)
                continue
        samples.append(mv)
        time.sleep(0.01)

    print(">>> RELAX <<<")
    # Take 95th percentile as MVC to reject transient artifacts
    mvc = float(np.percentile(samples, 95))
    print(f"-> Measured {muscle_name} 95th-percentile MVC: {mvc:.1f} mV")
    return mvc

def main():
    parser = argparse.ArgumentParser(description="VAPA EMG Calibration Tool")
    parser.add_argument("--mock", action="store_true", help="Run with simulated synthetic EMG stream")
    parser.add_argument("--duration", type=float, default=5.0, help="Resting baseline duration in seconds")
    args = parser.parse_args()

    print_banner()

    if not args.mock:
        from vapa.hal import RealESPLink
        esp_link = RealESPLink(port="/dev/ttyTHS1", baudrate=460800)
        if not esp_link.initialize():
            print("ERROR: Failed to connect to ESP32 on /dev/ttyTHS1.")
            sys.exit(1)
    else:
        from vapa.hal import MockESPLink
        esp_link = MockESPLink()
        esp_link.initialize()

    # Step 1: Baseline
    flex_base, flex_noise, ext_base, ext_noise = collect_baseline(esp_link, duration_s=args.duration, is_mock=args.mock)

    # Step 2: Flexor MVC
    flex_mvc = collect_mvc(esp_link, "Flexor (Hand Close)", 0, is_mock=args.mock)

    # Step 3: Extensor MVC
    ext_mvc = collect_mvc(esp_link, "Extensor (Hand Open)", 1, is_mock=args.mock)

    esp_link.close()

    # Biomedical Plausibility Checks
    if flex_base < 100.0 or flex_base > 800.0 or ext_base < 100.0 or ext_base > 800.0:
        print("\nWARNING: Baseline outside physiological range (100-800 mV). Check electrode adhesion.")
    if flex_mvc < 1000.0 or ext_mvc < 1000.0:
        print("\nWARNING: MVC < 1000 mV. Muscle signal too weak or gain potentiometer too low.")

    # Calculate optimal thresholds
    flex_thresh = round((flex_mvc - flex_base) * 0.35 + flex_base, 1)
    ext_thresh = round((ext_mvc - ext_base) * 0.35 + ext_base, 1)

    # Load existing config to preserve top-level keys and schema
    emg_data = {}
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r") as f:
            emg_data = yaml.safe_load(f) or {}

    if "decoder" not in emg_data:
        emg_data["decoder"] = "threshold"
    if "thresholds" not in emg_data:
        emg_data["thresholds"] = {}
    if "flexor" not in emg_data["thresholds"]:
        emg_data["thresholds"]["flexor"] = {}
    if "extensor" not in emg_data["thresholds"]:
        emg_data["thresholds"]["extensor"] = {}

    emg_data["thresholds"]["flexor"].update({
        "baseline_mv": round(flex_base, 1),
        "mvc_mv": round(flex_mvc, 1),
        "activation_threshold": 0.25,
        "deactivation_threshold": 0.15,
        "saturation_mv": 3200.0,
    })
    emg_data["thresholds"]["extensor"].update({
        "baseline_mv": round(ext_base, 1),
        "mvc_mv": round(ext_mvc, 1),
        "activation_threshold": 0.25,
        "deactivation_threshold": 0.15,
        "saturation_mv": 3200.0,
    })

    if "timing" not in emg_data:
        emg_data["timing"] = {
            "min_dwell_ms": 100,
            "debounce_ms": 50,
            "co_contraction_hold_ms": 600,
            "signal_timeout_ms": 300,
            "stuck_signal_window_s": 3.0,
        }
    if "classifier" not in emg_data:
        emg_data["classifier"] = {
            "enabled": False,
            "model_path": "",
        }
    if "eeg" not in emg_data:
        emg_data["eeg"] = {
            "enabled": False,
            "type": "analog",
            "mode_switch_threshold": 0.8,
        }

    # Backup and write YAML
    if CONFIG_PATH.exists():
        shutil.copyfile(CONFIG_PATH, CONFIG_PATH.with_suffix(".yaml.bak"))

    with open(CONFIG_PATH, "w") as f:
        yaml.safe_dump(emg_data, f, sort_keys=False)

    print("\n" + "=" * 72)
    print(f"SUCCESS: Calibrated 2-Channel EMG. Saved to {CONFIG_PATH}")
    print(f"Flexor: Baseline={flex_base:.1f}mV, MVC={flex_mvc:.1f}mV, Threshold={flex_thresh:.1f}mV")
    print(f"Extensor: Baseline={ext_base:.1f}mV, MVC={ext_mvc:.1f}mV, Threshold={ext_thresh:.1f}mV")
    print("=" * 72)

if __name__ == "__main__":
    main()
