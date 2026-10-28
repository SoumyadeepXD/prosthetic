#!/usr/bin/env python3
"""Interactive Human-Run Vision Replay & Distance Matrix Verification Tool.

SAFETY INSTRUCTIONS:
- This tool is an offline replay utility for evaluating vision algorithms.
- Servos are NOT commanded during replay.
- Never run this script autonomously.
"""

import sys
import time
import argparse
from pathlib import Path
import numpy as np

def print_banner():
    print("=" * 65)
    print(" VAPA BENCH TOOL: Vision Offline Replay & Proximity Inspector")
    print("=" * 65)
    print("NOTICE: Offline inspection tool. No hardware actuators are driven.")
    print("=" * 65)

def print_ascii_matrix(grid_m: np.ndarray, grid_valid: np.ndarray, nearest_cell):
    """Render a compact 12x16 ASCII visualization of the distance matrix."""
    rows, cols = grid_m.shape
    print("\n   " + "".join([f"{c:3d}" for c in range(cols)]))
    for r in range(rows):
        line = [f"{r:2d} "]
        for c in range(cols):
            if nearest_cell and (r, c) == nearest_cell:
                line.append(" * ")
            elif grid_valid[r, c]:
                val = grid_m[r, c]
                if val < 0.30:
                    line.append(" # ")
                elif val < 0.50:
                    line.append(" + ")
                else:
                    line.append(" . ")
            else:
                line.append("   ")
        print("".join(line))
    print("Legend: [*] Nearest Target  [#] <30cm  [+] 30-50cm  [.] >50cm\n")

def main():
    parser = argparse.ArgumentParser(description="Replay recorded or synthetic depth sequence.")
    parser.add_argument("--input", type=str, default="data/recorded_sequence.npz", help="Input .npz archive")
    parser.add_argument("--delay", type=float, default=0.033, help="Playback delay in seconds (default: 0.033s for 30fps)")
    args = parser.parse_args()

    print_banner()

    confirm = input("Confirm: Run offline vision replay inspection? (type 'yes'): ")
    if confirm.strip().lower() != "yes":
        print("Replay cancelled.")
        sys.exit(1)

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"File not found: {in_path}")
        print("Tip: Generate a synthetic sequence first with: python3 tools/bench/record_realsense.py --synthetic")
        sys.exit(1)

    from vapa.vision.replay import VisionReplayHarness
    from vapa.vision.filters import FilterConfig

    harness = VisionReplayHarness(in_path, filter_config=FilterConfig())
    print(f"\nLoaded sequence with {len(harness)} frames from {in_path}.")
    print("Streaming frames through depth filters and 12x16 distance matrix processor...")

    try:
        for idx, res, t in harness.stream():
            print(f"--- Frame {idx + 1:3d}/{len(harness)} | Timestamp: {t:6.3f}s ---")
            print(f"  Nearest Surface : {res.nearest_distance_mm:6.1f} mm ({res.nearest_distance_m:.3f} m)")
            print(f"  Approach Vel    : {res.approach_velocity_mm_s:6.1f} mm/s (negative = closing in)")
            print(f"  Reach Confidence: {res.reach_confidence:5.2f} (0.0 to 1.0)")
            if res.nearest_cell:
                print(f"  Tracked Cell    : Row {res.nearest_cell[0]}, Col {res.nearest_cell[1]}")

            if (idx + 1) % 15 == 0 or idx == len(harness) - 1:
                print_ascii_matrix(res.grid_depth_m, res.grid_valid, res.nearest_cell)

            time.sleep(args.delay)

        print("\nReplay completed successfully.")
    except KeyboardInterrupt:
        print("\nReplay stopped by user.")

if __name__ == "__main__":
    main()
