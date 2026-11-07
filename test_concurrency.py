import asyncio
import time
from types import SimpleNamespace
from unittest.mock import patch

from app.circuit_breaker import CircuitState, gemini_breaker
from app.config import settings
from app.providers import call_gemini


def reset_breaker():
    gemini_breaker.state = CircuitState.CLOSED
    gemini_breaker.failure_count = 0
    gemini_breaker.opened_at = None
    gemini_breaker.probe_in_progress = False
    gemini_breaker.generation = 0


async def test_overlapping_requests():
    first_request_started = asyncio.Event()
    release_first_request = asyncio.Event()
    call_count = 0
    first_task = None

    async def mock_gemini(**kwargs):
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            first_request_started.set()
            await release_first_request.wait()

            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="Successful response"
                        )
                    )
                ]
            )

        raise RuntimeError("Simulated Gemini failure")

    reset_breaker()

    try:
        with (
            patch.object(settings, "GEMINI_API_KEY", "test-key"),
            patch("app.providers.acompletion", side_effect=mock_gemini),
        ):
            first_task = asyncio.create_task(
                call_gemini("First request")
            )

            await first_request_started.wait()

            for _ in range(3):
                try:
                    await call_gemini("Failing request")
                except RuntimeError:
                    pass

            assert gemini_breaker.state == CircuitState.OPEN

            release_first_request.set()
            result = await first_task

            assert result == "Successful response"
            assert gemini_breaker.state == CircuitState.OPEN

            print("PASS: overlapping requests handled correctly")
            print("PASS: late success does not close open circuit")

    finally:
        release_first_request.set()

        if first_task is not None and not first_task.done():
            first_task.cancel()
            try:
                await first_task
            except asyncio.CancelledError:
                pass

        reset_breaker()


async def test_late_failure_does_not_modify_open_circuit():
    first_request_started = asyncio.Event()
    release_first_request = asyncio.Event()
    call_count = 0
    first_task = None

    async def mock_gemini(**kwargs):
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            first_request_started.set()
            await release_first_request.wait()
            raise RuntimeError("Late request failure")

        raise RuntimeError("Simulated Gemini failure")

    reset_breaker()

    try:
        with (
            patch.object(settings, "GEMINI_API_KEY", "test-key"),
            patch("app.providers.acompletion", side_effect=mock_gemini),
        ):
            first_task = asyncio.create_task(
                call_gemini("Older request")
            )

            await first_request_started.wait()

            for _ in range(3):
                try:
                    await call_gemini("Failing request")
                except RuntimeError:
                    pass

            assert gemini_breaker.state == CircuitState.OPEN
            opened_at = gemini_breaker.opened_at

            release_first_request.set()

            try:
                await first_task
            except RuntimeError:
                pass

            assert gemini_breaker.state == CircuitState.OPEN
            assert gemini_breaker.opened_at == opened_at

            print("PASS: late failure does not alter open circuit")
            print("PASS: late failure does not restart recovery timeout")

    finally:
        release_first_request.set()

        if first_task is not None and not first_task.done():
            first_task.cancel()
            try:
                await first_task
            except asyncio.CancelledError:
                pass

        reset_breaker()


if __name__ == "__main__":
    asyncio.run(test_overlapping_requests())
    asyncio.run(test_late_failure_does_not_modify_open_circuit())