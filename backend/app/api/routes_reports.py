from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.analytics import ReportFormat
from app.services.rbac import Permission, Principal, require_permission
from app.services.report_service import export_report

router = APIRouter(prefix="/api", tags=["reports"])


@router.get(
    "/reports",
    summary="Export the routing report as CSV or PDF",
    description="Downloads a report with the performance summary, team breakdown and ticket table.",
    response_class=Response,
    responses={
        status.HTTP_200_OK: {
            "description": "The generated report file",
            "content": {"text/csv": {}, "application/pdf": {}},
        },
        status.HTTP_401_UNAUTHORIZED: {"description": "A known user is required"},
        status.HTTP_403_FORBIDDEN: {"description": "Role lacks the reports:export permission"},
    },
)
def export_report_endpoint(
    report_format: ReportFormat = Query(default=ReportFormat.CSV, alias="format", description="csv or pdf"),
    window_days: Optional[int] = Query(default=None, ge=1, le=365, description="Only include the last N days; omit for all time"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission(Permission.REPORTS_EXPORT)),
) -> Response:
    """Generates the report and returns it as an attachment."""
    report = export_report(db, principal, report_format, window_days=window_days)
    return Response(
        content=report.content,
        media_type=report.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{report.filename}"',
            "Cache-Control": "no-store",
        },
    )
