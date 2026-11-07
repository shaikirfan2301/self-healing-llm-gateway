
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    def __init__(self):
        self.APP_NAME = os.getenv(
            "APP_NAME",
            "Self-Healing LLM Gateway",
        ).strip()

        self.APP_VERSION = os.getenv(
            "APP_VERSION",
            "0.1.0",
        ).strip()

        gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.GEMINI_API_KEY = gemini_api_key or None

        gateway_api_key = os.getenv("GATEWAY_API_KEY", "").strip()
        self.GATEWAY_API_KEY = gateway_api_key or None

        self._validate()

    def _validate(self):
        if not self.APP_NAME:
            raise ValueError("APP_NAME cannot be empty")

        if not self.APP_VERSION:
            raise ValueError("APP_VERSION cannot be empty")

        if self.GEMINI_API_KEY is not None:
            if len(self.GEMINI_API_KEY) < 10:
                raise ValueError("GEMINI_API_KEY appears invalid")

        if not self.GATEWAY_API_KEY:
            raise ValueError("GATEWAY_API_KEY must be configured")

        if len(self.GATEWAY_API_KEY) < 32:
            raise ValueError(
                "GATEWAY_API_KEY must contain at least 32 characters"
            )


settings = Settings()
