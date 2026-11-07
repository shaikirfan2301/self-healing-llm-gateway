import asyncio
from unittest.mock import patch

from app.providers import call_llm


async def main():
    with patch(
        "app.providers.call_gemini",
        side_effect=RuntimeError("Simulated Gemini outage"),
    ):
        answer = await call_llm(
            "Explain circuit breakers in two sentences."
        )

    print("\nGemini failure simulated successfully.")
    print("Ollama fallback response:")
    print(answer)


if __name__ == "__main__":
    asyncio.run(main())