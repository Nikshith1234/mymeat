"""
Application configuration using pydantic-settings.
All values are loaded from environment variables or .env file.
"""
import json
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App
    APP_NAME: str = "Meatcraft Voice Ordering"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    BASE_URL: str = "https://nonsciatic-fulsomely-rodney.ngrok-free.dev"

    # Database
    DATABASE_URL: str = "sqlite:///./meatcraft.db"

    # Razorpay
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""

    # Petpooja POS
    PETPOOJA_API_URL: str = "https://pponlineordercb.petpooja.com"
    PETPOOJA_APP_KEY: str = ""
    PETPOOJA_APP_SECRET: str = ""
    PETPOOJA_ACCESS_TOKEN: str = ""
    PETPOOJA_RESTAURANT_ID: str = ""
    PETPOOJA_RESTAURANT_NAME: str = "Meatcraft"



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


def get_settings() -> Settings:
    """Settings instance — reads from .env each call (no caching so .env changes take effect on restart)."""
    return Settings()
