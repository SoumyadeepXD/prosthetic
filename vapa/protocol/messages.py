"""Protocol message definitions and dataclasses for VAPA."""

from dataclasses import dataclass
from typing import Tuple

# Protocol Constants
SYNC_BYTE_0 = 0xA5
SYNC_BYTE_1 = 0x5A
HEADER_SIZE = 5  # SYNC0, SYNC1, LEN, TYPE, SEQ
FOOTER_SIZE = 2  # CRC16 (2 bytes LE)
OVERHEAD_SIZE = HEADER_SIZE + FOOTER_SIZE  # 7 bytes

# Message Types
MSG_TYPE_SENSOR = 0x01
MSG_TYPE_STATUS = 0x02
MSG_TYPE_HEARTBEAT = 0x10
MSG_TYPE_CONFIG = 0x11
MSG_TYPE_CLEAR_FAULT = 0x12
MSG_TYPE_ACK_NACK = 0x7F

# Flag Bits for MSG_TYPE_SENSOR
FLAG_ESTOP_PRESSED = 1 << 0
FLAG_OE_ENABLED    = 1 << 1
FLAG_ARMED         = 1 << 2
FLAG_HEARTBEAT_OK  = 1 << 3
FLAG_FORCE_FAULT   = 1 << 4
FLAG_ADS_FAULT     = 1 << 5
FLAG_LATCHED_FAULT = 1 << 6

@dataclass
class SensorMessage:
    t_ms: int
    emg: Tuple[int, int]
    eeg: int
    fsr: Tuple[int, int, int, int, int]
    flags: int

    @property
    def estop_pressed(self) -> bool:
        return bool(self.flags & FLAG_ESTOP_PRESSED)

    @property
    def oe_enabled(self) -> bool:
        return bool(self.flags & FLAG_OE_ENABLED)

    @property
    def armed(self) -> bool:
        return bool(self.flags & FLAG_ARMED)

    @property
    def heartbeat_ok(self) -> bool:
        return bool(self.flags & FLAG_HEARTBEAT_OK)

    @property
    def force_fault(self) -> bool:
        return bool(self.flags & FLAG_FORCE_FAULT)

    @property
    def ads_fault(self) -> bool:
        return bool(self.flags & FLAG_ADS_FAULT)

    @property
    def latched_fault(self) -> bool:
        return bool(self.flags & FLAG_LATCHED_FAULT)

@dataclass
class StatusMessage:
    fw_version: int
    reset_reason: int
    fault_code: int
    rx_err: int
    ads_err: int
    hb_age_ms: int

@dataclass
class HeartbeatMessage:
    arm_request: int  # 0 or 1
    jetson_state: int

@dataclass
class ConfigMessage:
    force_ceiling: int
    hb_timeout_ms: int
    force_hold_ms: int

@dataclass
class ClearFaultMessage:
    pass

@dataclass
class AckNackMessage:
    ref_type: int
    ref_seq: int
    code: int  # 0 = ACK, >0 = error/nack code
