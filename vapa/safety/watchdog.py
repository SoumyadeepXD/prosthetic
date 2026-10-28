"""Dedicated 50 Hz heartbeat thread and watchdog supervisor."""

import time
import threading
import logging
from typing import Callable, Optional
from ..protocol import HeartbeatMessage

logger = logging.getLogger(__name__)

class HeartbeatThread:
    """Sends 50 Hz heartbeats to ESP32 only if control loop continues feeding the watchdog."""

    def __init__(
        self,
        send_fn: Callable[[HeartbeatMessage], None],
        get_arm_request_fn: Callable[[], int],
        get_state_fn: Callable[[], int],
        stall_timeout_s: float = 0.05,  # 50 ms stall threshold
        on_stall_callback: Optional[Callable[[], None]] = None,
    ):
        self.send_fn = send_fn
        self.get_arm_request_fn = get_arm_request_fn
        self.get_state_fn = get_state_fn
        self.stall_timeout_s = stall_timeout_s
        self.on_stall_callback = on_stall_callback

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_feed_time = time.time()
        self._lock = threading.Lock()

    def start(self) -> None:
        self._running = True
        self._last_feed_time = time.time()
        self._thread = threading.Thread(target=self._run, daemon=True, name="vapa-heartbeat")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.2)
            self._thread = None

    def feed(self) -> None:
        """Called by the 100 Hz main control loop on every iteration."""
        with self._lock:
            self._last_feed_time = time.time()

    def _run(self) -> None:
        period = 0.02  # 50 Hz
        while self._running:
            start_time = time.time()

            # Check if main control loop has stalled
            with self._lock:
                stall_age = start_time - self._last_feed_time

            if stall_age > self.stall_timeout_s:
                # Loop has stalled: stop transmitting heartbeats, causing ESP32 supervisor to drop OE
                logger.warning(f"Control loop stalled ({stall_age * 1000:.1f} ms > {self.stall_timeout_s * 1000:.1f} ms)! Suppressing heartbeats.")
                # Send 0 arm_request immediately before pausing
                try:
                    self.send_fn(HeartbeatMessage(arm_request=0, jetson_state=0))
                except Exception:
                    pass
                if self.on_stall_callback:
                    try:
                        self.on_stall_callback()
                    except Exception:
                        pass
            else:
                try:
                    arm_req = self.get_arm_request_fn()
                    state_id = self.get_state_fn()
                    self.send_fn(HeartbeatMessage(arm_request=arm_req, jetson_state=state_id))
                except Exception as e:
                    logger.error(f"Error sending heartbeat: {e}")

            elapsed = time.time() - start_time
            sleep_time = max(0.001, period - elapsed)
            time.sleep(sleep_time)
