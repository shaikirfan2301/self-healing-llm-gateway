import time

from app.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
)


def test_circuit_starts_closed():
    breaker = CircuitBreaker()

    assert breaker.state == CircuitState.CLOSED
    print("PASS: circuit starts closed")


def test_circuit_opens_after_3_failures():
    breaker = CircuitBreaker()

    for _ in range(3):
        token = breaker.allow_request()
        breaker.record_failure(token)

    assert breaker.state == CircuitState.OPEN
    print("PASS: circuit opens after 3 failures")


def test_success_resets_failure_count():
    breaker = CircuitBreaker()

    token = breaker.allow_request()
    breaker.record_failure(token)

    token = breaker.allow_request()
    breaker.record_success(token)

    assert breaker.failure_count == 0
    print("PASS: success resets failure count")


def test_recovery_probe_after_timeout():
    breaker = CircuitBreaker(recovery_timeout=0.1)

    for _ in range(3):
        token = breaker.allow_request()
        breaker.record_failure(token)

    time.sleep(0.15)

    token = breaker.allow_request()

    assert token is not None
    assert token.is_probe is True
    assert breaker.state == CircuitState.HALF_OPEN

    print("PASS: circuit allows a recovery probe after timeout")


def test_only_one_half_open_probe():
    breaker = CircuitBreaker(recovery_timeout=0.1)

    for _ in range(3):
        token = breaker.allow_request()
        breaker.record_failure(token)

    time.sleep(0.15)

    first_token = breaker.allow_request()
    second_token = breaker.allow_request()

    assert first_token is not None
    assert first_token.is_probe is True
    assert second_token is None

    breaker.record_success(first_token)

    assert breaker.state == CircuitState.CLOSED
    print("PASS: only one half-open probe is allowed")


def test_late_success_does_not_close_open_circuit():
    breaker = CircuitBreaker()

    old_token = breaker.allow_request()

    for _ in range(3):
        token = breaker.allow_request()
        breaker.record_failure(token)

    breaker.record_success(old_token)

    assert breaker.state == CircuitState.OPEN
    print("PASS: late success does not close an open circuit")


def test_late_failure_does_not_modify_new_generation():
    breaker = CircuitBreaker(recovery_timeout=0.1)

    old_token = breaker.allow_request()

    for _ in range(3):
        token = breaker.allow_request()
        breaker.record_failure(token)

    time.sleep(0.15)

    probe_token = breaker.allow_request()
    breaker.record_success(probe_token)

    assert breaker.state == CircuitState.CLOSED

    breaker.record_failure(old_token)

    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0

    print("PASS: late failure does not affect recovered circuit")


def test_cancelled_probe_reopens_circuit():
    breaker = CircuitBreaker(recovery_timeout=0.1)

    for _ in range(3):
        token = breaker.allow_request()
        breaker.record_failure(token)

    time.sleep(0.15)

    probe_token = breaker.allow_request()
    breaker.record_probe_cancelled(probe_token)

    assert breaker.state == CircuitState.OPEN
    assert breaker.probe_in_progress is False

    print("PASS: cancelled recovery probe reopens circuit")


if __name__ == "__main__":
    test_circuit_starts_closed()
    test_circuit_opens_after_3_failures()
    test_success_resets_failure_count()
    test_recovery_probe_after_timeout()
    test_only_one_half_open_probe()
    test_late_success_does_not_close_open_circuit()
    test_late_failure_does_not_modify_new_generation()
    test_cancelled_probe_reopens_circuit()