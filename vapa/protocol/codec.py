"""Frame encoder and streaming parser for VAPA UART protocol."""

import struct
from typing import Optional, Tuple, Any
from .crc import crc16_ccitt_false
from .messages import (
    SYNC_BYTE_0, SYNC_BYTE_1, HEADER_SIZE, FOOTER_SIZE,
    MSG_TYPE_SENSOR, MSG_TYPE_STATUS, MSG_TYPE_HEARTBEAT,
    MSG_TYPE_CONFIG, MSG_TYPE_CLEAR_FAULT, MSG_TYPE_ACK_NACK,
    SensorMessage, StatusMessage, HeartbeatMessage,
    ConfigMessage, ClearFaultMessage, AckNackMessage
)

def encode_payload(msg: Any) -> Tuple[int, bytes]:
    """Encode a high-level message into (msg_type, payload_bytes)."""
    if isinstance(msg, SensorMessage):
        payload = struct.pack(
            "<I2HH5HH",
            msg.t_ms,
            msg.emg[0], msg.emg[1],
            msg.eeg,
            msg.fsr[0], msg.fsr[1], msg.fsr[2], msg.fsr[3], msg.fsr[4],
            msg.flags
        )
        return MSG_TYPE_SENSOR, payload
    elif isinstance(msg, StatusMessage):
        payload = struct.pack(
            "<HBBHHH",
            msg.fw_version, msg.reset_reason, msg.fault_code,
            msg.rx_err, msg.ads_err, msg.hb_age_ms
        )
        return MSG_TYPE_STATUS, payload
    elif isinstance(msg, HeartbeatMessage):
        payload = struct.pack("<BB", msg.arm_request, msg.jetson_state)
        return MSG_TYPE_HEARTBEAT, payload
    elif isinstance(msg, ConfigMessage):
        payload = struct.pack("<HHH", msg.force_ceiling, msg.hb_timeout_ms, msg.force_hold_ms)
        return MSG_TYPE_CONFIG, payload
    elif isinstance(msg, ClearFaultMessage):
        return MSG_TYPE_CLEAR_FAULT, b""
    elif isinstance(msg, AckNackMessage):
        payload = struct.pack("<BBB", msg.ref_type, msg.ref_seq, msg.code)
        return MSG_TYPE_ACK_NACK, payload
    else:
        raise ValueError(f"Unknown message type: {type(msg)}")

def decode_payload(msg_type: int, payload: bytes) -> Any:
    """Decode payload bytes into a high-level message dataclass."""
    if msg_type == MSG_TYPE_SENSOR:
        if len(payload) != 22:
            raise ValueError(f"Invalid SENSOR payload length: {len(payload)} != 22")
        fields = struct.unpack("<I2HH5HH", payload)
        return SensorMessage(
            t_ms=fields[0],
            emg=(fields[1], fields[2]),
            eeg=fields[3],
            fsr=(fields[4], fields[5], fields[6], fields[7], fields[8]),
            flags=fields[9]
        )
    elif msg_type == MSG_TYPE_STATUS:
        if len(payload) != 10:
            raise ValueError(f"Invalid STATUS payload length: {len(payload)} != 10")
        fields = struct.unpack("<HBBHHH", payload)
        return StatusMessage(
            fw_version=fields[0],
            reset_reason=fields[1],
            fault_code=fields[2],
            rx_err=fields[3],
            ads_err=fields[4],
            hb_age_ms=fields[5]
        )
    elif msg_type == MSG_TYPE_HEARTBEAT:
        if len(payload) != 2:
            raise ValueError(f"Invalid HEARTBEAT payload length: {len(payload)} != 2")
        arm_req, j_state = struct.unpack("<BB", payload)
        return HeartbeatMessage(arm_request=arm_req, jetson_state=j_state)
    elif msg_type == MSG_TYPE_CONFIG:
        if len(payload) != 6:
            raise ValueError(f"Invalid CONFIG payload length: {len(payload)} != 6")
        fc, hbt, fhm = struct.unpack("<HHH", payload)
        return ConfigMessage(force_ceiling=fc, hb_timeout_ms=hbt, force_hold_ms=fhm)
    elif msg_type == MSG_TYPE_CLEAR_FAULT:
        if len(payload) != 0:
            raise ValueError(f"Invalid CLEAR_FAULT payload length: {len(payload)} != 0")
        return ClearFaultMessage()
    elif msg_type == MSG_TYPE_ACK_NACK:
        if len(payload) != 3:
            raise ValueError(f"Invalid ACK_NACK payload length: {len(payload)} != 3")
        rt, rs, c = struct.unpack("<BBB", payload)
        return AckNackMessage(ref_type=rt, ref_seq=rs, code=c)
    else:
        raise ValueError(f"Unsupported message type: 0x{msg_type:02X}")

def encode_frame(msg_type: int, seq: int, payload: bytes) -> bytes:
    """Encode a binary frame with SYNC, LEN, TYPE, SEQ, PAYLOAD, CRC16."""
    payload_len = len(payload)
    if payload_len > 255:
        raise ValueError(f"Payload length exceeds 255 bytes: {payload_len}")

    header_body = bytes([payload_len, msg_type, seq & 0xFF]) + payload
    crc = crc16_ccitt_false(header_body)
    return bytes([SYNC_BYTE_0, SYNC_BYTE_1]) + header_body + struct.pack("<H", crc)

class FrameParser:
    """Streaming state machine parser with resync on garbage."""

    def __init__(self):
        self.buffer = bytearray()
        self.crc_errors = 0
        self.resync_count = 0
        self.frames_received = 0

    def parse(self, chunk: bytes):
        """Append chunk and yield all successfully parsed (msg_type, seq, payload) tuples."""
        self.buffer.extend(chunk)

        while True:
            # Need at least header (5 bytes) to determine frame length
            if len(self.buffer) < HEADER_SIZE:
                return

            # Scan for SYNC sequence 0xA5 0x5A
            if self.buffer[0] != SYNC_BYTE_0 or self.buffer[1] != SYNC_BYTE_1:
                # Discard 1 byte and resync
                self.buffer.pop(0)
                self.resync_count += 1
                continue

            payload_len = self.buffer[2]
            total_frame_len = HEADER_SIZE + payload_len + FOOTER_SIZE

            if len(self.buffer) < total_frame_len:
                # Wait for more bytes
                return

            # Complete frame candidate available
            msg_type = self.buffer[3]
            seq = self.buffer[4]
            payload = bytes(self.buffer[HEADER_SIZE : HEADER_SIZE + payload_len])
            crc_received = struct.unpack("<H", self.buffer[HEADER_SIZE + payload_len : total_frame_len])[0]

            # Verify CRC over LEN, TYPE, SEQ, PAYLOAD
            crc_data = bytes(self.buffer[2 : HEADER_SIZE + payload_len])
            crc_calculated = crc16_ccitt_false(crc_data)

            if crc_received == crc_calculated:
                # Valid frame
                del self.buffer[:total_frame_len]
                self.frames_received += 1
                yield (msg_type, seq, payload)
            else:
                # CRC error - drop sync byte 0 and scan forward
                self.crc_errors += 1
                self.buffer.pop(0)
                self.resync_count += 1
