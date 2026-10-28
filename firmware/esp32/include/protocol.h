#ifndef VAPA_PROTOCOL_H
#define VAPA_PROTOCOL_H

#include <stdint.h>
#include <stddef.h>

#define VAPA_SYNC0 0xA5
#define VAPA_SYNC1 0x5A

#define MSG_TYPE_SENSOR      0x01
#define MSG_TYPE_STATUS      0x02
#define MSG_TYPE_HEARTBEAT   0x10
#define MSG_TYPE_CONFIG      0x11
#define MSG_TYPE_CLEAR_FAULT 0x12
#define MSG_TYPE_ACK_NACK    0x7F

#define FLAG_ESTOP_PRESSED (1 << 0)
#define FLAG_OE_ENABLED    (1 << 1)
#define FLAG_ARMED         (1 << 2)
#define FLAG_HEARTBEAT_OK  (1 << 3)
#define FLAG_FORCE_FAULT   (1 << 4)
#define FLAG_ADS_FAULT     (1 << 5)
#define FLAG_LATCHED_FAULT (1 << 6)

#pragma pack(push, 1)

typedef struct {
    uint32_t t_ms;
    uint16_t emg[2];
    uint16_t eeg;
    uint16_t fsr[5];
    uint16_t flags;
} sensor_payload_t;

typedef struct {
    uint16_t fw_version;
    uint8_t reset_reason;
    uint8_t fault_code;
    uint16_t rx_err;
    uint16_t ads_err;
    uint16_t hb_age_ms;
} status_payload_t;

typedef struct {
    uint8_t arm_request;
    uint8_t jetson_state;
} heartbeat_payload_t;

typedef struct {
    uint16_t force_ceiling;
    uint16_t hb_timeout_ms;
    uint16_t force_hold_ms;
} config_payload_t;

typedef struct {
    uint8_t ref_type;
    uint8_t ref_seq;
    uint8_t code;
} ack_nack_payload_t;

#pragma pack(pop)

// CRC16-CCITT-FALSE (poly 0x1021, init 0xFFFF)
static inline uint16_t crc16_ccitt_false(const uint8_t *data, size_t length) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < length; ++i) {
        crc ^= ((uint16_t)data[i] << 8);
        for (int j = 0; j < 8; ++j) {
            if (crc & 0x8000) {
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF;
            } else {
                crc = (crc << 1) & 0xFFFF;
            }
        }
    }
    return crc;
}

#endif // VAPA_PROTOCOL_H
