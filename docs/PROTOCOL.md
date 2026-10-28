# ESP32 <-> Jetson Communication Protocol Specification

**Interface:** UART2, 460800 baud, 8N1. Little-endian byte order.

## 1. Frame Structure

Every transmission is framed as follows:

```
+------------+------------+----------+-----------+----------+-----------+----------------+
| SYNC0      | SYNC1      | LEN      | TYPE      | SEQ      | PAYLOAD   | CRC16          |
| 0xA5 (1 B) | 0x5A (1 B) | (1 Byte) | (1 Byte)  | (1 Byte) | (LEN B)   | (2 Bytes, LE)  |
+------------+------------+----------+-----------+----------+-----------+----------------+
```

- **SYNC:** `0xA5`, `0x5A` (2 bytes)
- **LEN:** Payload length in bytes (`0` to `255`). Total frame size = `LEN + 7`.
- **TYPE:** Message type identifier (`0x00` - `0xFF`).
- **SEQ:** Rolling sequence counter (`0` to `255`).
- **PAYLOAD:** Raw payload bytes of length `LEN`.
- **CRC16:** CRC16-CCITT-FALSE (polynomial `0x1021`, initial value `0xFFFF`, no reflection, XOR out `0x0000`). Calculated over `LEN`, `TYPE`, `SEQ`, and `PAYLOAD` (all bytes excluding SYNC and CRC itself).

## 2. Message Types

| TYPE | Name | Direction | Rate | Payload Format |
|---|---|---|---|---|
| `0x01` | `SENSOR` | ESP32 -> Jetson | 100 Hz | `t_ms (u32), emg[2] (2*u16), eeg (u16), fsr[5] (5*u16), flags (u16)` [22 bytes] |
| `0x02` | `STATUS` | ESP32 -> Jetson | 2 Hz | `fw_version (u16), reset_reason (u8), fault_code (u8), rx_err (u16), ads_err (u16), hb_age_ms (u16)` [10 bytes] |
| `0x10` | `HEARTBEAT` | Jetson -> ESP32 | 50 Hz | `arm_request (u8), jetson_state (u8)` [2 bytes] |
| `0x11` | `CONFIG` | Jetson -> ESP32 | On connect/change | `force_ceiling (u16), hb_timeout_ms (u16), force_hold_ms (u16)` [6 bytes] |
| `0x12` | `CLEAR_FAULT`| Jetson -> ESP32 | On demand | `(empty)` [0 bytes] |
| `0x7F` | `ACK_NACK` | Bidirectional | Asynchronous | `ref_type (u8), ref_seq (u8), code (u8)` [3 bytes] |

### Flags Bitfield (`SENSOR` message)
- Bit 0: `estop_pressed` (1 = E-stop active / LOW on GPIO27)
- Bit 1: `oe_enabled` (1 = PCA9685 OE active LOW / PWM outputs live)
- Bit 2: `armed` (1 = ESP32 supervisor is armed and healthy)
- Bit 3: `heartbeat_ok` (1 = recent heartbeat received within timeout)
- Bit 4: `force_fault` (1 = FSR exceeded force ceiling for > `force_hold_ms`)
- Bit 5: `ads_fault` (1 = ADS1115 I2C communication failure)
- Bit 6: `latched_fault` (1 = supervisor has latched a fault requiring clear)

## 3. Resynchronization and Error Handling
- The receiver must scan byte-by-byte for `0xA5 0x5A`.
- If an invalid length, unsupported type, or CRC mismatch occurs, the parser logs a sync error, drops the frame, and resumes scanning after `0xA5`.
- Non-blocking I/O must be maintained on both endpoints.
