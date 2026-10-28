#!/usr/bin/env python3
"""Interactive RealSense Depth Camera Bench Validation Tool.

SAFETY & INSTRUCTION:
- This script does NOT command or energize servos.
- Ensure camera is securely mounted on the test bench.
- Use a physical tape measure to verify RealSense depth matrix accuracy.
- Operator must verify depth calibration at 300 mm, 500 mm, and 1000 mm.
"""

import sys
import time
import argparse
import numpy as np
from pathlib import Path

def print_banner():
    print("=" * 70)
    print(" VAPA BENCH TOOL: RealSense Depth Camera Validation (Checkpoint 9)")
    print("=" * 70)
    print("SAFETY NOTICE:")
    print("1. This tool strictly inspects vision depth accuracy.")
    print("2. Servos are NOT commanded or energized during vision testing.")
    print("3. Keep USB 3.0 cable securely fastened to avoid mid-test disconnects.")
    print("=" * 70)

def main():
    parser = argparse.ArgumentParser(description="RealSense Depth Matrix Bench Verification.")
    parser.add_argument("--mock", action="store_true", help="Run with simulated synthetic frames")
    parser.add_argument("--fps", type=int, default=30, help="Camera frame rate (default: 30)")
    args = parser.parse_args()

    print_banner()

    confirm = input("Confirm: Camera securely mounted and ready to test? (type 'yes'): ")
    if confirm.strip().lower() != "yes":
        print("Test cancelled by operator.")
        sys.exit(1)

    try:
        from vapa.vision.distance_matrix import DistanceMatrixProcessor, DistanceMatrixConfig
        from vapa.vision.filters import RealSenseFilterPipeline
    except ImportError:
        print("ERROR: Run with project dependencies installed: pip install -e .")
        sys.exit(1)

    # Initialize Camera
    if args.mock:
        print("\n[MOCK MODE] Using synthetic depth generator...")
        from vapa.hal.realsense import MockRealSense
        cam = MockRealSense(width=640, height=480, fps=args.fps)
    else:
        print("\nAttempting connection to Intel RealSense D435i...")
        from vapa.hal.realsense import RealRealSense
        cam = RealRealSense(width=640, height=480, fps=args.fps)

    if not cam.initialize():
        print("ERROR: Failed to initialize RealSense camera.")
        print("Tip: If running on a developer laptop without camera hardware, pass --mock")
        sys.exit(1)

    processor = DistanceMatrixProcessor(
        config=DistanceMatrixConfig(rows=12, cols=16, min_valid_depth_m=0.10, max_valid_depth_m=1.50)
    )

    print("\n" + "=" * 70)
    print(" TAPE MEASURE VALIDATION PROTOCOL:")
    print(" Place a flat, opaque target (cardboard or book) perpendicular to camera.")
    print("=" * 70)

    test_targets_mm = [300.0, 500.0, 1000.0]
    tolerance_mm = {300.0: 15.0, 500.0: 25.0, 1000.0: 50.0}

    results = {}

    try:
        for target_dist_mm in test_targets_mm:
            print(f"\n>>> STEP: Position target at EXACTLY {target_dist_mm:.0f} mm from front lens glass.")
            input(f"    Press Enter when target is in place at {target_dist_mm:.0f} mm...")

            samples = []
            print(f"    Sampling 30 depth frames at {target_dist_mm:.0f} mm...", end="", flush=True)

            for _ in range(30):
                color, depth, t_s = cam.capture_frame()
                res = processor.process_frame(depth, t_s)
                if res.nearest_distance_m is not None:
                    samples.append(res.nearest_distance_m * 1000.0)
                time.sleep(0.033)
                print(".", end="", flush=True)

            if not samples:
                print("\n    ERROR: No valid depth pixels detected in central zone!")
                results[target_dist_mm] = (0.0, 999.0, False)
                continue

            measured_median = float(np.median(samples))
            measured_std = float(np.std(samples))
            error_mm = abs(measured_median - target_dist_mm)
            tol = tolerance_mm[target_dist_mm]
            passed = error_mm <= tol

            results[target_dist_mm] = (measured_median, error_mm, passed)
            status_str = "PASS" if passed else "FAIL"
            print(f"\n    Measured: {measured_median:.1f} mm ± {measured_std:.1f} mm | "
                  f"Error: {error_mm:.1f} mm (Tol: ±{tol:.1f} mm) -> [{status_str}]")

        # Summary Table
        print("\n" + "=" * 70)
        print(" REALSENSE DEPTH BENCH VALIDATION SUMMARY")
        print("=" * 70)
        print(f"{'Target (mm)':<15} | {'Measured (mm)':<15} | {'Error (mm)':<12} | {'Result':<8}")
        print("-" * 70)
        all_passed = True
        for tgt, (meas, err, passed) in results.items():
            status = "PASS" if passed else "FAIL"
            if not passed:
                all_passed = False
            print(f"{tgt:<15.1f} | {meas:<15.1f} | {err:<12.1f} | {status:<8}")
        print("-" * 70)

        if all_passed:
            print("\n>>> OVERALL RESULT: CHECKPOINT 9 PASSED <<<")
            print("Depth measurement meets accuracy criteria for preshape aperture guidance.")
        else:
            print("\n>>> OVERALL RESULT: CHECKPOINT 9 FAILED <<<")
            print("Depth measurement exceeds error tolerance. Check lighting, IR emitter, and lens cleanliness.")

    finally:
        cam.close()
        print("Camera link closed.")

if __name__ == "__main__":
    main()
