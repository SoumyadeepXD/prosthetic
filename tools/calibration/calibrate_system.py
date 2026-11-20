#!/usr/bin/env python3
"""Master Calibration Orchestrator & System Verification Wizard for VAPA Rev 2.

Runs subsystem calibration modules in orderly engineering sequence:
1. Servos: 9-channel pulse width bounds, neutral, and direction calibration.
2. FSRs: 5-fingertip force response curves and open/short plausibility bounds.
3. EMG: Flexor & Extensor resting baseline and MVC contraction thresholds.
4. Vision: RealSense D435i temporal depth precision and workspace transform.

Generates a unified system calibration certificate upon completion.
"""

import sys
import subprocess
import argparse
import time
from pathlib import Path
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CERTIFICATE_PATH = Path("config/calibration_certificate.yaml")

def print_master_banner():
    print("=" * 76)
    print("   VAPA MASTER SYSTEM CALIBRATION & HARDWARE COMMISSIONING WIZARD")
    print("=" * 76)
    print("This wizard will guide you through full bench calibration of the arm:")
    print("  [Step 1/4] Servo Controller & Actuators (9 Channels)")
    print("  [Step 2/4] FSR402 Fingertip Force Sensors (5 Channels)")
    print("  [Step 3/4] MyoWare 2.0 Isolated EMG Envelope Acquisition (2 Channels)")
    print("  [Step 4/4] Intel RealSense D435i Camera & Workspace Calibration")
    print("=" * 76)

def run_step(step_num: int, total_steps: int, script_name: str, description: str, mock_flag: bool) -> bool:
    print(f"\n{'='*30} [STEP {step_num}/{total_steps}: {description.upper()}] {'='*30}")
    script_path = Path(__file__).parent / script_name

    cmd = [sys.executable, str(script_path)]
    if mock_flag:
        cmd.append("--mock")

    try:
        ret = subprocess.run(cmd, check=True)
        return ret.returncode == 0
    except subprocess.CalledProcessError:
        print(f"\nERROR: Step {step_num} ({description}) failed or was aborted.")
        return False
    except KeyboardInterrupt:
        print("\nMaster calibration cancelled by user.")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="VAPA Master System Calibration Wizard")
    parser.add_argument("--mock", action="store_true", help="Run full calibration in mock simulation mode")
    parser.add_argument("--skip-servos", action="store_true", help="Skip servo calibration")
    parser.add_argument("--skip-emg", action="store_true", help="Skip EMG calibration")
    parser.add_argument("--skip-camera", action="store_true", default=True, help="Skip camera calibration (default: True until webcam integration)")
    parser.add_argument("--with-camera", action="store_true", help="Include camera calibration step")
    args = parser.parse_args()

    print_master_banner()

    if not args.mock:
        confirm = input("Are you ready to begin the full system calibration? (yes/no): ")
        if confirm.strip().lower() != "yes":
            print("Aborted.")
            sys.exit(1)

    include_camera = args.with_camera or (args.mock and not args.skip_camera)

    steps = [
        ("calibrate_servos.py", "Servo Controller & Actuator Limits", not args.skip_servos),
        ("calibrate_fsr.py", "FSR402 Fingertip Force Sensors", True),
        ("calibrate_emg.py", "Two-Channel EMG Baseline & MVC", not args.skip_emg),
        ("calibrate_camera.py", "RealSense D435i Camera Alignment", include_camera),
    ]

    active_steps = [s for s in steps if s[2]]
    total = len(active_steps)

    results = {}
    for idx, (script, desc, enabled) in enumerate(active_steps, 1):
        success = run_step(idx, total, script, desc, args.mock)
        results[desc] = "PASSED" if success else "FAILED"
        if not success and not args.mock:
            cont = input("Step failed. Continue to next step? (yes/no): ")
            if cont.strip().lower() != "yes":
                sys.exit(1)

    # Generate Calibration Certificate
    all_passed = all(status == "PASSED" for status in results.values())
    certificate = {
        "certificate_id": f"VAPA-CAL-{int(time.time())}",
        "date": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "mode": "MOCK_SIMULATION" if args.mock else "PHYSICAL_BENCH_HARDWARE",
        "overall_status": "CERTIFIED" if all_passed else "INCOMPLETE",
        "subsystem_checks": results,
        "operator": "VAPA Validation Engineer",
    }

    with open(CERTIFICATE_PATH, "w") as f:
        yaml.safe_dump(certificate, f, sort_keys=False)

    print("\n" + "=" * 76)
    print("   MASTER CALIBRATION COMPLETE")
    print("=" * 76)
    for name, stat in results.items():
        print(f"  • {name:<45} : [{stat}]")
    print(f"\nCalibration Certificate written to: {CERTIFICATE_PATH}")
    print("=" * 76)

if __name__ == "__main__":
    main()
