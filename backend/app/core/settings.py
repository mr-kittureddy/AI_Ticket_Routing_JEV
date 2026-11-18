from functools import lru_cache

from pydantic import Field

from app.core.config import AppConfig


class Settings(AppConfig):
    """
    Superset of AppConfig. Every field in AppConfig keeps its exact name, default and
    behavior; the fields below only add runtime settings required by the persistence,
    RAG, RBAC and savings-metric layers.
    """

    # Persistence (SQLite by default per PRD; PostgreSQL via DATABASE_URL in Docker Compose)
    DATABASE_URL: str = Field(
        default="sqlite:///./support_tickets.db",
        description="SQLAlchemy URL. SQLite for prototyping, postgresql+psycopg2://... for Compose",
    )

    # ChromaDB knowledge base (past-ticket RAG)
    CHROMA_PERSIST_DIR: str = Field(
        default="./chroma_store",
        description="Directory where the ChromaDB persistent client stores its data",
    )
    CHROMA_COLLECTION: str = Field(
        default="past_tickets_kb",
        description="ChromaDB collection holding resolved historical tickets",
    )
    RAG_TOP_K: int = Field(
        default=3,
        description="Number of similar past tickets retrieved to ground Gemini resolutions",
    )

    # Outbound call timeouts
    OPENROUTER_TIMEOUT_SECONDS: float = Field(
        default=5.0,
        description="HTTP timeout for the JEV classification call",
    )
    GEMINI_TIMEOUT_SECONDS: float = Field(
        default=12.0,
        description="Timeout for the Gemini resolution call",
    )

    # RBAC
    ENFORCE_RBAC_ON_PROCESS_TICKET: bool = Field(
        default=False,
        description="When False, /api/process-ticket is open per the PRD's no-auth prototype flow",
    )

    # Savings metric baselines (PRD: Gemini drafting time is ~1000-2000ms)
    BASELINE_GEMINI_LATENCY_MS: int = Field(
        default=1500,
        description="Assumed Gemini drafting latency used to compute time saved when Gemini is bypassed",
    )
    BASELINE_GEMINI_COST_USD: float = Field(
        default=0.0004,
        description="Assumed cost per Gemini resolution call used to compute cost saved when bypassed",
    )


@lru_cache()
def get_settings() -> Settings:
    """Returns the cached extended settings singleton."""
    return Settings()


settings = get_settings()
