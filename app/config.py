"""
Application configuration using pydantic-settings.
All values are loaded from environment variables or .env file.
"""
import json
from typing import List
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App
    APP_NAME: str = "Meatcraft Voice Ordering"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    BASE_URL: str = "http://localhost:8000"

    # Database
    DATABASE_URL: str = "sqlite:///./meatcraft.db"

    # Razorpay
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""

    # Petpooja POS
    PETPOOJA_API_URL: str = "https://api.petpooja.com/v2"
    PETPOOJA_TOKEN: str = ""
    PETPOOJA_RESTAURANT_ID: str = ""
    PETPOOJA_APP_KEY: str = ""



    # Rightside AI
    RIGHTSIDE_API_KEY: str = ""
    RIGHTSIDE_API_URL: str = "https://voice.rock8.ai"
    RIGHTSIDE_PHONE_NUMBER: str = ""
    SIP_TRUNK_ID: str = ""
    DISPATCH_RULE_ID: str = ""

    # CORS
    CORS_ORIGINS: str = '["*"]'

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS_ORIGINS JSON string to list."""
        try:
            return json.loads(self.CORS_ORIGINS)
        except (json.JSONDecodeError, TypeError):
            return ["*"]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore"
    }


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance — created once and reused."""
    return Settings()
