"""Global exception, signal, and termination handlers ensuring fail-closed safety."""

import sys
import atexit
import signal
import threading
import logging
from typing import Optional, Callable
from .state_machine import SafetyStateMachine
from .watchdog import HeartbeatThread
from ..hal import HALContainer
from ..protocol import HeartbeatMessage

logger = logging.getLogger(__name__)

class SafetyEmergencyShutdown:
    """Installs global fail-safe hooks for exceptions, signals, and process exits."""

    def __init__(
        self,
        safety_machine: SafetyStateMachine,
        heartbeat_thread: Optional[HeartbeatThread] = None,
        hal: Optional[HALContainer] = None,
    ):
        self.safety = safety_machine
        self.heartbeat = heartbeat_thread
        self.hal = hal
        self._shutdown_executed = False
        self._lock = threading.Lock()

    def execute_fail_safe_shutdown(self, reason: str) -> None:
        """Immediately drop arm request, halt heartbeats, and disable PWM."""
        with self._lock:
            if self._shutdown_executed:
                return
            self._shutdown_executed = True

            logger.critical(f"EMERGENCY FAIL-SAFE SHUTDOWN TRIGGERED: {reason}")

            # 1. Transition state machine to FAULT and drop arm_request to 0
            self.safety.trigger_fault(f"Fail-safe shutdown: {reason}")

            # 2. Transmit immediate disarm heartbeat to ESP32 before stopping thread
            if self.hal and hasattr(self.hal.esp_link, "send_message"):
                try:
                    self.hal.esp_link.send_message(HeartbeatMessage(arm_request=0, jetson_state=0))
                except Exception as e:
                    logger.error(f"Failed to transmit disarm heartbeat: {e}")

            # 3. Halt heartbeat thread to trigger ESP32 hardware watchdog disarm
            if self.heartbeat:
                try:
                    self.heartbeat.stop()
                except Exception as e:
                    logger.error(f"Error stopping heartbeat thread: {e}")

            # 4. Disable all PWM outputs immediately
            if self.hal and hasattr(self.hal.pca9685, "disable_all"):
                try:
                    self.hal.pca9685.disable_all()
                except Exception as e:
                    logger.error(f"Error disabling PCA9685 outputs: {e}")

    def install(self) -> None:
        """Register sys.excepthook, threading.excepthook, signals, and atexit."""
        def handle_sys_exception(exc_type, exc_value, exc_traceback):
            self.execute_fail_safe_shutdown(f"Unhandled exception: {exc_type.__name__}: {exc_value}")
            sys.__excepthook__(exc_type, exc_value, exc_traceback)

        def handle_thread_exception(args):
            self.execute_fail_safe_shutdown(
                f"Unhandled thread exception in {args.thread.name}: {args.exc_type.__name__}: {args.exc_value}"
            )

        def handle_signal(signum, frame):
            sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
            self.execute_fail_safe_shutdown(f"Signal received: {sig_name}")
            sys.exit(128 + signum)

        sys.excepthook = handle_sys_exception
        if hasattr(threading, "excepthook"):
            threading.excepthook = handle_thread_exception

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, handle_signal)
            except (ValueError, OSError):
                pass

        atexit.register(self.execute_fail_safe_shutdown, "Process atexit")
