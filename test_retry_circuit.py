import asyncio
from unittest.mock import patch

from app.circuit_breaker import CircuitState, gemini_breaker
from app.config import settings
from app.providers import call_gemini


async def test_retry_stops_after_circuit_opens():
    retry_started = asyncio.Event()
    release_retry = asyncio.Event()
    api_call_count = 0

    async def mock_gemini(**kwargs):
        nonlocal api_call_count
        api_call_count += 1
        raise RuntimeError("Simulated temporary failure")

    async def mock_sleep(delay):
        retry_started.set()
        await release_retry.wait()

    # Start with a clean breaker.
    gemini_breaker.state = CircuitState.CLOSED
    gemini_breaker.failure_count = 0
    gemini_breaker.opened_at = None
    gemini_breaker.probe_in_progress = False
    gemini_breaker.generation = 0

    task = None

    try:
        with (
            patch.object(settings, "GEMINI_API_KEY", "test-key"),
            patch("app.providers.acompletion", side_effect=mock_gemini),
            patch("app.providers.RETRYABLE_ERRORS", (RuntimeError,)),
            patch("app.providers.asyncio.sleep", side_effect=mock_sleep),
        ):
            task = asyncio.create_task(
                call_gemini("Test retry")
            )

            # Wait until the first attempt fails and enters backoff.
            await retry_started.wait()

            # Simulate three other requests failing.
            for _ in range(3):
                token = gemini_breaker.allow_request()
                assert token is not None
                gemini_breaker.record_failure(token)

            assert gemini_breaker.state == CircuitState.OPEN

            # Let the original request leave its retry delay.
            release_retry.set()

            try:
                await task
                assert False, "Expected the stale request to be rejected"
            except RuntimeError as exc:
                assert "invalidated by circuit breaker" in str(exc)

            # The stale request must not make a second Gemini call.
            assert api_call_count == 1

            print("PASS: circuit opening invalidates the old request")
            print("PASS: stale request does not make another retry")

    finally:
        release_retry.set()

        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        gemini_breaker.state = CircuitState.CLOSED
        gemini_breaker.failure_count = 0
        gemini_breaker.opened_at = None
        gemini_breaker.probe_in_progress = False
        gemini_breaker.generation = 0


if __name__ == "__main__":
    asyncio.run(test_retry_stops_after_circuit_opens())
    