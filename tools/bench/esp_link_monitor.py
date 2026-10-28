#!/usr/bin/env python3
"""ESP32 <-> Jetson UART2 Link Integrity Monitor.

Baud: 460800 8N1
Pin 8 TXD -> ESP32 GPIO16 RX2
Pin 10 RXD -> ESP32 GPIO17 TX2
"""

import sys
import time

def main():
    print("=" * 60)
    print(" VAPA BENCH TOOL: ESP32 UART Link Monitor")
    print("=" * 60)
    print("Monitors real-time 100 Hz sensor frames from ESP32.")
    print("Port: /dev/ttyTHS1, Baud: 460800")
    print("Verify cross-wiring before proceeding (Jetson Pin 8 -> ESP32 Pin 16, Pin 10 -> Pin 17).")
    input("\nPress Enter to begin monitoring...")

    try:
        from vapa.hal.esp_link import RealESPLink
    except ImportError:
        print("ERROR: Run from project root with vapa installed: pip install -e .")
        sys.exit(1)

    link = RealESPLink(port="/dev/ttyTHS1", baudrate=460800)
    if not link.initialize():
        print("ERROR: Failed to open serial port /dev/ttyTHS1")
        print("Ensure 'nvgetty' is disabled and user is in 'dialout' group.")
        sys.exit(1)

    print("\nStreaming sensor frames (Press Ctrl+C to stop)...\n")
    print("t_ms     | Flex | Ext  | FSR Thumb/Idx/Mid/Rng/Lit    | Flags (OE/Arm/Estop/Fault)")
    print("-" * 75)

    try:
        while True:
            sensor = link.get_latest_sensor()
            if sensor:
                flags_desc = []
                if sensor.oe_enabled:
                    flags_desc.append("OE_ON")
                else:
                    flags_desc.append("OE_DIS")
                if sensor.armed:
                    flags_desc.append("ARMED")
                if sensor.estop_pressed:
                    flags_desc.append("ESTOP_ACT")
                if sensor.latched_fault:
                    flags_desc.append("LATCH_FAULT")
                if sensor.force_fault:
                    flags_desc.append("FORCE_FAULT")

                fsr_str = f"{sensor.fsr[0]:4d} {sensor.fsr[1]:4d} {sensor.fsr[2]:4d} {sensor.fsr[3]:4d} {sensor.fsr[4]:4d}"
                print(
                    f"{sensor.t_ms:8d} | {sensor.emg[0]:4d} | {sensor.emg[1]:4d} | {fsr_str} | {', '.join(flags_desc)}"
                )
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        stats = link.get_link_stats()
        print("\n\nSession Statistics:")
        print(f"  Frames Received: {stats.get('frames_received', 0)}")
        print(f"  CRC Errors:      {stats.get('crc_errors', 0)}")
        print(f"  Resync Events:   {stats.get('resyncs', 0)}")
        link.close()

if __name__ == "__main__":
    main()
