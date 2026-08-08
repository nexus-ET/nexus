"""FlowX service — country workflows, enrollments, Kanban, SLA."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.academia_institution import Campus, College, Institution
from app.models.counselling_booking import CounsellingBooking
from app.models.country import Country
from app.models.flowx import (
    AUDIT_ACTIONS,
    JOURNEY_STAGE_LABELS,
    JOURNEY_STAGES,
    KANBAN_STATUSES,
    STAGE_DEFAULT_TRACKS,
    TRACK_LABELS,
    FlowxAuditLog,
    FlowxCountryWorkflow,
    FlowxEnrollment,
    FlowxEnrollmentTrack,
    FlowxStage,
    FlowxSubprocessLink,
    FlowxTask,
    FlowxTaskTemplate,
    FlowxTrack,
    FlowxWorkflowRule,
)
from app.models.lead import Lead
from app.utils.timezone import office_now, utc_now

# Sub-process 1.1 — driven by counselling booking / lead status_definitions (my-bookings).
INTAKE_SESSION_TITLE = "Intake Session"
STATUS_COUNSELLING_PROSPECT_QUALIFIED = 14

# Generic seed tasks per track (applied to every country skeleton).
GENERIC_TRACK_TASKS: dict[str, list[str]] = {
    "counselling_desk": [
        "Intake Session",
        "Profile & goals capture",
        "Destination shortlist discussion",
    ],
    "college_finder": [
        "Shortlist target universities",
        "Confirm program fit",
        "Submit university enquiry",
    ],
    "paperwork_studio": [
        "Collect academic transcripts",
        "Prepare SOP draft",
        "Gather recommendation letters",
    ],
    "exam_desk": [
        "Confirm required tests",
        "Book exam slot",
        "Upload score report",
    ],
    "visa_money": [
        "Proof of funds checklist",
        "Visa document pack",
        "Fee payment plan",
    ],
}

# Country-specific extras injected into templates (iso2 lower → track, title).
COUNTRY_EXTRA_TEMPLATES: dict[str, list[tuple[str, str, str]]] = {
    "de": [("paperwork_studio", "APS Certificate", "germany_aps")],
    "us": [
        ("visa_money", "SEVIS / I-20 tracking", "usa_sevis"),
        ("visa_money", "DS-160 prep", "usa_ds160"),
    ],
    "gb": [
        ("visa_money", "TB Test", "uk_tb"),
        ("visa_money", "IHS payment", "uk_ihs"),
    ],
}

ISO2_ALIASES = {
    "uk": "GB",
    "gb": "GB",
    "usa": "US",
    "us": "US",
    "germany": "DE",
    "de": "DE",
    "canada": "CA",
    "ca": "CA",
    "australia": "AU",
    "au": "AU",
}

# Canonical Master Workflow (not a real country). Cloned onto every destination board.
MASTER_WORKFLOW_ISO2 = "__"
SOURCE_PROCESS_ISO2 = MASTER_WORKFLOW_ISO2


def _track_label(name: str) -> str:
    return TRACK_LABELS.get(name, name.replace("_", " ").title())


def _sla_health(tasks: list[FlowxTask]) -> str:
    if any(t.sla_status == "breached" for t in tasks):
        return "breached"
    if any(t.sla_status == "amber" for t in tasks):
        return "amber"
    return "on_track"


def _recompute_track_progress(track: FlowxEnrollmentTrack) -> None:
    tasks = track.tasks or []
    if not tasks:
        track.progress_percentage = 0
        track.track_status = "not_started"
        return
    # Optional child processes appear on the journey but do not block completion.
    required = [t for t in tasks if not bool(getattr(t, "is_optional", False))]
    basis = required if required else tasks
    approved = sum(1 for t in basis if t.kanban_status == "approved")
    blocked = any(t.kanban_status == "blocked" for t in basis)
    track.progress_percentage = int(round(100 * approved / len(basis)))
    if blocked:
        track.track_status = "blocked"
    elif approved == len(basis):
        track.track_status = "completed"
    elif approved > 0 or any(t.kanban_status != "todo" for t in basis):
        track.track_status = "in_progress"
    else:
        track.track_status = "not_started"


def is_intake_session_task(task: FlowxTask | None) -> bool:
    if task is None:
        return False
    return (task.title or "").strip().lower() == INTAKE_SESSION_TITLE.lower()


def _intake_slot_end(db: Session, booking: CounsellingBooking) -> datetime | None:
    """End of the counselling appointment window (scheduled_time + slot duration)."""
    if not booking or not booking.scheduled_time:
        return None
    from app.services.counselling_service import _get_slot_minutes

    minutes = _get_slot_minutes(db) or 30
    start = booking.scheduled_time
    if start.tzinfo is not None:
        start = start.replace(tzinfo=None)
    return start + timedelta(minutes=minutes)


def _format_intake_delay_parts(delay_days: int) -> dict[str, Any]:
    days = max(0, int(delay_days))
    weeks = days // 7
    months = days // 30
    day_unit = "day" if days == 1 else "days"
    week_unit = "week" if weeks == 1 else "weeks"
    month_unit = "month" if months == 1 else "months"
    label = f"{days} {day_unit} · {weeks} {week_unit} · {months} {month_unit}"
    return {
        "delay_days": days,
        "delay_weeks": weeks,
        "delay_months": months,
        "delay_label": label,
    }


def compute_intake_overdue(
    db: Session,
    booking: CounsellingBooking | None,
    *,
    status_definition_id: int | None = None,
    booking_status: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Past appointment end without Finished/Cancelled → overdue Delayed metadata."""
    empty = {
        "is_overdue": False,
        "scheduled_time": None,
        "scheduled_end_at": None,
        "delay_days": 0,
        "delay_weeks": 0,
        "delay_months": 0,
        "delay_label": None,
    }
    if booking is None or not booking.scheduled_time:
        return empty

    from app.services.status_definition_service import (
        STATUS_COUNSELLING_CANCELLED,
        STATUS_COUNSELLING_FINISHED,
        STATUS_COUNSELLING_FOLLOW_UP,
        STATUS_LEAD_CANCELLED_NO_ANSWER,
        STATUS_LEAD_SESSION_CANCELLED,
    )

    bs = (booking_status or booking.status or "").strip().upper()
    sid = status_definition_id
    # Terminal outcomes are never overdue (finished / cancelled).
    if bs in ("COMPLETED", "CANCELLED"):
        return {**empty, "scheduled_time": booking.scheduled_time.isoformat()}
    if sid in (
        STATUS_COUNSELLING_FINISHED,
        STATUS_COUNSELLING_PROSPECT_QUALIFIED,
        STATUS_COUNSELLING_FOLLOW_UP,
        STATUS_LEAD_SESSION_CANCELLED,
        STATUS_LEAD_CANCELLED_NO_ANSWER,
        STATUS_COUNSELLING_CANCELLED,
    ):
        return {**empty, "scheduled_time": booking.scheduled_time.isoformat()}

    slot_end = _intake_slot_end(db, booking)
    if slot_end is None:
        return empty

    current = now or office_now(db)
    if current.tzinfo is not None:
        current = current.replace(tzinfo=None)

    if current <= slot_end:
        return {
            **empty,
            "scheduled_time": booking.scheduled_time.isoformat(),
            "scheduled_end_at": slot_end.isoformat(),
        }

    # Calendar days since the slot ended (at least 1 once past end).
    delay_days = (current.date() - slot_end.date()).days
    if delay_days < 1:
        delay_days = 1
    parts = _format_intake_delay_parts(delay_days)
    return {
        "is_overdue": True,
        "scheduled_time": booking.scheduled_time.isoformat(),
        "scheduled_end_at": slot_end.isoformat(),
        **parts,
    }


def resolve_intake_session_state(
    *,
    status_definition_id: int | None,
    booking_status: str | None = None,
    is_overdue: bool = False,
) -> tuple[str, str, int]:
    """Map lead status_definitions (+ booking fallback) → Intake Session UI state.

    Returns ``(kanban_status, sla_status, progress_percentage)``.

    status_definitions:
      4 / 5  Session Booked / Rescheduled → Planned 25%
      12     Counselling: Scheduled → In progress 50%
      6 / 7  Session Cancelled / No Answer → Delayed 0%
      13 / 14 / 15  Finished / Prospect Qualified / Follow-up → Complete 100%

    Overdue (appointment end passed, status not Finished/Cancelled) → Delayed 0%.

    When lead status and booking status disagree, Delayed wins; otherwise the
    furthest progress wins (e.g. lead still Booked + booking SCHEDULED → 50%).
    """
    from app.services.status_definition_service import (
        STATUS_COUNSELLING_CANCELLED,
        STATUS_COUNSELLING_FINISHED,
        STATUS_COUNSELLING_FOLLOW_UP,
        STATUS_COUNSELLING_SCHEDULED,
        STATUS_LEAD_CANCELLED_NO_ANSWER,
        STATUS_LEAD_SESSION_BOOKED,
        STATUS_LEAD_SESSION_CANCELLED,
        STATUS_LEAD_SESSION_RESCHEDULED,
    )

    signals: list[tuple[str, str, int]] = []

    sid = status_definition_id
    if sid in (
        STATUS_COUNSELLING_FINISHED,
        STATUS_COUNSELLING_PROSPECT_QUALIFIED,
        STATUS_COUNSELLING_FOLLOW_UP,
    ):
        signals.append(("approved", "on_track", 100))
    elif sid in (
        STATUS_LEAD_SESSION_CANCELLED,
        STATUS_LEAD_CANCELLED_NO_ANSWER,
        STATUS_COUNSELLING_CANCELLED,
    ):
        signals.append(("todo", "breached", 0))
    elif sid == STATUS_COUNSELLING_SCHEDULED:
        signals.append(("in_progress", "on_track", 50))
    elif sid in (STATUS_LEAD_SESSION_BOOKED, STATUS_LEAD_SESSION_RESCHEDULED):
        signals.append(("todo", "on_track", 25))

    bs = (booking_status or "").strip().upper()
    if bs == "COMPLETED":
        signals.append(("approved", "on_track", 100))
    elif bs == "CANCELLED":
        signals.append(("todo", "breached", 0))
    elif bs == "SCHEDULED":
        signals.append(("in_progress", "on_track", 50))
    elif bs == "PENDING":
        signals.append(("todo", "on_track", 25))

    if not signals:
        result = ("todo", "on_track", 0)
    elif any(s[1] == "breached" for s in signals):
        result = ("todo", "breached", 0)
    else:
        result = max(signals, key=lambda s: s[2])

    # Finished always wins; otherwise a past unclosed slot is Delayed 0%.
    if result[2] >= 100:
        return result
    if is_overdue:
        return "todo", "breached", 0
    return result


def _promote_intake_status_for_booking(
    db: Session,
    *,
    status_id: int | None,
    status_name: str | None,
    status_category: str | None,
    booking_status: str | None,
) -> tuple[int | None, str | None, str | None]:
    """When lead still shows Session Booked but booking has advanced, promote Intake status.

    ``resolve_lead_status_meta`` prefers ``lead.status_definition_id`` and can lag behind
    an assigned (SCHEDULED) counselling booking. Intake Session 1.1 must follow the booking.
    """
    from app.services.status_definition_service import (
        STAGE_COUNSELLING_FINISHED,
        STAGE_COUNSELLING_SCHEDULED,
        STATUS_LEAD_SESSION_BOOKED,
        STATUS_LEAD_SESSION_RESCHEDULED,
        get_status_definition_by_name,
    )

    bs = (booking_status or "").strip().upper()
    lagging = status_id in (
        None,
        STATUS_LEAD_SESSION_BOOKED,
        STATUS_LEAD_SESSION_RESCHEDULED,
    )
    if bs == "SCHEDULED" and lagging:
        row = get_status_definition_by_name(db, STAGE_COUNSELLING_SCHEDULED)
        if row:
            return row.id, row.stage_name, row.category
    if bs == "COMPLETED" and (lagging or status_id not in (13, 14, 15)):
        row = get_status_definition_by_name(db, STAGE_COUNSELLING_FINISHED)
        if row:
            return row.id, row.stage_name, row.category
    return status_id, status_name, status_category


def _resolve_intake_status_inputs(
    db: Session,
    *,
    lead: Lead | None,
    booking: CounsellingBooking | None,
) -> tuple[int | None, str | None]:
    """Same status source as the Intake Session blue label / My Bookings."""
    from app.services.status_definition_service import resolve_lead_status_meta

    booking_status = booking.status if booking else None
    status_id, status_name, status_category = resolve_lead_status_meta(
        db,
        lead,
        booking_status=booking_status,
    )
    status_id, _name, _cat = _promote_intake_status_for_booking(
        db,
        status_id=status_id,
        status_name=status_name,
        status_category=status_category,
        booking_status=booking_status,
    )
    return status_id, booking_status


def _latest_counselling_booking_for_lead(db: Session, lead_id: int) -> CounsellingBooking | None:
    return (
        db.query(CounsellingBooking)
        .filter(CounsellingBooking.lead_id == lead_id)
        .order_by(
            CounsellingBooking.scheduled_time.desc().nullslast(),
            CounsellingBooking.id.desc(),
        )
        .first()
    )


def _intake_booking_payload(
    db: Session,
    *,
    lead: Lead | None,
    booking: CounsellingBooking | None,
) -> dict[str, Any] | None:
    """Compact booking context for Intake Session (1.1) journey UI."""
    if booking is None and lead is None:
        return None
    from app.services.status_definition_service import resolve_lead_status_meta

    booking_status = booking.status if booking else None
    status_id, status_name, status_category = resolve_lead_status_meta(
        db,
        lead,
        booking_status=booking_status,
    )
    status_id, status_name, status_category = _promote_intake_status_for_booking(
        db,
        status_id=status_id,
        status_name=status_name,
        status_category=status_category,
        booking_status=booking_status,
    )
    if booking is None:
        if not status_id and not status_name:
            return None
        return {
            "id": None,
            "lead_id": lead.id if lead else None,
            "candidate_name": (lead.full_name if lead else None) or "Candidate",
            "status_definition_id": status_id,
            "status_stage_name": status_name,
            "status_category": status_category,
            "booking_status": None,
            "date_label": None,
            "time_label": None,
            "scheduled_time": None,
            "scheduled_end_at": None,
            "is_overdue": False,
            "delay_days": 0,
            "delay_weeks": 0,
            "delay_months": 0,
            "delay_label": None,
        }

    overdue = compute_intake_overdue(
        db,
        booking,
        status_definition_id=status_id,
        booking_status=booking_status,
    )

    # Reuse My Bookings serialization for schedule labels when available.
    try:
        from app.services.counselling_service import _serialize_my_booking

        admin = None
        if booking.admin_id:
            from app.models.user import User

            admin = db.query(User).filter(User.id == booking.admin_id).first()
        row = _serialize_my_booking(db, booking, admin, section="today", lead=lead)
        return {
            "id": booking.id,
            "lead_id": booking.lead_id,
            "candidate_name": row.get("candidate_name")
            or (lead.full_name if lead else None)
            or "Candidate",
            "status_definition_id": status_id or row.get("status_definition_id"),
            "status_stage_name": status_name or row.get("status_stage_name"),
            "status_category": status_category or row.get("status_category"),
            "booking_status": booking.status,
            "date_label": row.get("date_label"),
            "time_label": row.get("time_label"),
            **overdue,
        }
    except Exception:
        return {
            "id": booking.id,
            "lead_id": booking.lead_id,
            "candidate_name": (lead.full_name if lead else None) or "Candidate",
            "status_definition_id": status_id,
            "status_stage_name": status_name,
            "status_category": status_category,
            "booking_status": booking.status,
            "date_label": None,
            "time_label": None,
            **overdue,
        }


def sync_intake_session_for_lead(
    db: Session,
    lead_id: int,
    *,
    commit: bool = False,
) -> int:
    """Align FlowX ``Intake Session`` bricks with my-bookings / status_definitions.

    Confirmation of intake comes from counselling booking status changes
    (e.g. Counselling: Finished = 13), not a separate FlowX confirmation UI.
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return 0

    booking = _latest_counselling_booking_for_lead(db, lead_id)
    status_id, booking_status = _resolve_intake_status_inputs(db, lead=lead, booking=booking)
    overdue = compute_intake_overdue(
        db,
        booking,
        status_definition_id=status_id,
        booking_status=booking_status,
    )
    kanban, sla, _progress = resolve_intake_session_state(
        status_definition_id=status_id,
        booking_status=booking_status,
        is_overdue=bool(overdue.get("is_overdue")),
    )

    enrollments = (
        db.query(FlowxEnrollment)
        .options(joinedload(FlowxEnrollment.tracks).joinedload(FlowxEnrollmentTrack.tasks))
        .filter(
            FlowxEnrollment.lead_id == lead_id,
            FlowxEnrollment.status.in_(("active", "paused")),
        )
        .all()
    )

    changed = 0
    now = utc_now()
    for enrollment in enrollments:
        for track in enrollment.tracks or []:
            track_dirty = False
            for task in track.tasks or []:
                if not is_intake_session_task(task):
                    continue
                if task.kanban_status != kanban or task.sla_status != sla:
                    task.kanban_status = kanban
                    task.sla_status = sla
                    task.updated_at = now
                    track_dirty = True
                    changed += 1
            if track_dirty:
                _recompute_track_progress(track)
                track.updated_at = now

    if not changed:
        return 0
    if commit:
        db.commit()
    else:
        db.flush()
    return changed


def _task_progress_percentage(
    task: FlowxTask,
    *,
    intake_progress: int | None = None,
) -> int:
    if is_intake_session_task(task) and intake_progress is not None:
        return int(intake_progress)
    if task.kanban_status == "approved":
        return 100
    if task.sla_status in ("breached", "amber"):
        return 0
    if task.kanban_status in ("in_progress", "in_review"):
        return 50
    return 0


def normalize_iso2(raw: str | None) -> str | None:
    if not raw:
        return None
    key = raw.strip().lower()
    if key in ISO2_ALIASES:
        return ISO2_ALIASES[key]
    if len(raw.strip()) == 2:
        return raw.strip().upper()
    # Try match by country name later in callers
    return raw.strip().upper() if len(raw.strip()) == 2 else None


def resolve_country(db: Session, hint: str) -> Country:
    iso = normalize_iso2(hint)
    country = None
    if iso and len(iso) == 2:
        country = db.query(Country).filter(Country.iso2 == iso, Country.is_active.is_(True)).first()
    if not country:
        country = (
            db.query(Country)
            .filter(Country.name.ilike(hint.strip()), Country.is_active.is_(True))
            .first()
        )
    if not country and iso:
        country = db.query(Country).filter(Country.iso2 == iso).first()
    if not country:
        raise ValueError(f"Unknown country: {hint}")
    return country


def _workflow_load(db: Session, workflow_id: uuid.UUID) -> FlowxCountryWorkflow | None:
    return (
        db.query(FlowxCountryWorkflow)
        .options(
            joinedload(FlowxCountryWorkflow.stages)
            .joinedload(FlowxStage.tracks)
            .joinedload(FlowxTrack.task_templates)
        )
        .filter(FlowxCountryWorkflow.id == workflow_id)
        .first()
    )


def _workflow_by_iso(db: Session, iso2: str) -> FlowxCountryWorkflow | None:
    return (
        db.query(FlowxCountryWorkflow)
        .options(
            joinedload(FlowxCountryWorkflow.stages)
            .joinedload(FlowxStage.tracks)
            .joinedload(FlowxTrack.task_templates)
        )
        .filter(FlowxCountryWorkflow.country_iso2 == iso2.upper())
        .first()
    )


def _enrollment_load(db: Session, enrollment_id: uuid.UUID) -> FlowxEnrollment | None:
    return (
        db.query(FlowxEnrollment)
        .options(
            joinedload(FlowxEnrollment.workflow),
            joinedload(FlowxEnrollment.tracks).joinedload(FlowxEnrollmentTrack.tasks),
        )
        .filter(FlowxEnrollment.id == enrollment_id)
        .first()
    )


def _seed_workflow_skeleton(db: Session, country: Country) -> FlowxCountryWorkflow:
    now = utc_now()
    workflow = FlowxCountryWorkflow(
        id=uuid.uuid4(),
        country_iso2=country.iso2.upper(),
        name=f"{country.name} overseas education journey",
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.add(workflow)
    db.flush()

    extras = COUNTRY_EXTRA_TEMPLATES.get(country.iso2.lower(), [])

    for pos, stage_key in enumerate(JOURNEY_STAGES):
        existing_label = (
            db.query(FlowxStage.label)
            .filter(FlowxStage.stage_key == stage_key)
            .order_by(FlowxStage.updated_at.desc())
            .limit(1)
            .scalar()
        )
        stage = FlowxStage(
            id=uuid.uuid4(),
            workflow_id=workflow.id,
            stage_key=stage_key,
            label=existing_label or JOURNEY_STAGE_LABELS[stage_key],
            position_index=pos,
            is_hidden=False,
            created_at=now,
            updated_at=now,
        )
        db.add(stage)
        db.flush()
        for tpos, track_name in enumerate(STAGE_DEFAULT_TRACKS.get(stage_key, ["paperwork_studio"])):
            track = FlowxTrack(
                id=uuid.uuid4(),
                stage_id=stage.id,
                track_name=track_name,
                position_index=tpos,
                created_at=now,
                updated_at=now,
            )
            db.add(track)
            db.flush()
            titles = list(GENERIC_TRACK_TASKS.get(track_name, ["Complete stage checklist"]))
            # Only attach country extras once (first matching track occurrence).
            for title, source in [(e[1], e[2]) for e in extras if e[0] == track_name]:
                if title not in titles:
                    titles.append(title)
            for ipos, title in enumerate(titles):
                is_specific = any(e[1] == title for e in extras)
                source = next((e[2] for e in extras if e[1] == title), None)
                db.add(
                    FlowxTaskTemplate(
                        id=uuid.uuid4(),
                        track_id=track.id,
                        title=title,
                        position_index=ipos,
                        sla_days=7,
                        is_country_specific=is_specific,
                        auto_trigger_source=source,
                        created_at=now,
                    )
                )

    db.commit()
    loaded = _workflow_by_iso(db, country.iso2)
    assert loaded is not None
    return loaded


def _clear_workflow_structure(db: Session, workflow: FlowxCountryWorkflow) -> None:
    """Remove stages, tracks, templates, and links under a workflow (keep the workflow row)."""
    db.query(FlowxSubprocessLink).filter(
        FlowxSubprocessLink.workflow_id == workflow.id
    ).delete(synchronize_session=False)

    stage_ids = [
        row[0]
        for row in db.query(FlowxStage.id)
        .filter(FlowxStage.workflow_id == workflow.id)
        .all()
    ]
    if not stage_ids:
        db.flush()
        db.expire(workflow, ["stages"])
        return

    track_ids = [
        row[0]
        for row in db.query(FlowxTrack.id).filter(FlowxTrack.stage_id.in_(stage_ids)).all()
    ]
    if track_ids:
        # Break self-FK before deleting templates.
        db.query(FlowxTaskTemplate).filter(FlowxTaskTemplate.track_id.in_(track_ids)).update(
            {FlowxTaskTemplate.parent_template_id: None},
            synchronize_session=False,
        )
        db.query(FlowxTaskTemplate).filter(FlowxTaskTemplate.track_id.in_(track_ids)).delete(
            synchronize_session=False
        )
        db.query(FlowxTrack).filter(FlowxTrack.id.in_(track_ids)).delete(synchronize_session=False)

    db.query(FlowxStage).filter(FlowxStage.id.in_(stage_ids)).delete(synchronize_session=False)
    db.flush()
    db.expire(workflow, ["stages"])


def _copy_structure_from_workflow(
    db: Session,
    *,
    source: FlowxCountryWorkflow,
    target: FlowxCountryWorkflow,
    link_to_master: bool = False,
) -> dict[str, int]:
    """Deep-copy stages / tracks / bricks / nesting / links from source onto an empty target.

    When link_to_master=True (source is Master), country bricks get master_template_id set.
    """
    now = utc_now()
    template_id_map: dict[uuid.UUID, uuid.UUID] = {}
    pending_parents: list[tuple[uuid.UUID, uuid.UUID]] = []
    stages_copied = 0
    templates_copied = 0

    for stage in sorted(source.stages or [], key=lambda s: s.position_index):
        new_stage = FlowxStage(
            id=uuid.uuid4(),
            workflow_id=target.id,
            stage_key=stage.stage_key,
            label=stage.label,
            position_index=stage.position_index,
            is_hidden=bool(getattr(stage, "is_hidden", False)),
            created_at=now,
            updated_at=now,
        )
        db.add(new_stage)
        db.flush()
        stages_copied += 1

        for track in sorted(stage.tracks or [], key=lambda t: t.position_index):
            new_track = FlowxTrack(
                id=uuid.uuid4(),
                stage_id=new_stage.id,
                track_name=track.track_name,
                position_index=track.position_index,
                created_at=now,
                updated_at=now,
            )
            db.add(new_track)
            db.flush()

            for tpl in sorted(track.task_templates or [], key=lambda x: x.position_index):
                new_id = uuid.uuid4()
                template_id_map[tpl.id] = new_id
                db.add(
                    FlowxTaskTemplate(
                        id=new_id,
                        track_id=new_track.id,
                        title=tpl.title,
                        description=tpl.description,
                        action_steps=tpl.action_steps,
                        position_index=tpl.position_index,
                        sla_days=tpl.sla_days or 7,
                        is_country_specific=bool(tpl.is_country_specific),
                        auto_trigger_source=tpl.auto_trigger_source,
                        is_active=bool(getattr(tpl, "is_active", True)),
                        is_optional=False,
                        override_action=None,
                        override_reason=None,
                        overridden_at=None,
                        overridden_by=None,
                        parent_template_id=None,
                        master_template_id=tpl.id if link_to_master else None,
                        created_at=now,
                    )
                )
                templates_copied += 1
                if tpl.parent_template_id:
                    pending_parents.append((new_id, tpl.parent_template_id))

    db.flush()
    for new_id, old_parent_id in pending_parents:
        mapped_parent = template_id_map.get(old_parent_id)
        if not mapped_parent:
            continue
        row = db.query(FlowxTaskTemplate).filter(FlowxTaskTemplate.id == new_id).first()
        if row:
            row.parent_template_id = mapped_parent

    links_copied = 0
    source_links = (
        db.query(FlowxSubprocessLink)
        .filter(FlowxSubprocessLink.workflow_id == source.id)
        .all()
    )
    for link in source_links:
        new_from = template_id_map.get(link.from_template_id)
        new_to = template_id_map.get(link.to_template_id)
        if not new_from or not new_to:
            continue
        db.add(
            FlowxSubprocessLink(
                id=uuid.uuid4(),
                workflow_id=target.id,
                from_template_id=new_from,
                to_template_id=new_to,
                link_type=link.link_type or "depends_on",
                created_at=now,
            )
        )
        links_copied += 1

    db.flush()
    return {
        "stages_copied": stages_copied,
        "templates_copied": templates_copied,
        "links_copied": links_copied,
    }


def _create_workflow_from_source(
    db: Session,
    country: Country,
    source: FlowxCountryWorkflow,
) -> FlowxCountryWorkflow:
    now = utc_now()
    workflow = FlowxCountryWorkflow(
        id=uuid.uuid4(),
        country_iso2=country.iso2.upper(),
        name=f"{country.name} overseas education journey",
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.add(workflow)
    db.flush()
    link_to_master = (source.country_iso2 or "").upper() == MASTER_WORKFLOW_ISO2
    _copy_structure_from_workflow(
        db, source=source, target=workflow, link_to_master=link_to_master
    )
    db.commit()
    loaded = _workflow_by_iso(db, country.iso2)
    assert loaded is not None
    return loaded


def replace_workflow_structure_from_source(
    db: Session,
    target: FlowxCountryWorkflow,
    source: FlowxCountryWorkflow,
    *,
    sync_enrollments: bool = True,
) -> dict[str, int]:
    """Replace target country board with a deep copy of source (Master by default)."""
    if target.id == source.id:
        raise ValueError("Cannot copy a workflow onto itself")
    _clear_workflow_structure(db, target)
    link_to_master = (source.country_iso2 or "").upper() == MASTER_WORKFLOW_ISO2
    stats = _copy_structure_from_workflow(
        db, source=source, target=target, link_to_master=link_to_master
    )
    target.updated_at = utc_now()
    db.flush()
    enrollments_synced = 0
    if sync_enrollments:
        enrollments_synced = sync_workflow_enrollments(db, target.id)
    stats["enrollments_synced"] = enrollments_synced
    return stats


def _iter_active_destination_workflows(db: Session) -> list[FlowxCountryWorkflow]:
    return (
        db.query(FlowxCountryWorkflow)
        .options(
            joinedload(FlowxCountryWorkflow.stages)
            .joinedload(FlowxStage.tracks)
            .joinedload(FlowxTrack.task_templates)
        )
        .filter(
            FlowxCountryWorkflow.status == "active",
            FlowxCountryWorkflow.country_iso2 != MASTER_WORKFLOW_ISO2,
        )
        .order_by(FlowxCountryWorkflow.country_iso2)
        .all()
    )


def ensure_master_workflow(db: Session) -> FlowxCountryWorkflow:
    """Ensure the singleton Master Workflow exists (bootstrapped from Canada when available)."""
    existing = _workflow_by_iso(db, MASTER_WORKFLOW_ISO2)
    if existing:
        if existing.status != "active":
            existing.status = "active"
            existing.updated_at = utc_now()
            db.commit()
            reloaded = _workflow_by_iso(db, MASTER_WORKFLOW_ISO2)
            assert reloaded is not None
            return reloaded
        return existing

    now = utc_now()
    master = FlowxCountryWorkflow(
        id=uuid.uuid4(),
        country_iso2=MASTER_WORKFLOW_ISO2,
        name="Master Workflow",
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.add(master)
    db.flush()

    canada = _workflow_by_iso(db, "CA")
    if canada and (canada.stages or []):
        _copy_structure_from_workflow(db, source=canada, target=master, link_to_master=False)
        db.commit()
    else:
        # Generic skeleton without a Country row.
        for pos, stage_key in enumerate(JOURNEY_STAGES):
            stage = FlowxStage(
                id=uuid.uuid4(),
                workflow_id=master.id,
                stage_key=stage_key,
                label=JOURNEY_STAGE_LABELS[stage_key],
                position_index=pos,
                is_hidden=False,
                created_at=now,
                updated_at=now,
            )
            db.add(stage)
            db.flush()
            for tpos, track_name in enumerate(
                STAGE_DEFAULT_TRACKS.get(stage_key, ["paperwork_studio"])
            ):
                track = FlowxTrack(
                    id=uuid.uuid4(),
                    stage_id=stage.id,
                    track_name=track_name,
                    position_index=tpos,
                    created_at=now,
                    updated_at=now,
                )
                db.add(track)
                db.flush()
                titles = list(GENERIC_TRACK_TASKS.get(track_name, ["Complete stage checklist"]))
                for ipos, title in enumerate(titles):
                    db.add(
                        FlowxTaskTemplate(
                            id=uuid.uuid4(),
                            track_id=track.id,
                            title=title,
                            position_index=ipos,
                            sla_days=7,
                            created_at=now,
                        )
                    )
        db.commit()

    loaded = _workflow_by_iso(db, MASTER_WORKFLOW_ISO2)
    assert loaded is not None
    return loaded


def get_master_workflow(db: Session) -> dict[str, Any]:
    master = ensure_master_workflow(db)
    detail = workflow_to_detail(db, master)
    detail["country_iso2"] = MASTER_WORKFLOW_ISO2
    detail["country_name"] = "Master"
    detail["is_master"] = True
    return detail



def _workflow_is_master(workflow: FlowxCountryWorkflow | None) -> bool:
    return bool(workflow and (workflow.country_iso2 or '').upper() == MASTER_WORKFLOW_ISO2)


def _find_track_on_workflow(
    workflow: FlowxCountryWorkflow,
    *,
    stage_key: str,
    track_name: str,
) -> FlowxTrack | None:
    for stage in workflow.stages or []:
        if stage.stage_key != stage_key:
            continue
        for track in stage.tracks or []:
            if track.track_name == track_name:
                return track
    return None


def _ensure_track_on_stage(
    db: Session,
    stage: FlowxStage,
    track_name: str,
) -> FlowxTrack:
    """Return an existing track on the stage, or create one for drag/move targets."""
    wanted = (track_name or "").strip() or "paperwork_studio"
    for track in stage.tracks or []:
        if track.track_name == wanted:
            return track
    # Prefer the first existing track when the named track is missing (common for
    # country boards that only seed one track per process).
    if stage.tracks:
        return stage.tracks[0]
    now = utc_now()
    track = FlowxTrack(
        id=uuid.uuid4(),
        stage_id=stage.id,
        track_name=wanted,
        position_index=0,
        created_at=now,
        updated_at=now,
    )
    db.add(track)
    db.flush()
    if stage.tracks is None:
        stage.tracks = []
    stage.tracks.append(track)
    return track


def master_update_task_template(
    db: Session,
    template_id: uuid.UUID,
    *,
    title: str | None = None,
    description: str | None = None,
    action_steps: list[str] | None = None,
) -> dict[str, Any]:
    """Edit a Master brick and push title/definition/steps to every country copy."""
    master = ensure_master_workflow(db)
    tpl = (
        db.query(FlowxTaskTemplate)
        .options(joinedload(FlowxTaskTemplate.track).joinedload(FlowxTrack.stage))
        .filter(FlowxTaskTemplate.id == template_id)
        .first()
    )
    if not tpl or not tpl.track or not tpl.track.stage:
        raise ValueError('Sub-process not found')
    if tpl.track.stage.workflow_id != master.id:
        raise ValueError('Template is not on the Master Workflow')

    clean_title = (title or '').strip() if title is not None else None
    if description is None:
        clean_description = None
    else:
        words = (description or '').strip().split()
        clean_description = ' '.join(words[:5]) if words else ''
    clean_steps = None if action_steps is None else _format_action_steps(action_steps)

    if clean_title is None and clean_description is None and clean_steps is None:
        raise ValueError('Provide a title, definition, and/or steps to update')
    if clean_title is not None and not clean_title:
        raise ValueError('Sub-process name is required')
    if clean_title is not None and len(clean_title) > 255:
        raise ValueError('Sub-process name is too long')
    if action_steps is not None and not clean_steps:
        raise ValueError('Add at least one step to perform (one per line)')

    if clean_title is not None:
        tpl.title = clean_title
    if clean_description is not None:
        tpl.description = clean_description or None
    if clean_steps is not None:
        tpl.action_steps = clean_steps

    copies = (
        db.query(FlowxTaskTemplate)
        .filter(FlowxTaskTemplate.master_template_id == tpl.id)
        .all()
    )
    for item in copies:
        if clean_title is not None:
            item.title = clean_title
        if clean_description is not None:
            item.description = clean_description or None
        if clean_steps is not None:
            item.action_steps = clean_steps

    # Refresh journey task labels for synced slots (all countries).
    if clean_title is not None or clean_description is not None:
        now = utc_now()
        stage_key = tpl.track.stage.stage_key
        track_name = tpl.track.track_name
        position_index = tpl.position_index
        enrollment_tasks = (
            db.query(FlowxTask)
            .join(FlowxEnrollmentTrack, FlowxTask.enrollment_track_id == FlowxEnrollmentTrack.id)
            .filter(
                FlowxEnrollmentTrack.track_name == track_name,
                FlowxEnrollmentTrack.stage_key == stage_key,
                FlowxTask.position_index == position_index,
            )
            .all()
        )
        for task in enrollment_tasks:
            if clean_title is not None:
                task.title = clean_title
            if clean_description is not None:
                task.description = clean_description or None
            task.updated_at = now

        seed_titles = GENERIC_TRACK_TASKS.get(track_name)
        if seed_titles and 0 <= position_index < len(seed_titles) and clean_title is not None:
            updated = list(seed_titles)
            updated[position_index] = clean_title
            GENERIC_TRACK_TASKS[track_name] = updated

    db.commit()
    return get_master_workflow(db)


def master_add_task_template(
    db: Session,
    track_id: uuid.UUID,
    *,
    title: str,
    description: str | None = None,
    action_steps: list[str] | None = None,
    sla_days: int = 7,
    parent_template_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Add a Master brick and create a linked copy on every active country."""
    master = ensure_master_workflow(db)
    track = (
        db.query(FlowxTrack)
        .options(joinedload(FlowxTrack.task_templates), joinedload(FlowxTrack.stage))
        .filter(FlowxTrack.id == track_id)
        .first()
    )
    if not track or not track.stage or track.stage.workflow_id != master.id:
        raise ValueError('Master track not found')
    steps = _parse_action_steps(action_steps or [])
    if not steps:
        raise ValueError('Add at least one step to perform (one per line)')
    clean_title = title.strip()
    if not clean_title:
        raise ValueError('Sub-process name is required')
    if description is None:
        clean_description = None
    else:
        words = description.strip().split()
        clean_description = ' '.join(words[:5]) if words else ''

    if parent_template_id is not None:
        parent = (
            db.query(FlowxTaskTemplate)
            .options(joinedload(FlowxTaskTemplate.track).joinedload(FlowxTrack.stage))
            .filter(FlowxTaskTemplate.id == parent_template_id)
            .first()
        )
        if not parent or not parent.track or parent.track.stage.workflow_id != master.id:
            raise ValueError('Parent sub-process not found on Master')

    next_pos = max((t.position_index for t in (track.task_templates or [])), default=-1) + 1
    now = utc_now()
    master_tpl = FlowxTaskTemplate(
        id=uuid.uuid4(),
        track_id=track.id,
        title=clean_title,
        description=clean_description or None,
        action_steps=_format_action_steps(steps),
        position_index=next_pos,
        sla_days=max(1, sla_days),
        parent_template_id=parent_template_id,
        created_at=now,
    )
    db.add(master_tpl)
    db.flush()

    stage_key = track.stage.stage_key
    track_name = track.track_name
    for workflow in _iter_active_destination_workflows(db):
        dest_track = _find_track_on_workflow(workflow, stage_key=stage_key, track_name=track_name)
        if not dest_track:
            continue
        dest_parent_id = None
        if parent_template_id is not None:
            dest_parent = (
                db.query(FlowxTaskTemplate)
                .join(FlowxTrack, FlowxTaskTemplate.track_id == FlowxTrack.id)
                .join(FlowxStage, FlowxTrack.stage_id == FlowxStage.id)
                .filter(
                    FlowxTaskTemplate.master_template_id == parent_template_id,
                    FlowxStage.workflow_id == workflow.id,
                )
                .first()
            )
            if dest_parent:
                dest_parent_id = dest_parent.id
        dest_pos = (
            max(
                (t.position_index for t in (dest_track.task_templates or [])),
                default=-1,
            )
            + 1
        )
        db.add(
            FlowxTaskTemplate(
                id=uuid.uuid4(),
                track_id=dest_track.id,
                title=clean_title,
                description=clean_description or None,
                action_steps=_format_action_steps(steps),
                position_index=dest_pos,
                sla_days=max(1, sla_days),
                parent_template_id=dest_parent_id,
                master_template_id=master_tpl.id,
                created_at=now,
            )
        )
        sync_workflow_enrollments(db, workflow.id)

    db.commit()
    return get_master_workflow(db)


def _template_ids_with_descendants(db: Session, root_id: uuid.UUID) -> list[uuid.UUID]:
    """BFS: root template id plus every nested child under parent_template_id."""
    ids: list[uuid.UUID] = []
    queue = [root_id]
    seen: set[uuid.UUID] = set()
    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        ids.append(current)
        children = (
            db.query(FlowxTaskTemplate.id)
            .filter(FlowxTaskTemplate.parent_template_id == current)
            .all()
        )
        for (child_id,) in children:
            queue.append(child_id)
    return ids


def _expand_template_ids_with_descendants(
    db: Session, root_ids: list[uuid.UUID] | set[uuid.UUID]
) -> list[uuid.UUID]:
    """Union of each root plus its nested descendants (stable BFS order)."""
    ordered: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for root_id in root_ids:
        for tid in _template_ids_with_descendants(db, root_id):
            if tid in seen:
                continue
            seen.add(tid)
            ordered.append(tid)
    return ordered


def _purge_templates_and_mapped_tasks(
    db: Session,
    template_ids: list[uuid.UUID],
    *,
    workflow_id: uuid.UUID | None = None,
) -> set[uuid.UUID]:
    """Delete templates (children first), their links, and mapped journey tasks.

    Returns enrollment-track ids that need progress recompute.
    """
    if not template_ids:
        return set()
    templates = (
        db.query(FlowxTaskTemplate)
        .options(joinedload(FlowxTaskTemplate.track).joinedload(FlowxTrack.stage))
        .filter(FlowxTaskTemplate.id.in_(template_ids))
        .all()
    )
    by_id = {tpl.id: tpl for tpl in templates}
    affected_track_ids: set[uuid.UUID] = set()

    for tid in reversed(template_ids):
        tpl = by_id.get(tid)
        if not tpl:
            continue
        if tpl.track and tpl.track.stage:
            wf_id = workflow_id or tpl.track.stage.workflow_id
            mapped_rows = (
                db.query(FlowxTask.id, FlowxEnrollmentTrack.id)
                .join(
                    FlowxEnrollmentTrack,
                    FlowxTask.enrollment_track_id == FlowxEnrollmentTrack.id,
                )
                .join(FlowxEnrollment, FlowxEnrollmentTrack.enrollment_id == FlowxEnrollment.id)
                .filter(
                    FlowxEnrollment.country_workflow_id == wf_id,
                    FlowxEnrollmentTrack.stage_key == tpl.track.stage.stage_key,
                    FlowxEnrollmentTrack.track_name == tpl.track.track_name,
                    FlowxTask.position_index == tpl.position_index,
                )
                .all()
            )
            task_ids = [row[0] for row in mapped_rows]
            affected_track_ids.update(row[1] for row in mapped_rows)
            if task_ids:
                db.query(FlowxTask).filter(FlowxTask.id.in_(task_ids)).delete(
                    synchronize_session=False
                )
        db.query(FlowxSubprocessLink).filter(
            (FlowxSubprocessLink.from_template_id == tid)
            | (FlowxSubprocessLink.to_template_id == tid)
        ).delete(synchronize_session=False)
        # May already be gone via parent CASCADE — re-check.
        row = db.query(FlowxTaskTemplate).filter(FlowxTaskTemplate.id == tid).first()
        if row:
            db.delete(row)

    db.flush()
    return affected_track_ids


def master_delete_task_template(db: Session, template_id: uuid.UUID) -> dict[str, Any]:
    """Delete a Master brick (and nested children) plus every linked country copy."""
    master = ensure_master_workflow(db)
    root = (
        db.query(FlowxTaskTemplate)
        .options(joinedload(FlowxTaskTemplate.track).joinedload(FlowxTrack.stage))
        .filter(FlowxTaskTemplate.id == template_id)
        .first()
    )
    if not root or not root.track or not root.track.stage:
        raise ValueError('Sub-process not found')
    if root.track.stage.workflow_id != master.id:
        raise ValueError('Template is not on the Master Workflow')

    # Collect master template ids: root + descendants (nested under parent_template_id).
    master_ids = _template_ids_with_descendants(db, root.id)

    # Country copies linked to those master bricks, plus country-local nested children
    # under those copies (they may have no master_template_id).
    copy_roots = (
        db.query(FlowxTaskTemplate.id)
        .filter(FlowxTaskTemplate.master_template_id.in_(master_ids))
        .all()
    )
    country_delete_ids = _expand_template_ids_with_descendants(
        db, [row[0] for row in copy_roots]
    )
    country_templates = (
        db.query(FlowxTaskTemplate)
        .options(joinedload(FlowxTaskTemplate.track).joinedload(FlowxTrack.stage))
        .filter(FlowxTaskTemplate.id.in_(country_delete_ids))
        .all()
        if country_delete_ids
        else []
    )
    affected_workflow_ids: set[uuid.UUID] = set()
    for copy in country_templates:
        if copy.track and copy.track.stage:
            affected_workflow_ids.add(copy.track.stage.workflow_id)

    # Group country deletes by workflow so journey-task mapping stays scoped.
    by_workflow: dict[uuid.UUID, list[uuid.UUID]] = {}
    for copy in country_templates:
        if not copy.track or not copy.track.stage:
            continue
        by_workflow.setdefault(copy.track.stage.workflow_id, []).append(copy.id)
    for wf_id, ids in by_workflow.items():
        # Preserve descendant-aware order from country_delete_ids.
        ordered = [tid for tid in country_delete_ids if tid in set(ids)]
        _purge_templates_and_mapped_tasks(db, ordered, workflow_id=wf_id)

    db.query(FlowxSubprocessLink).filter(
        (FlowxSubprocessLink.from_template_id.in_(master_ids))
        | (FlowxSubprocessLink.to_template_id.in_(master_ids))
    ).delete(synchronize_session=False)

    # Clear reverse master links, then delete master bricks (children first).
    db.query(FlowxTaskTemplate).filter(
        FlowxTaskTemplate.master_template_id.in_(master_ids)
    ).update({FlowxTaskTemplate.master_template_id: None}, synchronize_session=False)
    _purge_templates_and_mapped_tasks(db, master_ids, workflow_id=master.id)

    for workflow_id in affected_workflow_ids:
        sync_workflow_enrollments(db, workflow_id)

    db.commit()
    return get_master_workflow(db)


def master_rename_process_label(
    db: Session,
    *,
    stage_key: str,
    label: str,
) -> dict[str, Any]:
    """Rename a main process on Master and every country board."""
    ensure_master_workflow(db)
    rename_global_process_label(db, stage_key=stage_key, label=label)
    return get_master_workflow(db)


def apply_source_processes_to_active_countries(
    db: Session,
    *,
    source_iso2: str = SOURCE_PROCESS_ISO2,
    target_iso_codes: list[str] | None = None,
) -> dict[str, Any]:
    """Copy Master (or another source) processes onto active destination countries."""
    source_code = (source_iso2 or SOURCE_PROCESS_ISO2).strip().upper() or MASTER_WORKFLOW_ISO2
    if source_code == MASTER_WORKFLOW_ISO2:
        source = ensure_master_workflow(db)
    else:
        source = _workflow_by_iso(db, source_code)
    if not source or source.status != "active":
        raise ValueError(
            f"Active FlowX workflow for {source_code} is required as the process template"
        )
    if not (source.stages or []):
        raise ValueError(f"{source_code} workflow has no processes to copy")

    wanted = (
        {c.strip().upper() for c in target_iso_codes if c and c.strip()}
        if target_iso_codes is not None
        else None
    )

    updated: list[dict[str, Any]] = []
    skipped: list[str] = []
    for workflow in _iter_active_destination_workflows(db):
        iso = (workflow.country_iso2 or "").upper()
        if iso == source_code:
            skipped.append(iso)
            continue
        if wanted is not None and iso not in wanted:
            continue
        stats = replace_workflow_structure_from_source(
            db, workflow, source, sync_enrollments=True
        )
        updated.append({"country_iso2": iso, **stats})

    db.commit()
    return {
        "source_iso2": source_code,
        "updated_count": len(updated),
        "updated": updated,
        "skipped": skipped,
    }


def ensure_country_workflow(db: Session, country_hint: str) -> FlowxCountryWorkflow:
    hint = (country_hint or "").strip().upper()
    if hint == MASTER_WORKFLOW_ISO2:
        return ensure_master_workflow(db)

    country = resolve_country(db, country_hint)
    existing = _workflow_by_iso(db, country.iso2)
    master = ensure_master_workflow(db)
    source_ready = bool(master and master.status == "active" and (master.stages or []))

    if existing:
        if existing.status != "active":
            # Re-adding from "Add countries" — restore Master process tree by default.
            existing.status = "active"
            existing.updated_at = utc_now()
            if source_ready:
                replace_workflow_structure_from_source(
                    db, existing, master, sync_enrollments=True
                )
            db.commit()
            reloaded = _workflow_by_iso(db, country.iso2)
            assert reloaded is not None
            return reloaded
        return existing

    if source_ready:
        return _create_workflow_from_source(db, country, master)
    return _seed_workflow_skeleton(db, country)


def archive_country_workflow(
    db: Session,
    country_hint: str,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Remove a destination from the FlowX catalog (soft-archive).

    When force=True, active/paused student journeys are archived first so the
    country can leave the catalog.
    """
    if (country_hint or "").strip().upper() == MASTER_WORKFLOW_ISO2:
        raise ValueError("Cannot remove the Master Workflow")
    country = resolve_country(db, country_hint)
    workflow = _workflow_by_iso(db, country.iso2)
    if not workflow or workflow.status != "active":
        raise ValueError(f"No active FlowX workflow for {country.iso2}")
    open_enrollments = (
        db.query(FlowxEnrollment)
        .filter(
            FlowxEnrollment.country_workflow_id == workflow.id,
            FlowxEnrollment.status.in_(("active", "paused")),
        )
        .all()
    )
    if open_enrollments and not force:
        raise ValueError(
            f"Cannot remove {country.name}: {len(open_enrollments)} active student "
            "journey(s) still enrolled. Confirm Remove anyway to archive those journeys "
            "and remove the country."
        )
    if open_enrollments and force:
        now = utc_now()
        for enrollment in open_enrollments:
            enrollment.status = "archived"
            enrollment.updated_at = now
    workflow.status = "archived"
    workflow.updated_at = utc_now()
    db.commit()
    return workflow_to_summary(db, workflow)


def seed_default_country_workflows(db: Session, iso_codes: list[str] | None = None) -> int:
    """Ensure skeletons for destination countries. Returns count of newly created workflows."""
    if iso_codes is None:
        active = (
            db.query(Country)
            .filter(Country.is_active.is_(True))
            .order_by(Country.sort_order, Country.name)
            .all()
        )
        codes = [c.iso2 for c in active]
    else:
        codes = iso_codes
    created = 0
    for code in codes:
        country = db.query(Country).filter(Country.iso2 == code.upper()).first()
        if not country:
            continue
        before = _workflow_by_iso(db, country.iso2)
        ensure_country_workflow(db, country.iso2)
        if not before:
            created += 1
    return created


def _country_name(db: Session, iso2: str) -> str:
    if (iso2 or "").upper() == MASTER_WORKFLOW_ISO2:
        return "Master"
    row = db.query(Country).filter(Country.iso2 == iso2.upper()).first()
    return row.name if row else iso2.upper()


def _country_catalog_counts(db: Session, iso_codes: list[str]) -> dict[str, dict[str, int]]:
    """Batch institution / college / student counts keyed by ISO2."""
    codes = sorted({(c or "").strip().upper() for c in iso_codes if c and str(c).strip()})
    empty = {
        "institution_count": 0,
        "college_count": 0,
        "students_processed": 0,
        "students_in_process": 0,
    }
    if not codes:
        return {}

    out: dict[str, dict[str, int]] = {code: dict(empty) for code in codes}

    country_rows = (
        db.query(Country.id, Country.iso2)
        .filter(func.upper(Country.iso2).in_(codes))
        .all()
    )
    id_to_iso = {(cid): (iso or "").strip().upper() for cid, iso in country_rows if cid is not None}
    country_ids = list(id_to_iso.keys())

    if country_ids:
        # Institutions: prefer institution.country_id; also credit via campus.country_id.
        inst_ids_by_iso: dict[str, set[int]] = {code: set() for code in codes}

        for country_id, inst_id in (
            db.query(Institution.country_id, Institution.id)
            .filter(
                Institution.country_id.in_(country_ids),
                Institution.is_active.is_(True),
            )
            .all()
        ):
            iso = id_to_iso.get(country_id)
            if iso and inst_id is not None:
                inst_ids_by_iso[iso].add(int(inst_id))

        for country_id, inst_id in (
            db.query(Campus.country_id, Campus.institution_id)
            .join(Institution, Institution.id == Campus.institution_id)
            .filter(
                Campus.country_id.in_(country_ids),
                Institution.is_active.is_(True),
            )
            .all()
        ):
            iso = id_to_iso.get(country_id)
            if iso and inst_id is not None:
                inst_ids_by_iso[iso].add(int(inst_id))

        for iso, inst_ids in inst_ids_by_iso.items():
            out[iso]["institution_count"] = len(inst_ids)
            if not inst_ids:
                continue
            college_count = (
                db.query(func.count(College.id))
                .filter(
                    College.institution_id.in_(inst_ids),
                    College.is_active.is_(True),
                )
                .scalar()
            )
            out[iso]["college_count"] = int(college_count or 0)

    # Student journey counts from FlowX enrollments.
    enrollment_rows = (
        db.query(
            FlowxCountryWorkflow.country_iso2,
            FlowxEnrollment.status,
            func.count(FlowxEnrollment.id),
        )
        .join(
            FlowxEnrollment,
            FlowxEnrollment.country_workflow_id == FlowxCountryWorkflow.id,
        )
        .filter(func.upper(FlowxCountryWorkflow.country_iso2).in_(codes))
        .group_by(FlowxCountryWorkflow.country_iso2, FlowxEnrollment.status)
        .all()
    )
    for iso2, status, count in enrollment_rows:
        key = (iso2 or "").strip().upper()
        if key not in out:
            continue
        n = int(count or 0)
        if status == "completed":
            out[key]["students_processed"] += n
        elif status in ("active", "paused"):
            out[key]["students_in_process"] += n

    return out


def workflow_to_summary(
    db: Session,
    workflow: FlowxCountryWorkflow,
    *,
    catalog_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    stages = workflow.stages or []
    templates = sum(len(tr.task_templates or []) for st in stages for tr in (st.tracks or []))
    enroll_count = (
        db.query(FlowxEnrollment).filter(FlowxEnrollment.country_workflow_id == workflow.id).count()
    )
    iso = (workflow.country_iso2 or "").strip().upper()
    counts = catalog_counts if catalog_counts is not None else _country_catalog_counts(db, [iso]).get(iso, {})
    return {
        "id": workflow.id,
        "country_iso2": workflow.country_iso2,
        "country_name": _country_name(db, workflow.country_iso2),
        "name": workflow.name,
        "status": workflow.status,
        "stage_count": len(stages),
        "template_task_count": templates,
        "enrollment_count": enroll_count,
        "institution_count": int(counts.get("institution_count", 0)),
        "college_count": int(counts.get("college_count", 0)),
        "students_processed": int(counts.get("students_processed", 0)),
        "students_in_process": int(counts.get("students_in_process", 0)),
        "updated_at": workflow.updated_at,
    }


def _parse_action_steps(raw: str | None | list[str]) -> list[str]:
    if isinstance(raw, list):
        return [str(s).strip() for s in raw if str(s).strip()]
    if not raw:
        return []
    return [ln.strip() for ln in str(raw).splitlines() if ln.strip()]


def _format_action_steps(steps: list[str] | None) -> str | None:
    cleaned = _parse_action_steps(steps or [])
    return "\n".join(cleaned) if cleaned else None


def _template_brick_dict(
    tpl: FlowxTaskTemplate,
    *,
    stage: FlowxStage | None,
    track: FlowxTrack | None,
    link_count: int = 0,
) -> dict[str, Any]:
    return {
        "id": tpl.id,
        "track_id": tpl.track_id,
        "stage_id": stage.id if stage else (track.stage_id if track else None),
        "stage_key": stage.stage_key if stage else None,
        "track_name": track.track_name if track else None,
        "track_label": _track_label(track.track_name) if track else None,
        "title": tpl.title,
        "description": tpl.description,
        "action_steps": _parse_action_steps(getattr(tpl, "action_steps", None)),
        "position_index": tpl.position_index,
        "sla_days": tpl.sla_days,
        "is_country_specific": tpl.is_country_specific,
        "auto_trigger_source": tpl.auto_trigger_source,
        "is_active": bool(getattr(tpl, "is_active", True)),
        "is_optional": bool(getattr(tpl, "is_optional", False)),
        "override_action": getattr(tpl, "override_action", None),
        "override_reason": getattr(tpl, "override_reason", None),
        "link_count": link_count,
        "parent_template_id": getattr(tpl, "parent_template_id", None),
        "master_template_id": getattr(tpl, "master_template_id", None),
        "children": [],
    }


def _nest_stage_bricks(bricks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach child bricks under their parent; return top-level bricks only."""
    by_id = {b["id"]: b for b in bricks}
    for b in bricks:
        b["children"] = []
    top: list[dict[str, Any]] = []
    for b in bricks:
        parent_id = b.get("parent_template_id")
        if parent_id and parent_id in by_id:
            by_id[parent_id]["children"].append(b)
        else:
            top.append(b)
    for parent in top:
        parent["children"] = sorted(
            parent.get("children") or [],
            key=lambda x: (x.get("position_index", 0), x.get("title") or ""),
        )
    top.sort(key=lambda x: (x.get("position_index", 0), x.get("title") or ""))
    return top


def workflow_to_detail(db: Session, workflow: FlowxCountryWorkflow) -> dict[str, Any]:
    links = (
        db.query(FlowxSubprocessLink)
        .filter(FlowxSubprocessLink.workflow_id == workflow.id)
        .all()
    )
    link_counts: dict[uuid.UUID, int] = {}
    for link in links:
        link_counts[link.from_template_id] = link_counts.get(link.from_template_id, 0) + 1
        link_counts[link.to_template_id] = link_counts.get(link.to_template_id, 0) + 1

    title_by_id: dict[uuid.UUID, str] = {}
    stages_out = []
    unlinked: list[dict[str, Any]] = []

    for stage in sorted(workflow.stages or [], key=lambda s: s.position_index):
        tracks_out = []
        bricks: list[dict[str, Any]] = []
        for track in sorted(stage.tracks or [], key=lambda t: t.position_index):
            active_tpls = []
            for tpl in sorted(track.task_templates or [], key=lambda x: x.position_index):
                title_by_id[tpl.id] = tpl.title
                brick = _template_brick_dict(
                    tpl, stage=stage, track=track, link_count=link_counts.get(tpl.id, 0)
                )
                # Dropped (waive) stays on the country board; only structural unlink hides it.
                is_dropped = brick.get("override_action") == "waive"
                if brick["is_active"] or is_dropped:
                    if is_dropped:
                        brick["is_active"] = True
                    active_tpls.append(brick)
                    bricks.append(brick)
                else:
                    unlinked.append(brick)
            tracks_out.append(
                {
                    "id": track.id,
                    "stage_id": track.stage_id,
                    "track_name": track.track_name,
                    "track_label": _track_label(track.track_name),
                    "position_index": track.position_index,
                    "task_templates": active_tpls,
                }
            )
        nested_bricks = _nest_stage_bricks(bricks)
        stages_out.append(
            {
                "id": stage.id,
                "workflow_id": stage.workflow_id,
                "stage_key": stage.stage_key,
                "label": stage.label,
                "position_index": stage.position_index,
                "is_hidden": bool(getattr(stage, "is_hidden", False)),
                "tracks": tracks_out,
                "bricks": nested_bricks,
            }
        )

    enroll_count = (
        db.query(FlowxEnrollment).filter(FlowxEnrollment.country_workflow_id == workflow.id).count()
    )
    iso = (workflow.country_iso2 or "").strip().upper()
    counts = _country_catalog_counts(db, [iso]).get(iso, {})
    links_out = [
        {
            "id": link.id,
            "workflow_id": link.workflow_id,
            "from_template_id": link.from_template_id,
            "to_template_id": link.to_template_id,
            "from_title": title_by_id.get(link.from_template_id),
            "to_title": title_by_id.get(link.to_template_id),
            "link_type": link.link_type,
            "created_at": link.created_at,
        }
        for link in links
    ]
    return {
        "id": workflow.id,
        "country_iso2": workflow.country_iso2,
        "country_name": _country_name(db, workflow.country_iso2),
        "name": workflow.name,
        "status": workflow.status,
        "stages": stages_out,
        "links": links_out,
        "unlinked_bricks": unlinked,
        "enrollment_count": enroll_count,
        "institution_count": int(counts.get("institution_count", 0)),
        "college_count": int(counts.get("college_count", 0)),
        "students_processed": int(counts.get("students_processed", 0)),
        "students_in_process": int(counts.get("students_in_process", 0)),
        "is_master": (workflow.country_iso2 or "").upper() == MASTER_WORKFLOW_ISO2,
        "created_at": workflow.created_at,
        "updated_at": workflow.updated_at,
    }


def list_country_workflows(db: Session) -> list[dict[str, Any]]:
    """Return enabled country workflows only — does not auto-create missing destinations."""
    rows = (
        db.query(FlowxCountryWorkflow)
        .options(
            joinedload(FlowxCountryWorkflow.stages)
            .joinedload(FlowxStage.tracks)
            .joinedload(FlowxTrack.task_templates)
        )
        .filter(
            FlowxCountryWorkflow.status == "active",
            FlowxCountryWorkflow.country_iso2 != MASTER_WORKFLOW_ISO2,
        )
        .order_by(FlowxCountryWorkflow.country_iso2)
        .all()
    )
    catalog = _country_catalog_counts(db, [w.country_iso2 for w in rows])
    return [
        workflow_to_summary(
            db,
            w,
            catalog_counts=catalog.get(w.country_iso2.upper()),
        )
        for w in rows
    ]


def get_country_workflow(db: Session, iso2: str) -> dict[str, Any]:
    workflow = ensure_country_workflow(db, iso2)
    return workflow_to_detail(db, workflow)


def add_task_template(
    db: Session,
    track_id: uuid.UUID,
    *,
    title: str,
    description: str | None = None,
    action_steps: list[str] | None = None,
    sla_days: int = 7,
    parent_template_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    track = (
        db.query(FlowxTrack)
        .options(joinedload(FlowxTrack.task_templates), joinedload(FlowxTrack.stage))
        .filter(FlowxTrack.id == track_id)
        .first()
    )
    if not track or not track.stage:
        raise ValueError("Track not found")
    steps = _parse_action_steps(action_steps or [])
    if not steps:
        raise ValueError("Add at least one step to perform (one per line)")
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("Sub-process name is required")
    if description is None:
        clean_description = None
    else:
        words = description.strip().split()
        clean_description = " ".join(words[:5]) if words else ""

    if parent_template_id is not None:
        parent = (
            db.query(FlowxTaskTemplate)
            .options(joinedload(FlowxTaskTemplate.track).joinedload(FlowxTrack.stage))
            .filter(FlowxTaskTemplate.id == parent_template_id)
            .first()
        )
        if (
            not parent
            or not parent.track
            or not parent.track.stage
            or parent.track.stage.workflow_id != track.stage.workflow_id
        ):
            raise ValueError("Parent sub-process not found on this country workflow")
        if parent.parent_template_id:
            raise ValueError("Cannot nest under a nested sub-process")
        if parent.track_id != track_id:
            raise ValueError("Parent sub-process must be on the same process track")

    next_pos = max((t.position_index for t in (track.task_templates or [])), default=-1) + 1
    db.add(
        FlowxTaskTemplate(
            id=uuid.uuid4(),
            track_id=track_id,
            title=clean_title,
            description=clean_description,
            action_steps=_format_action_steps(steps),
            position_index=next_pos,
            sla_days=max(1, sla_days),
            parent_template_id=parent_template_id,
            is_country_specific=True,
            created_at=utc_now(),
        )
    )
    workflow_id = track.stage.workflow_id
    db.commit()
    workflow = _workflow_load(db, workflow_id)
    assert workflow is not None
    return workflow_to_detail(db, workflow)


def rename_global_process_label(
    db: Session,
    *,
    stage_key: str,
    label: str,
) -> dict[str, Any]:
    """Rename a main process across every country workflow that uses this stage_key."""
    if stage_key not in JOURNEY_STAGES:
        raise ValueError("Invalid process key")
    clean = (label or "").strip()
    if not clean:
        raise ValueError("Process name is required")
    if len(clean) > 128:
        raise ValueError("Process name is too long")

    stages = db.query(FlowxStage).filter(FlowxStage.stage_key == stage_key).all()
    if not stages:
        raise ValueError("No processes found for this key")

    now = utc_now()
    for stage in stages:
        stage.label = clean
        stage.updated_at = now

    # Keep seed defaults aligned for newly ensured countries in this process.
    JOURNEY_STAGE_LABELS[stage_key] = clean

    db.commit()
    return {
        "stage_key": stage_key,
        "label": clean,
        "countries_updated": len({s.workflow_id for s in stages}),
        "stages_updated": len(stages),
    }


def rename_task_template(
    db: Session,
    template_id: uuid.UUID,
    *,
    title: str | None = None,
    description: str | None = None,
    action_steps: list[str] | None = None,
) -> dict[str, Any]:
    """Update a single country's sub-process (does not touch Master or other countries).

    Global structure edits belong on Master Workflow (master_* helpers).
    """
    clean_title = (title or "").strip() if title is not None else None
    clean_description: str | None
    if description is None:
        clean_description = None
    else:
        words = (description or "").strip().split()
        clean_description = " ".join(words[:5]) if words else ""

    clean_steps: str | None
    if action_steps is None:
        clean_steps = None
    else:
        clean_steps = _format_action_steps(action_steps)

    if clean_title is None and clean_description is None and clean_steps is None:
        raise ValueError("Provide a title, definition, and/or steps to update")
    if clean_title is not None and not clean_title:
        raise ValueError("Sub-process name is required")
    if clean_title is not None and len(clean_title) > 255:
        raise ValueError("Sub-process name is too long")
    if action_steps is not None and not clean_steps:
        raise ValueError("Add at least one step to perform (one per line)")

    tpl = (
        db.query(FlowxTaskTemplate)
        .options(joinedload(FlowxTaskTemplate.track).joinedload(FlowxTrack.stage))
        .filter(FlowxTaskTemplate.id == template_id)
        .first()
    )
    if not tpl or not tpl.track or not tpl.track.stage:
        raise ValueError("Sub-process not found")

    workflow_id = tpl.track.stage.workflow_id
    workflow_row = (
        db.query(FlowxCountryWorkflow).filter(FlowxCountryWorkflow.id == workflow_id).first()
    )
    iso = (workflow_row.country_iso2 or "").upper() if workflow_row else ""
    if iso == MASTER_WORKFLOW_ISO2:
        raise ValueError("Use Master Workflow endpoints to edit the master process tree")

    if clean_title is not None:
        tpl.title = clean_title
    if clean_description is not None:
        tpl.description = clean_description or None
    if clean_steps is not None:
        tpl.action_steps = clean_steps

    if clean_title is not None or clean_description is not None:
        now = utc_now()
        enrollment_tasks = (
            db.query(FlowxTask)
            .join(FlowxEnrollmentTrack, FlowxTask.enrollment_track_id == FlowxEnrollmentTrack.id)
            .join(FlowxEnrollment, FlowxEnrollmentTrack.enrollment_id == FlowxEnrollment.id)
            .filter(
                FlowxEnrollment.country_workflow_id == workflow_id,
                FlowxEnrollmentTrack.track_name == tpl.track.track_name,
                FlowxEnrollmentTrack.stage_key == tpl.track.stage.stage_key,
                FlowxTask.position_index == tpl.position_index,
            )
            .all()
        )
        for task in enrollment_tasks:
            if clean_title is not None:
                task.title = clean_title
            if clean_description is not None:
                task.description = clean_description or None
            task.updated_at = now

    db.commit()
    workflow = _workflow_load(db, workflow_id)
    assert workflow is not None
    return workflow_to_detail(db, workflow)


def move_task_template(
    db: Session,
    template_id: uuid.UUID,
    *,
    target_stage_id: uuid.UUID,
    position_index: int = 0,
    track_name: str | None = None,
) -> dict[str, Any]:
    tpl = (
        db.query(FlowxTaskTemplate)
        .options(joinedload(FlowxTaskTemplate.track).joinedload(FlowxTrack.stage))
        .filter(FlowxTaskTemplate.id == template_id)
        .first()
    )
    if not tpl or not tpl.track or not tpl.track.stage:
        raise ValueError("Template not found")
    workflow_id = tpl.track.stage.workflow_id
    target_stage = (
        db.query(FlowxStage)
        .options(joinedload(FlowxStage.tracks).joinedload(FlowxTrack.task_templates))
        .filter(FlowxStage.id == target_stage_id, FlowxStage.workflow_id == workflow_id)
        .first()
    )
    if not target_stage:
        raise ValueError("Target stage not found on this workflow")

    target_track = _ensure_track_on_stage(db, target_stage, track_name or tpl.track.track_name)
    # Reindex top-level siblings only (nested children keep their own positions under parents).
    siblings = [
        t
        for t in (target_track.task_templates or [])
        if t.id != tpl.id
        and bool(getattr(t, "is_active", True))
        and not getattr(t, "parent_template_id", None)
    ]
    siblings.sort(key=lambda t: t.position_index)
    pos = max(0, min(position_index, len(siblings)))
    siblings.insert(pos, tpl)
    for idx, item in enumerate(siblings):
        item.position_index = idx
        item.track_id = target_track.id
    tpl.is_active = True
    tpl.track_id = target_track.id
    # Drag onto a stage column promotes the brick to top-level (clears nest parent).
    tpl.parent_template_id = None
    db.commit()
    workflow = _workflow_load(db, workflow_id)
    assert workflow is not None
    return workflow_to_detail(db, workflow)


def unlink_task_template(db: Session, template_id: uuid.UUID) -> dict[str, Any]:
    """Detach sub-process from its stage (soft unlink — recoverable)."""
    tpl = (
        db.query(FlowxTaskTemplate)
        .options(joinedload(FlowxTaskTemplate.track).joinedload(FlowxTrack.stage))
        .filter(FlowxTaskTemplate.id == template_id)
        .first()
    )
    if not tpl or not tpl.track or not tpl.track.stage:
        raise ValueError("Template not found")
    workflow_id = tpl.track.stage.workflow_id
    tpl.is_active = False
    db.commit()
    workflow = _workflow_load(db, workflow_id)
    assert workflow is not None
    return workflow_to_detail(db, workflow)


def _count_template_slot_usage(db: Session, tpl: FlowxTaskTemplate) -> int:
    if not tpl.track or not tpl.track.stage:
        return 0
    return int(
        db.query(func.count(FlowxTask.id))
        .join(FlowxEnrollmentTrack, FlowxTask.enrollment_track_id == FlowxEnrollmentTrack.id)
        .join(FlowxEnrollment, FlowxEnrollmentTrack.enrollment_id == FlowxEnrollment.id)
        .filter(
            FlowxEnrollment.country_workflow_id == tpl.track.stage.workflow_id,
            FlowxEnrollmentTrack.stage_key == tpl.track.stage.stage_key,
            FlowxEnrollmentTrack.track_name == tpl.track.track_name,
            FlowxTask.position_index == tpl.position_index,
        )
        .scalar()
        or 0
    )


def count_template_student_usage(db: Session, template_id: uuid.UUID) -> int:
    """How many student-journey tasks map to this brick or any nested child."""
    root = (
        db.query(FlowxTaskTemplate)
        .options(joinedload(FlowxTaskTemplate.track).joinedload(FlowxTrack.stage))
        .filter(FlowxTaskTemplate.id == template_id)
        .first()
    )
    if not root or not root.track or not root.track.stage:
        raise ValueError("Template not found")
    ids = _template_ids_with_descendants(db, root.id)
    templates = (
        db.query(FlowxTaskTemplate)
        .options(joinedload(FlowxTaskTemplate.track).joinedload(FlowxTrack.stage))
        .filter(FlowxTaskTemplate.id.in_(ids))
        .all()
    )
    return sum(_count_template_slot_usage(db, tpl) for tpl in templates)


def delete_task_template(db: Session, template_id: uuid.UUID) -> dict[str, Any]:
    """Hard-delete a country brick, nested children, and matching journey tasks."""
    root = (
        db.query(FlowxTaskTemplate)
        .options(joinedload(FlowxTaskTemplate.track).joinedload(FlowxTrack.stage))
        .filter(FlowxTaskTemplate.id == template_id)
        .first()
    )
    if not root or not root.track or not root.track.stage:
        raise ValueError("Template not found")
    workflow_id = root.track.stage.workflow_id
    delete_ids = _template_ids_with_descendants(db, root.id)
    affected_track_ids = _purge_templates_and_mapped_tasks(
        db, delete_ids, workflow_id=workflow_id
    )

    if affected_track_ids:
        for track in (
            db.query(FlowxEnrollmentTrack)
            .options(joinedload(FlowxEnrollmentTrack.tasks))
            .filter(FlowxEnrollmentTrack.id.in_(affected_track_ids))
            .all()
        ):
            _recompute_track_progress(track)
            track.updated_at = utc_now()

    db.commit()
    workflow = _workflow_load(db, workflow_id)
    assert workflow is not None
    return workflow_to_detail(db, workflow)


def relink_task_template(
    db: Session,
    template_id: uuid.UUID,
    *,
    target_stage_id: uuid.UUID,
    track_name: str | None = None,
    position_index: int = 0,
) -> dict[str, Any]:
    tpl = (
        db.query(FlowxTaskTemplate)
        .options(joinedload(FlowxTaskTemplate.track).joinedload(FlowxTrack.stage))
        .filter(FlowxTaskTemplate.id == template_id)
        .first()
    )
    if not tpl or not tpl.track or not tpl.track.stage:
        raise ValueError("Template not found")
    tpl.is_active = True
    return move_task_template(
        db,
        template_id,
        target_stage_id=target_stage_id,
        position_index=position_index,
        track_name=track_name,
    )


def link_subprocesses(
    db: Session,
    *,
    workflow_id: uuid.UUID,
    from_template_id: uuid.UUID,
    to_template_id: uuid.UUID,
    link_type: str = "depends_on",
) -> dict[str, Any]:
    if from_template_id == to_template_id:
        raise ValueError("Cannot link a sub-process to itself")
    if link_type not in ("depends_on", "related"):
        raise ValueError("Invalid link type")
    workflow = _workflow_load(db, workflow_id)
    if not workflow:
        raise ValueError("Workflow not found")
    ids = {
        tpl.id
        for stage in (workflow.stages or [])
        for track in (stage.tracks or [])
        for tpl in (track.task_templates or [])
    }
    if from_template_id not in ids or to_template_id not in ids:
        raise ValueError("Both templates must belong to this country workflow")
    existing = (
        db.query(FlowxSubprocessLink)
        .filter(
            FlowxSubprocessLink.from_template_id == from_template_id,
            FlowxSubprocessLink.to_template_id == to_template_id,
            FlowxSubprocessLink.link_type == link_type,
        )
        .first()
    )
    if not existing:
        db.add(
            FlowxSubprocessLink(
                id=uuid.uuid4(),
                workflow_id=workflow_id,
                from_template_id=from_template_id,
                to_template_id=to_template_id,
                link_type=link_type,
                created_at=utc_now(),
            )
        )
        db.commit()
    workflow = _workflow_load(db, workflow_id)
    assert workflow is not None
    return workflow_to_detail(db, workflow)


def unlink_subprocess_link(db: Session, link_id: uuid.UUID) -> dict[str, Any]:
    link = db.query(FlowxSubprocessLink).filter(FlowxSubprocessLink.id == link_id).first()
    if not link:
        raise ValueError("Link not found")
    workflow_id = link.workflow_id
    db.delete(link)
    db.commit()
    workflow = _workflow_load(db, workflow_id)
    assert workflow is not None
    return workflow_to_detail(db, workflow)


def override_task_template(
    db: Session,
    template_id: uuid.UUID,
    *,
    actor_id: int | None,
    action: str,
    reason: str,
) -> dict[str, Any]:
    if action not in ("waive", "make_optional", "force_required", "clear"):
        raise ValueError("Invalid override action")
    if not reason.strip() and action != "clear":
        raise ValueError("Reason is required")
    tpl = (
        db.query(FlowxTaskTemplate)
        .options(joinedload(FlowxTaskTemplate.track).joinedload(FlowxTrack.stage))
        .filter(FlowxTaskTemplate.id == template_id)
        .first()
    )
    if not tpl or not tpl.track or not tpl.track.stage:
        raise ValueError("Template not found")
    workflow_id = tpl.track.stage.workflow_id
    now = utc_now()
    if action == "clear":
        tpl.override_action = None
        tpl.override_reason = None
        tpl.overridden_at = None
        tpl.overridden_by = None
        tpl.is_optional = False
        tpl.is_active = True
    elif action == "waive":
        # Stay on the country board; skipped only when seeding student journeys.
        tpl.override_action = "waive"
        tpl.override_reason = reason.strip()
        tpl.overridden_at = now
        tpl.overridden_by = actor_id
        tpl.is_active = True
        tpl.is_optional = False
    elif action == "make_optional":
        tpl.override_action = "make_optional"
        tpl.override_reason = reason.strip()
        tpl.overridden_at = now
        tpl.overridden_by = actor_id
        tpl.is_optional = True
        tpl.is_active = True
    elif action == "force_required":
        tpl.override_action = "force_required"
        tpl.override_reason = reason.strip()
        tpl.overridden_at = now
        tpl.overridden_by = actor_id
        tpl.is_optional = False
        tpl.is_active = True
    db.commit()
    # Drop → Required/Optional must re-add tasks on existing student journeys.
    if sync_workflow_enrollments(db, workflow_id):
        db.commit()
    workflow = _workflow_load(db, workflow_id)
    assert workflow is not None
    return workflow_to_detail(db, workflow)


PATHWAY_TYPES = (
    "centralized_national_portal",
    "regional_clearing_agency",
    "direct_institutional_portal",
    "third_party_aggregator",
    "partner_portal",
    "paper_offline_route",
)
APPLICATION_STATUSES = (
    "drafting",
    "submitted",
    "under_review",
    "conditional_offer",
    "unconditional_offer",
    "rejected",
    "deferred",
)
FEE_STATUSES = ("not_required", "pending_payment", "paid", "fee_waiver")


def enroll_lead(
    db: Session,
    *,
    country_hint: str,
    lead_id: int,
    institution_id: int | None = None,
    college_id: int | None = None,
    campus_id: int | None = None,
    level_id: int | None = None,
    qualification_program_id: uuid.UUID | None = None,
    intake_id: int | None = None,
    pathway_type: str | None = None,
    pathway_name: str | None = None,
    custom_pathway_name: str | None = None,
    portal_url: str | None = None,
    portal_username: str | None = None,
    portal_password_hint: str | None = None,
    institutional_app_id: str | None = None,
    application_status: str | None = "drafting",
    fee_status: str | None = "not_required",
    fee_amount: float | None = None,
    fee_currency: str | None = "USD",
    internal_target_date: datetime | None = None,
    official_deadline: datetime | None = None,
) -> dict[str, Any]:
    from app.models.academia_wizard import InstitutionIntake
    from app.models.flowx import FlowxPathwayRegistry
    from app.models.level import Level
    from app.models.program import Program

    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.archived_at.is_(None)).first()
    if not lead:
        raise ValueError("Lead not found")

    workflow = ensure_country_workflow(db, country_hint)
    iso2 = (workflow.country_iso2 or "").strip().upper()

    resolved_institution_id = institution_id
    resolved_college_id = college_id
    university_name = None

    if college_id is not None:
        college = db.query(College).filter(College.id == college_id, College.is_active.is_(True)).first()
        if not college:
            raise ValueError("College not found")
        resolved_institution_id = college.institution_id
        if campus_id is None and college.campus_id:
            campus_id = college.campus_id
    if resolved_institution_id is not None:
        inst = (
            db.query(Institution)
            .filter(Institution.id == resolved_institution_id, Institution.is_active.is_(True))
            .first()
        )
        if not inst:
            raise ValueError("Institution not found")
        university_name = inst.name
        if inst.country_id is not None:
            country = db.query(Country).filter(Country.id == inst.country_id).first()
            if country and (country.iso2 or "").strip().upper() != iso2:
                raise ValueError(f"Institution does not belong to destination country {iso2}")

    if campus_id is not None:
        campus = db.query(Campus).filter(Campus.id == campus_id, Campus.is_active.is_(True)).first()
        if not campus:
            raise ValueError("Campus not found")
        if resolved_institution_id and campus.institution_id != resolved_institution_id:
            raise ValueError("Campus does not belong to selected institution")
        if resolved_institution_id is None:
            resolved_institution_id = campus.institution_id
            inst = db.query(Institution).filter(Institution.id == campus.institution_id).first()
            university_name = inst.name if inst else university_name

    if level_id is not None:
        if not db.query(Level).filter(Level.id == level_id).first():
            raise ValueError("Level not found")
    if qualification_program_id is not None:
        program = db.query(Program).filter(Program.id == qualification_program_id).first()
        if not program:
            raise ValueError("Program not found")
        if level_id is None:
            level_id = program.level_id
        elif program.level_id != level_id:
            raise ValueError("Program does not belong to selected level")
    if intake_id is not None:
        intake = db.query(InstitutionIntake).filter(InstitutionIntake.id == intake_id).first()
        if not intake:
            raise ValueError("Intake not found")
        if resolved_institution_id and intake.institution_id != resolved_institution_id:
            raise ValueError("Intake does not belong to selected institution")

    resolved_pathway_type = (pathway_type or "").strip() or None
    resolved_pathway_name = (custom_pathway_name or pathway_name or "").strip() or None
    if resolved_pathway_type and resolved_pathway_type not in PATHWAY_TYPES:
        raise ValueError("Invalid pathway type")
    if custom_pathway_name and custom_pathway_name.strip():
        if not resolved_pathway_type:
            raise ValueError("pathway_type required when creating a custom pathway")
        existing_path = (
            db.query(FlowxPathwayRegistry)
            .filter(func.lower(FlowxPathwayRegistry.pathway_name) == custom_pathway_name.strip().lower())
            .first()
        )
        if not existing_path:
            db.add(
                FlowxPathwayRegistry(
                    id=uuid.uuid4(),
                    pathway_type=resolved_pathway_type,
                    pathway_name=custom_pathway_name.strip(),
                    is_custom=True,
                )
            )
        resolved_pathway_name = custom_pathway_name.strip()

    app_status = (application_status or "drafting").strip()
    if app_status not in APPLICATION_STATUSES:
        raise ValueError("Invalid application status")
    resolved_fee_status = (fee_status or "not_required").strip()
    if resolved_fee_status not in FEE_STATUSES:
        raise ValueError("Invalid fee status")

    existing_q = db.query(FlowxEnrollment).filter(
        FlowxEnrollment.lead_id == lead_id,
        FlowxEnrollment.country_workflow_id == workflow.id,
    )
    if resolved_college_id is None:
        existing_q = existing_q.filter(FlowxEnrollment.college_id.is_(None))
    else:
        existing_q = existing_q.filter(FlowxEnrollment.college_id == resolved_college_id)
    if intake_id is None:
        existing_q = existing_q.filter(FlowxEnrollment.intake_id.is_(None))
    else:
        existing_q = existing_q.filter(FlowxEnrollment.intake_id == intake_id)
    existing = existing_q.first()
    if existing:
        return get_enrollment(db, existing.id)

    now = utc_now()
    enrollment = FlowxEnrollment(
        id=uuid.uuid4(),
        lead_id=lead_id,
        country_workflow_id=workflow.id,
        institution_id=resolved_institution_id,
        college_id=resolved_college_id,
        university_name=university_name,
        campus_id=campus_id,
        level_id=level_id,
        qualification_program_id=qualification_program_id,
        intake_id=intake_id,
        pathway_type=resolved_pathway_type,
        pathway_name=resolved_pathway_name,
        portal_url=(portal_url or None),
        portal_username=(portal_username or None),
        portal_password_hint=(portal_password_hint or None),
        institutional_app_id=(institutional_app_id or None),
        application_status=app_status,
        fee_status=resolved_fee_status,
        fee_amount=fee_amount,
        fee_currency=(fee_currency or "USD").upper()[:10],
        internal_target_date=internal_target_date,
        official_deadline=official_deadline,
        submitted_at=now if app_status == "submitted" else None,
        current_stage_key="counselling",
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.add(enrollment)
    db.flush()

    for stage in sorted(workflow.stages or [], key=lambda s: s.position_index):
        # Hidden stages (e.g. Canada Tests nested under Document readiness) stay off journeys.
        if bool(getattr(stage, "is_hidden", False)):
            continue
        for track in sorted(stage.tracks or [], key=lambda t: t.position_index):
            et = FlowxEnrollmentTrack(
                id=uuid.uuid4(),
                enrollment_id=enrollment.id,
                stage_key=stage.stage_key,
                track_name=track.track_name,
                position_index=track.position_index,
                track_status="not_started",
                progress_percentage=0,
                created_at=now,
                updated_at=now,
            )
            db.add(et)
            db.flush()
            for tpl in sorted(track.task_templates or [], key=lambda x: x.position_index):
                if not bool(getattr(tpl, "is_active", True)):
                    continue
                # Dropped country mode: never appear on the student journey.
                if getattr(tpl, "override_action", None) == "waive":
                    continue
                db.add(
                    FlowxTask(
                        id=uuid.uuid4(),
                        enrollment_track_id=et.id,
                        title=tpl.title,
                        description=tpl.description,
                        kanban_status="todo",
                        position_index=tpl.position_index,
                        sla_due_at=now + timedelta(days=tpl.sla_days or 7),
                        sla_status="on_track",
                        is_auto_added=bool(tpl.is_country_specific),
                        is_optional=bool(getattr(tpl, "is_optional", False)),
                        auto_trigger_source=tpl.auto_trigger_source,
                        created_at=now,
                        updated_at=now,
                    )
                )

    if not lead.preferred_country:
        lead.preferred_country = workflow.country_iso2

    db.commit()
    return get_enrollment(db, enrollment.id)


def _application_labels(db: Session, enrollment: FlowxEnrollment) -> dict[str, Any]:
    from app.models.academia_wizard import InstitutionIntake
    from app.models.level import Level
    from app.models.program import Program

    institution_name = enrollment.university_name
    college_name = None
    campus_name = None
    level_name = None
    program_name = None
    intake_name = None

    if enrollment.institution_id:
        inst = db.query(Institution).filter(Institution.id == enrollment.institution_id).first()
        if inst:
            institution_name = institution_name or inst.name
    if enrollment.college_id:
        college = db.query(College).filter(College.id == enrollment.college_id).first()
        college_name = college.name if college else None
        if college and not institution_name and college.institution_id:
            inst = db.query(Institution).filter(Institution.id == college.institution_id).first()
            institution_name = inst.name if inst else institution_name
    if enrollment.campus_id:
        campus = db.query(Campus).filter(Campus.id == enrollment.campus_id).first()
        campus_name = campus.name if campus else None
    if enrollment.level_id:
        level = db.query(Level).filter(Level.id == enrollment.level_id).first()
        level_name = level.name if level else None
    if enrollment.qualification_program_id:
        program = db.query(Program).filter(Program.id == enrollment.qualification_program_id).first()
        program_name = program.name if program else None
    if enrollment.intake_id:
        intake = db.query(InstitutionIntake).filter(InstitutionIntake.id == enrollment.intake_id).first()
        if intake:
            intake_name = intake.name or intake.term_name or f"Intake #{intake.id}"

    return {
        "institution_id": enrollment.institution_id,
        "institution_name": institution_name,
        "college_id": enrollment.college_id,
        "college_name": college_name,
        "university_name": institution_name,
        "campus_id": enrollment.campus_id,
        "campus_name": campus_name,
        "level_id": enrollment.level_id,
        "level_name": level_name,
        "qualification_program_id": enrollment.qualification_program_id,
        "program_name": program_name,
        "intake_id": enrollment.intake_id,
        "intake_name": intake_name,
        "pathway_type": enrollment.pathway_type,
        "pathway_name": enrollment.pathway_name,
        "portal_url": enrollment.portal_url,
        "portal_username": enrollment.portal_username,
        "portal_password_hint": enrollment.portal_password_hint,
        "institutional_app_id": enrollment.institutional_app_id,
        "application_status": getattr(enrollment, "application_status", None) or "drafting",
        "fee_status": getattr(enrollment, "fee_status", None) or "not_required",
        "fee_amount": float(enrollment.fee_amount) if enrollment.fee_amount is not None else None,
        "fee_currency": getattr(enrollment, "fee_currency", None) or "USD",
        "internal_target_date": enrollment.internal_target_date,
        "official_deadline": enrollment.official_deadline,
        "submitted_at": enrollment.submitted_at,
    }


def list_pathways(db: Session, pathway_type: str | None = None) -> list[dict[str, Any]]:
    from app.models.flowx import FlowxPathwayRegistry

    q = db.query(FlowxPathwayRegistry)
    if pathway_type:
        q = q.filter(FlowxPathwayRegistry.pathway_type == pathway_type)
    rows = q.order_by(FlowxPathwayRegistry.pathway_name.asc()).all()
    return [
        {
            "id": row.id,
            "pathway_type": row.pathway_type,
            "pathway_name": row.pathway_name,
            "is_custom": bool(row.is_custom),
        }
        for row in rows
    ]


def create_custom_pathway(db: Session, *, pathway_type: str, pathway_name: str) -> dict[str, Any]:
    from app.models.flowx import FlowxPathwayRegistry

    if pathway_type not in PATHWAY_TYPES:
        raise ValueError("Invalid pathway type")
    name = pathway_name.strip()
    if not name:
        raise ValueError("pathway_name required")
    existing = (
        db.query(FlowxPathwayRegistry)
        .filter(func.lower(FlowxPathwayRegistry.pathway_name) == name.lower())
        .first()
    )
    if existing:
        return {
            "id": existing.id,
            "pathway_type": existing.pathway_type,
            "pathway_name": existing.pathway_name,
            "is_custom": bool(existing.is_custom),
        }
    row = FlowxPathwayRegistry(
        id=uuid.uuid4(),
        pathway_type=pathway_type,
        pathway_name=name,
        is_custom=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "pathway_type": row.pathway_type,
        "pathway_name": row.pathway_name,
        "is_custom": True,
    }


def application_lookups(
    db: Session,
    *,
    institution_id: int | None = None,
    campus_id: int | None = None,
    college_id: int | None = None,
    level_id: int | None = None,
) -> dict[str, Any]:
    from app.models.academia_wizard import InstitutionIntake
    from app.models.level import Level
    from app.models.program import Program

    campuses: list[dict[str, Any]] = []
    colleges: list[dict[str, Any]] = []
    intakes: list[dict[str, Any]] = []
    if institution_id:
        campuses = [
            {"id": c.id, "name": c.name, "code": None}
            for c in (
                db.query(Campus)
                .filter(Campus.institution_id == institution_id, Campus.is_active.is_(True))
                .order_by(Campus.name.asc())
                .all()
            )
        ]
        college_q = db.query(College).filter(
            College.institution_id == institution_id, College.is_active.is_(True)
        )
        if campus_id:
            college_q = college_q.filter(
                (College.campus_id == campus_id) | (College.campus_id.is_(None))
            )
        colleges = [
            {"id": c.id, "name": c.name, "code": c.code}
            for c in college_q.order_by(College.name.asc()).all()
        ]
        intake_q = db.query(InstitutionIntake).filter(
            InstitutionIntake.institution_id == institution_id,
            InstitutionIntake.is_active.is_(True),
        )
        if campus_id:
            intake_q = intake_q.filter(
                (InstitutionIntake.campus_id == campus_id) | (InstitutionIntake.campus_id.is_(None))
            )
        if college_id:
            intake_q = intake_q.filter(
                ((InstitutionIntake.entity_type == "college") & (InstitutionIntake.entity_id == college_id))
                | (InstitutionIntake.entity_type == "institution")
                | (InstitutionIntake.entity_type.is_(None))
            )
        intakes = [
            {
                "id": i.id,
                "name": i.name or i.term_name or f"Intake {i.id}",
                "code": i.intake_code,
                "extra": {"year": i.year, "term_name": i.term_name, "status": i.status},
            }
            for i in intake_q.order_by(InstitutionIntake.year.desc().nullslast(), InstitutionIntake.name.asc()).all()
        ]

    levels = [
        {"id": lv.id, "name": lv.name, "code": lv.code}
        for lv in db.query(Level).order_by(Level.name.asc()).all()
    ]

    program_q = db.query(Program).filter(Program.is_active.is_(True))
    if level_id:
        program_q = program_q.filter(Program.level_id == level_id)
    programs = [
        {"id": str(p.id), "name": p.name, "code": p.code, "extra": {"level_id": p.level_id}}
        for p in program_q.order_by(Program.name.asc()).all()
    ]

    return {
        "campuses": campuses,
        "colleges": colleges,
        "levels": levels,
        "programs": programs,
        "intakes": intakes,
    }


def list_country_geography(
    db: Session,
    country_hint: str,
    *,
    state_id: int | None = None,
) -> dict[str, Any]:
    """States and cities for a destination country (Academia geography FKs)."""
    from app.models.academia_geography import GeographyCity, GeographyState

    country = resolve_country(db, country_hint)
    iso2 = (country.iso2 or "").strip().upper()
    states = (
        db.query(GeographyState)
        .filter(
            GeographyState.country_id == country.id,
            GeographyState.is_active.is_(True),
        )
        .order_by(GeographyState.sort_order.asc(), GeographyState.name.asc())
        .all()
    )
    city_q = db.query(GeographyCity).filter(
        GeographyCity.country_id == country.id,
        GeographyCity.is_active.is_(True),
    )
    if state_id is not None:
        city_q = city_q.filter(GeographyCity.state_id == state_id)
    cities = city_q.order_by(GeographyCity.sort_order.asc(), GeographyCity.name.asc()).all()
    return {
        "country_iso2": iso2,
        "country_id": country.id,
        "states": [{"id": s.id, "name": s.name, "state_id": None} for s in states],
        "cities": [{"id": c.id, "name": c.name, "state_id": c.state_id} for c in cities],
    }


def list_country_destinations(
    db: Session,
    country_hint: str,
    *,
    state_id: int | None = None,
    city_id: int | None = None,
) -> dict[str, Any]:
    """Institutions and colleges available for a FlowX destination country."""
    country = resolve_country(db, country_hint)
    iso2 = (country.iso2 or "").strip().upper()

    institutions = (
        db.query(Institution)
        .filter(Institution.country_id == country.id, Institution.is_active.is_(True))
        .order_by(Institution.name.asc())
        .all()
    )
    campus_inst_ids = {
        row[0]
        for row in (
            db.query(Campus.institution_id)
            .join(Institution, Institution.id == Campus.institution_id)
            .filter(Campus.country_id == country.id, Institution.is_active.is_(True))
            .all()
        )
        if row[0]
    }
    existing_ids = {i.id for i in institutions}
    extra_ids = campus_inst_ids - existing_ids
    if extra_ids:
        institutions.extend(
            db.query(Institution)
            .filter(Institution.id.in_(extra_ids), Institution.is_active.is_(True))
            .order_by(Institution.name.asc())
            .all()
        )
        institutions.sort(key=lambda i: (i.name or "").lower())

    if state_id is not None or city_id is not None:
        inst_ids = [i.id for i in institutions]
        campus_match_ids: set[int] = set()
        if inst_ids:
            campus_q = db.query(Campus.institution_id).filter(
                Campus.institution_id.in_(inst_ids),
                Campus.is_active.is_(True),
            )
            if city_id is not None:
                campus_q = campus_q.filter(Campus.location_id == city_id)
            elif state_id is not None:
                campus_q = campus_q.filter(Campus.state_id == state_id)
            campus_match_ids = {row[0] for row in campus_q.all() if row[0]}

        filtered: list[Institution] = []
        for inst in institutions:
            if city_id is not None:
                if inst.city_id == city_id or inst.id in campus_match_ids:
                    filtered.append(inst)
            elif state_id is not None:
                if inst.state_id == state_id or inst.id in campus_match_ids:
                    filtered.append(inst)
        institutions = filtered

    out = []
    for inst in institutions:
        colleges = (
            db.query(College)
            .filter(College.institution_id == inst.id, College.is_active.is_(True))
            .order_by(College.name.asc())
            .all()
        )
        out.append(
            {
                "id": inst.id,
                "name": inst.name,
                "state_id": inst.state_id,
                "city_id": inst.city_id,
                "colleges": [{"id": c.id, "name": c.name, "institution_id": inst.id} for c in colleges],
            }
        )
    return {"country_iso2": iso2, "institutions": out}


def _workflow_dropped_keys(
    workflow: FlowxCountryWorkflow | None,
) -> tuple[set[tuple[str, str, int]], set[tuple[str, str, str]]]:
    """Return (stage, track, position) and (stage, track, title_lower) for dropped templates."""
    by_pos: set[tuple[str, str, int]] = set()
    by_title: set[tuple[str, str, str]] = set()
    if not workflow:
        return by_pos, by_title
    for stage in workflow.stages or []:
        for track in stage.tracks or []:
            for tpl in track.task_templates or []:
                if bool(getattr(tpl, "is_active", True)) and getattr(tpl, "override_action", None) != "waive":
                    continue
                by_pos.add((stage.stage_key, track.track_name, tpl.position_index))
                by_title.add((stage.stage_key, track.track_name, (tpl.title or "").strip().lower()))
    return by_pos, by_title


def _task_is_dropped_for_workflow(
    *,
    stage_key: str,
    track_name: str,
    position_index: int,
    title: str,
    dropped_pos: set[tuple[str, str, int]],
    dropped_titles: set[tuple[str, str, str]],
) -> bool:
    if (stage_key, track_name, position_index) in dropped_pos:
        return True
    return (stage_key, track_name, (title or "").strip().lower()) in dropped_titles


def enrollment_to_dict(db: Session, enrollment: FlowxEnrollment, lead: Lead | None = None) -> dict[str, Any]:
    if lead is None:
        lead = db.query(Lead).filter(Lead.id == enrollment.lead_id).first()
    workflow = _workflow_load(db, enrollment.country_workflow_id)
    iso2 = workflow.country_iso2 if workflow else ""
    dropped_pos, dropped_titles = _workflow_dropped_keys(workflow)

    booking = _latest_counselling_booking_for_lead(db, enrollment.lead_id)
    status_id, booking_status = _resolve_intake_status_inputs(db, lead=lead, booking=booking)
    overdue = compute_intake_overdue(
        db,
        booking,
        status_definition_id=status_id,
        booking_status=booking_status,
    )
    intake_kanban, intake_sla, intake_progress = resolve_intake_session_state(
        status_definition_id=status_id,
        booking_status=booking_status,
        is_overdue=bool(overdue.get("is_overdue")),
    )

    # Country-workflow stage meta (labels / visibility) — journeys must mirror the country board.
    stages_out: list[dict[str, Any]] = []
    hidden_stage_keys: set[str] = set()
    if workflow:
        for stage in sorted(workflow.stages or [], key=lambda s: s.position_index):
            hidden = bool(getattr(stage, "is_hidden", False))
            if hidden:
                hidden_stage_keys.add(stage.stage_key)
            stages_out.append(
                {
                    "stage_key": stage.stage_key,
                    "label": stage.label
                    or JOURNEY_STAGE_LABELS.get(stage.stage_key, stage.stage_key),
                    "position_index": stage.position_index,
                    "is_hidden": hidden,
                }
            )
    else:
        for idx, key in enumerate(JOURNEY_STAGES):
            stages_out.append(
                {
                    "stage_key": key,
                    "label": JOURNEY_STAGE_LABELS.get(key, key),
                    "position_index": idx,
                    "is_hidden": False,
                }
            )

    # Template slot → id / parent for nesting on journey tasks.
    tpl_by_slot: dict[tuple[str, str, int], Any] = {}
    tpl_id_to_slot: dict[uuid.UUID, tuple[str, str, int]] = {}
    title_by_tpl: dict[uuid.UUID, str] = {}
    if workflow:
        for stage in workflow.stages or []:
            for track in stage.tracks or []:
                for tpl in track.task_templates or []:
                    slot = (stage.stage_key, track.track_name, tpl.position_index)
                    tpl_by_slot[slot] = tpl
                    tpl_id_to_slot[tpl.id] = slot
                    title_by_tpl[tpl.id] = tpl.title

    def visible_tasks(track: FlowxEnrollmentTrack) -> list[FlowxTask]:
        out: list[FlowxTask] = []
        for task in sorted(track.tasks or [], key=lambda x: (x.position_index, str(x.id))):
            if _task_is_dropped_for_workflow(
                stage_key=track.stage_key,
                track_name=track.track_name,
                position_index=task.position_index,
                title=task.title,
                dropped_pos=dropped_pos,
                dropped_titles=dropped_titles,
            ):
                continue
            out.append(task)
        return out

    tracks_out = []
    visible_all: list[FlowxTask] = []
    task_by_slot: dict[tuple[str, str, int], FlowxTask] = {}
    for track in sorted(
        enrollment.tracks or [],
        key=lambda t: (
            JOURNEY_STAGES.index(t.stage_key) if t.stage_key in JOURNEY_STAGES else 99,
            getattr(t, "position_index", 0),
            t.track_name,
        ),
    ):
        if track.stage_key in hidden_stage_keys:
            continue
        tasks = visible_tasks(track)
        visible_all.extend(tasks)
        for task in tasks:
            task_by_slot[(track.stage_key, track.track_name, task.position_index)] = task
        tracks_out.append(
            {
                "id": track.id,
                "enrollment_id": track.enrollment_id,
                "stage_key": track.stage_key,
                "track_name": track.track_name,
                "track_label": _track_label(track.track_name),
                "position_index": getattr(track, "position_index", 0),
                "track_status": track.track_status,
                "progress_percentage": track.progress_percentage,
                "tasks": [],
            }
        )
        task_dicts = tracks_out[-1]["tasks"]
        for task in tasks:
            tpl = tpl_by_slot.get((track.stage_key, track.track_name, task.position_index))
            is_intake = is_intake_session_task(task)
            task_dicts.append(
                {
                    "id": task.id,
                    "enrollment_track_id": task.enrollment_track_id,
                    "title": task.title,
                    "description": task.description,
                    "kanban_status": intake_kanban if is_intake else task.kanban_status,
                    "position_index": task.position_index,
                    "sla_due_at": task.sla_due_at,
                    "sla_status": intake_sla if is_intake else task.sla_status,
                    "progress_percentage": _task_progress_percentage(
                        task,
                        intake_progress=intake_progress,
                    ),
                    "is_auto_added": task.is_auto_added,
                    "is_optional": bool(getattr(task, "is_optional", False)),
                    "auto_trigger_source": task.auto_trigger_source,
                    "assigned_to": task.assigned_to,
                    "action_steps": _parse_action_steps(
                        getattr(tpl, "action_steps", None) if tpl is not None else None
                    ),
                    "checklist_state": getattr(task, "checklist_state", None),
                    "template_id": tpl.id if tpl is not None else None,
                    "parent_template_id": getattr(tpl, "parent_template_id", None)
                    if tpl is not None
                    else None,
                    "created_at": task.created_at,
                    "updated_at": task.updated_at,
                }
            )

    # Resolve country-board subprocess links onto this journey's visible tasks.

    link_rows = (
        db.query(FlowxSubprocessLink)
        .filter(FlowxSubprocessLink.workflow_id == enrollment.country_workflow_id)
        .all()
    )
    links_out: list[dict[str, Any]] = []
    for link in link_rows:
        from_slot = tpl_id_to_slot.get(link.from_template_id)
        to_slot = tpl_id_to_slot.get(link.to_template_id)
        from_task = task_by_slot.get(from_slot) if from_slot else None
        to_task = task_by_slot.get(to_slot) if to_slot else None
        from_title = (from_task.title if from_task else None) or title_by_tpl.get(
            link.from_template_id
        )
        to_title = (to_task.title if to_task else None) or title_by_tpl.get(link.to_template_id)
        if not from_title and not to_title:
            continue
        links_out.append(
            {
                "id": link.id,
                "workflow_id": link.workflow_id,
                "from_template_id": link.from_template_id,
                "to_template_id": link.to_template_id,
                "from_task_id": from_task.id if from_task else None,
                "to_task_id": to_task.id if to_task else None,
                "from_title": from_title,
                "to_title": to_title,
                "link_type": link.link_type,
                "created_at": link.created_at,
            }
        )

    return {
        "id": enrollment.id,
        "lead_id": enrollment.lead_id,
        "lead_name": lead.full_name if lead else None,
        "lead_phone": lead.phone_number if lead else None,
        "preferred_country": lead.preferred_country if lead else None,
        "country_iso2": iso2,
        "country_name": _country_name(db, iso2) if iso2 else "",
        "country_workflow_id": enrollment.country_workflow_id,
        **_application_labels(db, enrollment),
        "current_stage_key": enrollment.current_stage_key,
        "status": enrollment.status,
        "sla_health": (
            "breached"
            if overdue.get("is_overdue")
            else _sla_health(visible_all)
        ),
        "stages": stages_out,
        "tracks": tracks_out,
        "links": links_out,
        "intake_booking": _intake_booking_payload(db, lead=lead, booking=booking),
        "created_at": enrollment.created_at,
        "updated_at": enrollment.updated_at,
    }


def sync_enrollment_with_workflow(db: Session, enrollment: FlowxEnrollment) -> bool:
    """Align journey tasks with the country workflow (names, optional, dropped).

    - Titles/descriptions/is_optional follow current task templates
    - Dropped (waive) / inactive templates are removed from the journey
    - Missing active templates are added as new todo tasks
    Returns True when any change was applied.
    """
    # Always reload the full template tree — enrollment.workflow may be a shallow join.
    workflow = _workflow_load(db, enrollment.country_workflow_id)
    if not workflow:
        return False

    tpl_by_key: dict[tuple[str, str, int], FlowxTaskTemplate] = {}
    hidden_stage_keys: set[str] = set()
    for stage in workflow.stages or []:
        if bool(getattr(stage, "is_hidden", False)):
            hidden_stage_keys.add(stage.stage_key)
            continue
        for track in stage.tracks or []:
            for tpl in track.task_templates or []:
                tpl_by_key[(stage.stage_key, track.track_name, tpl.position_index)] = tpl

    dropped_pos, dropped_titles = _workflow_dropped_keys(workflow)
    any_changed = False
    now = utc_now()
    for et in enrollment.tracks or []:
        track_changed = False
        if et.stage_key in hidden_stage_keys:
            for task in list(et.tasks or []):
                db.delete(task)
                track_changed = True
            if track_changed:
                db.flush()
                db.refresh(et)
                _recompute_track_progress(et)
                et.updated_at = now
                any_changed = True
            continue
        tasks = list(et.tasks or [])
        seen_pos: set[int] = set()
        for task in tasks:
            key = (et.stage_key, et.track_name, task.position_index)
            tpl = tpl_by_key.get(key)
            dropped = _task_is_dropped_for_workflow(
                stage_key=et.stage_key,
                track_name=et.track_name,
                position_index=task.position_index,
                title=task.title,
                dropped_pos=dropped_pos,
                dropped_titles=dropped_titles,
            )
            if dropped or (
                tpl is not None
                and (
                    not bool(getattr(tpl, "is_active", True))
                    or getattr(tpl, "override_action", None) == "waive"
                )
            ):
                db.delete(task)
                track_changed = True
                continue
            if tpl is None:
                continue
            seen_pos.add(task.position_index)
            new_optional = bool(getattr(tpl, "is_optional", False))
            if (
                task.title != tpl.title
                or (task.description or None) != (tpl.description or None)
                or bool(getattr(task, "is_optional", False)) != new_optional
            ):
                task.title = tpl.title
                task.description = tpl.description
                task.is_optional = new_optional
                task.updated_at = now
                track_changed = True

        # Add templates that exist on the country board but not yet on this journey.
        for (stage_key, track_name, pos), tpl in tpl_by_key.items():
            if stage_key != et.stage_key or track_name != et.track_name:
                continue
            if pos in seen_pos:
                continue
            if not bool(getattr(tpl, "is_active", True)) or getattr(tpl, "override_action", None) == "waive":
                continue
            db.add(
                FlowxTask(
                    id=uuid.uuid4(),
                    enrollment_track_id=et.id,
                    title=tpl.title,
                    description=tpl.description,
                    kanban_status="todo",
                    position_index=pos,
                    sla_due_at=now + timedelta(days=tpl.sla_days or 7),
                    sla_status="on_track",
                    is_auto_added=bool(tpl.is_country_specific),
                    is_optional=bool(getattr(tpl, "is_optional", False)),
                    auto_trigger_source=tpl.auto_trigger_source,
                    created_at=now,
                    updated_at=now,
                )
            )
            track_changed = True

        if track_changed:
            db.flush()
            db.refresh(et)
            _recompute_track_progress(et)
            et.updated_at = now
            any_changed = True

    if any_changed:
        enrollment.updated_at = now
    return any_changed


def sync_workflow_enrollments(db: Session, workflow_id: uuid.UUID) -> int:
    """Re-sync every student journey on a country workflow. Returns changed count."""
    enrollments = (
        db.query(FlowxEnrollment)
        .options(joinedload(FlowxEnrollment.tracks).joinedload(FlowxEnrollmentTrack.tasks))
        .filter(FlowxEnrollment.country_workflow_id == workflow_id)
        .all()
    )
    changed = 0
    for enrollment in enrollments:
        if sync_enrollment_with_workflow(db, enrollment):
            changed += 1
    return changed


def get_enrollment(db: Session, enrollment_id: uuid.UUID) -> dict[str, Any]:
    enrollment = _enrollment_load(db, enrollment_id)
    if not enrollment:
        raise ValueError("Enrollment not found")
    if sync_enrollment_with_workflow(db, enrollment):
        db.commit()
        enrollment = _enrollment_load(db, enrollment_id)
        assert enrollment is not None
    # Keep Intake Session (1.1) aligned with my-bookings / status_definitions.
    if sync_intake_session_for_lead(db, enrollment.lead_id, commit=True):
        enrollment = _enrollment_load(db, enrollment_id)
        assert enrollment is not None
    return enrollment_to_dict(db, enrollment)


def list_enrollments(
    db: Session,
    *,
    country_iso2: str | None = None,
    status: str | None = None,
    q: str | None = None,
    lead_id: int | None = None,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], int]:
    query = (
        db.query(FlowxEnrollment, Lead, FlowxCountryWorkflow)
        .join(Lead, Lead.id == FlowxEnrollment.lead_id)
        .join(FlowxCountryWorkflow, FlowxCountryWorkflow.id == FlowxEnrollment.country_workflow_id)
        .options(joinedload(FlowxEnrollment.tracks).joinedload(FlowxEnrollmentTrack.tasks))
        .filter(Lead.archived_at.is_(None))
    )
    if lead_id is not None:
        query = query.filter(FlowxEnrollment.lead_id == lead_id)
    if country_iso2:
        query = query.filter(FlowxCountryWorkflow.country_iso2 == country_iso2.upper())
    if status:
        query = query.filter(FlowxEnrollment.status == status)
    if q:
        query = query.filter(Lead.full_name.ilike(f"%{q.strip()}%"))

    rows = query.order_by(FlowxEnrollment.updated_at.desc()).limit(max(1, min(limit, 200))).all()
    items = []
    for enrollment, lead, workflow in rows:
        all_tasks = []
        enr = _enrollment_load(db, enrollment.id)
        if enr:
            all_tasks = [t for tr in (enr.tracks or []) for t in (tr.tasks or [])]
        labels = _application_labels(db, enrollment)
        booking = _latest_counselling_booking_for_lead(db, lead.id)
        status_id, booking_status = _resolve_intake_status_inputs(db, lead=lead, booking=booking)
        overdue = compute_intake_overdue(
            db,
            booking,
            status_definition_id=status_id,
            booking_status=booking_status,
        )
        sla_health = "breached" if overdue.get("is_overdue") else _sla_health(all_tasks)
        items.append(
            {
                "id": enrollment.id,
                "lead_id": lead.id,
                "lead_name": lead.full_name or f"Lead #{lead.id}",
                "country_iso2": workflow.country_iso2,
                "country_name": _country_name(db, workflow.country_iso2),
                "institution_id": labels.get("institution_id"),
                "institution_name": labels.get("institution_name"),
                "college_id": labels.get("college_id"),
                "college_name": labels.get("college_name"),
                "university_name": labels.get("university_name"),
                "campus_name": labels.get("campus_name"),
                "program_name": labels.get("program_name"),
                "intake_name": labels.get("intake_name"),
                "pathway_name": labels.get("pathway_name"),
                "application_status": labels.get("application_status") or "drafting",
                "current_stage_key": enrollment.current_stage_key,
                "status": enrollment.status,
                "sla_health": sla_health,
                "intake_overdue": bool(overdue.get("is_overdue")),
                "intake_delay_label": overdue.get("delay_label"),
                "updated_at": enrollment.updated_at,
            }
        )
    return items, len(items)


def get_ops_overview(db: Session) -> dict[str, Any]:
    """Tier-1 Ops Dashboard aggregates for active Country Workflow destinations only."""
    country_rows = list_country_workflows(db)
    catalog_by_iso = {(r.get("country_iso2") or "").upper(): r for r in country_rows}
    active_isos = set(catalog_by_iso.keys())

    # Seed cards only from Country Workflows (active destinations) — never pad extras.
    per_country: dict[str, dict[str, Any]] = {}
    for iso, cat in catalog_by_iso.items():
        if iso == MASTER_WORKFLOW_ISO2:
            continue
        per_country[iso] = {
            "country_iso2": iso,
            "country_name": cat.get("country_name") or _country_name(db, iso),
            "active_applications": 0,
            "delayed_count": 0,
            "at_risk_count": 0,
            "on_track_count": 0,
            "students_processed": int(cat.get("students_processed") or 0),
            "students_in_process": int(cat.get("students_in_process") or 0),
            "institution_count": int(cat.get("institution_count") or 0),
            "college_count": int(cat.get("college_count") or 0),
            "stage_counts": {k: 0 for k in JOURNEY_STAGES},
        }

    query = (
        db.query(FlowxEnrollment, FlowxCountryWorkflow)
        .join(FlowxCountryWorkflow, FlowxCountryWorkflow.id == FlowxEnrollment.country_workflow_id)
        .join(Lead, Lead.id == FlowxEnrollment.lead_id)
        .options(joinedload(FlowxEnrollment.tracks).joinedload(FlowxEnrollmentTrack.tasks))
        .filter(
            Lead.archived_at.is_(None),
            FlowxEnrollment.status.in_(("active", "paused")),
            FlowxCountryWorkflow.status == "active",
            FlowxCountryWorkflow.country_iso2 != MASTER_WORKFLOW_ISO2,
        )
    )
    rows = query.order_by(FlowxEnrollment.updated_at.desc()).limit(800).all()

    bottleneck_map: dict[tuple[str, str], dict[str, Any]] = {}
    visas_in_process = 0
    landed_candidates = 0

    for enrollment, workflow in rows:
        iso = (workflow.country_iso2 or "").upper()
        # Skip journeys for destinations not on the Country Workflows catalog.
        if iso not in active_isos or iso not in per_country:
            continue
        bucket = per_country[iso]
        bucket["active_applications"] += 1
        stage = (
            enrollment.current_stage_key
            if enrollment.current_stage_key in JOURNEY_STAGES
            else "counselling"
        )
        bucket["stage_counts"][stage] = bucket["stage_counts"].get(stage, 0) + 1
        if stage == "visa_processing":
            visas_in_process += 1
        if stage == "landing":
            landed_candidates += 1

        tasks = [t for tr in (enrollment.tracks or []) for t in (tr.tasks or [])]
        health = _sla_health(tasks)
        if health == "breached":
            bucket["delayed_count"] += 1
        elif health == "amber":
            bucket["at_risk_count"] += 1
        else:
            bucket["on_track_count"] += 1

        if health in ("breached", "amber"):
            key = (iso, stage)
            if key not in bottleneck_map:
                bottleneck_map[key] = {
                    "country_iso2": iso,
                    "country_name": bucket["country_name"],
                    "stage_key": stage,
                    "stage_label": JOURNEY_STAGE_LABELS.get(stage, stage),
                    "delayed_count": 0,
                    "at_risk_count": 0,
                }
            if health == "breached":
                bottleneck_map[key]["delayed_count"] += 1
            else:
                bottleneck_map[key]["at_risk_count"] += 1

    countries_out: list[dict[str, Any]] = []
    for iso, bucket in sorted(
        per_country.items(),
        key=lambda x: (-x[1]["active_applications"], x[0]),
    ):
        # Ops lists only destinations with open journeys — template-only countries
        # stay on Configure → Country Workflows and must not clutter the dashboard.
        if int(bucket.get("active_applications") or 0) <= 0:
            continue
        stage_counts = bucket.pop("stage_counts")
        top_stage = max(stage_counts.items(), key=lambda kv: kv[1]) if stage_counts else (None, 0)
        top_key = top_stage[0] if top_stage and top_stage[1] > 0 else None
        countries_out.append(
            {
                **bucket,
                "top_stage_key": top_key,
                "top_stage_label": JOURNEY_STAGE_LABELS.get(top_key, top_key) if top_key else None,
            }
        )

    bottlenecks = sorted(
        bottleneck_map.values(),
        key=lambda b: (-(b["delayed_count"] + b["at_risk_count"]), b["country_iso2"]),
    )[:12]

    total_active = sum(c["active_applications"] for c in countries_out)
    total_delayed = sum(c["delayed_count"] for c in countries_out)
    total_at_risk = sum(c["at_risk_count"] for c in countries_out)
    total_on_track = sum(c["on_track_count"] for c in countries_out)

    return {
        "total_active": total_active,
        "total_delayed": total_delayed,
        "total_at_risk": total_at_risk,
        "total_on_track": total_on_track,
        "visas_in_process": visas_in_process,
        "landed_candidates": landed_candidates,
        "countries": countries_out,
        "bottlenecks": bottlenecks,
    }


def board_by_country(db: Session, country_iso2: str | None = None) -> dict[str, Any]:
    query = (
        db.query(FlowxEnrollment, Lead, FlowxCountryWorkflow)
        .join(Lead, Lead.id == FlowxEnrollment.lead_id)
        .join(FlowxCountryWorkflow, FlowxCountryWorkflow.id == FlowxEnrollment.country_workflow_id)
        .filter(Lead.archived_at.is_(None), FlowxEnrollment.status == "active")
    )
    if country_iso2:
        query = query.filter(FlowxCountryWorkflow.country_iso2 == country_iso2.upper())
    rows = query.order_by(FlowxEnrollment.updated_at.desc()).limit(300).all()

    columns: dict[str, list[dict[str, Any]]] = {k: [] for k in JOURNEY_STAGES}
    for enrollment, lead, workflow in rows:
        enr = _enrollment_load(db, enrollment.id)
        tasks = [t for tr in (enr.tracks or []) for t in (tr.tasks or [])] if enr else []
        stage = enrollment.current_stage_key if enrollment.current_stage_key in columns else "counselling"
        labels = _application_labels(db, enrollment)
        columns[stage].append(
            {
                "enrollment_id": enrollment.id,
                "lead_id": lead.id,
                "lead_name": lead.full_name or f"Lead #{lead.id}",
                "country_iso2": workflow.country_iso2,
                "country_name": _country_name(db, workflow.country_iso2),
                "institution_name": labels.get("institution_name"),
                "college_name": labels.get("college_name"),
                "current_stage_key": enrollment.current_stage_key,
                "status": enrollment.status,
                "sla_health": _sla_health(tasks),
            }
        )
    return {
        "country_iso2": country_iso2.upper() if country_iso2 else None,
        "columns": [
            {"stage_key": key, "label": JOURNEY_STAGE_LABELS[key], "cards": columns[key]}
            for key in JOURNEY_STAGES
        ],
    }


def update_enrollment_stage(
    db: Session,
    enrollment_id: uuid.UUID,
    *,
    stage_key: str,
    client_updated_at: datetime | None,
) -> dict[str, Any]:
    if stage_key not in JOURNEY_STAGES:
        raise ValueError("Invalid stage")
    enrollment = _enrollment_load(db, enrollment_id)
    if not enrollment:
        raise ValueError("Enrollment not found")
    if client_updated_at and enrollment.updated_at:
        server_ts = enrollment.updated_at
        client_ts = client_updated_at
        if server_ts.tzinfo and client_ts.tzinfo is None:
            client_ts = client_ts.replace(tzinfo=timezone.utc)
        if client_ts < server_ts:
            raise ValueError("Enrollment was updated by another session — refresh and retry")
    enrollment.current_stage_key = stage_key
    enrollment.updated_at = utc_now()
    db.commit()
    return get_enrollment(db, enrollment_id)


def move_enrollment_track(
    db: Session,
    track_id: uuid.UUID,
    *,
    position_index: int,
    client_updated_at: datetime | None = None,
) -> dict[str, Any]:
    """Reorder a sub-process (enrollment track) within its parent process/stage."""
    track = (
        db.query(FlowxEnrollmentTrack)
        .options(
            joinedload(FlowxEnrollmentTrack.enrollment).joinedload(FlowxEnrollment.tracks)
        )
        .filter(FlowxEnrollmentTrack.id == track_id)
        .first()
    )
    if not track or not track.enrollment:
        raise ValueError("Sub-process not found")

    enrollment = track.enrollment
    if client_updated_at and enrollment.updated_at:
        server_ts = enrollment.updated_at
        client_ts = client_updated_at
        if server_ts.tzinfo and client_ts.tzinfo is None:
            client_ts = client_ts.replace(tzinfo=timezone.utc)
        if client_ts < server_ts:
            raise ValueError("Enrollment was updated by another session — refresh and retry")

    siblings = [
        t
        for t in (enrollment.tracks or [])
        if t.stage_key == track.stage_key and t.id != track.id
    ]
    siblings.sort(key=lambda t: (getattr(t, "position_index", 0), t.track_name, str(t.id)))
    pos = max(0, min(position_index, len(siblings)))
    siblings.insert(pos, track)
    now = utc_now()
    for idx, item in enumerate(siblings):
        item.position_index = idx
        item.updated_at = now
    enrollment.updated_at = now
    db.commit()
    return get_enrollment(db, enrollment.id)


def move_task(
    db: Session,
    task_id: uuid.UUID,
    *,
    kanban_status: str,
    position_index: int,
    client_updated_at: datetime | None,
) -> dict[str, Any]:
    if kanban_status not in KANBAN_STATUSES:
        raise ValueError("Invalid kanban status")
    task = (
        db.query(FlowxTask)
        .options(
            joinedload(FlowxTask.enrollment_track)
            .joinedload(FlowxEnrollmentTrack.enrollment)
            .joinedload(FlowxEnrollment.tracks)
            .joinedload(FlowxEnrollmentTrack.tasks)
        )
        .filter(FlowxTask.id == task_id)
        .first()
    )
    if not task:
        raise ValueError("Task not found")
    if client_updated_at and task.updated_at:
        server_ts = task.updated_at
        client_ts = client_updated_at
        if server_ts.tzinfo and client_ts.tzinfo is None:
            client_ts = client_ts.replace(tzinfo=timezone.utc)
        if client_ts < server_ts:
            raise ValueError("Task was updated by another session — refresh and retry")

    task.kanban_status = kanban_status
    task.position_index = max(0, position_index)
    task.updated_at = utc_now()
    if task.enrollment_track:
        _recompute_track_progress(task.enrollment_track)
        task.enrollment_track.updated_at = utc_now()
        if task.enrollment_track.enrollment:
            task.enrollment_track.enrollment.updated_at = utc_now()
    db.commit()
    assert task.enrollment_track is not None
    return get_enrollment(db, task.enrollment_track.enrollment_id)


def update_task_checklist(
    db: Session,
    task_id: uuid.UUID,
    *,
    checked: list[bool],
    confirmed_complete: bool,
    steps: list[str] | None = None,
    actor_id: int | None = None,
    client_updated_at: datetime | None = None,
) -> dict[str, Any]:
    """Persist activity checklist ticks / confirmation on a journey task."""
    task = (
        db.query(FlowxTask)
        .options(
            joinedload(FlowxTask.enrollment_track)
            .joinedload(FlowxEnrollmentTrack.enrollment)
        )
        .filter(FlowxTask.id == task_id)
        .first()
    )
    if not task:
        raise ValueError("Task not found")
    if client_updated_at and task.updated_at:
        server_ts = task.updated_at
        client_ts = client_updated_at
        if server_ts.tzinfo and client_ts.tzinfo is None:
            client_ts = client_ts.replace(tzinfo=timezone.utc)
        # Soft conflict: still accept checklist saves so rapid toggles are not blocked
        # by concurrent enrollment refreshes that bump updated_at.

    clean_steps = [str(s).strip() for s in (steps or []) if str(s).strip()]
    clean_checked = [bool(v) for v in (checked or [])]
    if clean_steps and len(clean_checked) < len(clean_steps):
        clean_checked.extend([False] * (len(clean_steps) - len(clean_checked)))
    if clean_steps and len(clean_checked) > len(clean_steps):
        clean_checked = clean_checked[: len(clean_steps)]

    all_done = bool(clean_checked) and all(clean_checked)
    confirmed = bool(confirmed_complete) and all_done
    now = utc_now()
    task.checklist_state = {
        "checked": clean_checked,
        "confirmed_complete": confirmed,
        "steps": clean_steps,
        "updated_by": actor_id,
        "updated_at": now.isoformat(),
    }
    task.updated_at = now
    if task.enrollment_track:
        task.enrollment_track.updated_at = now
        if task.enrollment_track.enrollment:
            task.enrollment_track.enrollment.updated_at = now
    db.commit()
    assert task.enrollment_track is not None
    return get_enrollment(db, task.enrollment_track.enrollment_id)


def reorder_enrollment_task(
    db: Session,
    task_id: uuid.UUID,
    *,
    position_index: int,
    client_updated_at: datetime | None = None,
) -> dict[str, Any]:
    """Reorder a child process within its parent sub-process (enrollment track)."""
    task = (
        db.query(FlowxTask)
        .options(
            joinedload(FlowxTask.enrollment_track)
            .joinedload(FlowxEnrollmentTrack.enrollment)
            .joinedload(FlowxEnrollment.tracks)
            .joinedload(FlowxEnrollmentTrack.tasks)
        )
        .filter(FlowxTask.id == task_id)
        .first()
    )
    if not task or not task.enrollment_track:
        raise ValueError("Child process not found")

    if client_updated_at and task.updated_at:
        server_ts = task.updated_at
        client_ts = client_updated_at
        if server_ts.tzinfo and client_ts.tzinfo is None:
            client_ts = client_ts.replace(tzinfo=timezone.utc)
        if client_ts < server_ts:
            raise ValueError("Task was updated by another session — refresh and retry")

    track = task.enrollment_track
    siblings = [t for t in (track.tasks or []) if t.id != task.id]
    siblings.sort(key=lambda t: (t.position_index, str(t.id)))
    pos = max(0, min(position_index, len(siblings)))
    siblings.insert(pos, task)
    now = utc_now()
    for idx, item in enumerate(siblings):
        item.position_index = idx
        item.updated_at = now
    track.updated_at = now
    if track.enrollment:
        track.enrollment.updated_at = now
    db.commit()
    return get_enrollment(db, track.enrollment_id)


def create_enrollment_task(
    db: Session,
    enrollment_track_id: uuid.UUID,
    *,
    title: str,
    description: str | None = None,
    kanban_status: str = "todo",
    sla_due_at: datetime | None = None,
    assigned_to: int | None = None,
    is_auto_added: bool = False,
    auto_trigger_source: str | None = None,
) -> dict[str, Any]:
    track = (
        db.query(FlowxEnrollmentTrack)
        .options(joinedload(FlowxEnrollmentTrack.tasks))
        .filter(FlowxEnrollmentTrack.id == enrollment_track_id)
        .first()
    )
    if not track:
        raise ValueError("Enrollment track not found")
    next_pos = max((t.position_index for t in (track.tasks or [])), default=-1) + 1
    now = utc_now()
    db.add(
        FlowxTask(
            id=uuid.uuid4(),
            enrollment_track_id=enrollment_track_id,
            title=title.strip(),
            description=description,
            kanban_status=kanban_status if kanban_status in KANBAN_STATUSES else "todo",
            position_index=next_pos,
            sla_due_at=sla_due_at or (now + timedelta(days=7)),
            sla_status="on_track",
            is_auto_added=is_auto_added,
            auto_trigger_source=auto_trigger_source,
            assigned_to=assigned_to,
            created_at=now,
            updated_at=now,
        )
    )
    _recompute_track_progress(track)
    track.updated_at = now
    db.commit()
    return get_enrollment(db, track.enrollment_id)


def apply_override(
    db: Session,
    enrollment_id: uuid.UUID,
    *,
    actor_id: int | None,
    action_type: str,
    target_entity: str,
    reason: str,
    evidence_url: str | None = None,
    track_name: str | None = None,
    stage_key: str | None = None,
    title: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    if action_type not in AUDIT_ACTIONS:
        raise ValueError("Invalid override action")
    if not reason.strip():
        raise ValueError("Reason is required")
    enrollment = _enrollment_load(db, enrollment_id)
    if not enrollment:
        raise ValueError("Enrollment not found")

    if action_type == "add_custom_task":
        if not title or not track_name:
            raise ValueError("title and track_name required for add_custom_task")
        sk = stage_key or enrollment.current_stage_key
        track = next(
            (t for t in (enrollment.tracks or []) if t.track_name == track_name and t.stage_key == sk),
            None,
        )
        if not track:
            track = next((t for t in (enrollment.tracks or []) if t.track_name == track_name), None)
        if not track:
            raise ValueError("Track not found on enrollment")
        create_enrollment_task(
            db,
            track.id,
            title=title,
            description=description,
            is_auto_added=False,
        )
        enrollment = _enrollment_load(db, enrollment_id)
        assert enrollment is not None

    elif action_type == "fast_forward":
        idx = JOURNEY_STAGES.index(enrollment.current_stage_key) if enrollment.current_stage_key in JOURNEY_STAGES else 0
        if idx < len(JOURNEY_STAGES) - 1:
            enrollment.current_stage_key = JOURNEY_STAGES[idx + 1]
            enrollment.updated_at = utc_now()

    elif action_type == "waive_step":
        # Mark matching tasks approved when target_entity matches a task title fragment
        for track in enrollment.tracks or []:
            for task in track.tasks or []:
                if target_entity.lower() in task.title.lower() or str(task.id) == target_entity:
                    task.kanban_status = "approved"
                    task.updated_at = utc_now()
            _recompute_track_progress(track)

    elif action_type == "override_sla":
        for track in enrollment.tracks or []:
            for task in track.tasks or []:
                if task.sla_status in ("amber", "breached"):
                    task.sla_status = "on_track"
                    task.sla_due_at = utc_now() + timedelta(days=3)
                    task.updated_at = utc_now()

    db.add(
        FlowxAuditLog(
            id=uuid.uuid4(),
            enrollment_id=enrollment_id,
            actor_id=actor_id,
            action_type=action_type,
            target_entity=target_entity,
            reason=reason.strip(),
            evidence_url=evidence_url,
            created_at=utc_now(),
        )
    )
    enrollment.updated_at = utc_now()
    db.commit()
    return get_enrollment(db, enrollment_id)


def list_audit_logs(db: Session, enrollment_id: uuid.UUID, *, limit: int = 50) -> list[FlowxAuditLog]:
    return (
        db.query(FlowxAuditLog)
        .filter(FlowxAuditLog.enrollment_id == enrollment_id)
        .order_by(FlowxAuditLog.created_at.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )


def evaluate_sla_breach(db: Session) -> int:
    now = utc_now()
    amber_cutoff = now + timedelta(hours=24)
    tasks = (
        db.query(FlowxTask)
        .filter(
            FlowxTask.sla_due_at.isnot(None),
            FlowxTask.kanban_status.notin_(["approved"]),
            FlowxTask.sla_status != "breached",
        )
        .all()
    )
    changed = 0
    for task in tasks:
        due = task.sla_due_at
        if due is None:
            continue
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        if due < now:
            task.sla_status = "breached"
            task.updated_at = now
            changed += 1
        elif due <= amber_cutoff and task.sla_status == "on_track":
            task.sla_status = "amber"
            task.updated_at = now
            changed += 1
    if changed:
        db.commit()
    return changed


def list_workflow_rules(db: Session) -> list[FlowxWorkflowRule]:
    return db.query(FlowxWorkflowRule).order_by(FlowxWorkflowRule.created_at.desc()).all()


def create_workflow_rule(
    db: Session,
    *,
    rule_name: str,
    trigger_condition: dict,
    action_payload: dict,
    is_active: bool = True,
) -> FlowxWorkflowRule:
    row = FlowxWorkflowRule(
        id=uuid.uuid4(),
        rule_name=rule_name,
        trigger_condition=trigger_condition,
        action_payload=action_payload,
        is_active=is_active,
        created_at=utc_now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
