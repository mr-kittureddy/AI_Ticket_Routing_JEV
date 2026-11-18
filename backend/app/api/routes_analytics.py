from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.analytics import AnalyticsResponse
from app.services.analytics_service import DEFAULT_SERIES_LIMIT, get_analytics
from app.services.rbac import Permission, Principal, require_permission

router = APIRouter(prefix="/api", tags=["analytics"])


@router.get(
    "/analytics",
    response_model=AnalyticsResponse,
    summary="JEV performance and cost-savings analytics",
    description=(
        "Summary metrics (average, p50 and p95 JEV latency, threshold compliance, Gemini bypass rate, "
        "time and cost saved), a per-team breakdown, and latency and cumulative-savings series."
    ),
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "A known user is required"},
        status.HTTP_403_FORBIDDEN: {"description": "Role lacks the analytics:read permission"},
    },
)
def get_analytics_endpoint(
    window_days: Optional[int] = Query(default=None, ge=1, le=365, description="Only include the last N days; omit for all time"),
    series_limit: int = Query(default=DEFAULT_SERIES_LIMIT, ge=1, le=500, description="Maximum points per chart series"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission(Permission.ANALYTICS_READ)),
) -> AnalyticsResponse:
    """Returns the analytics payload for the requested window."""
    return get_analytics(db, principal, window_days=window_days, series_limit=series_limit)
