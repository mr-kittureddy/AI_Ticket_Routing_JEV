from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.timeutil import ensure_utc
from app.db.models import Ticket, utc_now
from app.schemas.analytics import AnalyticsResponse, AnalyticsSummary, ReportFormat
from app.services.analytics_service import build_analytics
from app.services.audit_service import AuditAction, AuditEntity, record_audit_for_principal
from app.services.rbac import Principal

logger = get_logger(__name__)

MAX_CSV_TICKETS = 5000
MAX_PDF_TICKETS = 500
REPORT_TITLE = "IT Support Ticket AI Routing Report"

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

TICKET_HEADERS = [
    "Ticket ID",
    "Submitted by",
    "Team",
    "Status",
    "Human action",
    "JEV confidence",
    "JEV latency (ms)",
    "Gemini time (ms)",
    "Assigned queue",
    "Created (UTC)",
]
TEAM_HEADERS = ["Team", "Total", "Auto-resolved", "Assigned to human", "Avg JEV latency (ms)"]

# Column widths in millimetres; they sum to the 273 mm usable width of a landscape A4 page with 12 mm margins.
_PDF_TICKET_COL_WIDTHS_MM = [24, 48, 28, 32, 16, 16, 18, 20, 44, 27]


@dataclass(frozen=True)
class ReportFile:
    """A generated report ready to be streamed to the client."""

    content: bytes
    media_type: str
    filename: str


def _safe_cell(value: object) -> object:
    """Prefixes text that a spreadsheet could interpret as a formula, preventing CSV injection."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def _format_dt(value: datetime) -> str:
    return ensure_utc(value).strftime("%Y-%m-%d %H:%M:%S")


def _window_label(window_days: Optional[int]) -> str:
    return "All time" if window_days is None else f"Last {window_days} days"


def _summary_rows(summary: AnalyticsSummary) -> list[tuple[str, str]]:
    avg_gemini = "n/a" if summary.avg_gemini_latency_ms is None else f"{summary.avg_gemini_latency_ms:.2f} ms"
    return [
        ("Total tickets", str(summary.total_tickets)),
        ("Auto-resolved tickets", str(summary.auto_resolved_count)),
        ("Assigned to human (Gemini bypassed)", str(summary.assigned_to_human_count)),
        ("Gemini bypass rate", f"{summary.gemini_bypass_rate:.1%}"),
        ("Average JEV latency", f"{summary.avg_jev_latency_ms:.2f} ms"),
        ("P50 JEV latency", f"{summary.p50_jev_latency_ms:.0f} ms"),
        ("P95 JEV latency", f"{summary.p95_jev_latency_ms:.0f} ms"),
        ("JEV latency threshold", f"{summary.jev_threshold_ms} ms"),
        ("JEV within threshold", f"{summary.jev_within_threshold_rate:.1%}"),
        ("Average Gemini latency", avg_gemini),
        ("Average JEV confidence", f"{summary.avg_confidence:.2f}"),
        ("Estimated time saved", f"{summary.total_time_saved_ms} ms"),
        ("Estimated cost saved", f"${summary.total_cost_saved_usd:.4f}"),
    ]


def _team_rows(analytics: AnalyticsResponse) -> list[list[object]]:
    return [
        [
            item.team.value,
            item.total,
            item.auto_resolved,
            item.assigned_to_human,
            f"{item.avg_jev_latency_ms:.2f}",
        ]
        for item in analytics.team_breakdown
    ]


def _fetch_tickets(db: Session, window_days: Optional[int], limit: int) -> list[Ticket]:
    stmt = select(Ticket).order_by(Ticket.created_at.desc(), Ticket.id.desc()).limit(limit)
    if window_days is not None:
        stmt = stmt.where(Ticket.created_at >= utc_now() - timedelta(days=window_days))
    return list(db.scalars(stmt).all())


def _ticket_cells(ticket: Ticket) -> list[object]:
    return [
        ticket.ticket_id,
        ticket.submitted_by,
        ticket.target_team.value,
        ticket.status.value,
        "true" if ticket.requires_human_action else "false",
        f"{ticket.confidence_score:.2f}",
        ticket.jev_latency_ms,
        "" if ticket.gemini_execution_time_ms is None else ticket.gemini_execution_time_ms,
        ticket.assigned_queue or "",
        _format_dt(ticket.created_at),
    ]


def _build_csv(analytics: AnalyticsResponse, tickets: list[Ticket]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")

    writer.writerow([REPORT_TITLE])
    writer.writerow(["Generated at (UTC)", _format_dt(analytics.generated_at)])
    writer.writerow(["Window", _window_label(analytics.window_days)])
    writer.writerow([])

    writer.writerow(["Metric", "Value"])
    for label, value in _summary_rows(analytics.summary):
        writer.writerow([_safe_cell(label), _safe_cell(value)])
    writer.writerow([])

    writer.writerow(TEAM_HEADERS)
    for row in _team_rows(analytics):
        writer.writerow([_safe_cell(cell) for cell in row])
    writer.writerow([])

    writer.writerow(TICKET_HEADERS)
    for ticket in tickets:
        writer.writerow([_safe_cell(cell) for cell in _ticket_cells(ticket)])

    # UTF-8 with BOM so Excel detects the encoding.
    return buffer.getvalue().encode("utf-8-sig")


def _pdf_text(value: object) -> str:
    """Escapes markup and replaces characters the built-in Helvetica font cannot encode."""
    text = str(value).encode("cp1252", errors="replace").decode("cp1252")
    return escape(text)


def _build_pdf(analytics: AnalyticsResponse, tickets: list[Ticket], limit_reached: bool) -> bytes:
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=REPORT_TITLE,
        author="IT Support Ticket AI Routing Engine",
    )

    styles = getSampleStyleSheet()
    cell_style = ParagraphStyle("ReportCell", parent=styles["BodyText"], fontSize=7.5, leading=9)
    head_style = ParagraphStyle(
        "ReportHead", parent=cell_style, fontName="Helvetica-Bold", textColor=colors.white
    )

    def cell(value: object) -> Paragraph:
        return Paragraph(_pdf_text(value), cell_style)

    def head(value: object) -> Paragraph:
        return Paragraph(_pdf_text(value), head_style)

    def grid_style() -> TableStyle:
        return TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )

    story: list = [
        Paragraph(_pdf_text(REPORT_TITLE), styles["Title"]),
        Paragraph(
            _pdf_text(
                f"Generated {_format_dt(analytics.generated_at)} UTC | Window: {_window_label(analytics.window_days)}"
            ),
            styles["Normal"],
        ),
        Spacer(1, 6 * mm),
        Paragraph("Performance summary", styles["Heading2"]),
    ]

    summary_data = [[head("Metric"), head("Value")]]
    summary_data.extend([[cell(label), cell(value)] for label, value in _summary_rows(analytics.summary)])
    summary_table = Table(summary_data, colWidths=[80 * mm, 45 * mm], hAlign="LEFT", repeatRows=1)
    summary_table.setStyle(grid_style())
    story.extend([summary_table, Spacer(1, 6 * mm), Paragraph("Team breakdown", styles["Heading2"])])

    team_data = [[head(title) for title in TEAM_HEADERS]]
    team_data.extend([[cell(value) for value in row] for row in _team_rows(analytics)])
    team_table = Table(team_data, colWidths=[45 * mm, 25 * mm, 35 * mm, 40 * mm, 45 * mm], hAlign="LEFT", repeatRows=1)
    team_table.setStyle(grid_style())
    story.extend([team_table, Spacer(1, 6 * mm), Paragraph("Tickets", styles["Heading2"])])

    if not tickets:
        story.append(Paragraph("No tickets were processed in this window.", styles["Normal"]))
    else:
        if limit_reached:
            story.append(
                Paragraph(
                    _pdf_text(
                        f"Showing the {len(tickets)} most recent tickets. Export the CSV report for a larger extract."
                    ),
                    styles["Italic"],
                )
            )
            story.append(Spacer(1, 2 * mm))
        ticket_data = [[head(title) for title in TICKET_HEADERS]]
        ticket_data.extend([[cell(value) for value in _ticket_cells(ticket)] for ticket in tickets])
        ticket_table = Table(
            ticket_data,
            colWidths=[width * mm for width in _PDF_TICKET_COL_WIDTHS_MM],
            hAlign="LEFT",
            repeatRows=1,
        )
        ticket_table.setStyle(grid_style())
        story.append(ticket_table)

    document.build(story)
    return buffer.getvalue()


def export_report(
    db: Session,
    principal: Principal,
    fmt: ReportFormat,
    window_days: Optional[int] = None,
) -> ReportFile:
    """Builds a CSV or PDF report for the window and records the export in the audit trail."""
    analytics = build_analytics(db, window_days, series_limit=1)
    limit = MAX_PDF_TICKETS if fmt == ReportFormat.PDF else MAX_CSV_TICKETS
    tickets = _fetch_tickets(db, window_days, limit)

    if fmt == ReportFormat.CSV:
        content = _build_csv(analytics, tickets)
        media_type = "text/csv; charset=utf-8"
    else:
        content = _build_pdf(analytics, tickets, limit_reached=len(tickets) >= limit)
        media_type = "application/pdf"

    stamp = ensure_utc(analytics.generated_at).strftime("%Y%m%d-%H%M%S")
    filename = f"ticket-routing-report-{stamp}.{fmt.value}"

    record_audit_for_principal(
        db,
        principal,
        action=AuditAction.REPORT_EXPORTED,
        entity_type=AuditEntity.REPORT,
        entity_id=filename,
        details={
            "format": fmt,
            "window_days": window_days,
            "ticket_rows": len(tickets),
            "size_bytes": len(content),
        },
    )
    db.commit()
    return ReportFile(content=content, media_type=media_type, filename=filename)
