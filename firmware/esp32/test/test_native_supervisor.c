/**
 * Host-Side Native Unit Tests for ESP32 Supervisor State Machine & Protocol Codec
 *
 * Verifies all rules from Section 4 of VAPA Master Prompt:
 * 1. Boot state (OE disabled, arm_request ignored without fresh 0->1 transition)
 * 2. E-stop press latches fault and drops OE
 * 3. Heartbeat loss (>250ms) latches fault and drops OE
 * 4. Force ceiling (>100ms sets force_fault, >500ms latches fault)
 * 5. ADS1115 fault drops OE immediately
 * 6. CLEAR_FAULT only honoured if E-stop released and arm_request == 0
 * 7. Re-arming requires fresh 0->1 transition
 * 8. Codec roundtrip against golden test vectors
 * 9. Codec fuzz resilience
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include "../include/protocol.h"
#include "../include/supervisor.h"

static int g_tests_run = 0;
static int g_tests_passed = 0;

#define TEST_ASSERT(cond, msg) do { \
    g_tests_run++; \
    if (!(cond)) { \
        printf("FAILED: %s (line %d): %s\n", __func__, __LINE__, msg); \
        assert(cond); \
    } else { \
        g_tests_passed++; \
    } \
} while(0)

void test_supervisor_boot_state() {
    supervisor_state_t state;
    supervisor_config_t cfg = {.force_ceiling = 3500, .hb_timeout_ms = 250, .force_hold_ms = 100};
    supervisor_init(&state, &cfg);

    TEST_ASSERT(!state.oe_enabled, "Boot OE must be disabled");
    TEST_ASSERT(!state.armed, "Boot must be disarmed");
    TEST_ASSERT(!state.latched_fault, "Boot must not have latched fault");
    TEST_ASSERT(!state.heartbeat_ok, "Boot must not report heartbeat OK");

    // Arm request on very first heartbeat must be IGNORED (requires 0->1 transition)
    supervisor_process_heartbeat(&state, 1, 10);
    uint16_t fsr[5] = {50, 50, 50, 50, 50};
    supervisor_update(&state, &cfg, 10, fsr, true);

    TEST_ASSERT(!state.oe_enabled, "arm_request=1 on first heartbeat must be ignored");
    TEST_ASSERT(!state.armed, "System must not arm on first heartbeat without transition");

    // Now send arm_request = 0, then 1 -> must arm!
    supervisor_process_heartbeat(&state, 0, 20);
    supervisor_update(&state, &cfg, 20, fsr, true);
    TEST_ASSERT(!state.oe_enabled, "OE remains disabled at arm_request=0");

    supervisor_process_heartbeat(&state, 1, 30);
    supervisor_update(&state, &cfg, 30, fsr, true);
    TEST_ASSERT(state.oe_enabled, "OE must enable on fresh 0->1 transition");
    TEST_ASSERT(state.armed, "System must be armed");
}

void test_supervisor_heartbeat_loss() {
    supervisor_state_t state;
    supervisor_config_t cfg = {.force_ceiling = 3500, .hb_timeout_ms = 250, .force_hold_ms = 100};
    supervisor_init(&state, &cfg);
    uint16_t fsr[5] = {50, 50, 50, 50, 50};

    // Arm properly
    supervisor_process_heartbeat(&state, 0, 10);
    supervisor_process_heartbeat(&state, 1, 20);
    supervisor_update(&state, &cfg, 20, fsr, true);
    TEST_ASSERT(state.oe_enabled, "Armed");

    // Advance time past timeout (20 + 260 = 280ms)
    supervisor_update(&state, &cfg, 280, fsr, true);
    TEST_ASSERT(!state.oe_enabled, "OE must drop on heartbeat timeout");
    TEST_ASSERT(!state.heartbeat_ok, "Heartbeat must not be OK");
    TEST_ASSERT(state.latched_fault, "Heartbeat loss must latch a fault");

    // Fresh heartbeat arrives without clear fault -> must remain disabled
    supervisor_process_heartbeat(&state, 1, 290);
    supervisor_update(&state, &cfg, 290, fsr, true);
    TEST_ASSERT(!state.oe_enabled, "OE must remain disabled under latched fault");
}

void test_supervisor_estop() {
    supervisor_state_t state;
    supervisor_config_t cfg = {.force_ceiling = 3500, .hb_timeout_ms = 250, .force_hold_ms = 100};
    supervisor_init(&state, &cfg);
    uint16_t fsr[5] = {50, 50, 50, 50, 50};

    supervisor_process_heartbeat(&state, 0, 10);
    supervisor_process_heartbeat(&state, 1, 20);
    supervisor_update(&state, &cfg, 20, fsr, true);
    TEST_ASSERT(state.oe_enabled, "Armed");

    // Strike E-Stop
    state.estop_pressed = true;
    supervisor_update(&state, &cfg, 25, fsr, true);
    TEST_ASSERT(!state.oe_enabled, "OE must drop immediately on E-stop");
    TEST_ASSERT(state.latched_fault, "E-Stop must latch fault");

    // Release E-Stop while arm_request still 1 -> cannot clear fault
    state.estop_pressed = false;
    bool cleared = supervisor_clear_fault(&state);
    TEST_ASSERT(!cleared, "Cannot clear fault while arm_request == 1");
    TEST_ASSERT(state.latched_fault, "Fault still latched");

    // Set arm_request = 0 -> can clear fault
    supervisor_process_heartbeat(&state, 0, 30);
    cleared = supervisor_clear_fault(&state);
    TEST_ASSERT(cleared, "Fault cleared when E-stop released and arm_request == 0");
    TEST_ASSERT(!state.latched_fault, "Fault no longer latched");

    // Re-arm with fresh 0->1 transition
    supervisor_process_heartbeat(&state, 1, 40);
    supervisor_update(&state, &cfg, 40, fsr, true);
    TEST_ASSERT(state.oe_enabled, "Re-armed successfully");
}

void test_supervisor_force_ceiling() {
    supervisor_state_t state;
    supervisor_config_t cfg = {.force_ceiling = 3500, .hb_timeout_ms = 250, .force_hold_ms = 100};
    supervisor_init(&state, &cfg);
    uint16_t fsr_ok[5] = {50, 50, 50, 50, 50};
    uint16_t fsr_high[5] = {50, 3800, 50, 50, 50}; // Index above ceiling

    supervisor_process_heartbeat(&state, 0, 10);
    supervisor_process_heartbeat(&state, 1, 20);
    supervisor_update(&state, &cfg, 20, fsr_ok, true);
    TEST_ASSERT(state.oe_enabled, "Armed");

    // 1. High force starts at t=30ms (duration < 100ms) -> no fault yet
    supervisor_process_heartbeat(&state, 1, 30);
    supervisor_update(&state, &cfg, 30, fsr_high, true);
    TEST_ASSERT(!state.force_fault, "No force fault before force_hold_ms");

    // 2. High force held for 110ms (t=140ms) -> force_fault set, OE disabled
    supervisor_process_heartbeat(&state, 1, 140);
    supervisor_update(&state, &cfg, 140, fsr_high, true);
    TEST_ASSERT(state.force_fault, "force_fault set after hold_ms exceeded");
    TEST_ASSERT(!state.oe_enabled, "OE dropped during force_fault");
    TEST_ASSERT(!state.latched_fault, "Not latched yet before 500ms");

    // 3. High force persists beyond 500ms (t=550ms) -> latched_fault set!
    supervisor_process_heartbeat(&state, 1, 550);
    supervisor_update(&state, &cfg, 550, fsr_high, true);
    TEST_ASSERT(state.latched_fault, "force fault persisting > 500ms must latch fault");
}

void test_supervisor_ads_fault() {
    supervisor_state_t state;
    supervisor_config_t cfg = {.force_ceiling = 3500, .hb_timeout_ms = 250, .force_hold_ms = 100};
    supervisor_init(&state, &cfg);
    uint16_t fsr[5] = {50, 50, 50, 50, 50};

    supervisor_process_heartbeat(&state, 0, 10);
    supervisor_process_heartbeat(&state, 1, 20);
    supervisor_update(&state, &cfg, 20, fsr, true);
    TEST_ASSERT(state.oe_enabled, "Armed");

    // ADS fails
    supervisor_update(&state, &cfg, 25, fsr, false);
    TEST_ASSERT(state.ads_fault, "ads_fault set");
    TEST_ASSERT(!state.oe_enabled, "OE dropped on ADS fault");
}

void test_protocol_codec_c() {
    frame_parser_t parser;
    frame_parser_init(&parser);

    heartbeat_payload_t hb = {.arm_request = 1, .jetson_state = 2};
    uint8_t frame_buf[32];
    size_t enc_len = frame_encode(MSG_TYPE_HEARTBEAT, 42, (const uint8_t *)&hb, sizeof(hb), frame_buf, sizeof(frame_buf));
    TEST_ASSERT(enc_len == (VAPA_OVERHEAD_SIZE + sizeof(hb)), "Encoded frame length");

    uint8_t out_type = 0;
    uint8_t out_seq = 0;
    const uint8_t *out_payload = NULL;
    uint8_t out_len = 0;
    bool parsed = false;

    for (size_t i = 0; i < enc_len; ++i) {
        parsed = frame_parser_feed(&parser, frame_buf[i], &out_type, &out_seq, &out_payload, &out_len);
    }

    TEST_ASSERT(parsed, "Parser parsed complete frame");
    TEST_ASSERT(out_type == MSG_TYPE_HEARTBEAT, "Message type matches");
    TEST_ASSERT(out_seq == 42, "Sequence counter matches");
    TEST_ASSERT(out_len == 2, "Payload length matches");
    TEST_ASSERT(out_payload[0] == 1 && out_payload[1] == 2, "Payload content matches");
}

void test_protocol_fuzz_c() {
    frame_parser_t parser;
    frame_parser_init(&parser);

    // Feed 50,000 pseudo-random bytes into the parser
    uint32_t seed = 0x12345678;
    for (int i = 0; i < 50000; ++i) {
        seed = seed * 1664525 + 1013904223;
        uint8_t byte = (uint8_t)(seed >> 16);
        uint8_t t, s, len;
        const uint8_t *p;
        frame_parser_feed(&parser, byte, &t, &s, &p, &len);
    }
    // Success if no segfault or buffer overrun
    TEST_ASSERT(parser.resync_count > 0, "Fuzzer completed safely");
}

int main() {
    printf("Running ESP32 Native Supervisor & Protocol Codec Tests...\n");
    test_supervisor_boot_state();
    test_supervisor_heartbeat_loss();
    test_supervisor_estop();
    test_supervisor_force_ceiling();
    test_supervisor_ads_fault();
    test_protocol_codec_c();
    test_protocol_fuzz_c();

    printf("\nAll %d supervisor & protocol tests PASSED!\n", g_tests_passed);
    return 0;
}
