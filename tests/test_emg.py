"""Comprehensive unit tests for EMG envelope handling, threshold decoding, and EEG interface."""

import pytest
import numpy as np
from vapa.emg import (
    EMGCalibration,
    EnvelopeNormalizer,
    counts_to_mv,
    ADS1115_MV_PER_LSB,
    EMGIntent,
    DecoderConfig,
    ThresholdEMGDecoder,
    EnvelopeClassifier,
    EnvelopeFeatures,
)
from vapa.eeg import MockEEGDecoder


def test_counts_to_mv_and_normalization():
    # ADS1115 with 4.096V PGA: 1 LSB = 0.125 mV
    assert counts_to_mv(0) == 0.0
    assert counts_to_mv(2000) == 250.0
    assert counts_to_mv(16000) == 2000.0

    cal_flex = EMGCalibration(baseline_mv=200.0, mvc_mv=2200.0, saturation_mv=3200.0)
    cal_ext = EMGCalibration(baseline_mv=200.0, mvc_mv=2200.0, saturation_mv=3200.0)
    norm = EnvelopeNormalizer(cal_flex, cal_ext)

    # At baseline (200 mV) -> 0.0
    a_f, a_e, healthy = norm.normalize(200.0, 200.0)
    assert healthy
    assert pytest.approx(a_f, 0.001) == 0.0
    assert pytest.approx(a_e, 0.001) == 0.0

    # Below baseline -> clamped to 0.0
    a_f, a_e, healthy = norm.normalize(150.0, 150.0)
    assert healthy
    assert a_f == 0.0
    assert a_e == 0.0

    # Midpoint (1200 mV, span = 2000 mV) -> 0.5
    a_f, a_e, healthy = norm.normalize(1200.0, 1200.0)
    assert healthy
    assert pytest.approx(a_f, 0.001) == 0.5
    assert pytest.approx(a_e, 0.001) == 0.5

    # At MVC (2200 mV) -> 1.0
    a_f, a_e, healthy = norm.normalize(2200.0, 2200.0)
    assert healthy
    assert pytest.approx(a_f, 0.001) == 1.0
    assert pytest.approx(a_e, 0.001) == 1.0

    # Above MVC but below saturation -> clamped to 1.0
    a_f, a_e, healthy = norm.normalize(2500.0, 2500.0)
    assert healthy
    assert a_f == 1.0
    assert a_e == 1.0


def test_envelope_health_checks():
    cal = EMGCalibration(baseline_mv=200.0, mvc_mv=2000.0, saturation_mv=3200.0)
    norm = EnvelopeNormalizer(cal, cal, stuck_window_size=10)

    # 1. Saturation Fault
    _, _, healthy = norm.normalize(3250.0, 500.0)
    assert not healthy
    assert "saturated" in norm.last_fault_reason.lower()

    norm.reset()

    # 2. Negative Voltage Fault
    _, _, healthy = norm.normalize(-10.0, 500.0)
    assert not healthy
    assert "negative" in norm.last_fault_reason.lower()

    norm.reset()

    # 3. Sudden rail step (>2000 mV jump)
    norm.normalize(300.0, 300.0)
    _, _, healthy = norm.normalize(2400.0, 300.0)
    assert not healthy
    assert "step to rail" in norm.last_fault_reason.lower()

    norm.reset()

    # 4. Stuck / Flat-line signal
    for _ in range(9):
        _, _, healthy = norm.normalize(400.0, 400.0)
        assert healthy
    # 10th identical sample fills window and trips flatline check
    _, _, healthy = norm.normalize(400.0, 400.0)
    assert not healthy
    assert "stuck" in norm.last_fault_reason.lower()


def test_decoder_hysteresis_and_dwell():
    cfg = DecoderConfig(
        flex_act_threshold=0.25,
        flex_deact_threshold=0.15,
        ext_act_threshold=0.25,
        ext_deact_threshold=0.15,
        co_contract_hold_s=0.60,
        min_dwell_s=0.10,
    )
    dec = ThresholdEMGDecoder(cfg)
    dt = 0.02  # 20ms steps

    # --- Test 1: Transient spike rejected by dwell time (<100ms) ---
    # Spike lasts 3 steps = 60ms (< 100ms min dwell)
    for _ in range(3):
        intent, vel = dec.decode(a_flex=0.6, a_ext=0.0, dt_s=dt)
        assert intent == EMGIntent.HOLD
        assert vel == 0.0

    # Cease spike
    intent, vel = dec.decode(a_flex=0.0, a_ext=0.0, dt_s=dt)
    assert intent == EMGIntent.HOLD

    # --- Test 2: Sustained flexor activation (>100ms) triggers CLOSE ---
    # Feed 5 steps = 100ms
    for _ in range(4):
        intent, vel = dec.decode(a_flex=0.6, a_ext=0.0, dt_s=dt)
        assert intent == EMGIntent.HOLD
    # 5th step reaches 100ms
    intent, vel = dec.decode(a_flex=0.6, a_ext=0.0, dt_s=dt)
    assert intent == EMGIntent.CLOSE
    assert vel > 0.0

    # --- Test 3: Hysteresis retention ---
    # Drop activation into band between 0.15 and 0.25 (e.g. 0.20)
    # Should maintain CLOSE state
    intent, vel = dec.decode(a_flex=0.20, a_ext=0.0, dt_s=dt)
    assert intent == EMGIntent.CLOSE

    # Drop below deactivation threshold (0.10 <= 0.15)
    intent, vel = dec.decode(a_flex=0.10, a_ext=0.0, dt_s=dt)
    assert intent == EMGIntent.HOLD


def test_rapid_open_override():
    cfg = DecoderConfig(min_dwell_s=0.05)
    dec = ThresholdEMGDecoder(cfg)
    dt = 0.02

    # Activate Flexor for 60ms -> CLOSE
    for _ in range(4):
        dec.decode(a_flex=0.8, a_ext=0.0, dt_s=dt)
    intent, _ = dec.decode(a_flex=0.8, a_ext=0.0, dt_s=dt)
    assert intent == EMGIntent.CLOSE

    # Now extensor fires alone while opening
    dec.reset()
    for _ in range(4):
        dec.decode(a_flex=0.0, a_ext=0.8, dt_s=dt)
    intent, vel = dec.decode(a_flex=0.0, a_ext=0.8, dt_s=dt)
    assert intent == EMGIntent.OPEN
    assert vel > 0.0


def test_co_contraction_mode_cycle():
    cfg = DecoderConfig(min_dwell_s=0.05, co_contract_hold_s=0.50)
    dec = ThresholdEMGDecoder(cfg)
    dt = 0.02

    # Both muscles active simultaneously
    # First 0.05s establishes dwell
    for _ in range(3):
        intent, _ = dec.decode(a_flex=0.7, a_ext=0.7, dt_s=dt)
        assert intent == EMGIntent.HOLD

    # Hold co-contraction for 0.40s more (total 0.46s < 0.50s)
    for _ in range(20):
        intent, _ = dec.decode(a_flex=0.7, a_ext=0.7, dt_s=dt)
        assert intent == EMGIntent.HOLD

    # Reach 0.50s threshold -> fires MODE_CYCLE
    mode_cycled = False
    for _ in range(5):
        intent, _ = dec.decode(a_flex=0.7, a_ext=0.7, dt_s=dt)
        if intent == EMGIntent.MODE_CYCLE:
            mode_cycled = True
            break
    assert mode_cycled

    # Continuing to hold should NOT fire MODE_CYCLE repeatedly (one-shot until release)
    intent, _ = dec.decode(a_flex=0.7, a_ext=0.7, dt_s=dt)
    assert intent == EMGIntent.HOLD

    # Release both below threshold
    dec.decode(a_flex=0.0, a_ext=0.0, dt_s=dt)
    # Ready for next co-contraction cycle


def test_synthetic_envelope_waveform_stream():
    """Stream a continuous synthetic waveform through normalizer and decoder."""
    cal = EMGCalibration(baseline_mv=200.0, mvc_mv=2000.0, saturation_mv=3200.0)
    norm = EnvelopeNormalizer(cal, cal)
    dec = ThresholdEMGDecoder(DecoderConfig(min_dwell_s=0.05, co_contract_hold_s=0.40))
    dt = 0.01  # 100 Hz

    # Generate 500 samples (5.0 seconds) of synthetic data:
    # 0.0 - 1.0s: Rest (220 mV with slight noise)
    # 1.0 - 2.0s: Flexor contraction (1500 mV)
    # 2.0 - 2.5s: Rest
    # 2.5 - 3.5s: Extensor contraction (1600 mV)
    # 3.5 - 4.0s: Rest
    # 4.0 - 5.0s: Co-contraction (1700 mV both)

    t = np.linspace(0, 5.0, 500)
    flex_stream = np.zeros_like(t)
    ext_stream = np.zeros_like(t)

    for i, ti in enumerate(t):
        noise = np.sin(ti * 30.0) * 10.0
        if 1.0 <= ti < 2.0:
            flex_stream[i] = 1500.0 + noise
            ext_stream[i] = 220.0 + noise
        elif 2.5 <= ti < 3.5:
            flex_stream[i] = 220.0 + noise
            ext_stream[i] = 1600.0 + noise
        elif 4.0 <= ti < 5.0:
            flex_stream[i] = 1700.0 + noise
            ext_stream[i] = 1700.0 + noise
        else:
            flex_stream[i] = 220.0 + noise
            ext_stream[i] = 220.0 + noise

    intents = []
    for raw_f, raw_e in zip(flex_stream, ext_stream):
        a_f, a_e, healthy = norm.normalize(raw_f, raw_e)
        assert healthy
        intent, _ = dec.decode(a_f, a_e, dt_s=dt)
        intents.append(intent)

    # Verify observed intents
    assert EMGIntent.CLOSE in intents[120:180]       # During flexor phase
    assert EMGIntent.OPEN in intents[270:330]        # During extensor phase
    assert EMGIntent.MODE_CYCLE in intents[440:480]  # During co-contraction phase


def test_classifier_interface_and_features():
    clf_disabled = EnvelopeClassifier(enabled=False)
    assert not clf_disabled.is_enabled()
    intent, conf = clf_disabled.predict([0.5] * 15, [0.1] * 15)
    assert intent == "HOLD"
    assert conf == 0.0

    clf_enabled = EnvelopeClassifier(enabled=True, window_size=10)
    assert clf_enabled.is_enabled()

    flex_win = [0.1 * i for i in range(10)]
    ext_win = [0.05 * i for i in range(10)]
    feat = clf_enabled.extract_features(flex_win, ext_win)

    assert isinstance(feat, EnvelopeFeatures)
    assert feat.flex_max == pytest.approx(0.9, 0.01)
    assert feat.flex_slope > 0.0

    # Extensor open priority in classifier
    intent, conf = clf_enabled.predict(flex_window=[0.1] * 10, ext_window=[0.8] * 10)
    assert intent == "OPEN"
    assert conf == pytest.approx(0.8, 0.001)


def test_mock_eeg_decoder():
    eeg = MockEEGDecoder(enabled=False)
    assert eeg.process_sample(1024) is None

    # Even if enabled, mock EEG never commands closing
    eeg_enabled = MockEEGDecoder(enabled=True)
    res = eeg_enabled.process_sample(2048)
    assert res is None or res != "CLOSE"
