from fastapi import APIRouter

from app.core.settings import settings
from app.db.session import check_connection
from app.schemas.analytics import HealthResponse
from app.services.gemini_service import get_gemini_service
from app.services.jev_service import get_jev_service
from app.services.rag_service import get_rag_service

router = APIRouter(prefix="/api", tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health and engine modes",
    description="Reports database connectivity and whether JEV and Gemini run live or in deterministic simulator mode.",
)
def health_endpoint() -> HealthResponse:
    """Returns service health; the status is degraded when the database is unreachable."""
    database_ok = check_connection()
    return HealthResponse(
        status="ok" if database_ok else "degraded",
        environment=settings.ENVIRONMENT,
        database_ok=database_ok,
        jev_engine_mode="live" if get_jev_service().is_live else "simulated",
        gemini_engine_mode="live" if get_gemini_service().is_live else "simulated",
        rag_enabled=get_rag_service().is_ready,
        jev_threshold_ms=settings.JEV_LATENCY_THRESHOLD_MS,
    )
