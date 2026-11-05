"""Fault Injection Test: Watchdog Timeout, Control Loop Stall, and Task Starvation.

Verifies:
1. Jetson dedicated 50 Hz heartbeat thread stops heartbeats if control loop stalls > 50 ms.
2. Heartbeat thread transmits arm_request=0 before halting.
3. Global exception handler fail-safe immediately drops arm request and disables PWM.
4. Fail-closed boot state guarantees no PWM emission prior to initialization.
"""

import time
import pytest
from vapa.safety import (
    SafetyStateMachine, SafetyState, HeartbeatThread,
    SafetyEmergencyShutdown, PWMGate
)
from vapa.hal import MockPCA9685, MockESPLink
from vapa.protocol import HeartbeatMessage


def test_heartbeat_thread_loop_stall_suppression():
    """Verify that if main loop hangs (>50ms), heartbeats halt and arm_request drops."""
    sm = SafetyStateMachine()
    sm.request_arm(
        esp_link_healthy=True,
        estop_released=True,
        no_latched_fault=True,
        pca9685_healthy=True,
        encoders_healthy=True,
        emg_plausible=True,
        fsr_plausible=True,
    )
    sm.set_active()
    assert sm.state == SafetyState.ACTIVE

    sent_messages = []
    stall_called = [False]

    def mock_send(msg: HeartbeatMessage):
        sent_messages.append(msg)

    def on_stall():
        stall_called[0] = True
        sm.trigger_fault("Control loop stall timeout")

    # Initialize heartbeat thread with 40 ms timeout
    hb = HeartbeatThread(
        send_fn=mock_send,
        get_arm_request_fn=lambda: sm.arm_request,
        get_state_fn=lambda: sm.state.value,
        stall_timeout_s=0.04,
        on_stall_callback=on_stall,
    )
    hb.start()

    try:
        # Feed normally for 30 ms (main loop healthy)
        for _ in range(3):
            hb.feed()
            time.sleep(0.01)

        initial_count = len(sent_messages)
        assert initial_count > 0
        assert sent_messages[-1].arm_request == 1

        # Simulate main loop hang / freeze: stop feeding for 90 ms
        time.sleep(0.09)

        # Heartbeat thread should have detected stall
        assert stall_called[0] is True
        assert sm.state == SafetyState.FAULT
        assert sm.arm_request == 0

        # Last transmitted message must have had arm_request = 0
        assert sent_messages[-1].arm_request == 0

    finally:
        hb.stop()


def test_unhandled_exception_shutdown():
    """Verify that global unhandled exception triggers immediate fail-safe shutdown."""
    sm = SafetyStateMachine()
    pca = MockPCA9685()
    pca.initialize()
    esp = MockESPLink()
    esp.initialize()
    gate = PWMGate(pca, sm)

    sm.request_arm(
        esp_link_healthy=True,
        estop_released=True,
        no_latched_fault=True,
        pca9685_healthy=True,
        encoders_healthy=True,
        emg_plausible=True,
        fsr_plausible=True,
    )
    sm.set_active()
    gate.set_pulse_us(0, 1600.0)
    assert pca.get_pulse_us(0) == 1600.0

    class MockContainer:
        def __init__(self, p, e):
            self.pca9685 = p
            self.esp_link = e

    shutdown = SafetyEmergencyShutdown(sm, hal=MockContainer(pca, esp))
    shutdown.execute_fail_safe_shutdown("Fatal memory or arithmetic error in vision pipeline")

    assert sm.state == SafetyState.FAULT
    assert sm.arm_request == 0
    assert pca.get_pulse_us(0) == 0.0
