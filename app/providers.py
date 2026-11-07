import os
import asyncio
import logging
import random

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from litellm import acompletion
from litellm.exceptions import (
    APIConnectionError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)

from app.config import settings
from app.metrics import (
    CIRCUIT_BREAKER_STATE,
    FALLBACK_COUNT,
    PROVIDER_FAILURE_COUNT,
)

from app.circuit_breaker import CircuitState, gemini_breaker


logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3

RETRYABLE_ERRORS = (
    APIConnectionError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)

OLLAMA_MODEL = "ollama/llama3.2:1b"
OLLAMA_API_BASE = os.getenv(
    "OLLAMA_API_BASE",
    "http://localhost:11434",
)

def update_circuit_breaker_metric() -> None:
    """Publish the current Gemini circuit-breaker state."""
    state_values = {
        CircuitState.CLOSED: 0,
        CircuitState.OPEN: 1,
        CircuitState.HALF_OPEN: 2,
    }

    CIRCUIT_BREAKER_STATE.set(
        state_values[gemini_breaker.state]
    )


def get_retry_after_seconds(exc: Exception) -> float | None:
    """Read Retry-After guidance from a provider error."""
    headers = getattr(exc, "headers", None)

    if not headers:
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None)

    if not headers:
        return None

    retry_after = headers.get("retry-after")

    if not retry_after:
        return None

    try:
        return max(0.0, float(retry_after))
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(retry_after)

            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(
                    tzinfo=timezone.utc
                )

            return max(
                0.0,
                (
                    retry_at - datetime.now(timezone.utc)
                ).total_seconds(),
            )
        except (TypeError, ValueError, OverflowError):
            return None


async def call_gemini(prompt: str) -> str:
    """
    Call Gemini with retries.

    Raises if Gemini cannot answer, allowing call_llm()
    to select the fallback provider.
    """
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    token = gemini_breaker.allow_request()
    update_circuit_breaker_metric()

    if token is None:
        raise RuntimeError("Gemini circuit breaker is open")

    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):

            # Stop retries if this request belongs to an older
            # circuit generation.
            if not gemini_breaker.is_request_current(token):
                raise RuntimeError(
                    "Gemini request invalidated by circuit breaker"
                )

            try:
                response = await acompletion(
                    model="gemini/gemini-3.5-flash-lite",
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    api_key=settings.GEMINI_API_KEY,
                )

                answer = response.choices[0].message.content

                if not answer:
                    raise RuntimeError(
                        "Gemini returned an empty response"
                    )

                gemini_breaker.record_success(token)
                update_circuit_breaker_metric()

                return answer

            except RETRYABLE_ERRORS as exc:
                if attempt == MAX_ATTEMPTS:
                    gemini_breaker.record_failure(token)
                    update_circuit_breaker_metric()

                    PROVIDER_FAILURE_COUNT.labels(
                        provider="gemini"
                    ).inc()

                    logger.error(
                        "Gemini failed after %s attempts: %s",
                        attempt,
                        type(exc).__name__,
                    )
                    raise

                retry_after = get_retry_after_seconds(exc)

                if retry_after is not None:
                    delay = retry_after + random.uniform(0, 0.5)
                else:
                    delay = (
                        2 ** (attempt - 1)
                        + random.uniform(0, 0.5)
                    )

                logger.warning(
                    "Gemini attempt %s/%s failed with %s. "
                    "Retrying in %.2f seconds.",
                    attempt,
                    MAX_ATTEMPTS,
                    type(exc).__name__,
                    delay,
                )

                await asyncio.sleep(delay)

            except Exception:
                gemini_breaker.record_failure(token)
                update_circuit_breaker_metric()

                PROVIDER_FAILURE_COUNT.labels(
                    provider="gemini"
                ).inc()

                raise

    except asyncio.CancelledError:
        gemini_breaker.record_probe_cancelled(token)
        update_circuit_breaker_metric()

        logger.warning("Gemini request was cancelled.")
        raise

    raise RuntimeError("Gemini request ended unexpectedly")



async def call_ollama(prompt: str) -> str:
    """Generate a response using the local Ollama model."""
    logger.warning("Using Ollama fallback model: %s", OLLAMA_MODEL)

    try:
        response = await acompletion(
            model=OLLAMA_MODEL,
            api_base=OLLAMA_API_BASE,
            messages=[
                {"role": "user", "content": prompt}
            ],
            timeout=60,
        )

        answer = response.choices[0].message.content

        if not answer:
            raise RuntimeError("Ollama returned an empty response")

        return answer

    except Exception:
        PROVIDER_FAILURE_COUNT.labels(
            provider="ollama"
        ).inc()

        logger.exception("Ollama provider request failed.")
        raise



async def call_llm(prompt: str) -> str:
    """
    Try Gemini first and use Ollama if Gemini fails.

    Gemini's circuit breaker tracks Gemini only; a successful
    Ollama response does not reset Gemini's failure count.
    """
    try:
        return await call_gemini(prompt)

    except Exception as gemini_error:
        FALLBACK_COUNT.inc()

        logger.warning(
            "Gemini unavailable (%s); trying Ollama fallback.",
            type(gemini_error).__name__,
    )

        try:
            return await call_ollama(prompt)

        except Exception as ollama_error:
            logger.exception("Ollama fallback also failed.")

            raise RuntimeError(
                "Both Gemini and Ollama failed."
            ) from ollama_error