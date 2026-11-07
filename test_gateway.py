
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.main import app
from app.config import settings
from app.metrics import FALLBACK_COUNT


client = TestClient(app)

AUTH_HEADERS = {
    "X-API-Key": settings.GATEWAY_API_KEY
}


def test_root_endpoint():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

    print("PASS: root endpoint")


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert "providers" in response.json()

    print("PASS: health endpoint")


def test_authentication():
    # Missing API key
    response = client.post(
        "/chat",
        json={"prompt": "Hello"},
    )

    assert response.status_code == 401

    # Invalid API key
    response = client.post(
        "/chat",
        json={"prompt": "Hello"},
        headers={"X-API-Key": "invalid-test-key"},
    )

    assert response.status_code == 401

    print("PASS: missing API key rejected")
    print("PASS: invalid API key rejected")


def test_chat_success():
    fallback_count_before = FALLBACK_COUNT._value.get()

    with patch(
        "app.main.call_llm",
        new_callable=AsyncMock,
        return_value="Mock Gemini response",
    ) as mock_llm:
        response = client.post(
            "/chat",
            json={"prompt": "Hello"},
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 200, response.text
    assert response.json()["response"] == "Mock Gemini response"

    mock_llm.assert_awaited_once_with("Hello")

    fallback_count_after = FALLBACK_COUNT._value.get()

    assert fallback_count_after == fallback_count_before

    print("PASS: chat endpoint returns mocked response")
    print("PASS: successful chat does not increment fallback counter")


def test_chat_fallback_increments_counter():
    from app.providers import call_llm as real_call_llm

    fallback_count_before = FALLBACK_COUNT._value.get()

    async def mock_call_llm(prompt):
        with (
            patch(
                "app.providers.call_gemini",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Gemini unavailable"),
            ),
            patch(
                "app.providers.call_ollama",
                new_callable=AsyncMock,
                return_value="Mock Ollama fallback response",
            ),
        ):
            return await real_call_llm(prompt)

    with patch(
        "app.main.call_llm",
        side_effect=mock_call_llm,
    ):
        response = client.post(
            "/chat",
            json={"prompt": "Hello"},
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 200, response.text

    assert response.json()["response"] == (
        "Mock Ollama fallback response"
    )

    assert FALLBACK_COUNT._value.get() == fallback_count_before + 1

    print("PASS: chat endpoint returns fallback response")
    print("PASS: fallback counter increments through /chat")


def test_metrics_endpoint():
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "gateway_fallback_total" in response.text
    assert "gateway_requests_total" in response.text
    assert "gateway_request_duration_seconds" in response.text

    print("PASS: metrics endpoint returns Prometheus metrics")
    print("PASS: fallback counter is exposed")


def test_chat_prompt_validation():
    # Empty prompt
    response = client.post(
        "/chat",
        json={"prompt": ""},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 422

    # Whitespace-only prompt
    response = client.post(
        "/chat",
        json={"prompt": "   "},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 422

    # Prompt exceeding 10,000 characters
    response = client.post(
        "/chat",
        json={"prompt": "a" * 10001},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 422

    print("PASS: empty prompt rejected")
    print("PASS: whitespace-only prompt rejected")
    print("PASS: oversized prompt rejected")



def test_health_routes():
    from types import SimpleNamespace

    live = client.get("/health/live")

    assert live.status_code == 200
    assert live.json()["status"] == "alive"

    class MockAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_value, traceback):
            pass

        async def get(self, url):
            return SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "models": [
                        {"name": "llama3.2:1b"}
                    ]
                },
            )

    with patch(
        "app.main.httpx.AsyncClient",
        return_value=MockAsyncClient(),
    ):
        ready = client.get("/health/ready")

    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"

    print("PASS: liveness endpoint")
    print("PASS: readiness endpoint")



if __name__ == "__main__":
    test_root_endpoint()
    test_health_endpoint()
    test_authentication()
    test_chat_success()
    test_chat_fallback_increments_counter()
    test_metrics_endpoint()
    test_chat_prompt_validation()
    test_health_routes()

    print("\nALL GATEWAY TESTS PASSED")
