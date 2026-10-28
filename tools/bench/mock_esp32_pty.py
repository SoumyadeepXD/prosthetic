#!/usr/bin/env python3
"""Launch Mock ESP32 Simulator on a Virtual Serial Port (PTY).

Provides a virtual serial endpoint (e.g. /dev/ttys00X) simulating all Section 4
supervisor rules, ADS1115 envelope streams, and FSR sensors.
"""

import time
import signal
import sys
from vapa.hal import MockESP32Pty

def main():
    print("=" * 60)
    print(" VAPA BENCH TOOL: Mock ESP32 Virtual Serial Peer (PTY)")
    print("=" * 60)

    sim = MockESP32Pty()
    slave_port = sim.start()

    print(f"\n[+] Mock ESP32 is running on virtual serial port: {slave_port}")
    print("You can connect another terminal or test tool to this port:")
    print(f"    python tools/bench/esp_link_monitor.py (configured with {slave_port})")
    print(f"    minicom -D {slave_port} -b 460800")
    print("\nPress Ctrl+C to terminate the virtual peer...")

    def handle_exit(sig, frame):
        print("\nStopping Mock ESP32...")
        sim.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()
