#!/usr/bin/env python3
"""Raw UART Diagnostic Tool for Jetson <-> ESP32 Serial Line Verification.

Used to test raw TX/RX line integrity before flashing full binary protocol firmware.
Default port: /dev/ttyTHS1 (Jetson Pins 8 TXD, 10 RXD, 9 GND).
"""

import sys
import time
import argparse

def main():
    parser = argparse.ArgumentParser(description="VAPA Raw UART Test Tool")
    parser.add_argument("--port", default="/dev/ttyTHS1", help="Serial port device (default: /dev/ttyTHS1)")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate (default: 115200 for basic test, 460800 for VAPA production)")
    parser.add_argument("--send-interval", type=float, default=1.0, help="Interval in seconds between ping messages")
    args = parser.parse_args()

    print("=" * 65)
    print("      VAPA RAW UART LINE INTEGRITY TEST")
    print("=" * 65)
    print(f" Port: {args.port}")
    print(f" Baud: {args.baud}")
    print(" Pin Wiring:")
    print("   Jetson Pin 8  (TXD) -> ESP32 RX (GPIO16 recommended)")
    print("   Jetson Pin 10 (RXD) -> ESP32 TX (GPIO17 recommended)")
    print("   Jetson Pin 9  (GND) -> ESP32 GND")
    print("=" * 65)

    try:
        import serial
    except ImportError:
        print("ERROR: pyserial is not installed. Run: pip install pyserial")
        sys.exit(1)

    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.1)
    except PermissionError:
        print(f"\n[ERROR] Permission denied on {args.port}.")
        print("To fix permission permanently, run:")
        print(f"  sudo usermod -aG dialout $USER")
        print("Or temporarily grant access for this session:")
        print(f"  sudo chmod 666 {args.port}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Could not open {args.port}: {e}")
        sys.exit(1)

    print(f"\n[SUCCESS] Successfully opened {args.port} at {args.baud} baud.")
    print("Listening for incoming bytes and sending PINGs every second...")
    print("Press Ctrl+C to exit.\n")

    counter = 0
    last_send = time.time()

    try:
        while True:
            # Check for incoming bytes
            if ser.in_waiting > 0:
                raw = ser.read(ser.in_waiting)
                try:
                    text = raw.decode("utf-8", errors="replace").strip()
                    print(f" [RX from ESP32] {text}  (hex: {raw.hex(' ')})")
                except Exception:
                    print(f" [RX raw hex] {raw.hex(' ')}")

            # Send ping periodically
            now = time.time()
            if now - last_send >= args.send_interval:
                counter += 1
                msg = f"PING_FROM_JETSON_{counter}\n"
                ser.write(msg.encode("utf-8"))
                print(f" [TX to ESP32]   {msg.strip()}")
                last_send = now

            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\nTest terminated by user.")
    finally:
        ser.close()
        print("Serial port closed cleanly.")

if __name__ == "__main__":
    main()
