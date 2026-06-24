from __future__ import annotations

import io
import time
from datetime import datetime
from typing import Literal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.schemas.sync_log import SyncLogOut
from app.services.business_profile_service import DEFAULT_BUSINESS_ID, get_business_profile

_BUSINESS_NAME_CACHE: tuple[str, float] | None = None
_BUSINESS_NAME_CACHE_TTL_SECONDS = 300

_PAGE_SIZE = landscape(A4)
_PAGE_WIDTH, _PAGE_HEIGHT = _PAGE_SIZE
_MARGIN = 0.55 * inch
_FOOTER_Y = 0.42 * inch


class _NumberedCanvas(canvas.Canvas):
    """Two-pass canvas so footers can show 'Page X of Y'."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._page_states: list[dict] = []

    def showPage(self) -> None:
        self._page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total_pages = len(self._page_states)
        for state in self._page_states:
            self.__dict__.update(state)
            self._draw_footer(total_pages)
            super().showPage()
        super().save()

    def _draw_footer(self, total_pages: int) -> None:
        self.saveState()
        self.setFont("Helvetica", 9)
        self.setFillColor(colors.HexColor("#64748b"))
        self.drawCentredString(
            _PAGE_WIDTH / 2,
            _FOOTER_Y,
            f"Page {self._pageNumber} of {total_pages}",
        )
        self.restoreState()


def _cached_business_name(db: Session) -> str:
    global _BUSINESS_NAME_CACHE
    now = time.monotonic()
    if (
        _BUSINESS_NAME_CACHE is not None
        and now - _BUSINESS_NAME_CACHE[1] < _BUSINESS_NAME_CACHE_TTL_SECONDS
    ):
        return _BUSINESS_NAME_CACHE[0]

    profile = get_business_profile(db, DEFAULT_BUSINESS_ID)
    name = (profile.get("business_name") or "NEXUS").strip() or "NEXUS"
    _BUSINESS_NAME_CACHE = (name, now)
    return name


def _format_range_label(start_date: datetime | None, end_date: datetime | None) -> str:
    if start_date and end_date:
        return f"{start_date.date().isoformat()} to {end_date.date().isoformat()}"
    if start_date:
        return f"From {start_date.date().isoformat()}"
    if end_date:
        return f"Through {end_date.date().isoformat()}"
    return "All available records"


def _format_timestamp(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.strftime("%Y-%m-%d %H:%M:%S UTC")


def _format_sync_mode(mode: str) -> str:
    normalized = (mode or "").strip().upper()
    if normalized == "AUTOMATED":
        return "Scheduled"
    if normalized == "MANUAL":
        return "Manual"
    return mode or "—"


def _format_source(source: str) -> str:
    normalized = (source or "").strip().lower()
    mapping = {
        "scheduled": "Scheduler",
        "manual_api": "Settings",
        "webhook": "Webhook",
        "backfill": "Backfill",
    }
    return mapping.get(normalized, source or "—")


def _truncate(text: str | None, *, max_len: int = 120) -> str:
    value = (text or "—").strip() or "—"
    if len(value) <= max_len:
        return value
    return value[: max_len - 1] + "…"


def _build_table_rows(logs: list[SyncLogOut]) -> list[list[str]]:
    rows: list[list[str]] = []
    for log in logs:
        rows.append(
            [
                _format_timestamp(log.attempt_timestamp),
                _format_sync_mode(log.sync_mode),
                _format_source(log.source),
                _truncate(log.triggered_by_user, max_len=28),
                (log.status or "—").upper(),
                str(log.leads_created),
                str(log.leads_seen),
                _truncate(log.message, max_len=90),
            ]
        )
    return rows


def generate_sync_logs_pdf(
    db: Session,
    *,
    logs: list[SyncLogOut],
    start_date: datetime | None,
    end_date: datetime | None,
    sort_by: str,
    sort_order: Literal["asc", "desc"],
    generated_at: datetime | None = None,
) -> bytes:
    """Build a professional PDF export for the full filtered sync-log dataset."""
    business_name = _cached_business_name(db)
    generated = generated_at or datetime.utcnow()
    range_label = _format_range_label(start_date, end_date)
    sort_label = f"{sort_by.replace('_', ' ')} ({sort_order.upper()})"

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=_PAGE_SIZE,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=_MARGIN,
        bottomMargin=0.75 * inch,
        title="Meta Lead Sync Logs",
        author=business_name,
        canvasmaker=_NumberedCanvas,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        textColor=colors.HexColor("#475569"),
        leading=14,
        spaceAfter=6,
    )
    meta_style = ParagraphStyle(
        "ReportMeta",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        textColor=colors.HexColor("#64748b"),
        leading=12,
    )

    story = [
        Paragraph(business_name, ParagraphStyle(
            "BusinessName",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            textColor=colors.HexColor("#334155"),
            spaceAfter=8,
        )),
        Paragraph("Meta Lead Sync Logs — Full Report", title_style),
        Paragraph(f"Report period: {range_label}", subtitle_style),
        Paragraph(
            f"Generated {generated.strftime('%Y-%m-%d %H:%M:%S UTC')} · "
            f"{len(logs):,} record{'s' if len(logs) != 1 else ''} · "
            f"Sorted by {sort_label}",
            meta_style,
        ),
        Spacer(1, 0.18 * inch),
    ]

    headers = [
        "Attempted",
        "Mode",
        "Source",
        "Triggered By",
        "Status",
        "New Leads",
        "Seen",
        "Message",
    ]
    table_data = [headers] + _build_table_rows(logs)

    col_widths = [
        1.05 * inch,
        0.72 * inch,
        0.72 * inch,
        1.05 * inch,
        0.68 * inch,
        0.58 * inch,
        0.48 * inch,
        3.35 * inch,
    ]

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#18181b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("FONTSIZE", (0, 1), (-1, -1), 7),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("ALIGN", (0, 0), (-1, 0), "LEFT"),
                ("ALIGN", (5, 1), (6, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(table)

    doc.build(story)
    return buffer.getvalue()
