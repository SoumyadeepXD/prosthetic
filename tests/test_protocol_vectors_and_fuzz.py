"""Comprehensive test suite for protocol golden vectors and streaming fuzz testing."""

import json
import random
from pathlib import Path
from vapa.protocol import (
    FrameParser, encode_frame, decode_payload,
    MSG_TYPE_SENSOR, MSG_TYPE_STATUS, MSG_TYPE_HEARTBEAT,
    MSG_TYPE_CONFIG, MSG_TYPE_CLEAR_FAULT, MSG_TYPE_ACK_NACK,
    crc16_ccitt_false
)

def test_shared_golden_vectors():
    fixtures_file = Path("tests/fixtures/test_vectors.json")
    assert fixtures_file.exists(), "Test vectors JSON must exist"

    with open(fixtures_file, "r") as f:
        vectors = json.load(f)

    parser = FrameParser()
    for vec in vectors:
        frame_bytes = bytes.fromhex(vec["frame_hex"])
        payload_bytes = bytes.fromhex(vec["payload_hex"])

        # 1. Verify CRC calculation over LEN, TYPE, SEQ, PAYLOAD
        crc_data = bytes([vec["len"], vec["type"], vec["seq"]]) + payload_bytes
        expected_crc = crc16_ccitt_false(crc_data)
        received_crc = frame_bytes[-2] | (frame_bytes[-1] << 8)
        assert expected_crc == received_crc, f"CRC mismatch on vector {vec['name']}"

        # 2. Verify parser extracts the frame
        parsed_frames = list(parser.parse(frame_bytes))
        assert len(parsed_frames) == 1, f"Failed to parse vector {vec['name']}"
        mtype, seq, payload = parsed_frames[0]
        assert mtype == vec["type"]
        assert seq == vec["seq"]
        assert payload == payload_bytes

        # 3. Verify decode_payload succeeds
        decoded = decode_payload(mtype, payload)
        assert decoded is not None

def test_protocol_fuzz_stream():
    """Feed 100,000 pseudo-random bytes into FrameParser. Must never crash or loop."""
    parser = FrameParser()
    rng = random.Random(0xDEADBEEF)

    # Generate random stream of 100k bytes interspersed with occasional valid frames
    data_chunks = []
    for _ in range(100):
        # 1000 random bytes
        junk = bytes(rng.getrandbits(8) for _ in range(1000))
        data_chunks.append(junk)

        # Valid heartbeat frame
        valid = encode_frame(MSG_TYPE_HEARTBEAT, seq=rng.randint(0, 255), payload=b"\x01\x02")
        data_chunks.append(valid)

    total_stream = b"".join(data_chunks)

    valid_count = 0
    # Feed stream in varied small chunk sizes to test buffer reassembly
    pos = 0
    while pos < len(total_stream):
        chunk_len = rng.randint(1, 128)
        chunk = total_stream[pos : pos + chunk_len]
        pos += chunk_len
        for mtype, seq, payload in parser.parse(chunk):
            if mtype == MSG_TYPE_HEARTBEAT and payload == b"\x01\x02":
                valid_count += 1

    # Ensure all 100 valid frames hidden inside the random noise were recovered
    assert valid_count == 100
    assert parser.crc_errors > 0 or parser.resync_count > 0
