from app.circuit_breaker import CircuitBreaker

invalid_configs = [
    {"failure_threshold": 0},
    {"failure_threshold": -1},
    {"recovery_timeout": 0},
    {"recovery_timeout": -5},
]

for config in invalid_configs:
    try:
        CircuitBreaker(**config)
        print(f"FAIL: accepted {config}")
    except ValueError:
        print(f"PASS: rejected {config}")