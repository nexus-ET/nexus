from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, safe_close_session
from app.models.lead import Lead, LeadChannel, LeadStage
from app.services.lead_sync_errors import format_lead_sync_error
from app.services.facebook_leads import (
    LeadgenWebhookEvent,
    extract_leadgen_events,
    fetch_leadgen_details,
    map_platform_to_channel,
    map_platform_to_source,
    meta_created_time_to_utc_naive,
)

from app.services.sync_log_service import (
    SOURCE_WEBHOOK,
    SYNC_MODE_AUTOMATED,
    TRIGGERED_BY_WEBHOOK,
    begin_sync_transaction,
    fail_sync_transaction,
    finalize_sync_transaction,
)

FRESHEN_ON_CONFLICT = (
    "full_name",
    "email",
    "phone_number",
    "channel",
    "source",
    "meta_campaign_name",
    "meta_form_id",
    "meta_ad_id",
    "academic_summary",
    "additional_data",
    "preferred_country",
    "intake_context",
)

# Normalized keys reserved for top-level contact columns (excluded from additional_data).
_META_NAME_KEYS = frozenset({"full_name", "name", "first_name", "last_name"})
_META_EMAIL_KEYS = frozenset({"email", "email_address"})
_META_PHONE_KEYS = frozenset({"phone_number", "phone", "mobile", "phone_number_country_code"})

INITIAL_DELTA_LOOKBACK_DAYS = 30
INITIAL_DELTA_LOOKBACK_SECONDS = INITIAL_DELTA_LOOKBACK_DAYS * 86_400


@dataclass(frozen=True)
class DeltaSyncCursor:
    """Graph API ``since`` cursor derived from locally stored Meta leads."""

    since_unix: str
    since_label: str
    is_initial_backfill: bool


def _as_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def get_latest_meta_lead_created_at(db: Session) -> datetime | None:
    """Most recent ``created_at`` among Meta-imported leads (naive UTC in DB)."""
    return (
        db.query(func.max(Lead.created_at))
        .filter(Lead.meta_leadgen_id.isnot(None))
        .scalar()
    )


def resolve_delta_sync_cursor(db: Session) -> DeltaSyncCursor:
    """
    Build the Meta Graph ``since`` filter from local lead state.

    Uses the latest stored Meta lead timestamp for delta mode. When no Meta leads
    exist yet, falls back to the last 30 days for initial setup.
    """
    latest = get_latest_meta_lead_created_at(db)
    if latest is None:
        since_epoch = int(time.time()) - INITIAL_DELTA_LOOKBACK_SECONDS
        since_label = datetime.fromtimestamp(since_epoch, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
        return DeltaSyncCursor(
            since_unix=str(since_epoch),
            since_label=since_label,
            is_initial_backfill=True,
        )

    latest_utc = _as_utc_datetime(latest)
    since_epoch = int(latest_utc.timestamp())
    since_label = latest_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
    return DeltaSyncCursor(
        since_unix=str(since_epoch),
        since_label=since_label,
        is_initial_backfill=False,
    )


def format_no_new_leads_delta_message(since_label: str) -> str:
    return f"No new leads detected since {since_label}."


def normalize_meta_field_key(raw_key: str) -> str:
    """Convert Meta form labels to stable snake_case keys for JSON storage."""
    key = (raw_key or "").strip().lower()
    if key.startswith("your_"):
        key = key[5:]
    key = key.replace("?", "")
    key = re.sub(r"[^\w]+", "_", key)
    key = re.sub(r"_+", "_", key).strip("_")
    return key or "field"


def _field_data_value(item: dict[str, Any]) -> str | None:
    values = item.get("values")
    if isinstance(values, list) and values:
        value = _optional_str(values[0])
        if value:
            return value
    return _optional_str(item.get("value"))


def parse_meta_field_data(field_data: Any) -> dict[str, str]:
    """Parse Meta ``field_data`` array into normalized snake_case key/value pairs."""
    if not isinstance(field_data, list):
        return {}

    parsed: dict[str, str] = {}
    for item in field_data:
        if not isinstance(item, dict):
            continue
        raw_name = _optional_str(item.get("name"))
        if not raw_name:
            continue
        value = _field_data_value(item)
        if not value:
            continue
        parsed[normalize_meta_field_key(raw_name)] = value
    return parsed


def split_meta_contact_fields(
    normalized_fields: dict[str, str],
) -> tuple[str, str | None, str | None, dict[str, str]]:
    """
    Pull full_name, email, and phone into top-level columns.

    All remaining normalized form answers are returned as additional_data candidates.
    """
    remaining = dict(normalized_fields)

    full_name = (
        remaining.pop("full_name", None)
        or remaining.pop("name", None)
        or _combine_meta_name_parts(remaining)
    )
    email = None
    for key in _META_EMAIL_KEYS:
        if key in remaining:
            email = remaining.pop(key)
            break

    phone_number = None
    for key in _META_PHONE_KEYS:
        if key in remaining:
            phone_number = remaining.pop(key)
            break

    for reserved in _META_NAME_KEYS:
        remaining.pop(reserved, None)

    return (full_name or "Meta Lead", email, phone_number, remaining)


def _combine_meta_name_parts(fields: dict[str, str]) -> str | None:
    first = fields.get("first_name")
    last = fields.get("last_name")
    parts = [part for part in (first, last) if part]
    if not parts:
        return None
    for key in ("first_name", "last_name"):
        fields.pop(key, None)
    return " ".join(parts)


def _merge_additional_data(
    existing: dict[str, Any] | None,
    incoming: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not incoming:
        return existing
    if not existing:
        return dict(incoming)
    merged = dict(existing)
    merged.update(incoming)
    return merged


@dataclass(frozen=True)
class SaveLeadResult:
    lead: Lead
    created: bool


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _coerce_channel(value: Any) -> LeadChannel:
    if isinstance(value, LeadChannel):
        return value
    if isinstance(value, str):
        try:
            return LeadChannel[value.upper()]
        except KeyError:
            return LeadChannel(value)
    return LeadChannel.WHATSAPP


def _coerce_stage(value: Any) -> LeadStage:
    if isinstance(value, LeadStage):
        return value
    if isinstance(value, str):
        normalized = value.upper().replace("-", "_")
        return LeadStage(normalized)
    return LeadStage.AI_ACTIVE


def normalize_lead_row(lead_data: dict[str, Any]) -> dict[str, Any]:
    """Map inbound lead payloads to Lead table columns."""
    leadgen_id = (
        _optional_str(lead_data.get("leadgen_id"))
        or _optional_str(lead_data.get("meta_leadgen_id"))
    )
    if not leadgen_id:
        raise ValueError("leadgen_id is required for idempotent lead ingestion.")

    full_name = _optional_str(lead_data.get("full_name")) or "Meta Lead"
    email = _optional_str(lead_data.get("email"))
    if not email:
        email = f"meta_{leadgen_id}@meta.nexus"

    phone_number = _optional_str(lead_data.get("phone_number") or lead_data.get("phone"))
    channel = _coerce_channel(lead_data.get("channel", LeadChannel.FACEBOOK))
    stage = _coerce_stage(lead_data.get("stage", LeadStage.AI_ACTIVE))

    row: dict[str, Any] = {
        "full_name": full_name[:255],
        "email": email[:255],
        "phone_number": phone_number,
        "channel": channel,
        "source": _optional_str(lead_data.get("source")),
        "meta_leadgen_id": leadgen_id,
        "meta_campaign_name": _optional_str(lead_data.get("meta_campaign_name")),
        "meta_form_id": _optional_str(lead_data.get("meta_form_id")),
        "meta_ad_id": _optional_str(lead_data.get("meta_ad_id")),
        "stage": stage,
        "is_human_locked": bool(lead_data.get("is_human_locked", False)),
        "academic_summary": _optional_str(lead_data.get("academic_summary")),
    }
    additional_data = lead_data.get("additional_data")
    if isinstance(additional_data, dict) and additional_data:
        row["additional_data"] = additional_data
    preferred_country = _optional_str(lead_data.get("preferred_country"))
    if preferred_country:
        row["preferred_country"] = preferred_country
    intake_context = lead_data.get("intake_context")
    if isinstance(intake_context, str) and intake_context.strip():
        row["intake_context"] = intake_context.strip()
    created_at = lead_data.get("created_at")
    if isinstance(created_at, datetime):
        row["created_at"] = _as_utc_datetime(created_at).replace(tzinfo=None)
    return row


def _is_synthetic_meta_email(email: str | None) -> bool:
    if not email:
        return True
    return email.endswith("@meta.nexus") or email.startswith("meta_")


def _email_taken_by_other(db: Session, email: str, exclude_id: int | None) -> bool:
    query = db.query(Lead.id).filter(Lead.email == email)
    if exclude_id is not None:
        query = query.filter(Lead.id != exclude_id)
    return query.first() is not None


def _phone_taken_by_other(db: Session, phone: str | None, exclude_id: int | None) -> bool:
    if not phone:
        return False
    query = db.query(Lead.id).filter(Lead.phone_number == phone)
    if exclude_id is not None:
        query = query.filter(Lead.id != exclude_id)
    return query.first() is not None


def _freshen_lead(lead: Lead, row: dict[str, Any], db: Session) -> None:
    """Refresh Meta metadata without overwriting unique email/phone on another lead."""
    for key in FRESHEN_ON_CONFLICT:
        if key not in row:
            continue
        value = row[key]
        if key == "email":
            if _is_synthetic_meta_email(value) or value == lead.email:
                continue
            if _email_taken_by_other(db, value, lead.id):
                continue
        elif key == "phone_number":
            if not value or value == lead.phone_number:
                continue
            if _phone_taken_by_other(db, value, lead.id):
                continue
        elif key == "additional_data":
            if isinstance(value, dict):
                lead.additional_data = _merge_additional_data(lead.additional_data, value)
            continue
        setattr(lead, key, value)


def _maybe_attach_leadgen_id(lead: Lead, leadgen_id: str, db: Session) -> None:
    if lead.meta_leadgen_id:
        if lead.meta_leadgen_id != leadgen_id:
            logger.info(
                "save_lead kept existing leadgen_id=%s on lead_id=%s (incoming=%s)",
                lead.meta_leadgen_id,
                lead.id,
                leadgen_id,
            )
        return
    taken = (
        db.query(Lead.id)
        .filter(Lead.meta_leadgen_id == leadgen_id, Lead.id != lead.id)
        .first()
    )
    if taken:
        logger.warning(
            "save_lead meta_leadgen_id=%s already linked to lead_id=%s; skipped attach on lead_id=%s",
            leadgen_id,
            taken[0],
            lead.id,
        )
        return
    lead.meta_leadgen_id = leadgen_id


def _merge_existing_lead(
    db: Session,
    lead: Lead,
    row: dict[str, Any],
    leadgen_id: str,
    *,
    matched_by: str,
) -> SaveLeadResult:
    _maybe_attach_leadgen_id(lead, leadgen_id, db)
    _freshen_lead(lead, row, db)
    from app.services.lead_study_interest import hydrate_lead_study_interest

    hydrate_lead_study_interest(db, lead, commit=False)
    db.commit()
    db.refresh(lead)
    logger.info(
        "save_lead merged by %s leadgen_id=%s lead_id=%s",
        matched_by,
        leadgen_id,
        lead.id,
    )
    return SaveLeadResult(lead=lead, created=False)


def format_lead_ingestion_error(leadgen_id: str, exc: Exception) -> str:
    return format_lead_sync_error(leadgen_id, exc)


def save_lead(db: Session, lead_data: dict[str, Any]) -> SaveLeadResult:
    """
    Idempotent Meta lead persistence.

    Matches by meta_leadgen_id first, then email/phone, merging duplicate submissions
    into the existing lead instead of violating unique constraints.
    """
    row = normalize_lead_row(lead_data)
    leadgen_id = row["meta_leadgen_id"]

    existing_by_leadgen = db.query(Lead).filter(Lead.meta_leadgen_id == leadgen_id).first()
    if existing_by_leadgen:
        _freshen_lead(existing_by_leadgen, row, db)
        from app.services.lead_study_interest import hydrate_lead_study_interest

        hydrate_lead_study_interest(db, existing_by_leadgen, commit=True)
        logger.info("save_lead updated leadgen_id=%s lead_id=%s", leadgen_id, existing_by_leadgen.id)
        return SaveLeadResult(lead=existing_by_leadgen, created=False)

    email = row.get("email")
    if email and not _is_synthetic_meta_email(email):
        existing_by_email = db.query(Lead).filter(Lead.email == email).first()
        if existing_by_email:
            return _merge_existing_lead(
                db, existing_by_email, row, leadgen_id, matched_by="email"
            )

    phone = row.get("phone_number")
    if phone:
        existing_by_phone = db.query(Lead).filter(Lead.phone_number == phone).first()
        if existing_by_phone:
            return _merge_existing_lead(
                db, existing_by_phone, row, leadgen_id, matched_by="phone"
            )

    try:
        lead = Lead(**row)
        db.add(lead)
        db.commit()
        db.refresh(lead)
        from app.services.lead_study_interest import hydrate_lead_study_interest

        hydrate_lead_study_interest(db, lead, commit=True)
        from app.services.student_status_service import on_lead_created

        on_lead_created(db, lead, source="Meta")
        logger.info("save_lead inserted leadgen_id=%s lead_id=%s", leadgen_id, lead.id)
        return SaveLeadResult(lead=lead, created=True)
    except IntegrityError:
        db.rollback()
        if email and not _is_synthetic_meta_email(email):
            existing_by_email = db.query(Lead).filter(Lead.email == email).first()
            if existing_by_email:
                return _merge_existing_lead(
                    db, existing_by_email, row, leadgen_id, matched_by="email"
                )
        if phone:
            existing_by_phone = db.query(Lead).filter(Lead.phone_number == phone).first()
            if existing_by_phone:
                return _merge_existing_lead(
                    db, existing_by_phone, row, leadgen_id, matched_by="phone"
                )
        existing_by_leadgen = db.query(Lead).filter(Lead.meta_leadgen_id == leadgen_id).first()
        if existing_by_leadgen:
            _freshen_lead(existing_by_leadgen, row, db)
            db.commit()
            db.refresh(existing_by_leadgen)
            return SaveLeadResult(lead=existing_by_leadgen, created=False)
        raise


def build_lead_data_from_meta(
    event: LeadgenWebhookEvent,
    details: dict[str, Any],
) -> dict[str, Any]:
    """Transform Meta Graph lead payload into save_lead input."""
    from app.services.facebook_leads import (
        _normalize_email,
        _normalize_phone,
        _optional_str as fb_optional_str,
    )

    platform = fb_optional_str(details.get("platform"))
    source = map_platform_to_source(platform)
    channel = map_platform_to_channel(platform)

    normalized_fields = parse_meta_field_data(details.get("field_data"))
    full_name, email, phone_number, additional_fields = split_meta_contact_fields(normalized_fields)
    email = _normalize_email(email)
    phone_number = _normalize_phone(phone_number)

    campaign_name = fb_optional_str(details.get("campaign_name"))
    form_id = event.form_id or fb_optional_str(details.get("form_id"))

    additional_data: dict[str, Any] = dict(additional_fields)

    summary_parts = [f"Source: {source.value}"]
    if campaign_name:
        summary_parts.append(f"Campaign: {campaign_name}")
    if form_id:
        summary_parts.append(f"Form ID: {form_id}")

    meta_created_at = meta_created_time_to_utc_naive(details.get("created_time"))
    if meta_created_at is None and event.created_time is not None:
        meta_created_at = meta_created_time_to_utc_naive(event.created_time)

    payload: dict[str, Any] = {
        "leadgen_id": event.leadgen_id,
        "full_name": full_name,
        "email": email,
        "phone_number": phone_number,
        "channel": channel,
        "source": source.value,
        "stage": LeadStage.AI_ACTIVE,
        "is_human_locked": False,
        "meta_campaign_name": campaign_name,
        "meta_form_id": form_id,
        "meta_ad_id": event.ad_id or fb_optional_str(event.raw_value.get("ad_id")),
        "academic_summary": " | ".join(summary_parts),
        "additional_data": additional_data,
    }
    if meta_created_at is not None:
        payload["created_at"] = meta_created_at

    from app.services.lead_study_interest import enrich_lead_payload_from_meta_fields

    return enrich_lead_payload_from_meta_fields(payload)


def ingest_meta_leadgen_event(
    db: Session,
    event: LeadgenWebhookEvent,
    *,
    access_token: str | None = None,
    sync_mode: str = SYNC_MODE_AUTOMATED,
    triggered_by_user: str = TRIGGERED_BY_WEBHOOK,
    triggered_by_user_id: int | None = None,
    source: str = SOURCE_WEBHOOK,
    sync_log_id: int | None = None,
) -> "StageLeadResult":
    """Fetch Meta Graph details and stage raw payload (no validation at ingest)."""
    from app.services.lead_ingestion_pipeline import StageLeadResult, stage_meta_lead_raw

    details = fetch_leadgen_details(event.leadgen_id, access_token=access_token)
    return stage_meta_lead_raw(
        db,
        event=event,
        details=details,
        sync_mode=sync_mode,
        triggered_by_user=triggered_by_user,
        triggered_by_user_id=triggered_by_user_id,
        source=source,
        sync_log_id=sync_log_id,
    )


def meta_leadgen_id_exists(leadgen_id: str) -> bool:
    """Fast existence check without fetching full lead details from Meta."""
    db = SessionLocal()
    try:
        return (
            db.query(Lead.id)
            .filter(Lead.meta_leadgen_id == leadgen_id)
            .first()
            is not None
        )
    finally:
        safe_close_session(db)


def ingest_meta_leadgen_event_sync(
    event: LeadgenWebhookEvent,
    *,
    access_token: str | None = None,
    sync_mode: str = SYNC_MODE_AUTOMATED,
    triggered_by_user: str = TRIGGERED_BY_WEBHOOK,
    triggered_by_user_id: int | None = None,
    source: str = SOURCE_WEBHOOK,
    sync_log_id: int | None = None,
) -> "StageLeadResult | None":
    db = SessionLocal()
    try:
        return ingest_meta_leadgen_event(
            db,
            event,
            access_token=access_token,
            sync_mode=sync_mode,
            triggered_by_user=triggered_by_user,
            triggered_by_user_id=triggered_by_user_id,
            source=source,
            sync_log_id=sync_log_id,
        )
    except Exception:
        logger.exception("Failed to stage Meta leadgen_id=%s", event.leadgen_id)
        db.rollback()
        return None
    finally:
        safe_close_session(db)


async def ingest_meta_leadgen_event_async(
    event: LeadgenWebhookEvent,
    *,
    access_token: str | None = None,
    sync_mode: str = SYNC_MODE_AUTOMATED,
    triggered_by_user: str = TRIGGERED_BY_WEBHOOK,
    triggered_by_user_id: int | None = None,
    source: str = SOURCE_WEBHOOK,
    sync_log_id: int | None = None,
) -> "StageLeadResult | None":
    return await asyncio.to_thread(
        ingest_meta_leadgen_event_sync,
        event,
        access_token=access_token,
        sync_mode=sync_mode,
        triggered_by_user=triggered_by_user,
        triggered_by_user_id=triggered_by_user_id,
        source=source,
        sync_log_id=sync_log_id,
    )


async def process_leadgen_webhook_payload(payload: dict[str, Any]) -> int:
    """
    Parse Meta leadgen webhook notifications, fetch Graph details, and save each lead.

    Returns the number of leads successfully processed.
    """
    events = extract_leadgen_events(payload)
    if not events:
        return 0

    db = SessionLocal()
    log_row = begin_sync_transaction(
        db,
        sync_mode=SYNC_MODE_AUTOMATED,
        triggered_by_user=TRIGGERED_BY_WEBHOOK,
        source=SOURCE_WEBHOOK,
    )
    processed = 0
    created = 0
    skipped = 0
    errors: list[str] = []

    try:
        try:
            for event in events:
                logger.info(
                    "Meta webhook leadgen received leadgen_id=%s form_id=%s page_id=%s",
                    event.leadgen_id,
                    event.form_id,
                    event.page_id,
                )
                try:
                    result = await ingest_meta_leadgen_event_async(
                        event,
                        sync_log_id=log_row.id,
                    )
                except Exception as exc:
                    logger.exception("Failed to stage Meta leadgen_id=%s", event.leadgen_id)
                    errors.append(format_lead_ingestion_error(event.leadgen_id, exc))
                    continue

                if result is None:
                    errors.append(f"{event.leadgen_id}: staging failed")
                    continue

                processed += 1
                if result.created:
                    created += 1
                elif result.skipped:
                    skipped += 1
        except Exception as exc:
            logger.exception("Meta webhook leadgen batch failed.")
            fail_sync_transaction(db, log_row.id, error=str(exc))
            raise
        finally:
            finalize_sync_transaction(
                db,
                log_row.id,
                forms_processed=0,
                leads_seen=len(events),
                leads_created=created,
                leads_skipped=skipped,
                errors=errors,
            )
    finally:
        safe_close_session(db)

    return processed


def process_meta_leadgen_webhook(db: Session, payload: dict[str, Any]) -> int:
    """Synchronous wrapper used by legacy call sites and background workers."""
    events = extract_leadgen_events(payload)
    if not events:
        return 0

    processed = 0
    for event in events:
        try:
            result = ingest_meta_leadgen_event(db, event)
            if result.created or result.skipped:
                processed += 1
        except Exception:
            logger.exception("Failed to stage Meta leadgen_id=%s", event.leadgen_id)
            db.rollback()
    return processed
