"""Test protocol CRC, frame packing, parsing, resync, and error handling."""

import struct
from vapa.protocol import (
    crc16_ccitt_false,
    encode_frame, encode_payload, decode_payload,
    FrameParser,
    SensorMessage, StatusMessage, HeartbeatMessage, ConfigMessage,
    ClearFaultMessage, AckNackMessage,
    MSG_TYPE_SENSOR, MSG_TYPE_HEARTBEAT
)

def test_crc16_known_vector():
    # Standard test vector for CRC16-CCITT-FALSE (init 0xFFFF, poly 0x1021)
    # "123456789" ASCII -> 0x29B1
    test_str = b"123456789"
    crc = crc16_ccitt_false(test_str)
    assert crc == 0x29B1

def test_sensor_message_roundtrip():
    msg = SensorMessage(
        t_ms=123456,
        emg=(350, 420),
        eeg=512,
        fsr=(55, 60, 75, 40, 30),
        flags=0x0006  # armed | oe_enabled
    )
    msg_type, payload = encode_payload(msg)
    assert msg_type == MSG_TYPE_SENSOR
    assert len(payload) == 22

    frame = encode_frame(msg_type, seq=42, payload=payload)
    assert frame[0] == 0xA5
    assert frame[1] == 0x5A

    parser = FrameParser()
    frames = list(parser.parse(frame))
    assert len(frames) == 1
    rx_type, rx_seq, rx_payload = frames[0]
    assert rx_type == msg_type
    assert rx_seq == 42

    decoded = decode_payload(rx_type, rx_payload)
    assert decoded.t_ms == 123456
    assert decoded.emg == (350, 420)
    assert decoded.eeg == 512
    assert decoded.fsr == (55, 60, 75, 40, 30)
    assert decoded.oe_enabled is True
    assert decoded.armed is True
    assert decoded.estop_pressed is False

def test_parser_resync_after_garbage():
    parser = FrameParser()
    garbage = b"\x00\xFF\x12\xA5\x00\x55\xDE\xAD\xBE\xEF"

    hb = HeartbeatMessage(arm_request=1, jetson_state=2)
    mtype, payload = encode_payload(hb)
    valid_frame = encode_frame(mtype, seq=10, payload=payload)

    stream = garbage + valid_frame
    frames = list(parser.parse(stream))
    assert len(frames) == 1
    assert frames[0][0] == MSG_TYPE_HEARTBEAT
    assert frames[0][1] == 10
    assert parser.resync_count > 0

def test_parser_corrupted_crc_dropped():
    parser = FrameParser()
    hb = HeartbeatMessage(arm_request=1, jetson_state=2)
    mtype, payload = encode_payload(hb)
    frame = bytearray(encode_frame(mtype, seq=5, payload=payload))

    # Corrupt a byte in payload
    frame[5] ^= 0xFF

    frames = list(parser.parse(bytes(frame)))
    assert len(frames) == 0
    assert parser.crc_errors == 1
