import time
import math
from enum import Enum
from dataclasses import dataclass


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class RequestToken:
    generation: int
    is_probe: bool


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
    ):
        if (
            not isinstance(failure_threshold, int)
            or isinstance(failure_threshold, bool)
            or failure_threshold <= 0
        ):
            raise ValueError(
                "failure_threshold must be a positive integer"
            )

        if (
            isinstance(recovery_timeout, bool)
            or not isinstance(recovery_timeout, (int, float))
            or not math.isfinite(recovery_timeout)
            or recovery_timeout <= 0
        ):
            raise ValueError(
                "recovery_timeout must be a finite positive number"
            )

        self.failure_threshold = failure_threshold
        self.recovery_timeout = float(recovery_timeout)

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.opened_at: float | None = None
        self.probe_in_progress = False
        self.generation = 0

    def allow_request(self) -> RequestToken | None:
        if self.state == CircuitState.CLOSED:
            return RequestToken(
                generation=self.generation,
                is_probe=False,
            )

        if self.state == CircuitState.OPEN:
            elapsed = time.monotonic() - self.opened_at

            if elapsed < self.recovery_timeout:
                return None

            self.state = CircuitState.HALF_OPEN
            self.probe_in_progress = True

            return RequestToken(
                generation=self.generation,
                is_probe=True,
            )

        # HALF_OPEN: allow only one recovery probe.
        if self.probe_in_progress:
            return None

        self.probe_in_progress = True

        return RequestToken(
            generation=self.generation,
            is_probe=True,
        )

    def record_success(self, token: RequestToken) -> None:
        if token.generation != self.generation:
            return

        if self.state == CircuitState.OPEN:
            return

        if self.state == CircuitState.HALF_OPEN:
            if not token.is_probe:
                return

            self.failure_count = 0
            self.opened_at = None
            self.probe_in_progress = False
            self.state = CircuitState.CLOSED

            # Start a new circuit generation after recovery.
            self.generation += 1
            return

        if token.is_probe:
            return

        self.failure_count = 0

    def record_failure(self, token: RequestToken) -> None:
        if token.generation != self.generation:
            return

        if self.state == CircuitState.OPEN:
            return

        if self.state == CircuitState.HALF_OPEN:
            if not token.is_probe:
                return

            self._open_circuit()
            return

        if token.is_probe:
            return

        self.failure_count += 1

        if self.failure_count >= self.failure_threshold:
            self._open_circuit()

    def record_probe_cancelled(self, token: RequestToken) -> None:
        if (
            token.generation == self.generation
            and token.is_probe
            and self.state == CircuitState.HALF_OPEN
            and self.probe_in_progress
        ):
            self._open_circuit()

    def _open_circuit(self) -> None:
        self.state = CircuitState.OPEN
        self.opened_at = time.monotonic()
        self.probe_in_progress = False

        # Invalidate requests admitted during the previous generation.
        self.generation += 1

    def is_request_current(self, token: RequestToken) -> bool:
        return (
            token.generation == self.generation
            and self.state != CircuitState.OPEN
        )


gemini_breaker = CircuitBreaker(
    failure_threshold=3,
    recovery_timeout=30.0,
)