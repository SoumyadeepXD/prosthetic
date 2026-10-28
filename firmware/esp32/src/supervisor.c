#include "supervisor.h"
#include <string.h>

void supervisor_init(supervisor_state_t *state, const supervisor_config_t *cfg) {
    (void)cfg;
    if (!state) return;
    memset(state, 0, sizeof(supervisor_state_t));
    state->oe_enabled = false;
    state->armed = false;
    state->estop_pressed = false;
    state->latched_fault = false;
    state->force_fault = false;
    state->ads_fault = false;
    state->heartbeat_ok = false;
    state->had_first_heartbeat = false;
    state->arm_request_transitioned = false;
    state->arm_request = 0;
    state->last_heartbeat_time_ms = 0;
    state->force_fault_start_ms = 0;
}

void supervisor_process_heartbeat(supervisor_state_t *state, uint8_t arm_req, uint32_t current_time_ms) {
    if (!state) return;

    state->last_heartbeat_time_ms = current_time_ms;

    if (!state->had_first_heartbeat) {
        state->had_first_heartbeat = true;
        // On boot or reset: arm_request ignored until the first valid heartbeat plus a fresh 0 to 1 transition
        if (arm_req == 0) {
            state->arm_request_transitioned = false;
        } else {
            // Heartbeat arrived with arm_request already 1 without 0->1 transition -> ignore arming
            state->arm_request_transitioned = false;
        }
    } else {
        if (state->arm_request == 0 && arm_req == 1) {
            state->arm_request_transitioned = true;
        } else if (arm_req == 0) {
            state->arm_request_transitioned = false;
        }
    }

    state->arm_request = arm_req;
}

void supervisor_update(supervisor_state_t *state, const supervisor_config_t *cfg, uint32_t current_time_ms, const uint16_t fsr[5], bool ads_ok) {
    if (!state || !cfg) return;

    // 1. Heartbeat age check
    if (state->had_first_heartbeat) {
        uint32_t hb_age = current_time_ms - state->last_heartbeat_time_ms;
        if (hb_age > cfg->hb_timeout_ms) {
            state->heartbeat_ok = false;
            state->latched_fault = true; // Heartbeat loss latches a fault!
        } else {
            state->heartbeat_ok = true;
        }
    } else {
        state->heartbeat_ok = false;
    }

    // 2. E-Stop check
    if (state->estop_pressed) {
        state->latched_fault = true; // E-stop press latches a fault!
    }

    // 3. ADS1115 check
    if (!ads_ok) {
        state->ads_fault = true;
    } else {
        state->ads_fault = false;
    }

    // 4. Force ceiling check
    bool any_over_ceiling = false;
    if (fsr) {
        for (int i = 0; i < 5; ++i) {
            if (fsr[i] >= cfg->force_ceiling) {
                any_over_ceiling = true;
                break;
            }
        }
    }

    if (any_over_ceiling) {
        if (state->force_fault_start_ms == 0) {
            state->force_fault_start_ms = current_time_ms;
        } else {
            uint32_t duration = current_time_ms - state->force_fault_start_ms;
            if (duration >= cfg->force_hold_ms) {
                state->force_fault = true;
            }
            if (duration >= 500) {
                state->latched_fault = true; // Sustained beyond 500 ms latches fault
            }
        }
    } else {
        state->force_fault_start_ms = 0;
        state->force_fault = false;
    }

    // 5. Evaluate Output Enable (OE)
    // OE is LOW (enabled) only if:
    // arm_request == 1, arm_request_transitioned == 1, heartbeat_ok == 1,
    // E-stop released, no latched fault, ADS1115 healthy.
    if (state->arm_request == 1 &&
        state->arm_request_transitioned &&
        state->heartbeat_ok &&
        !state->estop_pressed &&
        !state->latched_fault &&
        !state->ads_fault &&
        !state->force_fault) {
        state->oe_enabled = true;
        state->armed = true;
    } else {
        state->oe_enabled = false;
        state->armed = false;
    }
}

bool supervisor_clear_fault(supervisor_state_t *state) {
    if (!state) return false;
    // Honoured only if E-stop released and arm_request is 0
    if (!state->estop_pressed && state->arm_request == 0) {
        state->latched_fault = false;
        state->force_fault = false;
        state->force_fault_start_ms = 0;
        state->arm_request_transitioned = false; // Requires fresh 0->1 transition
        return true;
    }
    return false;
}

uint16_t supervisor_get_flags(const supervisor_state_t *state) {
    if (!state) return 0;
    uint16_t flags = 0;
    if (state->estop_pressed) flags |= FLAG_ESTOP_PRESSED;
    if (state->oe_enabled)    flags |= FLAG_OE_ENABLED;
    if (state->armed)         flags |= FLAG_ARMED;
    if (state->heartbeat_ok)  flags |= FLAG_HEARTBEAT_OK;
    if (state->force_fault)   flags |= FLAG_FORCE_FAULT;
    if (state->ads_fault)     flags |= FLAG_ADS_FAULT;
    if (state->latched_fault) flags |= FLAG_LATCHED_FAULT;
    return flags;
}
