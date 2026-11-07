from prometheus_client import Counter, Histogram, Gauge

# Total number of HTTP requests handled by the gateway.
REQUEST_COUNT = Counter(
    "gateway_requests_total",
    "Total HTTP requests handled by the gateway",
    ["method", "path", "status"],
)

# Time taken to process HTTP requests, measured in seconds.
REQUEST_LATENCY = Histogram(
    "gateway_request_duration_seconds",
    "HTTP request processing time in seconds",
    ["method", "path"],
)

# Current state of the Gemini circuit breaker:
# 0 = closed, 1 = open, 2 = half-open.
CIRCUIT_BREAKER_STATE = Gauge(
    "gateway_circuit_breaker_state",
    "Current Gemini circuit breaker state",
)

CIRCUIT_BREAKER_STATE.set(0)

# Total number of times the gateway attempts Ollama fallback.
FALLBACK_COUNT = Counter(
    "gateway_fallback_total",
    "Total number of attempts to fall back from Gemini to Ollama",
)

# Total number of failed requests for each LLM provider.
PROVIDER_FAILURE_COUNT = Counter(
    "gateway_provider_failures_total",
    "Total number of failed requests for each LLM provider",
    ["provider"],
)

# Initialize provider failure counters so they appear in Prometheus at zero.
PROVIDER_FAILURE_COUNT.labels(provider="gemini")
PROVIDER_FAILURE_COUNT.labels(provider="ollama")