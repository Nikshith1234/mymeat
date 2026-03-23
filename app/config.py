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
    BASE_URL: str

    # Database
    MONGODB_URL: str
    MONGODB_DB_NAME: str = "meatcraft"

    # JWT Config
    SECRET_KEY: str = "your_super_secret_jwt_key_here"  # Override in .env
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days

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
    RIGHTSIDE_API_URL: str = "https://devvoice.rock8.ai"
    RIGHTSIDE_PHONE_NUMBER: str = ""
    SIP_TRUNK_ID: str = ""
    DISPATCH_RULE_ID: str = ""

    # Twilio WhatsApp
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_WHATSAPP_FROM: str = "+14155238886"  # Twilio sandbox default

    # Meta WhatsApp API
    META_PHONE_NUMBER_ID: str = ""
    META_ACCESS_TOKEN: str = ""

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
