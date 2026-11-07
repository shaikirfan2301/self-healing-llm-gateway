
import time

from collections import defaultdict
from fastapi import Request, HTTPException


RATE_LIMIT = 10
WINDOW_SECONDS = 60

request_counts = defaultdict(list)


async def enforce_rate_limit(request: Request):
    """Limit authenticated requests by client IP."""

    client_ip = (
        request.client.host
        if request.client
        else "unknown"
    )

    current_time = time.monotonic()
    window_start = current_time - WINDOW_SECONDS

    # Keep only requests within the current time window.
    timestamps = request_counts[client_ip]

    timestamps[:] = [
        timestamp
        for timestamp in timestamps
        if timestamp > window_start
    ]

    if len(timestamps) >= RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Try again later.",
            headers={"Retry-After": str(WINDOW_SECONDS)},
        )

    timestamps.append(current_time)

