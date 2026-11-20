#!/usr/bin/env python3
"""Interactive USB Webcam & Perception Bench Validation Tool.

SAFETY & INSTRUCTION:
- This script does NOT command or energize servos.
- Ensure webcam (e.g. Logitech C920) is securely mounted or aimed at the test workspace.
- Operator can present various target objects (bottle, cup, apple, pen, book)
  to verify real-time object detection, class-to-profile mapping, and N-of-M voting.
"""

import sys
import os
import time
import argparse
from pathlib import Path
from typing import Optional
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

def print_banner():
    print("=" * 70)
    print(" VAPA BENCH TOOL: USB Webcam & Perception Validation")
    print("=" * 70)
    print("SAFETY NOTICE:")
    print("1. This tool strictly inspects video capture and perception.")
    print("2. Servos are NOT commanded or energized during vision testing.")
    print("3. Hold target objects (bottle, cup, pen, ball) 20-50 cm in front of lens.")
    print("=" * 70)

def main():
    parser = argparse.ArgumentParser(description="USB Webcam & Grip Perception Bench Tool.")
    parser.add_argument("--device-index", type=int, default=0, help="V4L2 video device index (default: 0 -> /dev/video0)")
    parser.add_argument("--width", type=int, default=640, help="Capture width (default: 640)")
    parser.add_argument("--height", type=int, default=480, help="Capture height (default: 480)")
    parser.add_argument("--fps", type=int, default=30, help="Target FPS (default: 30)")
    parser.add_argument("--mock", action="store_true", help="Run with synthetic test frames instead of physical camera")
    parser.add_argument("--headless", action="store_true", help="Run in terminal without GUI preview window")
    parser.add_argument("--duration", type=float, default=0.0, help="Optional duration in seconds (0 = run until stopped)")
    args = parser.parse_args()

    print_banner()

    confirm = input("Confirm: Ready to begin webcam perception test? (type 'yes'): ")
    if confirm.strip().lower() != "yes":
        print("Test cancelled by operator.")
        sys.exit(1)

    try:
        from vapa.hal import GenericWebcam, MockWebcam
        from vapa.vision.detector import (
            MockObjectDetector,
            ONNXObjectDetector,
            GripSelector,
            GripSelectionResult,
        )
    except ImportError as e:
        print(f"ERROR importing VAPA modules: {e}")
        print("Run with project dependencies installed: pip install -e .")
        sys.exit(1)

    # 1. Initialize Camera Backend
    if args.mock:
        print(f"\n[MOCK MODE] Initializing MockWebcam ({args.width}x{args.height} @ {args.fps}fps)...")
        cam = MockWebcam(width=args.width, height=args.height, fps=args.fps)
    else:
        print(f"\nConnecting to physical USB webcam at /dev/video{args.device_index}...")
        cam = GenericWebcam(device_index=args.device_index, width=args.width, height=args.height, fps=args.fps)

    if not cam.initialize():
        print(f"\nERROR: Failed to initialize webcam on index {args.device_index}.")
        print("Check connections with 'ls -l /dev/video*' or verify user is in 'video' group.")
        sys.exit(1)

    # 2. Initialize Grip Selector
    if args.mock:
        detector = MockObjectDetector(default_class="bottle", confidence=0.90)
    else:
        # Load ONNX detector if model exists, or standby
        model_path = "models/yolov8n_prosthetics.onnx"
        detector = ONNXObjectDetector(model_path=model_path, confidence_threshold=0.45)

    selector = GripSelector(
        detector=detector,
        confidence_threshold=0.45,
        voting_n=5,
        voting_m=7,
    )

    can_show_gui = False
    if not args.headless and os.environ.get("DISPLAY"):
        try:
            import cv2
            can_show_gui = True
            print("GUI preview enabled (press 'q' in preview window to exit).")
        except Exception:
            can_show_gui = False

    print("\nStreaming webcam frames (Press Ctrl+C to stop)...")
    print("-" * 75)
    print(f"{'FPS':<6} | {'Detected Class':<16} | {'Conf':<6} | {'Grip Profile':<14} | {'Locked':<6} | {'Status'}")
    print("-" * 75)

    frame_count = 0
    t_start = time.time()
    t_last_fps = t_start
    fps_measured = 0.0

    try:
        while True:
            t0 = time.perf_counter()

            # Grab frame
            try:
                frame, t_frame = cam.capture_frame()
            except Exception as e:
                print(f"Frame capture error: {e}")
                time.sleep(0.02)
                continue

            frame_count += 1

            # Process grip perception
            result: GripSelectionResult = selector.process(frame)

            # Measure rolling FPS
            now = time.time()
            if (now - t_last_fps) >= 1.0:
                fps_measured = frame_count / (now - t_last_fps)
                frame_count = 0
                t_last_fps = now

                cls_str = result.class_name if result.class_name else "none"
                conf_str = f"{result.confidence:.2f}" if result.confidence > 0 else "--"
                lock_str = "YES" if result.is_locked else "no"
                print(
                    f"{fps_measured:<6.1f} | {cls_str:<16} | {conf_str:<6} | "
                    f"{result.profile_name:<14} | {lock_str:<6} | OK"
                )

            # Optional GUI preview
            if can_show_gui:
                import cv2
                display_img = frame.copy()
                h, w = display_img.shape[:2]

                # Draw bounding box if present
                if result.bounding_box is not None:
                    x1, y1, x2, y2 = result.bounding_box
                    pt1 = (int(x1 * w), int(y1 * h))
                    pt2 = (int(x2 * w), int(y2 * h))
                    cv2.rectangle(display_img, pt1, pt2, (0, 255, 0), 2)

                # Draw telemetry banner
                banner_text = f"Profile: {result.profile_name} (Lock: {result.is_locked}) | FPS: {fps_measured:.1f}"
                cv2.putText(
                    display_img,
                    banner_text,
                    (15, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 255),
                    2,
                )
                if result.class_name:
                    sub_text = f"Class: {result.class_name} ({result.confidence*100:.0f}%)"
                    cv2.putText(
                        display_img,
                        sub_text,
                        (15, 60),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (0, 255, 0),
                        2,
                    )

                cv2.imshow("VAPA USB Webcam Perception Feed", display_img)
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == 27:
                    break

            if args.duration > 0 and (now - t_start) >= args.duration:
                print(f"\nTest duration limit ({args.duration}s) reached.")
                break

            # Rate limit loop
            dt_step = 1.0 / args.fps
            elapsed = time.perf_counter() - t0
            time.sleep(max(0.0, dt_step - elapsed))

    except KeyboardInterrupt:
        print("\nTest interrupted by operator (Ctrl+C).")
    finally:
        cam.close()
        if can_show_gui:
            try:
                import cv2
                cv2.destroyAllWindows()
            except Exception:
                pass
        print("Webcam closed cleanly. Perception test finished.")

if __name__ == "__main__":
    main()
