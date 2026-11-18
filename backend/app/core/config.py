import os
from functools import lru_cache
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class AppConfig(BaseSettings):
    """
    Centralized Configuration for PRD Support Ticket AI Routing Engine.
    Loads variables from local environment or .env file automatically.
    """
    # Environment Setup
    ENVIRONMENT: str = Field(default="development", description="Execution environment: development | staging | production")
    DEBUG: bool = Field(default=True, description="Enable debug logs and endpoint traces")

    # Server Configuration
    BACKEND_HOST: str = Field(default="0.0.0.0", description="Backend server host")
    BACKEND_PORT: int = Field(default=8000, description="Backend server port")
    CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        description="Allowed origins for frontend dashboard"
    )

    # API Credentials & Engine Masking
    OPENROUTER_API_KEY: Optional[str] = Field(
        default="sk-or-v1-MASKED_KEY_HERE",
        description="OpenRouter API Key used by JEV AI Router"
    )
    GEMINI_API_KEY: Optional[str] = Field(
        default="AIzaSy_MASKED_KEY_HERE",
        description="Google Gemini API Key used by Generative Engine"
    )

    # Model & Engine Parameters
    OPENROUTER_MODEL: str = Field(
        default="typesafe/jev-1.14",
        description="TypeSafe JEV 1.14 System One decision model on OpenRouter for sub-100ms routing"
    )
    OPENROUTER_BASE_URL: str = Field(
        default="https://openrouter.ai/api/v1",
        description="Base URL for OpenRouter completions"
    )
    GEMINI_MODEL: str = Field(
        default="gemini-3.5-flash-lite",
        description="Google Gemini model for structured ticket auto-resolution"
    )
    JEV_LATENCY_THRESHOLD_MS: int = Field(
        default=500,
        description="Target SLA threshold for JEV classification engine in milliseconds"
    )

    # Pydantic Settings Configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True
    )

    @property
    def is_openrouter_masked(self) -> bool:
        """Check if OpenRouter key is missing or dummy/masked."""
        key = self.OPENROUTER_API_KEY or ""
        return "MASKED" in key or not key.startswith("sk-or")

    @property
    def is_gemini_masked(self) -> bool:
        """Check if Gemini key is missing or dummy/masked."""
        key = self.GEMINI_API_KEY or ""
        return "MASKED" in key or not (key.startswith("AIza") or key.startswith("AQ."))

@lru_cache()
def get_config() -> AppConfig:
    """Returns cached instance of the config singleton."""
    return AppConfig()

config = get_config()
