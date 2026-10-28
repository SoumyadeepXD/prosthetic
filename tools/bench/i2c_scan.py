#!/usr/bin/env python3
"""I2C Bus Scanner for Jetson Orin Nano (Bus 7).

Expected devices on Hardware Connection Guide Rev 2:
- 0x40: PCA9685 PWM Driver
- 0x71: TCA9548A I2C Multiplexer (A0 tied to 3.3V)
- Note: 0x70 is PCA9685 All-Call address (disabled in software)
"""

import sys

def main():
    print("=" * 60)
    print(" VAPA BENCH TOOL: I2C Bus Scanner (/dev/i2c-7)")
    print("=" * 60)
    print("This tool inspects connected I2C devices on the Jetson Orin Nano.")
    print("Ensure 3.3V logic connections are properly wired to Pins 3 & 5.")
    input("\nPress Enter to begin bus scan...")

    try:
        from smbus2 import SMBus
    except ImportError:
        print("\nERROR: 'smbus2' is not installed. Run: pip install smbus2")
        sys.exit(1)

    bus_num = 7
    print(f"\nScanning I2C bus {bus_num}...")
    found = []

    try:
        with SMBus(bus_num) as bus:
            for addr in range(0x03, 0x78):
                try:
                    bus.read_byte(addr)
                    found.append(addr)
                except Exception:
                    pass
    except Exception as e:
        print(f"Failed to access /dev/i2c-{bus_num}: {e}")
        print("Check user permissions (sudo usermod -aG i2c $USER) or verify bus number with 'i2cdetect -l'.")
        sys.exit(1)

    print("\nScan Results:")
    print("-" * 30)
    if not found:
        print("No I2C devices detected.")
    else:
        for addr in found:
            notes = []
            if addr == 0x40:
                notes.append("PCA9685 (Expected)")
            elif addr == 0x71:
                notes.append("TCA9548A Mux (Expected)")
            elif addr == 0x70:
                notes.append("PCA9685 All-Call (Expected until disabled)")
            elif addr == 0x36:
                notes.append("AS5600 (Visible if mux channel active)")
            note_str = f" <-- {', '.join(notes)}" if notes else ""
            print(f"Found device at: 0x{addr:02X}{note_str}")

    print("\nVerification checklist:")
    print(f"  [ {'X' if 0x40 in found else ' '} ] 0x40 PCA9685 present")
    print(f"  [ {'X' if 0x71 in found else ' '} ] 0x71 TCA9548A Mux present")

if __name__ == "__main__":
    main()
