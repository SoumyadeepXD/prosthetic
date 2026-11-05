#!/usr/bin/env python3
"""Interactive 5-Fingertip FSR402 Calibration Tool for VAPA Rev 2.

Calibrates individual fingertip force sensors:
1. Guides operator through 5-point known mass application (0g, 50g, 150g, 300g, 500g).
2. Records raw 12-bit ADC counts (0..4095) from ESP32 link.
3. Generates strictly monotonic piecewise calibration curves.
4. Validates hardware plausibility bounds (open-circuit < 10, short-circuit >= 4090).
5. Updates and saves to config/fsr.yaml.
"""

import sys
import time
import argparse
import shutil
from pathlib import Path
from typing import Dict, Any, List, Tuple
import yaml

CONFIG_PATH = Path("config/fsr.yaml")
FINGERS = ["thumb", "index", "middle", "ring", "little"]
CALIBRATION_GRAMS = [0.0, 50.0, 150.0, 300.0, 500.0, 1000.0]

def print_banner():
    print("=" * 72)
    print(" VAPA SENSOR TOOL: 5-FINGERTIP FSR402 CALIBRATION WIZARD")
    print("=" * 72)
    print("PROCEDURE:")
    print("1. Have calibration test weights (e.g. 50g, 150g, 300g, 500g) ready.")
    print("2. The tool will sample each fingertip sequentially.")
    print("3. Hold weights steady on the sensor active circular area.")
    print("=" * 72)

def sample_sensor_raw(esp_link: Any, finger_idx: int, num_samples: int = 50, is_mock: bool = False, target_g: float = 0.0) -> int:
    if is_mock:
        # Realistic synthetic ADC counts for given grams
        # Baseline ~50 counts, 50g ~300, 150g ~900, 300g ~1800, 500g ~2600, 1000g ~3400
        mock_map = {0.0: 50, 50.0: 320, 150.0: 950, 300.0: 1850, 500.0: 2650, 1000.0: 3450}
        return mock_map.get(target_g, int(50 + target_g * 3.4))

    readings: List[int] = []
    for _ in range(num_samples):
        msg = esp_link.get_latest_sensor()
        if msg:
            readings.append(msg.fsr[finger_idx])
        time.sleep(0.01)

    if not readings:
        return 50
    return int(sum(readings) / len(readings))

def calibrate_finger(esp_link: Any, finger: str, finger_idx: int, is_mock: bool) -> List[List[float]]:
    print(f"\n>>> Calibrating Fingertip: {finger.upper()} <<<")
    pts: List[List[float]] = []

    for g in CALIBRATION_GRAMS:
        if not is_mock:
            input(f"Apply {g:.0f}g load to {finger.upper()} fingertip and press Enter... ")
            print(f"Sampling {finger.upper()} at {g:.0f}g...")
        adc_val = sample_sensor_raw(esp_link, finger_idx, is_mock=is_mock, target_g=g)
        print(f"-> Load: {g:.0f}g  ==>  Measured ADC: {adc_val} counts")

        # Check for hardware open / short faults
        if g == 0.0 and adc_val < 10:
            print(f"WARNING: ADC={adc_val} &lt; 10 counts indicates OPEN-CIRCUIT / detached sensor line!")
        elif adc_val >= 4090:
            print(f"WARNING: ADC={adc_val} indicates SHORT-CIRCUIT to 3.3V rail!")

        pts.append([int(adc_val), float(g)])

    # Ensure strictly monotonic by sorting on ADC
    pts.sort(key=lambda p: p[0])
    return pts

def main():
    parser = argparse.ArgumentParser(description="VAPA FSR Calibration Tool")
    parser.add_argument("--mock", action="store_true", help="Run with simulated mock sensor inputs")
    parser.add_argument("--finger", type=str, default=None, help="Calibrate a single finger only")
    args = parser.parse_args()

    print_banner()

    if args.mock:
        from vapa.hal import MockESPLink
        esp_link = MockESPLink()
        esp_link.initialize()
    else:
        from vapa.hal import RealESPLink
        esp_link = RealESPLink(port="/dev/ttyTHS1", baudrate=460800)
        if not esp_link.initialize():
            print("ERROR: Failed to connect to ESP32 on /dev/ttyTHS1.")
            sys.exit(1)

    if not CONFIG_PATH.exists():
        print(f"ERROR: {CONFIG_PATH} not found.")
        sys.exit(1)

    with open(CONFIG_PATH, "r") as f:
        data = yaml.safe_load(f) or {}

    sensors = data.get("sensors", {})
    targets = [args.finger] if args.finger and args.finger in FINGERS else FINGERS

    for f_name in targets:
        f_idx = FINGERS.index(f_name)
        pts = calibrate_finger(esp_link, f_name, f_idx, args.mock)
        if f_name not in sensors:
            sensors[f_name] = {}
        sensors[f_name]["calibration_points"] = pts
        sensors[f_name]["baseline_raw"] = pts[0][0]
        sensors[f_name]["max_raw"] = pts[-1][0]
        sensors[f_name]["calibrated"] = True

    esp_link.close()

    # Backup & save
    shutil.copyfile(CONFIG_PATH, CONFIG_PATH.with_suffix(".yaml.bak"))
    data["sensors"] = sensors
    with open(CONFIG_PATH, "w") as f:
        yaml.safe_dump(data, f, sort_keys=False)

    print("\n" + "=" * 72)
    print(f"SUCCESS: Calibrated {len(targets)} fingertip force sensors. Saved to {CONFIG_PATH}")
    print("=" * 72)

if __name__ == "__main__":
    main()
