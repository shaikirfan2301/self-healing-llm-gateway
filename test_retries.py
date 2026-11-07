
import asyncio
from unittest.mock import AsyncMock, patch

from litellm.exceptions import ServiceUnavailableError
from litellm.exceptions import AuthenticationError
from litellm.exceptions import RateLimitError

from app.providers import call_gemini

from types import SimpleNamespace

async def test_retry_then_success():
    fake_response = type(
        "FakeResponse",
        (),
        {
            "choices": [
                type(
                    "Choice",
                    (),
                    {
                        "message": type(
                            "Message",
                            (),
                            {"content": "Recovered successfully"},
                        )()
                    },
                )()
            ]
        },
    )()

    temporary_error = ServiceUnavailableError(
        message="Temporary outage",
        llm_provider="gemini",
        model="gemini/gemini-3.5-flash-lite",
    )

    with (
        patch("app.providers.acompletion", new_callable=AsyncMock) as mock_call,
        patch("app.providers.asyncio.sleep", new_callable=AsyncMock),
    ):
        mock_call.side_effect = [temporary_error, fake_response]

        result = await call_gemini("Test prompt")

        assert result == "Recovered successfully"
        assert mock_call.await_count == 2

    print("PASS: temporary failure was retried and then succeeded")


async def test_retry_limit():
    temporary_error = ServiceUnavailableError(
        message="Simulated temporary outage",
        llm_provider="gemini",
        model="gemini/gemini-3.5-flash-lite",
    )

    with (
        patch("app.providers.acompletion", new_callable=AsyncMock) as mock_call,
        patch("app.providers.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        mock_call.side_effect = [
            temporary_error,
            temporary_error,
            temporary_error,
        ]

        try:
            await call_gemini("Test repeated failures")
            raise AssertionError("Expected ServiceUnavailableError")
        except ServiceUnavailableError:
            pass

        assert mock_call.await_count == 3
        assert mock_sleep.await_count == 2

    print("PASS: stopped after 3 attempts and waited only twice")


async def test_no_retry_on_authentication_error():
    auth_error = AuthenticationError(
        message="Invalid API key",
        llm_provider="gemini",
        model="gemini/gemini-3.5-flash-lite",
    )

    with patch(
        "app.providers.acompletion",
        new_callable=AsyncMock,
    ) as mock_call:
        mock_call.side_effect = auth_error

        try:
            await call_gemini("Test authentication failure")
            raise AssertionError("Expected AuthenticationError")
        except AuthenticationError:
            pass

        assert mock_call.await_count == 1

    print("PASS: authentication error was not retried")


async def test_rate_limit_is_retried():
    rate_limit_error = RateLimitError(
        message="Rate limit exceeded",
        llm_provider="gemini",
        model="gemini/gemini-3.5-flash-lite",
    )

    with patch(
        "app.providers.acompletion",
        new_callable=AsyncMock,
    ) as mock_call:
        mock_call.side_effect = [
            rate_limit_error,
            type(
                "MockResponse",
                (),
                {
                    "choices": [
                        type(
                            "MockChoice",
                            (),
                            {
                                "message": type(
                                    "MockMessage",
                                    (),
                                    {"content": "Recovered after rate limit"},
                                )()
                            },
                        )()
                    ]
                },
            )(),
        ]

        result = await call_gemini("Test rate limit")

        assert result == "Recovered after rate limit"
        assert mock_call.await_count == 2

    print("PASS: rate-limit error was retried successfully")


from app.providers import get_retry_after_seconds


def test_retry_after_header():
    class FakeError(Exception):
        headers = {"retry-after": "5"}

    delay = get_retry_after_seconds(FakeError())

    assert delay == 5.0
    print("PASS: Retry-After header was read correctly")


def test_missing_retry_after_header():
    class FakeError(Exception):
        headers = {}

    delay = get_retry_after_seconds(FakeError())

    assert delay is None
    print("PASS: missing Retry-After uses fallback")


async def test_retry_uses_provider_delay():
    temporary_error = ServiceUnavailableError(
        message="Temporary failure",
        llm_provider="gemini",
        model="gemini/gemini-3.5-flash-lite",
    )

    success_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="Recovered successfully")
            )
        ]
    )

    with (
        patch("app.providers.acompletion", new_callable=AsyncMock) as mock_call,
        patch("app.providers.get_retry_after_seconds", return_value=5.0),
        patch("app.providers.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        patch("app.providers.random.uniform", return_value=0.0),
    ):
        mock_call.side_effect = [temporary_error, success_response]

        result = await call_gemini("Test provider-directed retry")

        assert result == "Recovered successfully"
        mock_sleep.assert_awaited_once_with(5.0)

    print("PASS: retry loop uses provider-directed delay")


if __name__ == "__main__":
    asyncio.run(test_retry_then_success())
    asyncio.run(test_retry_limit())
    asyncio.run(test_no_retry_on_authentication_error())
    asyncio.run(test_rate_limit_is_retried())
    test_retry_after_header()
    test_missing_retry_after_header()
    asyncio.run(test_retry_uses_provider_delay())