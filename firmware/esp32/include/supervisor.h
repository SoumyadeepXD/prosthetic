#ifndef VAPA_SUPERVISOR_H
#define VAPA_SUPERVISOR_H

#include <stdint.h>
#include <stdbool.h>
#include "protocol.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint16_t force_ceiling;
    uint16_t hb_timeout_ms;
    uint16_t force_hold_ms;
} supervisor_config_t;

typedef struct {
    bool estop_pressed;
    bool oe_enabled;
    bool armed;
    bool heartbeat_ok;
    bool force_fault;
    bool ads_fault;
    bool latched_fault;
    bool had_first_heartbeat;
    bool arm_request_transitioned;
    uint8_t arm_request;
    uint32_t last_heartbeat_time_ms;
    uint32_t force_fault_start_ms;
} supervisor_state_t;

void supervisor_init(supervisor_state_t *state, const supervisor_config_t *cfg);
void supervisor_process_heartbeat(supervisor_state_t *state, uint8_t arm_req, uint32_t current_time_ms);
void supervisor_update(supervisor_state_t *state, const supervisor_config_t *cfg, uint32_t current_time_ms, const uint16_t fsr[5], bool ads_ok);
bool supervisor_clear_fault(supervisor_state_t *state);
uint16_t supervisor_get_flags(const supervisor_state_t *state);

#ifdef __cplusplus
}
#endif

#endif // VAPA_SUPERVISOR_H
