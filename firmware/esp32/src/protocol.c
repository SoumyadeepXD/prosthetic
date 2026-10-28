#include "protocol.h"
#include <string.h>

void frame_parser_init(frame_parser_t *parser) {
    if (!parser) return;
    memset(parser, 0, sizeof(frame_parser_t));
    parser->state = PARSER_WAIT_SYNC0;
}

bool frame_parser_feed(frame_parser_t *parser, uint8_t byte, uint8_t *out_type, uint8_t *out_seq, const uint8_t **out_payload, uint8_t *out_len) {
    if (!parser) return false;

    switch (parser->state) {
        case PARSER_WAIT_SYNC0:
            if (byte == VAPA_SYNC0) {
                parser->state = PARSER_WAIT_SYNC1;
            } else {
                parser->resync_count++;
            }
            break;

        case PARSER_WAIT_SYNC1:
            if (byte == VAPA_SYNC1) {
                parser->state = PARSER_WAIT_LEN;
            } else if (byte == VAPA_SYNC0) {
                // Stay in WAIT_SYNC1 in case of back-to-back 0xA5 0xA5 0x5A
                parser->state = PARSER_WAIT_SYNC1;
                parser->resync_count++;
            } else {
                parser->state = PARSER_WAIT_SYNC0;
                parser->resync_count++;
            }
            break;

        case PARSER_WAIT_LEN:
            parser->payload_len = byte;
            parser->state = PARSER_WAIT_TYPE;
            break;

        case PARSER_WAIT_TYPE:
            parser->msg_type = byte;
            parser->state = PARSER_WAIT_SEQ;
            break;

        case PARSER_WAIT_SEQ:
            parser->seq = byte;
            parser->payload_idx = 0;
            if (parser->payload_len == 0) {
                parser->state = PARSER_WAIT_CRC_L;
            } else {
                parser->state = PARSER_WAIT_PAYLOAD;
            }
            break;

        case PARSER_WAIT_PAYLOAD:
            parser->payload_buf[parser->payload_idx++] = byte;
            if (parser->payload_idx >= parser->payload_len) {
                parser->state = PARSER_WAIT_CRC_L;
            }
            break;

        case PARSER_WAIT_CRC_L:
            parser->crc_received = (uint16_t)byte;
            parser->state = PARSER_WAIT_CRC_H;
            break;

        case PARSER_WAIT_CRC_H: {
            parser->crc_received |= ((uint16_t)byte << 8);
            parser->state = PARSER_WAIT_SYNC0;

            // Calculate CRC over LEN, TYPE, SEQ, PAYLOAD
            uint8_t header_body[3 + 256];
            header_body[0] = parser->payload_len;
            header_body[1] = parser->msg_type;
            header_body[2] = parser->seq;
            if (parser->payload_len > 0) {
                memcpy(&header_body[3], parser->payload_buf, parser->payload_len);
            }
            uint16_t crc_calc = crc16_ccitt_false(header_body, 3 + parser->payload_len);

            if (crc_calc == parser->crc_received) {
                parser->frames_received++;
                if (out_type) *out_type = parser->msg_type;
                if (out_seq) *out_seq = parser->seq;
                if (out_payload) *out_payload = parser->payload_buf;
                if (out_len) *out_len = parser->payload_len;
                return true;
            } else {
                parser->crc_errors++;
                parser->resync_count++;
                return false;
            }
        }
    }
    return false;
}

size_t frame_encode(uint8_t msg_type, uint8_t seq, const uint8_t *payload, uint8_t payload_len, uint8_t *out_frame, size_t max_out_len) {
    size_t total_len = VAPA_HEADER_SIZE + payload_len + VAPA_FOOTER_SIZE;
    if (total_len > max_out_len || !out_frame) {
        return 0;
    }

    out_frame[0] = VAPA_SYNC0;
    out_frame[1] = VAPA_SYNC1;
    out_frame[2] = payload_len;
    out_frame[3] = msg_type;
    out_frame[4] = seq;

    if (payload && payload_len > 0) {
        memcpy(&out_frame[5], payload, payload_len);
    }

    // CRC is over bytes 2 .. 4 + payload_len (LEN, TYPE, SEQ, PAYLOAD)
    uint16_t crc = crc16_ccitt_false(&out_frame[2], 3 + payload_len);
    out_frame[5 + payload_len] = (uint8_t)(crc & 0xFF);
    out_frame[6 + payload_len] = (uint8_t)((crc >> 8) & 0xFF);

    return total_len;
}
