import asyncio
from unittest.mock import AsyncMock, patch

from app.providers import call_llm
from app.metrics import FALLBACK_COUNT


async def test_gemini_success_skips_ollama():
    with (
        patch(
            "app.providers.call_gemini",
            new_callable=AsyncMock,
            return_value="Gemini response",
        ) as mock_gemini,
        patch(
            "app.providers.call_ollama",
            new_callable=AsyncMock,
        ) as mock_ollama,
    ):
        result = await call_llm("Test prompt")

        assert result == "Gemini response"
        mock_gemini.assert_awaited_once_with("Test prompt")
        mock_ollama.assert_not_awaited()

    print("PASS: Gemini success skips Ollama")


async def test_gemini_failure_uses_ollama():
    fallback_count_before = FALLBACK_COUNT._value.get()

    with (
        patch(
            "app.providers.call_gemini",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Gemini unavailable"),
        ),
        patch(
            "app.providers.call_ollama",
            new_callable=AsyncMock,
            return_value="Ollama fallback response",
        ) as mock_ollama,
    ):
        result = await call_llm("Test prompt")

        assert result == "Ollama fallback response"
        mock_ollama.assert_awaited_once_with("Test prompt")

    fallback_count_after = FALLBACK_COUNT._value.get()

    assert fallback_count_after == fallback_count_before + 1

    print("PASS: Gemini failure triggers Ollama fallback")
    print("PASS: Fallback counter increments correctly")



async def test_both_providers_fail():
    with (
        patch(
            "app.providers.call_gemini",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Gemini unavailable"),
        ),
        patch(
            "app.providers.call_ollama",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Ollama unavailable"),
        ),
    ):
        try:
            await call_llm("Test prompt")
        except RuntimeError as exc:
            assert str(exc) == "Both Gemini and Ollama failed."
        else:
            raise AssertionError("Expected both providers to fail")

    print("PASS: failure of both providers raises a clear error")



async def test_open_circuit_uses_ollama():
    with (
        patch(
            "app.providers.call_gemini",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Gemini circuit breaker is open"),
        ) as mock_gemini,
        patch(
            "app.providers.call_ollama",
            new_callable=AsyncMock,
            return_value="Ollama fallback response",
        ) as mock_ollama,
    ):
        result = await call_llm("Test prompt")

        assert result == "Ollama fallback response"
        mock_gemini.assert_awaited_once_with("Test prompt")
        mock_ollama.assert_awaited_once_with("Test prompt")

    print("PASS: open Gemini circuit falls back to Ollama")



if __name__ == "__main__":
    asyncio.run(test_gemini_success_skips_ollama())
    asyncio.run(test_gemini_failure_uses_ollama())
    asyncio.run(test_both_providers_fail())
    asyncio.run(test_open_circuit_uses_ollama())