import asyncio
import time
from unittest.mock import patch

from app.circuit_breaker import CircuitState, gemini_breaker
from app.config import settings
from app.providers import call_gemini


async def test_cancelled_recovery_probe():
    started = asyncio.Event()

    async def slow_gemini(**kwargs):
        started.set()
        await asyncio.Event().wait()

    # Put the breaker into OPEN, with its recovery timeout elapsed.
    gemini_breaker.state = CircuitState.OPEN
    gemini_breaker.failure_count = 3
    gemini_breaker.opened_at = (
        time.monotonic() - gemini_breaker.recovery_timeout - 1
    )
    gemini_breaker.probe_in_progress = False

    try:
        with (
            patch.object(settings, "GEMINI_API_KEY", "test-key"),
            patch("app.providers.acompletion", side_effect=slow_gemini),
        ):
            task = asyncio.create_task(
                call_gemini("Test cancellation")
            )

            # Wait until the mocked Gemini request starts.
            await started.wait()

            # Cancel the in-progress recovery probe.
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

        assert gemini_breaker.state == CircuitState.OPEN
        assert gemini_breaker.probe_in_progress is False

        print("PASS: cancelled recovery probe returns circuit to OPEN")
        print("PASS: cancelled recovery probe releases probe lock")

    finally:
        # Restore the shared breaker to its initial state.
        gemini_breaker.state = CircuitState.CLOSED
        gemini_breaker.failure_count = 0
        gemini_breaker.opened_at = None
        gemini_breaker.probe_in_progress = False


if __name__ == "__main__":
    asyncio.run(test_cancelled_recovery_probe())