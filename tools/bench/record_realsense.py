#!/usr/bin/env python3
"""Interactive Human-Run RealSense Depth & Color Recording Tool.

SAFETY INSTRUCTIONS:
- RealSense capture does NOT drive servos.
- Ensure camera is securely mounted on the bench rig.
- Keep USB3 cable strain-relieved.
- Never run this script autonomously.
"""

import sys
import time
import argparse
from pathlib import Path
import numpy as np

def print_banner():
    print("=" * 65)
    print(" VAPA BENCH TOOL: RealSense Sequence Recorder")
    print("=" * 65)
    print("SAFETY NOTICE:")
    print("1. This tool records camera streams for offline algorithm testing.")
    print("2. Servos are NOT commanded during camera recording.")
    print("3. Ensure camera mount is rigid and USB3 cable is secured.")
    print("=" * 65)

def main():
    parser = argparse.ArgumentParser(description="Record aligned RealSense depth and color frames.")
    parser.add_argument("--duration", type=float, default=5.0, help="Recording duration in seconds (default: 5.0s)")
    parser.add_argument("--fps", type=int, default=30, help="Capture frame rate (default: 30 fps)")
    parser.add_argument("--output", type=str, default="data/recorded_sequence.npz", help="Output .npz filepath")
    parser.add_argument("--synthetic", action="store_true", help="Generate synthetic approach sequence instead of live capture")
    args = parser.parse_args()

    print_banner()

    confirm = input("Confirm: Camera securely mounted and ready to record? (type 'yes'): ")
    if confirm.strip().lower() != "yes":
        print("Recording cancelled.")
        sys.exit(1)

    out_path = Path(args.output)

    if args.synthetic:
        print(f"\nGenerating synthetic approach sequence ({args.duration}s @ {args.fps} fps)...")
        from vapa.vision.replay import VisionSequenceRecorder
        num_frames = int(args.duration * args.fps)
        VisionSequenceRecorder.create_synthetic_sequence(
            filepath=out_path,
            num_frames=num_frames,
            fps=float(args.fps),
            start_dist_m=0.70,
            end_dist_m=0.20,
        )
        print(f"Synthetic sequence saved to {out_path} ({num_frames} frames).")
        return

    # Live RealSense Recording
    print("\nAttempting connection to Intel RealSense D435i...")
    from vapa.hal.realsense import RealRealSense
    from vapa.vision.replay import VisionSequenceRecorder

    cam = RealRealSense(width=640, height=480, fps=args.fps)
    if not cam.initialize():
        print("ERROR: Could not initialize RealSense camera.")
        print("Tip: If running on a dev machine without camera, use --synthetic")
        sys.exit(1)

    recorder = VisionSequenceRecorder()
    num_target_frames = int(args.duration * args.fps)
    print(f"\nRecording {args.duration:.1f} seconds ({num_target_frames} frames) to {out_path}...")

    try:
        start_time = time.time()
        for idx in range(num_target_frames):
            color, depth, t = cam.capture_frame()
            recorder.record_frame(color, depth, t)
            print(f"  Frame {idx + 1:3d}/{num_target_frames} captured | time: {t - start_time:4.2f}s", end="\r")

        print(f"\nFinished capturing {len(recorder.timestamps)} frames.")
        recorder.save(out_path)
        print(f"Recording successfully saved to: {out_path} ({out_path.stat().st_size / 1e6:.2f} MB)")
    finally:
        cam.close()

if __name__ == "__main__":
    main()
