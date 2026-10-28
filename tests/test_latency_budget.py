"""Latency Budget Verification Suite.

Validates that end-to-end processing latency from raw sensor arrival through
EMG envelope extraction, intent decoding, shared-control arbitration,
slew rate limiting, force control, and PWM dispatch strictly meets the
latency budget (< 100 ms, target < 10 ms per 100 Hz cycle).
"""

import time
import pytest
import numpy as np
from pathlib import Path
import yaml

from vapa.protocol import SensorMessage, FLAG_HEARTBEAT_OK
from vapa.emg.envelope import EnvelopeNormalizer, EMGCalibration, counts_to_mv
from vapa.emg.decoder import ThresholdEMGDecoder, EMGIntent
from vapa.fusion.arbitrator import SharedControlArbitrator, ArbitrationOutput
from vapa.vision.distance_matrix import DistanceMatrixResult
from vapa.vision.detector import GripSelectionResult
from vapa.control.grip_executor import GripExecutor
from vapa.control.encoder_monitor import EncoderMonitor
from vapa.control.servo_mapper import ServoMapper
from vapa.control.slew_limiter import SlewRateLimiter
from vapa.control.force_controller import FingerForceController
from vapa.safety.state_machine import SafetyStateMachine, SafetyState
from vapa.safety.pwm_gate import PWMGate
from vapa.hal.pca9685 import MockPCA9685


@pytest.fixture
def configs():
    config_dir = Path("config")
    with open(config_dir / "servos.yaml", "r") as f:
        servo_cfg = yaml.safe_load(f)
    with open(config_dir / "emg.yaml", "r") as f:
        emg_cfg = yaml.safe_load(f)
    with open(config_dir / "grip_profiles.yaml", "r") as f:
        grip_cfg = yaml.safe_load(f)
    return {
        "servos": servo_cfg,
        "emg": emg_cfg,
        "grip_profiles": grip_cfg,
    }


@pytest.fixture
def vapa_pipeline(configs):
    # Setup full software pipeline components
    f_thresh = configs["emg"].get("thresholds", {}).get("flexor", {})
    e_thresh = configs["emg"].get("thresholds", {}).get("extensor", {})
    normalizer = EnvelopeNormalizer(
        flexor_cal=EMGCalibration(
            baseline_mv=float(f_thresh.get("baseline_mv", 250.0)),
            mvc_mv=float(f_thresh.get("mvc_mv", 2200.0)),
            saturation_mv=float(f_thresh.get("saturation_mv", 3200.0)),
        ),
        extensor_cal=EMGCalibration(
            baseline_mv=float(e_thresh.get("baseline_mv", 250.0)),
            mvc_mv=float(e_thresh.get("mvc_mv", 2000.0)),
            saturation_mv=float(e_thresh.get("saturation_mv", 3200.0)),
        ),
    )
    decoder = ThresholdEMGDecoder()
    arbitrator = SharedControlArbitrator(configs["grip_profiles"])

    pca = MockPCA9685(address=0x40)
    pca.initialize()
    safety = SafetyStateMachine()
    gate = PWMGate(pca, safety)

    # Transition to ARMED_IDLE
    safety.request_arm(
        esp_link_healthy=True,
        estop_released=True,
        no_latched_fault=True,
        pca9685_healthy=True,
        encoders_healthy=True,
        emg_plausible=True,
        fsr_plausible=True,
    )
    assert safety.state == SafetyState.ARMED_IDLE

    # Servo and Grip execution
    mapper = ServoMapper(configs["servos"])
    slew_rates = {k: float(v.get("max_slew_rate_deg_s", 180.0)) for k, v in configs["servos"].get("servos", {}).items()}
    slew = SlewRateLimiter(slew_rates)
    force = FingerForceController()
    encoder_mon = EncoderMonitor()
    executor = GripExecutor(mapper, slew, force, gate)

    return {
        "normalizer": normalizer,
        "decoder": decoder,
        "arbitrator": arbitrator,
        "executor": executor,
        "encoder_mon": encoder_mon,
        "safety": safety,
        "gate": gate,
        "pca": pca,
        "profiles": configs["grip_profiles"]["profiles"],
    }


def test_end_to_end_latency_budget(vapa_pipeline):
    """Verify that full pipeline cycle latency is strictly < 100 ms (and < 15 ms p99)."""
    p = vapa_pipeline
    normalizer: EnvelopeNormalizer = p["normalizer"]
    decoder: ThresholdEMGDecoder = p["decoder"]
    arbitrator: SharedControlArbitrator = p["arbitrator"]
    executor: GripExecutor = p["executor"]
    encoder_mon: EncoderMonitor = p["encoder_mon"]
    profiles = p["profiles"]

    dist_res = DistanceMatrixResult(
        grid_depth_m=np.full((12, 16), 0.35, dtype=np.float32),
        grid_valid=np.ones((12, 16), dtype=bool),
        nearest_distance_m=0.35,
        centroid_3d_m=(0.5, 0.5, 0.35),
        approach_velocity_mps=-0.1,
        reach_confidence=0.85,
    )

    measured_forces = {
        "thumb": 50.0,
        "index": 45.0,
        "middle": 40.0,
        "ring": 35.0,
        "little": 30.0,
    }

    iterations = 1000
    latencies_us = []

    # Run warm-up
    for _ in range(50):
        decoder.decode(0.3, 0.05, 0.01)

    # Benchmark loop
    for i in range(iterations):
        # Simulated raw ADC values
        raw_flex_counts = 1800 + (i % 200)
        raw_ext_counts = 400 + (i % 50)

        t_start = time.perf_counter_ns()

        # 1. Normalization
        raw_flex_mv = counts_to_mv(raw_flex_counts)
        raw_ext_mv = counts_to_mv(raw_ext_counts)
        a_flex, a_ext, emg_ok = normalizer.normalize(raw_flex_mv, raw_ext_mv)

        # 2. Intent Decoding
        intent, velocity = decoder.decode(a_flex, a_ext, dt_s=0.01)

        # 3. Shared-Control Arbitration
        arb = arbitrator.arbitrate(
            emg_intent=intent,
            emg_velocity=velocity,
            vision_profile="cylindrical",
            distance_result=dist_res,
            current_aperture=0.5,
        )

        # 4. Motion & Grip Execution (Limits Clamp -> Slew -> PWM Gate)
        pulses = executor.step(
            motion_command=arb.motion_command,
            emg_velocity=arb.command_velocity,
            profile_data=profiles["cylindrical"],
            preshape_aperture=arb.preshape_aperture,
            measured_forces=measured_forces,
            dt_s=0.01,
        )

        # 5. Closed-Loop Encoder Monitoring
        enc_fault, _ = encoder_mon.update(
            commanded_angles=executor.current_joint_angles,
            measured_angles=executor.current_joint_angles,
            dt_s=0.01,
        )

        t_end = time.perf_counter_ns()
        latency_us = (t_end - t_start) / 1000.0
        latencies_us.append(latency_us)

    latencies_ms = np.array(latencies_us) / 1000.0
    p50_ms = np.percentile(latencies_ms, 50)
    p95_ms = np.percentile(latencies_ms, 95)
    p99_ms = np.percentile(latencies_ms, 99)
    max_ms = np.max(latencies_ms)

    print(f"\n--- Latency Benchmark Results ({iterations} cycles) ---")
    print(f"Median (p50): {p50_ms:.3f} ms")
    print(f"p95:          {p95_ms:.3f} ms")
    print(f"p99:          {p99_ms:.3f} ms")
    print(f"Max:          {max_ms:.3f} ms")

    # Hard Non-Negotiable Assertions:
    # 1. Worst-case latency must be strictly < 100 ms
    assert max_ms < 100.0, f"Worst-case latency exceeded 100 ms: {max_ms:.3f} ms"
    # 2. p99 must fit comfortably in the 100 Hz frame budget (< 10 ms target, < 15 ms max tolerance)
    assert p99_ms < 15.0, f"p99 latency too high for 100 Hz control loop: {p99_ms:.3f} ms"
    # 3. Median execution time must be under 3 ms on host
    assert p50_ms < 3.0, f"Median execution time exceeded 3 ms: {p50_ms:.3f} ms"


def test_stage_latency_breakdown(vapa_pipeline):
    """Measure isolated latency of each processing stage."""
    p = vapa_pipeline
    normalizer: EnvelopeNormalizer = p["normalizer"]
    decoder: ThresholdEMGDecoder = p["decoder"]
    arbitrator: SharedControlArbitrator = p["arbitrator"]
    executor: GripExecutor = p["executor"]
    encoder_mon: EncoderMonitor = p["encoder_mon"]
    profiles = p["profiles"]

    dist_res = DistanceMatrixResult(
        grid_depth_m=np.full((12, 16), 0.35, dtype=np.float32),
        grid_valid=np.ones((12, 16), dtype=bool),
        nearest_distance_m=0.35,
        centroid_3d_m=(0.5, 0.5, 0.35),
        approach_velocity_mps=-0.1,
        reach_confidence=0.85,
    )
    forces = {"thumb": 50.0, "index": 45.0, "middle": 40.0, "ring": 35.0, "little": 30.0}

    iterations = 500
    times = {
        "norm": [],
        "decode": [],
        "arbitrate": [],
        "execute": [],
        "encoder": [],
    }

    for _ in range(iterations):
        # 1. Normalization
        t0 = time.perf_counter_ns()
        mv_f = counts_to_mv(2000)
        mv_e = counts_to_mv(400)
        af, ae, _ = normalizer.normalize(mv_f, mv_e)
        t1 = time.perf_counter_ns()
        times["norm"].append((t1 - t0) / 1000.0)

        # 2. Decoding
        t0 = time.perf_counter_ns()
        intent, vel = decoder.decode(af, ae, 0.01)
        t1 = time.perf_counter_ns()
        times["decode"].append((t1 - t0) / 1000.0)

        # 3. Arbitration
        t0 = time.perf_counter_ns()
        arb = arbitrator.arbitrate(intent, vel, "cylindrical", dist_res, 0.5)
        t1 = time.perf_counter_ns()
        times["arbitrate"].append((t1 - t0) / 1000.0)

        # 4. Execution
        t0 = time.perf_counter_ns()
        executor.step(
            arb.motion_command,
            arb.command_velocity,
            profiles["cylindrical"],
            arb.preshape_aperture,
            forces,
            0.01,
        )
        t1 = time.perf_counter_ns()
        times["execute"].append((t1 - t0) / 1000.0)

        # 5. Encoder Monitor
        t0 = time.perf_counter_ns()
        encoder_mon.update(executor.current_joint_angles, executor.current_joint_angles, 0.01)
        t1 = time.perf_counter_ns()
        times["encoder"].append((t1 - t0) / 1000.0)

    print("\n--- Subsystem Latency Breakdown (Mean ± Std in µs) ---")
    for stage, t_list in times.items():
        arr = np.array(t_list)
        print(f"  {stage:<12}: {np.mean(arr):6.2f} µs ± {np.std(arr):6.2f} µs (max: {np.max(arr):6.2f} µs)")
        # Each stage should typically take under 5000 µs (5 ms)
        assert np.max(arr) < 50000.0, f"Stage {stage} had excessive max latency: {np.max(arr)} µs"


def test_extensor_open_override_immediate_latency(vapa_pipeline):
    """Verify that extensor OPEN immediately overrides CLOSE within the current cycle."""
    p = vapa_pipeline
    normalizer: EnvelopeNormalizer = p["normalizer"]
    decoder: ThresholdEMGDecoder = p["decoder"]
    arbitrator: SharedControlArbitrator = p["arbitrator"]
    executor: GripExecutor = p["executor"]
    profiles = p["profiles"]

    # 1. Establish steady flexor closing state (satisfy dwell > 100 ms)
    # Flexor at 1800 mV (activation ~ 0.88), extensor at 300 mV (relaxed)
    for _ in range(15):
        af, ae, healthy = normalizer.normalize(1800.0, 300.0)
        assert healthy
        intent, vel = decoder.decode(af, ae, dt_s=0.01)
        arb = arbitrator.arbitrate(intent, vel, "pinch", None, 0.5)
        executor.step(arb.motion_command, arb.command_velocity, profiles["pinch"], None, {}, 0.01)

    assert intent == EMGIntent.CLOSE
    assert arb.motion_command == "CLOSE"

    # 2. Fire Extensor pulse (extensor 1800 mV, flexor relaxes to 400 mV: deltas < 2000 mV)
    # First cycle: Closing must be IMMEDIATELY aborted (motion_command != CLOSE)
    t0 = time.perf_counter_ns()
    af, ae, healthy = normalizer.normalize(400.0, 1800.0)
    assert healthy, f"Normalizer faulted: {normalizer.last_fault_reason}"
    intent_step1, vel_step1 = decoder.decode(af, ae, dt_s=0.01)
    arb_step1 = arbitrator.arbitrate(intent_step1, vel_step1, "pinch", None, 0.5)
    t_first_step_ns = time.perf_counter_ns() - t0

    assert arb_step1.motion_command != "CLOSE", "Closing must be immediately aborted upon extensor activation"
    assert (t_first_step_ns / 1e6) < 10.0, "First step latency exceeded 10 ms"

    # Sustained extensor across 100 ms dwell window (10 steps @ 100 Hz)
    step_latencies_ms = []
    for _ in range(10):
        t0 = time.perf_counter_ns()
        af, ae, _ = normalizer.normalize(400.0, 1800.0)
        override_intent, override_vel = decoder.decode(af, ae, dt_s=0.01)
        override_arb = arbitrator.arbitrate(override_intent, override_vel, "pinch", None, 0.5)
        override_pulses = executor.step(
            override_arb.motion_command,
            override_arb.command_velocity,
            profiles["pinch"],
            None,
            {},
            0.01,
        )
        step_latencies_ms.append((time.perf_counter_ns() - t0) / 1e6)

    # Invariant: Once dwell is satisfied, Extensor is OPEN
    assert override_intent == EMGIntent.OPEN
    assert override_arb.motion_command == "OPEN"
    assert max(step_latencies_ms) < 10.0, f"Max step latency during override exceeded 10 ms: {max(step_latencies_ms):.3f} ms"
    print(f"\nExtensor Override Latency: first cycle = {t_first_step_ns/1e6:.3f} ms, max during dwell = {max(step_latencies_ms):.3f} ms")
