from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.lead import Lead, LeadChannel, LeadSource, LeadStage
from app.services.phone_utils import clean_phone_number

logger = logging.getLogger(__name__)

GRAPH_LEAD_FIELDS = "field_data,platform,campaign_name,created_time,id"
GRAPH_FORM_FIELDS = "id,name"
GRAPH_FORM_LEAD_FIELDS = "id,created_time,ad_id,form_id"
GRAPH_PAGE_LIMIT = 100
DEFAULT_BACKFILL_DELAY_SECONDS = 1.0
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
META_GRAPH_API_BASE = "https://graph.facebook.com/v20.0"


@dataclass(frozen=True)
class LeadgenWebhookEvent:
    leadgen_id: str
    page_id: str | None
    form_id: str | None
    ad_id: str | None
    adgroup_id: str | None
    created_time: int | None
    raw_value: dict[str, Any]


@dataclass
class MetaLeadsBackfillResult:
    forms_processed: int = 0
    leads_seen: int = 0
    leads_created: int = 0
    leads_skipped: int = 0
    errors: list[str] = field(default_factory=list)
    delta_since_unix: str | None = None
    delta_since_label: str | None = None
    delta_is_initial_backfill: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "forms_processed": self.forms_processed,
            "leads_seen": self.leads_seen,
            "leads_created": self.leads_created,
            "leads_skipped": self.leads_skipped,
            "errors": self.errors,
            "delta_since_unix": self.delta_since_unix,
            "delta_since_label": self.delta_since_label,
            "delta_is_initial_backfill": self.delta_is_initial_backfill,
        }


def resolve_backfill_credentials(
    *,
    page_id: str | None = None,
    access_token: str | None = None,
) -> tuple[str, str]:
    resolved_page_id = (page_id or getattr(settings, "META_PAGE_ID", None) or "").strip()
    resolved_token = (access_token or _resolve_graph_access_token()).strip()

    if not resolved_page_id:
        raise ValueError("page_id is required (pass in request body or set META_PAGE_ID).")
    if not resolved_token:
        raise ValueError(
            "access_token is required (pass in request body or set META_GRAPH_ACCESS_TOKEN)."
        )
    return resolved_page_id, resolved_token


def _resolve_graph_access_token() -> str:
    for value in (
        getattr(settings, "META_GRAPH_ACCESS_TOKEN", None),
        settings.WHATSAPP_ACCESS_TOKEN,
    ):
        token = (value or "").strip()
        if token:
            return token
    return ""


def extract_leadgen_events(payload: dict[str, Any]) -> list[LeadgenWebhookEvent]:
    """Parse Meta leadgen webhook notifications (Facebook + Instagram Lead Ads)."""
    events: list[LeadgenWebhookEvent] = []

    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        page_id = str(entry.get("id") or "").strip() or None

        for change in entry.get("changes") or []:
            if not isinstance(change, dict):
                continue
            if str(change.get("field") or "").strip().lower() != "leadgen":
                continue

            value = change.get("value") or {}
            if not isinstance(value, dict):
                continue

            leadgen_id = str(value.get("leadgen_id") or "").strip()
            if not leadgen_id:
                logger.warning("Meta leadgen webhook missing leadgen_id: %s", value)
                continue

            created_raw = value.get("created_time")
            created_time: int | None
            try:
                created_time = int(created_raw) if created_raw is not None else None
            except (TypeError, ValueError):
                created_time = None

            events.append(
                LeadgenWebhookEvent(
                    leadgen_id=leadgen_id,
                    page_id=page_id,
                    form_id=_optional_str(value.get("form_id")),
                    ad_id=_optional_str(value.get("ad_id")),
                    adgroup_id=_optional_str(value.get("adgroup_id")),
                    created_time=created_time,
                    raw_value=value,
                )
            )

    return events


def fetch_leadgen_details(leadgen_id: str, *, access_token: str | None = None) -> dict[str, Any]:
    """Fetch lead details from Meta Graph API (/{leadgen_id})."""
    token = (access_token or _resolve_graph_access_token()).strip()
    if not token:
        raise RuntimeError("META_GRAPH_ACCESS_TOKEN or WHATSAPP_ACCESS_TOKEN is not configured.")

    url = f"{META_GRAPH_API_BASE}/{leadgen_id}"
    params = {"fields": GRAPH_LEAD_FIELDS, "access_token": token}

    with httpx.Client(timeout=20.0) as client:
        response = client.get(url, params=params)
        if response.status_code >= 400:
            raise RuntimeError(
                f"Meta Graph lead fetch failed ({response.status_code}): {response.text}"
            )
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("Meta Graph lead fetch returned non-object JSON.")
        return data


def _graph_get_json(url: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
    with httpx.Client(timeout=30.0) as client:
        response = client.get(url, params=params)
        if response.status_code >= 400:
            raise RuntimeError(_format_graph_http_error(response.status_code, response.text))
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("Meta Graph request returned non-object JSON.")
        return data


def _format_graph_http_error(status_code: int, body: str) -> str:
    from app.services.lead_sync_errors import META_RATE_LIMIT_USER_MESSAGE, is_meta_rate_limit_error

    raw = f"Meta Graph request failed ({status_code}): {body}"
    if is_meta_rate_limit_error(raw):
        return META_RATE_LIMIT_USER_MESSAGE
    return raw


def _append_preflight_finding(findings: list[str], message: str) -> bool:
    """Append a finding; return True when Meta rate-limit means stop further Graph calls."""
    from app.services.lead_sync_errors import (
        META_RATE_LIMIT_USER_MESSAGE,
        is_meta_rate_limit_error,
    )

    if is_meta_rate_limit_error(message):
        if META_RATE_LIMIT_USER_MESSAGE not in findings:
            findings.append(META_RATE_LIMIT_USER_MESSAGE)
        return True
    findings.append(message)
    return False


META_LEADS_REQUIRED_SCOPES = (
    "leads_retrieval",
    "pages_read_engagement",
    "pages_show_list",
)


def diagnose_meta_leads_access(
    page_id: str,
    access_token: str,
) -> list[str]:
    """
    Pre-flight checks for Meta Lead Ads backfill.

    Returns a list of human-readable findings (empty means basic checks passed).
    Stops early on Meta rate-limit (#4) so we do not burn more Graph quota.
    """
    findings: list[str] = []
    token = access_token.strip()
    page = page_id.strip()

    try:
        debug_payload = _graph_get_json(
            f"{META_GRAPH_API_BASE}/debug_token",
            params={"input_token": token, "access_token": token},
        )
    except RuntimeError as exc:
        _append_preflight_finding(findings, f"Token validation failed: {exc}")
        return findings

    debug_data = (debug_payload.get("data") or {}) if isinstance(debug_payload, dict) else {}
    if not debug_data.get("is_valid"):
        findings.append("Access token is invalid or expired.")
        return findings

    token_type = str(debug_data.get("type") or "unknown")
    scopes = set(debug_data.get("scopes") or [])
    missing_scopes = [scope for scope in META_LEADS_REQUIRED_SCOPES if scope not in scopes]
    if missing_scopes:
        findings.append(
            "Token is missing required permissions: "
            + ", ".join(missing_scopes)
            + f". Current token type: {token_type}. "
            "WhatsApp-only System User tokens cannot read Facebook Lead Ads."
        )

    try:
        page_token = resolve_page_access_token(page, token)
        _graph_get_json(
            f"{META_GRAPH_API_BASE}/{page}/leadgen_forms",
            params={"fields": "id", "limit": 1, "access_token": page_token},
        )
    except RuntimeError as exc:
        if _append_preflight_finding(
            findings,
            f"Leadgen API check failed for Facebook Page {page}: {exc}. "
            "Lead Ads endpoints require a Page Access Token derived from your System User token. "
            "Verify META_PAGE_ID is the Facebook Page ID (not the WhatsApp Business Account ID) "
            "and that this Page is assigned to your System User in Meta Business Manager.",
        ):
            return findings
        _append_accessible_pages_hint(findings, page, token)

    return findings


def _append_accessible_pages_hint(findings: list[str], page: str, token: str) -> None:
    """
    Best-effort diagnostic listing Pages the token can reach.

    Uses the app-level /me/accounts endpoint, so it only runs after a real
    failure — never on the happy path where it would waste app-level quota.
    """
    try:
        accounts_payload = _graph_get_json(
            f"{META_GRAPH_API_BASE}/me/accounts",
            params={"fields": "id,name", "access_token": token, "limit": 25},
        )
    except RuntimeError:
        return

    pages = accounts_payload.get("data") or []
    if not isinstance(pages, list):
        return

    if not pages:
        findings.append(
            "Token has no accessible Facebook Pages (/me/accounts is empty). "
            "Assign the Page asset to your System User, then regenerate the token."
        )
        return

    page_ids = {str(item.get("id")) for item in pages if isinstance(item, dict)}
    if page in page_ids:
        return

    available = ", ".join(
        f"{item.get('name')} ({item.get('id')})"
        for item in pages
        if isinstance(item, dict) and item.get("id")
    )
    findings.append(
        f"Page {page} is not in the token's accessible pages. Available: {available or 'none'}."
    )


_PAGE_TOKEN_CACHE_TTL_SECONDS = 900
_page_token_cache: dict[str, tuple[str, float]] = {}
_page_token_cache_lock = threading.Lock()


def resolve_page_access_token(page_id: str, access_token: str) -> str:
    """
    Obtain a Page Access Token for leadgen APIs.

    Meta requires a Page token (not a bare System User token) for
    /{page_id}/leadgen_forms and /{form_id}/leads.

    Resolves via the page-scoped edge first. /me/accounts counts against the
    app-level rate limit, which a low-traffic app exhausts quickly and which
    returns "(#4) Application request limit reached" even while page-scoped
    (business use case) quota is untouched.
    """
    page = page_id.strip()
    token = access_token.strip()
    if not page or not token:
        raise RuntimeError("page_id and access_token are required to resolve a Page Access Token.")

    cache_key = f"{page}:{token[-12:]}"
    now = time.monotonic()
    with _page_token_cache_lock:
        cached = _page_token_cache.get(cache_key)
        if cached and cached[1] > now:
            return cached[0]

    page_token: str | None = None
    page_scoped_error: RuntimeError | None = None
    try:
        page_payload = _graph_get_json(
            f"{META_GRAPH_API_BASE}/{page}",
            params={"fields": "access_token", "access_token": token},
        )
        page_token = _optional_str(page_payload.get("access_token"))
    except RuntimeError as exc:
        page_scoped_error = exc

    if not page_token:
        try:
            accounts_payload = _graph_get_json(
                f"{META_GRAPH_API_BASE}/me/accounts",
                params={"fields": "id,access_token", "access_token": token, "limit": 100},
            )
        except RuntimeError as exc:
            raise page_scoped_error or exc
        for item in accounts_payload.get("data") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("id") or "").strip() != page:
                continue
            page_token = _optional_str(item.get("access_token"))
            if page_token:
                break

    if not page_token:
        if page_scoped_error is not None:
            raise page_scoped_error
        raise RuntimeError(
            f"Could not obtain a Page Access Token for page_id={page}. "
            "Assign the Page to your System User in Business Manager, then regenerate the token."
        )

    with _page_token_cache_lock:
        _page_token_cache[cache_key] = (page_token, now + _PAGE_TOKEN_CACHE_TTL_SECONDS)
    return page_token


def _iter_graph_paginated(
    path: str,
    *,
    access_token: str,
    params: dict[str, Any] | None = None,
    request_delay_seconds: float = 0.0,
) -> Iterator[dict[str, Any]]:
    """Yield each object from data[] across all Graph API pages."""
    next_url = f"{META_GRAPH_API_BASE}/{path.lstrip('/')}"
    next_params: dict[str, Any] | None = dict(params or {})
    next_params.setdefault("limit", GRAPH_PAGE_LIMIT)
    next_params["access_token"] = access_token

    while next_url:
        if request_delay_seconds > 0:
            time.sleep(request_delay_seconds)

        payload = _graph_get_json(next_url, params=next_params)
        rows = payload.get("data") or []
        if not isinstance(rows, list):
            raise RuntimeError("Meta Graph pagination payload missing data[] list.")

        for row in rows:
            if isinstance(row, dict):
                yield row

        paging = payload.get("paging") or {}
        if not isinstance(paging, dict):
            break
        next_url = _optional_str(paging.get("next"))
        next_params = None


def fetch_leadgen_form_ids(
    page_id: str,
    access_token: str,
    *,
    request_delay_seconds: float = DEFAULT_BACKFILL_DELAY_SECONDS,
) -> list[str]:
    """Return all leadgen form IDs attached to a Facebook Page."""
    form_ids: list[str] = []
    for form in _iter_graph_paginated(
        f"{page_id}/leadgen_forms",
        access_token=access_token,
        params={"fields": GRAPH_FORM_FIELDS},
        request_delay_seconds=request_delay_seconds,
    ):
        form_id = _optional_str(form.get("id"))
        if form_id:
            form_ids.append(form_id)
    return form_ids


def build_meta_lead_time_filter(
    since_unix: str | int | None = None,
    until_unix: str | int | None = None,
) -> list[dict[str, Any]] | None:
    """
    Build Meta Graph ``filtering`` clauses for lead ``time_created``.

    The ``since`` query param is ignored on ``/{form_id}/leads``; Meta requires
    ``filtering`` with ``time_created`` for delta reads.
    """
    filters: list[dict[str, Any]] = []
    if since_unix is not None:
        filters.append(
            {
                "field": "time_created",
                "operator": "GREATER_THAN",
                "value": int(since_unix),
            }
        )
    if until_unix is not None:
        filters.append(
            {
                "field": "time_created",
                "operator": "LESS_THAN",
                "value": int(until_unix),
            }
        )
    return filters or None


def iter_form_leads(
    form_id: str,
    access_token: str,
    *,
    since: str | None = None,
    until: str | None = None,
    request_delay_seconds: float = DEFAULT_BACKFILL_DELAY_SECONDS,
) -> Iterator[dict[str, Any]]:
    """Yield historical lead summaries for a leadgen form (paginated)."""
    params: dict[str, Any] = {"fields": GRAPH_FORM_LEAD_FIELDS}
    filters = build_meta_lead_time_filter(since, until)
    if filters:
        params["filtering"] = json.dumps(filters)
        logger.info(
            "Meta delta fetch form_id=%s filtering=%s",
            form_id,
            params["filtering"],
        )

    yield from _iter_graph_paginated(
        f"{form_id}/leads",
        access_token=access_token,
        params=params,
        request_delay_seconds=request_delay_seconds,
    )


def _lead_summary_to_event(
    lead_summary: dict[str, Any],
    *,
    page_id: str,
    form_id: str,
) -> LeadgenWebhookEvent | None:
    leadgen_id = _optional_str(lead_summary.get("id"))
    if not leadgen_id:
        return None

    return LeadgenWebhookEvent(
        leadgen_id=leadgen_id,
        page_id=page_id,
        form_id=_optional_str(lead_summary.get("form_id")) or form_id,
        ad_id=_optional_str(lead_summary.get("ad_id")),
        adgroup_id=None,
        created_time=_parse_created_time(lead_summary.get("created_time")),
        raw_value=lead_summary,
    )


def backfill_historical_leads(
    db: Session,
    page_id: str,
    access_token: str,
    *,
    since: str | None = None,
    until: str | None = None,
    request_delay_seconds: float = DEFAULT_BACKFILL_DELAY_SECONDS,
    delta_since_label: str | None = None,
    delta_is_initial_backfill: bool = False,
    sync_mode: str = "AUTOMATED",
    triggered_by_user: str = "SYSTEM_SCHEDULER",
    triggered_by_user_id: int | None = None,
    source: str = "scheduled",
    sync_log_id: int | None = None,
) -> MetaLeadsBackfillResult:
    """
    Delta sync of Meta Lead Ads for a Page.

    Lists all leadgen forms on the page, fetches paginated leads per form, and
    ingests each new lead. When ``since`` is set, applies Graph API ``filtering``
    on ``time_created`` (``GREATER_THAN`` unix timestamp).
    """
    result = MetaLeadsBackfillResult(
        delta_since_unix=since,
        delta_since_label=delta_since_label,
        delta_is_initial_backfill=delta_is_initial_backfill,
    )
    token = access_token.strip()
    if not token:
        raise ValueError("access_token is required for historical Meta lead sync.")

    preflight = diagnose_meta_leads_access(page_id, token)
    if preflight:
        for message in preflight:
            logger.error("Meta backfill preflight: %s", message)
        result.errors.extend(preflight)
        return result

    try:
        page_token = resolve_page_access_token(page_id, token)
    except Exception as exc:
        logger.exception("Failed to resolve Page Access Token for page_id=%s", page_id)
        result.errors.append(f"page_access_token: {exc}")
        return result

    try:
        form_ids = fetch_leadgen_form_ids(
            page_id,
            page_token,
            request_delay_seconds=request_delay_seconds,
        )
    except Exception as exc:
        logger.exception("Failed to list leadgen forms for page_id=%s", page_id)
        result.errors.append(f"leadgen_forms: {exc}")
        return result

    if not form_ids:
        logger.warning(
            "No leadgen forms returned for page_id=%s (check Page token + leads_retrieval permission).",
            page_id,
        )
        return result

    logger.info(
        "Meta delta sync page_id=%s since=%s (%s) initial_backfill=%s",
        page_id,
        since or "none",
        delta_since_label or "unbounded",
        delta_is_initial_backfill,
    )

    for form_id in form_ids:
        result.forms_processed += 1
        try:
            for lead_summary in iter_form_leads(
                form_id,
                page_token,
                since=since,
                until=until,
                request_delay_seconds=request_delay_seconds,
            ):
                event = _lead_summary_to_event(
                    lead_summary,
                    page_id=page_id,
                    form_id=form_id,
                )
                if event is None:
                    continue

                result.leads_seen += 1
                try:
                    from app.services.leads import (
                        format_lead_ingestion_error,
                        ingest_meta_leadgen_event_sync,
                    )

                    if request_delay_seconds > 0:
                        time.sleep(request_delay_seconds)

                    stage_result = ingest_meta_leadgen_event_sync(
                        event,
                        access_token=page_token,
                        sync_mode=sync_mode,
                        triggered_by_user=triggered_by_user,
                        triggered_by_user_id=triggered_by_user_id,
                        source=source,
                        sync_log_id=sync_log_id,
                    )
                    if stage_result is None:
                        result.errors.append(
                            format_lead_ingestion_error(
                                event.leadgen_id,
                                RuntimeError("Lead staging failed"),
                            )
                        )
                        continue
                    if stage_result.created:
                        result.leads_created += 1
                    elif stage_result.skipped:
                        result.leads_skipped += 1
                except Exception as exc:
                    logger.exception(
                        "Failed to backfill Meta leadgen_id=%s form_id=%s",
                        event.leadgen_id,
                        form_id,
                    )
                    from app.services.leads import format_lead_ingestion_error

                    result.errors.append(format_lead_ingestion_error(event.leadgen_id, exc))
        except Exception as exc:
            db.rollback()
            logger.exception("Failed to fetch leads for form_id=%s", form_id)
            result.errors.append(f"form {form_id}: {exc}")

    logger.info(
        "Meta historical backfill complete page_id=%s forms=%s seen=%s created=%s skipped=%s errors=%s",
        page_id,
        result.forms_processed,
        result.leads_seen,
        result.leads_created,
        result.leads_skipped,
        len(result.errors),
    )
    return result


def map_platform_to_source(platform: str | None) -> LeadSource:
    normalized = (platform or "").strip().lower()
    if normalized == "instagram":
        return LeadSource.INSTAGRAM_LEAD
    if normalized in {"facebook", "fb"}:
        return LeadSource.FACEBOOK_LEAD
    # Meta occasionally omits platform; default to Facebook Lead Ads.
    return LeadSource.FACEBOOK_LEAD


def map_platform_to_channel(platform: str | None) -> LeadChannel:
    normalized = (platform or "").strip().lower()
    if normalized == "instagram":
        return LeadChannel.INSTAGRAM
    return LeadChannel.FACEBOOK


def sync_meta_leads(
    db: Session,
    event: LeadgenWebhookEvent,
    *,
    access_token: str | None = None,
    sync_mode: str = "AUTOMATED",
    triggered_by_user: str = "SYSTEM_SCHEDULER",
    source: str = "scheduled",
) -> Lead | None:
    """
    Fetch a Meta leadgen record and stage it for async processing.

    Returns an existing Lead when the leadgen id was already handled; otherwise None
    until the background processor promotes the staged row.
    """
    from app.models.lead import Lead
    from app.services.lead_ingestion_pipeline import raw_leadgen_already_handled
    from app.services.leads import ingest_meta_leadgen_event

    if raw_leadgen_already_handled(db, event.leadgen_id):
        return db.query(Lead).filter(Lead.meta_leadgen_id == event.leadgen_id).first()

    try:
        ingest_meta_leadgen_event(
            db,
            event,
            access_token=access_token,
            sync_mode=sync_mode,
            triggered_by_user=triggered_by_user,
            source=source,
        )
        return None
    except Exception:
        logger.exception("Failed to stage Meta leadgen_id=%s", event.leadgen_id)
        db.rollback()
        return None


def process_meta_leadgen_webhook(db: Session, payload: dict[str, Any]) -> int:
    """Process all leadgen events in a Meta webhook payload. Returns count ingested."""
    from app.services.leads import process_meta_leadgen_webhook as ingest_webhook

    return ingest_webhook(db, payload)


def _parse_field_data(field_data: Any) -> dict[str, str]:
    if not isinstance(field_data, list):
        return {}

    parsed: dict[str, str] = {}
    for item in field_data:
        if not isinstance(item, dict):
            continue
        name = _optional_str(item.get("name"))
        if not name:
            continue
        values = item.get("values")
        if isinstance(values, list) and values:
            value = _optional_str(values[0])
        else:
            value = _optional_str(item.get("value"))
        if value:
            parsed[name.lower()] = value
    return parsed


def _pick_field(fields: dict[str, str], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = fields.get(key)
        if value:
            return value
    return None


def _normalize_email(value: str | None) -> str | None:
    cleaned = (value or "").strip().lower()
    if not cleaned or not EMAIL_PATTERN.match(cleaned):
        return None
    return cleaned


def _normalize_phone(value: str | None) -> str | None:
    cleaned = clean_phone_number(value or "")
    return cleaned or None


def _parse_created_time(value: Any) -> int | None:
    """Parse Meta created_time values (Unix int or ISO-8601 string) to UTC epoch seconds."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        if cleaned.isdigit():
            return int(cleaned)
        normalized = cleaned.replace("Z", "+00:00")
        if normalized.endswith("+0000"):
            normalized = f"{normalized[:-5]}+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            else:
                parsed = parsed.astimezone(timezone.utc)
            return int(parsed.timestamp())
        except ValueError:
            return None
    return None


def meta_created_time_to_utc_naive(value: Any) -> datetime | None:
    """Convert Meta created_time to a naive UTC datetime for DB storage."""
    epoch = _parse_created_time(value)
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc).replace(tzinfo=None)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


# Public alias requested in product docs / older integrations.
sync_facebook_leads = sync_meta_leads
