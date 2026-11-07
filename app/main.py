import logging
import time
import uuid
import httpx
import secrets

from fastapi import (
    FastAPI,
    Request,
    HTTPException,
    Depends,
    Header,
)
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field, field_validator
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from app.rate_limiter import enforce_rate_limit
from app.config import settings
from app.providers import (
    call_llm,
    OLLAMA_API_BASE,
    OLLAMA_MODEL,
)
from app.circuit_breaker import CircuitState, gemini_breaker
from app.metrics import REQUEST_COUNT, REQUEST_LATENCY


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Self-Healing LLM Gateway",
    description="A gateway for routing LLM requests reliably.",
    version="0.1.0",
)

@app.middleware("http")
async def track_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start_time = time.perf_counter()
    status_code = 500

    try:
        response = await call_next(request)
        status_code = response.status_code

        response.headers["X-Request-ID"] = request_id

        return response

    except Exception:
        logger.exception(
            "request_id=%s method=%s path=%s failed",
            request_id,
            request.method,
            request.url.path,
        )
        raise

    finally:
        duration = time.perf_counter() - start_time

        REQUEST_COUNT.labels(
            method=request.method,
            path=request.url.path,
            status=str(status_code),
        ).inc()

        REQUEST_LATENCY.labels(
            method=request.method,
            path=request.url.path,
        ).observe(duration)

        logger.info(
            "request_id=%s method=%s path=%s status=%s duration_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            status_code,
            duration * 1000,
        )




@app.get("/")
def health_check():
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


@app.get("/health/live")
def liveness_check():
    return {
        "status": "alive",
        "service": settings.APP_NAME,
    }



@app.get("/health")
def gateway_health():
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "providers": {
            "gemini": {
                "circuit_breaker": gemini_breaker.state.value,
            }
        },
    }


@app.get("/health/ready")
async def readiness_check():
    gemini_available = (
        bool(settings.GEMINI_API_KEY)
        and gemini_breaker.state == CircuitState.CLOSED
    )

    ollama_available = False

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(
                f"{OLLAMA_API_BASE}/api/tags"
            )

            if response.status_code == 200:
                data = response.json()

                required_model = OLLAMA_MODEL.removeprefix("ollama/")

                ollama_available = any(
                    model.get("name") == required_model
                    or model.get("model") == required_model
                    for model in data.get("models", [])
                )

    except (httpx.RequestError, ValueError):
        ollama_available = False

    ready = gemini_available or ollama_available

    result = {
        "status": "ready" if ready else "not_ready",
        "providers": {
            "gemini": gemini_available,
            "ollama": ollama_available,
        },
    }

    return JSONResponse(
        status_code=200 if ready else 503,
        content=result,
    )


class ChatRequest(BaseModel):
    prompt: str = Field(
        min_length=1,
        max_length=10000,
    )

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Prompt cannot contain only whitespace")

        return value


async def verify_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    if (
        not x_api_key
        or not secrets.compare_digest(
            x_api_key,
            settings.GATEWAY_API_KEY,
        )
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
        )

    
@app.post("/chat")
async def chat(
    request: ChatRequest,
    _: None = Depends(verify_api_key),
    __: None = Depends(enforce_rate_limit),
):
    try:
        answer = await call_llm(request.prompt)

        return {
            "response": answer
        }

    except Exception:
        logger.exception("LLM provider request failed")

        raise HTTPException(
            status_code=502,
            detail="LLM provider request failed. Please try again later.",
        )

    

@app.get("/metrics")
def metrics():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
