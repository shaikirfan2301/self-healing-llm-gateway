
from fastapi.testclient import TestClient
from unittest.mock import patch

from app.main import app
from app.providers import gemini_breaker

client = TestClient(app)


def test_chat_rejects_request_when_circuit_is_open():
    with patch.object(gemini_breaker, "allow_request", return_value=False):
        response = client.post(
            "/chat",
            json={"prompt": "Test circuit breaker"},
        )

    assert response.status_code == 502, response.text
    print("PASS: gateway rejects requests when the circuit breaker is open")


if __name__ == "__main__":
    test_chat_rejects_request_when_circuit_is_open()
