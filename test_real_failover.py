import asyncio
from unittest.mock import AsyncMock, patch

from app.providers import call_llm


async def main():
    with patch(
        "app.providers.call_gemini",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Simulated Gemini outage"),
    ):
        result = await call_llm(
            "Explain an API gateway in two sentences."
        )

    assert isinstance(result, str) and result.strip()
    print("\nPASS: Gemini failure triggered real Ollama fallback.")
    print("\nOllama response:")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())