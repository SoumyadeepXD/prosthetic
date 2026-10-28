"""CRC16-CCITT-FALSE implementation for VAPA UART protocol.

Parameters:
- Polynomial: 0x1021 (x^16 + x^12 + x^5 + 1)
- Initial Value: 0xFFFF
- RefIn: False
- RefOut: False
- XorOut: 0x0000
"""

def crc16_ccitt_false(data: bytes | bytearray | memoryview) -> int:
    """Calculate CRC16-CCITT-FALSE over provided data bytes."""
    crc = 0xFFFF
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc
