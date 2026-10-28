"""Test safety state machine invariants, gating, and transitions."""

from vapa.safety import SafetyStateMachine, SafetyState

def test_boots_disarmed():
    sm = SafetyStateMachine()
    assert sm.state == SafetyState.DISARMED
    assert sm.arm_request == 0
    assert sm.is_pwm_allowed is False

def test_arming_preconditions_all_required():
    sm = SafetyStateMachine()

    # Precondition failure: E-stop is active
    ok = sm.request_arm(
        esp_link_healthy=True,
        estop_released=False,  # Active E-stop
        no_latched_fault=True,
        pca9685_healthy=True,
        encoders_healthy=True,
        emg_plausible=True,
        fsr_plausible=True,
    )
    assert ok is False
    assert sm.state == SafetyState.DISARMED
    assert sm.is_pwm_allowed is False

    # Precondition failure: Encoders missing magnet
    ok2 = sm.request_arm(
        esp_link_healthy=True,
        estop_released=True,
        no_latched_fault=True,
        pca9685_healthy=True,
        encoders_healthy=False,  # Bad encoder
        emg_plausible=True,
        fsr_plausible=True,
    )
    assert ok2 is False
    assert sm.state == SafetyState.DISARMED

    # All pass -> ARMED_IDLE
    ok3 = sm.request_arm(
        esp_link_healthy=True,
        estop_released=True,
        no_latched_fault=True,
        pca9685_healthy=True,
        encoders_healthy=True,
        emg_plausible=True,
        fsr_plausible=True,
    )
    assert ok3 is True
    assert sm.state == SafetyState.ARMED_IDLE
    assert sm.arm_request == 1
    assert sm.is_pwm_allowed is True

def test_fault_suppresses_pwm_and_drops_arm_request():
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
    assert sm.is_pwm_allowed is True

    # Fault occurs
    sm.trigger_fault("Hardware force ceiling exceeded")
    assert sm.state == SafetyState.FAULT
    assert sm.arm_request == 0
    assert sm.is_pwm_allowed is False

    # Cannot arm directly from FAULT
    assert sm.request_arm(
        esp_link_healthy=True,
        estop_released=True,
        no_latched_fault=True,
        pca9685_healthy=True,
        encoders_healthy=True,
        emg_plausible=True,
        fsr_plausible=True,
    ) is False
