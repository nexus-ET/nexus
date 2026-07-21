from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.attributes import flag_modified

from app.models.academia_institution import Campus, College, Institution
from app.models.academia_wizard import (
    InstitutionCourseOffering,
    InstitutionIntake,
    InstitutionPicture,
    InstitutionWizardDraft,
)
from app.models.program import Program
from app.models.education_major import EducationMajor
from app.models.target_course import TargetCourse
from app.schemas.academia_hub import (
    CampusCreate,
    CampusUpdate,
    CollegeCreate,
    CollegeUpdate,
    InstitutionCreate,
)
from app.schemas.academia_wizard import (
    WizardCampusStep,
    WizardCampusSyncStep,
    WizardCollegeItem,
    WizardCollegeSyncItem,
    WizardInstitutionStep,
    WizardPayload,
    WizardStepSaveRequest,
)
from app.services import academia_audit_service as audit_service
from app.services import academia_hub_service as hub


def _default_payload() -> dict[str, Any]:
    return {
        "institution": None,
        "campus": None,
        "campuses": [],
        "colleges": [],
        "courses": [],
        "college_academic_overrides": [],
        "intakes": [],
        "pictures": [],
        "college_picture_overrides": [],
    }


def _step_audit_summary(step: int, payload: dict[str, Any]) -> dict[str, Any]:
    if step == 1:
        institution = payload.get("institution") or {}
        return {
            "name": institution.get("name"),
            "institution_type": institution.get("institution_type"),
            "country_id": institution.get("country_id"),
        }
    if step == 2:
        campuses = payload.get("campuses") or ([payload["campus"]] if payload.get("campus") else [])
        campus_names = [
            str(item.get("name") or "").strip()
            for item in campuses
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ]
        return {"campus_count": len(campus_names), "campuses": campus_names}
    if step == 3:
        colleges = payload.get("colleges") or []
        college_names = [
            str(item.get("name") or "").strip()
            for item in colleges
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ]
        return {"college_count": len(college_names), "colleges": college_names}
    if step == 4:
        courses = payload.get("courses") or []
        return {"course_count": len(courses)}
    if step == 5:
        intakes = payload.get("intakes") or []
        return {"intake_count": len(intakes)}
    if step == 6:
        pictures = payload.get("pictures") or []
        return {"picture_count": len(pictures)}
    return {}


def _write_wizard_step_audit(
    db: Session,
    *,
    user_id: int,
    draft: InstitutionWizardDraft,
    step: int,
    payload: dict[str, Any],
) -> None:
    institution_id = draft.institution_id
    if not institution_id:
        return

    step_actions = {
        1: "wizard_save_institution",
        2: "wizard_save_campuses",
        3: "wizard_save_colleges",
        4: "wizard_save_courses",
        5: "wizard_save_intakes",
        6: "wizard_save_pictures",
    }
    audit_service.write_academia_audit(
        db,
        user_id=user_id,
        entity_type="institution",
        entity_id=institution_id,
        action=step_actions.get(step, f"wizard_save_step_{step}"),
        new_data={
            "step": step,
            "draft_id": draft.id,
            "summary": _step_audit_summary(step, payload),
        },
    )


def _campus_payload_from_record(campus: Campus) -> dict[str, Any]:
    return {
        "id": campus.id,
        "local_id": str(campus.id),
        "name": campus.name,
        "location_id": campus.location_id,
        "campus_type_id": campus.campus_type_id,
        "description": campus.description,
        "address": campus.address,
        "country_id": campus.country_id,
        "state_id": campus.state_id,
        "zipcode": campus.zipcode,
        "phone_numbers": campus.phone_numbers or [],
        "fax_numbers": campus.fax_numbers or [],
        "email_addresses": campus.email_addresses or [],
        "web_links": campus.web_links or [],
        "is_residential": campus.is_residential,
    }


def _campus_create_from_wizard(
    institution_id: int,
    step: Any,
    *,
    sort_order: int = 0,
    strict: bool = True,
) -> CampusCreate:
    data = {
        "institution_id": institution_id,
        "location_id": step.location_id,
        "name": step.name.strip(),
        "campus_type_id": step.campus_type_id,
        "description": step.description,
        "address": step.address,
        "country_id": step.country_id,
        "state_id": step.state_id,
        "zipcode": step.zipcode,
        "phone_numbers": step.phone_numbers or [],
        "fax_numbers": step.fax_numbers or [],
        "email_addresses": step.email_addresses or [],
        "web_links": getattr(step, "web_links", None) or [],
        "is_residential": step.is_residential,
        "sort_order": sort_order,
    }
    if strict:
        return CampusCreate(**data)
    return CampusCreate.model_construct(**data)


def _campus_update_from_wizard(
    step: Any,
    *,
    sort_order: int | None = None,
    strict: bool = True,
) -> CampusUpdate:
    data = {
        "location_id": step.location_id,
        "name": step.name.strip(),
        "campus_type_id": step.campus_type_id,
        "description": step.description,
        "address": step.address,
        "country_id": step.country_id,
        "state_id": step.state_id,
        "zipcode": step.zipcode,
        "phone_numbers": step.phone_numbers or [],
        "fax_numbers": step.fax_numbers or [],
        "email_addresses": step.email_addresses or [],
        "web_links": getattr(step, "web_links", None) or [],
        "is_residential": step.is_residential,
        "sort_order": sort_order,
    }
    if strict:
        return CampusUpdate(**data)
    return CampusUpdate.model_construct(**data)


def _college_create_from_wizard(
    institution_id: int,
    campus_id: int | None,
    step: Any,
    *,
    sort_order: int = 0,
    strict: bool = True,
) -> CollegeCreate:
    data = {
        "institution_id": institution_id,
        "campus_id": campus_id,
        "name": step.name.strip(),
        "code": getattr(step, "code", None),
        "category": getattr(step, "category", None) or "College",
        "dean_name": step.dean_name,
        "web_url": step.web_url,
        "web_links": step.web_links or [],
        "phone_numbers": step.phone_numbers or [],
        "email_addresses": step.email_addresses or [],
        "sort_order": sort_order,
    }
    if strict:
        return CollegeCreate(**data)
    return CollegeCreate.model_construct(**data)


def _college_update_from_wizard(
    step: Any,
    *,
    campus_id: int | None,
    sort_order: int,
    strict: bool = True,
) -> CollegeUpdate:
    data = {
        "name": step.name.strip(),
        "code": getattr(step, "code", None),
        "category": getattr(step, "category", None) or "College",
        "dean_name": step.dean_name,
        "web_url": step.web_url,
        "web_links": step.web_links or [],
        "phone_numbers": step.phone_numbers or [],
        "email_addresses": step.email_addresses or [],
        "campus_id": campus_id,
        "sort_order": sort_order,
    }
    if strict:
        return CollegeUpdate(**data)
    return CollegeUpdate.model_construct(**data)


def _parse_syncable_campus(data: dict[str, Any]) -> WizardCampusSyncStep | None:
    if not str(data.get("name") or "").strip():
        return None
    if not data.get("location_id") or not data.get("campus_type_id"):
        return None
    try:
        return WizardCampusSyncStep.model_validate(data)
    except Exception:
        return None


def _parse_syncable_college(data: dict[str, Any]) -> WizardCollegeSyncItem | None:
    if not str(data.get("name") or "").strip():
        return None
    try:
        return WizardCollegeSyncItem.model_validate(data)
    except Exception:
        return None


def _sync_campuses_for_institution(
    db: Session,
    institution_id: int,
    campuses_data: list[Any],
) -> None:
    syncable = [
        campus
        for item in campuses_data
        if isinstance(item, dict) and (campus := _parse_syncable_campus(item)) is not None
    ]
    if not syncable:
        return

    existing = hub.list_campuses_admin(db, institution_id=institution_id)
    for index, campus_item in enumerate(syncable):
        if index < len(existing):
            hub.update_campus_admin(
                db,
                existing[index].id,
                _campus_update_from_wizard(campus_item, sort_order=index, strict=False),
            )
        else:
            hub.create_campus_admin(
                db,
                _campus_create_from_wizard(
                    institution_id,
                    campus_item,
                    sort_order=index,
                    strict=False,
                ),
            )

    for campus in existing[len(syncable) :]:
        hub.delete_campus_admin(db, campus.id)


def _dedupe_college_dicts(colleges_data: list[Any]) -> list[dict[str, Any]]:
    """Collapse duplicate college rows by name; merge linked_campuses onto one record.

    Multi-campus contact mappings belong on ``linked_campuses`` of a single college,
    not as separate college rows keyed by campus_id.
    """
    by_name: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in colleges_data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        name_key = name.lower()
        if name_key not in by_name:
            next_item = dict(item)
            links = next_item.get("linked_campuses")
            next_item["linked_campuses"] = (
                [dict(link) for link in links if isinstance(link, dict)]
                if isinstance(links, list)
                else []
            )
            by_name[name_key] = next_item
            order.append(name_key)
            continue

        existing = by_name[name_key]
        incoming_links = item.get("linked_campuses")
        if isinstance(incoming_links, list):
            existing_links = existing.get("linked_campuses") or []
            if not isinstance(existing_links, list):
                existing_links = []
            merged_links = _merge_linked_campus_dicts(existing_links, incoming_links)
            existing["linked_campuses"] = merged_links
            if merged_links:
                primary = merged_links[0]
                existing["campus_id"] = primary.get("campus_id")
                existing["campus_local_id"] = primary.get("campus_local_id")
                existing["campus_name"] = primary.get("name")
                if primary.get("address") is not None:
                    existing["campus_address"] = primary.get("address")
                if primary.get("location_label") is not None:
                    existing["campus_location_label"] = primary.get("location_label")
        for field in (
            "code",
            "category",
            "dean_name",
            "web_url",
            "web_links",
            "fax_numbers",
            "long_description",
            "accreditation",
            "phone_numbers",
            "email_addresses",
        ):
            if existing.get(field) in (None, "", []):
                value = item.get(field)
                if value not in (None, "", []):
                    existing[field] = value
            # Prefer fax_numbers; fall back from legacy fax_number on incoming drafts.
            if field == "fax_numbers" and existing.get("fax_numbers") in (None, []):
                legacy = item.get("fax_number")
                if legacy not in (None, ""):
                    existing["fax_numbers"] = [{"type": "Main", "value": str(legacy).strip()}]

    return [by_name[key] for key in order]


def _merge_linked_campus_dicts(
    existing_links: list[Any], incoming_links: list[Any]
) -> list[dict[str, Any]]:
    """Union campus link dicts by campus identity; prefer incoming non-empty fields."""

    def _keys(link: dict[str, Any]) -> set[str]:
        keys: set[str] = set()
        local_id = str(link.get("campus_local_id") or "").strip().lower()
        if local_id:
            keys.add(f"local:{local_id}")
        campus_id = link.get("campus_id")
        if campus_id is not None:
            try:
                keys.add(f"id:{int(campus_id)}")
            except (TypeError, ValueError):
                pass
        name = str(link.get("name") or "").strip().lower()
        if name:
            keys.add(f"name:{name}")
        return keys

    merged: list[dict[str, Any]] = []
    for raw in [*existing_links, *incoming_links]:
        if not isinstance(raw, dict):
            continue
        link = dict(raw)
        link_keys = _keys(link)
        if not link_keys:
            continue
        match_index = next(
            (
                index
                for index, existing in enumerate(merged)
                if _keys(existing) & link_keys
            ),
            None,
        )
        if match_index is None:
            merged.append(link)
            continue
        existing = merged[match_index]
        for field, value in link.items():
            if value in (None, "", []):
                continue
            existing[field] = value
        merged[match_index] = existing
    return merged


def _sync_colleges_for_institution(
    db: Session,
    institution_id: int,
    colleges_data: list[Any],
) -> None:
    syncable = [
        college
        for item in _dedupe_college_dicts(colleges_data)
        if (college := _parse_syncable_college(item)) is not None
    ]
    if not syncable:
        return

    existing = hub.list_colleges_admin(db, institution_id=institution_id)
    matched_ids: set[int] = set()
    for index, college_item in enumerate(syncable):
        campus_id = college_item.campus_id
        name_key = college_item.name.strip().lower()
        # Match by college name only — campus links are metadata on one college row.
        match = next(
            (
                row
                for row in existing
                if row.id not in matched_ids
                and (row.name or "").strip().lower() == name_key
            ),
            None,
        )
        if match is None:
            match = next(
                (row for row in existing if row.id not in matched_ids),
                None,
            )
        if match is not None:
            matched_ids.add(match.id)
            hub.update_college_admin(
                db,
                match.id,
                _college_update_from_wizard(
                    college_item,
                    campus_id=campus_id,
                    sort_order=index,
                    strict=False,
                ),
            )
        else:
            created = hub.create_college_admin(
                db,
                _college_create_from_wizard(
                    institution_id,
                    campus_id,
                    college_item,
                    sort_order=index,
                    strict=False,
                ),
            )
            matched_ids.add(created.id)

    for college in existing:
        if college.id not in matched_ids:
            hub.delete_college_admin(db, college.id)


def reconcile_institution_hierarchy_from_draft(db: Session, institution_id: int) -> None:
    """Persist campuses/colleges from an in-progress wizard draft when DB rows are missing."""
    draft = (
        db.query(InstitutionWizardDraft)
        .filter(
            InstitutionWizardDraft.institution_id == institution_id,
            InstitutionWizardDraft.status == "draft",
        )
        .order_by(InstitutionWizardDraft.updated_at.desc())
        .first()
    )
    if not draft or not draft.payload:
        return

    payload = draft.payload
    campuses_data = payload.get("campuses") or (
        [payload["campus"]] if payload.get("campus") else []
    )
    colleges_data = payload.get("colleges") or []

    if not hub.list_campuses_admin(db, institution_id=institution_id) and campuses_data:
        _sync_campuses_for_institution(db, institution_id, campuses_data)

    if not hub.list_colleges_admin(db, institution_id=institution_id) and colleges_data:
        _sync_colleges_for_institution(db, institution_id, colleges_data)


def _draft_to_read(draft: InstitutionWizardDraft) -> dict[str, Any]:
    from app.services.institution_asset_storage import rewrite_media_url

    payload = deepcopy(draft.payload or _default_payload())
    pictures = payload.get("pictures")
    if isinstance(pictures, list):
        rewritten: list[Any] = []
        for item in pictures:
            if isinstance(item, dict):
                next_item = dict(item)
                next_item["url"] = rewrite_media_url(next_item.get("url"))
                rewritten.append(next_item)
            else:
                rewritten.append(item)
        payload["pictures"] = rewritten
    return {
        "id": draft.id,
        "created_by_user_id": draft.created_by_user_id,
        "institution_id": draft.institution_id,
        "title": draft.title,
        "status": draft.status,
        "current_step": draft.current_step,
        "completed_steps": draft.completed_steps or [],
        "payload": payload,
        "created_at": draft.created_at,
        "updated_at": draft.updated_at,
    }


def list_drafts_admin(db: Session, *, user_id: int) -> list[InstitutionWizardDraft]:
    return (
        db.query(InstitutionWizardDraft)
        .filter(
            InstitutionWizardDraft.created_by_user_id == user_id,
            InstitutionWizardDraft.status == "draft",
        )
        .order_by(InstitutionWizardDraft.updated_at.desc())
        .all()
    )


def _date_to_str(value) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _payload_intakes_from_institution(db: Session, institution_id: int) -> list[dict[str, Any]]:
    """Mirror live Step-5 calendars into the wizard draft (exclude orphan publish rows)."""
    intakes = [
        intake
        for intake in list_institution_intakes(db, institution_id)
        if intake.entity_type
    ]
    return [
        {
            "name": intake.term_name or intake.name,
            "intake_code": intake.intake_code,
            "start_date": _date_to_str(intake.start_date or intake.class_start_date),
            "end_date": _date_to_str(intake.end_date),
            "application_deadline": _date_to_str(intake.application_deadline),
        }
        for intake in intakes
    ]


def _ensure_college_local_ids(colleges: list[Any]) -> tuple[list[dict[str, Any]], bool]:
    changed = False
    normalized: list[dict[str, Any]] = []
    for item in colleges:
        college = dict(item) if isinstance(item, dict) else {}
        if not str(college.get("local_id") or "").strip():
            college["local_id"] = str(uuid.uuid4())
            changed = True
        normalized.append(college)
    return normalized, changed


def _repair_course_college_links(
    colleges: list[dict[str, Any]], courses: list[Any]
) -> tuple[list[dict[str, Any]], bool]:
    college_ids = {
        str(college.get("local_id")).strip()
        for college in colleges
        if str(college.get("local_id") or "").strip()
    }
    if not college_ids:
        return [dict(item) if isinstance(item, dict) else {} for item in courses], False

    orphan_ids = sorted(
        {
            str(course.get("college_local_id")).strip()
            for course in courses
            if isinstance(course, dict)
            and str(course.get("college_local_id") or "").strip()
            and str(course.get("college_local_id")).strip() not in college_ids
        }
    )
    if not orphan_ids:
        return [dict(item) if isinstance(item, dict) else {} for item in courses], False

    group_sizes: dict[str, int] = {}
    for course in courses:
        if not isinstance(course, dict):
            continue
        college_local_id = str(course.get("college_local_id") or "").strip()
        if college_local_id in orphan_ids:
            group_sizes[college_local_id] = group_sizes.get(college_local_id, 0) + 1

    remap: dict[str, str] = {}
    if len(orphan_ids) == len(colleges):
        colleges_by_name = sorted(
            colleges,
            key=lambda college: (-len(str(college.get("name") or "")), str(college.get("name") or "")),
        )
        sized_orphans = sorted(
            orphan_ids,
            key=lambda college_local_id: (
                -group_sizes.get(college_local_id, 0),
                college_local_id,
            ),
        )
        for orphan_id, college in zip(sized_orphans, colleges_by_name):
            college_local_id = str(college.get("local_id") or "").strip()
            if college_local_id:
                remap[orphan_id] = college_local_id

    changed = False
    repaired: list[dict[str, Any]] = []
    for item in courses:
        course = dict(item) if isinstance(item, dict) else {}
        college_local_id = str(course.get("college_local_id") or "").strip()
        if college_local_id and college_local_id not in college_ids:
            mapped = remap.get(college_local_id)
            if mapped:
                course["college_local_id"] = mapped
                changed = True
            else:
                course["college_local_id"] = None
                changed = True
        repaired.append(course)
    return repaired, changed


def _normalize_draft_academics_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    normalized = deepcopy(payload or _default_payload())
    changed = False

    colleges = [
        dict(item) if isinstance(item, dict) else {}
        for item in (normalized.get("colleges") or [])
    ]
    courses = [
        dict(item) if isinstance(item, dict) else {}
        for item in (normalized.get("courses") or [])
    ]

    college_ids = {
        str(college.get("local_id") or "").strip()
        for college in colleges
        if str(college.get("local_id") or "").strip()
    }
    group_sizes: dict[str, int] = {}
    for course in courses:
        college_local_id = str(course.get("college_local_id") or "").strip()
        if college_local_id:
            group_sizes[college_local_id] = group_sizes.get(college_local_id, 0) + 1

    orphan_ids = sorted(
        {
            college_local_id
            for college_local_id in group_sizes
            if college_local_id not in college_ids
        },
        key=lambda college_local_id: (
            -group_sizes.get(college_local_id, 0),
            college_local_id,
        ),
    )
    needing = [college for college in colleges if not str(college.get("local_id") or "").strip()]

    if orphan_ids and len(orphan_ids) == len(needing):
        needing_sorted = sorted(
            needing,
            key=lambda college: (
                -len(str(college.get("name") or "")),
                str(college.get("name") or ""),
            ),
        )
        assigned_by_name = {
            str(college.get("name") or ""): orphan_id
            for college, orphan_id in zip(needing_sorted, orphan_ids)
        }
        for college in colleges:
            if str(college.get("local_id") or "").strip():
                continue
            college["local_id"] = assigned_by_name.get(str(college.get("name") or "")) or str(
                uuid.uuid4()
            )
            changed = True
        normalized["colleges"] = colleges
        normalized["courses"] = courses
        return normalized, changed

    colleges, colleges_changed = _ensure_college_local_ids(colleges)
    normalized["colleges"] = colleges
    changed = changed or colleges_changed

    courses, courses_changed = _repair_course_college_links(colleges, courses)
    normalized["courses"] = courses
    changed = changed or courses_changed

    return normalized, changed


def _apply_draft_academics_normalization(draft: InstitutionWizardDraft) -> bool:
    payload, changed = _normalize_draft_academics_payload(draft.payload or _default_payload())
    if not changed:
        return False
    draft.payload = payload
    flag_modified(draft, "payload")
    return True


def _latest_wizard_courses_payload(db: Session, institution_id: int) -> list[dict[str, Any]]:
    drafts = (
        db.query(InstitutionWizardDraft)
        .filter(InstitutionWizardDraft.institution_id == institution_id)
        .order_by(InstitutionWizardDraft.updated_at.desc())
        .all()
    )
    for draft in drafts:
        courses = (draft.payload or {}).get("courses") or []
        if courses:
            return [item for item in courses if isinstance(item, dict)]
    return []


def _list_institution_course_offerings(
    db: Session, institution_id: int
) -> list[InstitutionCourseOffering]:
    return (
        db.query(InstitutionCourseOffering)
        .options(
            joinedload(InstitutionCourseOffering.course)
            .joinedload(TargetCourse.qualification_program)
            .joinedload(Program.level),
            joinedload(InstitutionCourseOffering.course)
            .joinedload(TargetCourse.education_major)
            .joinedload(EducationMajor.program)
            .joinedload(Program.level),
        )
        .filter(InstitutionCourseOffering.institution_id == institution_id)
        .order_by(InstitutionCourseOffering.sort_order.asc())
        .all()
    )


def _courses_payload_from_institution(
    db: Session, institution_id: int
) -> list[dict[str, Any]]:
    offerings = _list_institution_course_offerings(db, institution_id)
    if offerings:
        return [
            _course_offering_payload_from_record(db, offering) for offering in offerings
        ]
    return _latest_wizard_courses_payload(db, institution_id)


def _sync_draft_courses_payload(db: Session, draft: InstitutionWizardDraft) -> bool:
    """Backfill draft.payload.courses from live offerings or published wizard data."""
    if not draft.institution_id:
        return False
    payload = deepcopy(draft.payload or _default_payload())
    current = payload.get("courses") or []
    if current:
        return False
    items = _courses_payload_from_institution(db, draft.institution_id)
    if not items:
        return False
    payload["courses"] = items
    draft.payload = payload
    flag_modified(draft, "payload")
    completed = list(draft.completed_steps or [])
    if 4 not in completed:
        draft.completed_steps = sorted({*completed, 4})
    return True


def _picture_asset_key(picture_item: Any) -> str:
    storage_key = str(getattr(picture_item, "storage_key", "") or "").strip().lstrip("/")
    if storage_key:
        return storage_key
    url = str(getattr(picture_item, "url", "") or "").strip()
    if not url:
        return ""
    from app.services.institution_asset_storage import storage_key_from_url

    return (storage_key_from_url(url) or url).strip().lstrip("/")


def _picture_scope_key(picture_item: Any) -> str:
    college_id = getattr(picture_item, "college_id", None)
    if college_id:
        return f"college-id:{college_id}"
    college_local_id = str(getattr(picture_item, "college_local_id", "") or "").strip()
    if college_local_id:
        return f"college:{college_local_id}"
    return "institution"


def _sync_pictures_for_institution(
    db: Session,
    institution_id: int,
    pictures: list[Any],
    *,
    default_campus_id: int | None,
    college_local_id_map: dict[str, int] | None = None,
) -> None:
    """Replace-set sync. Same R2 asset may appear once per entity (university/college)."""
    local_map = college_local_id_map or {}
    desired: list[tuple[str, str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for picture_item in pictures:
        asset_key = _picture_asset_key(picture_item)
        url = str(getattr(picture_item, "url", "") or "").strip()
        if not url or not asset_key:
            continue
        college_id = getattr(picture_item, "college_id", None)
        college_local_id = str(getattr(picture_item, "college_local_id", "") or "").strip()
        if college_id is None and college_local_id:
            college_id = local_map.get(college_local_id)
        scope = f"college-id:{college_id}" if college_id else "institution"
        identity = (asset_key, scope)
        if identity in seen:
            continue
        seen.add(identity)
        # Stamp resolved college_id onto the item for row write below.
        try:
            picture_item.college_id = college_id
        except Exception:
            pass
        desired.append((asset_key, scope, picture_item))

    existing = list_institution_pictures(db, institution_id)
    by_identity: dict[tuple[str, str], InstitutionPicture] = {}
    for row in existing:
        row_key = (row.storage_key or "").strip().lstrip("/")
        if not row_key:
            from app.services.institution_asset_storage import storage_key_from_url

            row_key = (storage_key_from_url(row.url) or row.url).strip().lstrip("/")
        row_scope = f"college-id:{row.college_id}" if row.college_id else "institution"
        by_identity[(row_key, row_scope)] = row

    keep_ids: set[int] = set()
    for index, (asset_key, scope, picture_item) in enumerate(desired):
        row = by_identity.get((asset_key, scope))
        college_id = getattr(picture_item, "college_id", None)
        storage_key = str(getattr(picture_item, "storage_key", "") or "").strip() or asset_key
        if row is not None:
            row.caption = picture_item.caption
            row.picture_type = picture_item.picture_type
            row.campus_id = getattr(picture_item, "campus_id", None) or default_campus_id
            row.college_id = college_id
            row.storage_key = storage_key
            row.url = str(picture_item.url).strip()
            row.sort_order = index
            row.is_active = True
            keep_ids.add(row.id)
        else:
            db.add(
                InstitutionPicture(
                    institution_id=institution_id,
                    campus_id=getattr(picture_item, "campus_id", None) or default_campus_id,
                    college_id=college_id,
                    storage_key=storage_key,
                    url=str(picture_item.url).strip(),
                    caption=picture_item.caption,
                    picture_type=picture_item.picture_type,
                    sort_order=index,
                )
            )
    for row in existing:
        if row.id not in keep_ids:
            db.delete(row)


def _sync_draft_intakes_payload(db: Session, draft: InstitutionWizardDraft) -> bool:
    """Keep draft.payload.intakes aligned with calendars configured outside the draft form."""
    if not draft.institution_id:
        return False
    items = _payload_intakes_from_institution(db, draft.institution_id)
    payload = deepcopy(draft.payload or _default_payload())
    current = payload.get("intakes") or []
    if current == items:
        return False
    payload["intakes"] = items
    draft.payload = payload
    flag_modified(draft, "payload")
    return True


def get_draft_admin(db: Session, draft_id: int, *, user_id: int) -> InstitutionWizardDraft:
    draft = db.query(InstitutionWizardDraft).filter(InstitutionWizardDraft.id == draft_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Wizard draft not found.")
    if draft.created_by_user_id != user_id and draft.status == "draft":
        raise HTTPException(status_code=403, detail="Not authorized for this draft.")
    changed = _sync_draft_intakes_payload(db, draft)
    changed = _sync_draft_courses_payload(db, draft) or changed
    changed = _apply_draft_academics_normalization(draft) or changed
    if changed:
        db.commit()
        db.refresh(draft)
    return draft


def _course_offering_display_label(
    course: TargetCourse,
    program: Program | None,
    major: EducationMajor | None,
) -> str | None:
    level_name = program.level.name if program and getattr(program, "level", None) else None
    program_name = program.name if program else None
    major_name = major.label if major else None
    course_name = course.label if course else None
    parts = [part for part in [level_name, program_name, major_name, course_name] if part]
    return " > ".join(parts) if parts else None


def _course_offering_payload_from_record(
    db: Session,
    offering: InstitutionCourseOffering,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "course_id": offering.course_id,
        "college_id": offering.college_id,
    }
    course = offering.course
    if course is None:
        course = db.query(TargetCourse).filter(TargetCourse.id == offering.course_id).first()
    if course is None:
        return payload

    program = course.qualification_program
    major = course.education_major

    if course.qualification_program_id is not None:
        payload["program_id"] = str(course.qualification_program_id)
    if program is not None and program.level_id:
        payload["level_id"] = program.level_id
    if course.education_major_id is not None:
        payload["major_id"] = course.education_major_id
    if "program_id" not in payload and major is not None and major.program_id is not None:
        payload["program_id"] = str(major.program_id)

    display_label = _course_offering_display_label(course, program, major)
    if display_label:
        payload["display_label"] = display_label

    return payload


def create_draft_from_institution_admin(
    db: Session,
    institution_id: int,
    *,
    user_id: int,
) -> InstitutionWizardDraft:
    institution = hub.get_institution_admin(db, institution_id)

    existing = (
        db.query(InstitutionWizardDraft)
        .filter(
            InstitutionWizardDraft.institution_id == institution_id,
            InstitutionWizardDraft.created_by_user_id == user_id,
            InstitutionWizardDraft.status == "draft",
        )
        .order_by(InstitutionWizardDraft.updated_at.desc())
        .first()
    )
    if existing:
        changed = _sync_draft_intakes_payload(db, existing)
        changed = _sync_draft_courses_payload(db, existing) or changed
        changed = _apply_draft_academics_normalization(existing) or changed
        if changed:
            db.commit()
            db.refresh(existing)
        return existing

    campuses = hub.list_campuses_admin(db, institution_id=institution_id)
    campus = campuses[0] if campuses else None
    colleges = (
        hub.list_colleges_admin(db, institution_id=institution_id, campus_id=campus.id)
        if campus
        else []
    )
    pictures = list_institution_pictures(db, institution_id)

    payload: dict[str, Any] = {
        "institution": {
            "name": institution.name,
            "code": institution.code,
            "dean_name": institution.dean_name,
            "country_id": institution.country_id,
            "state_id": institution.state_id,
            "city_id": institution.city_id,
            "zipcode": institution.zipcode,
            "address": institution.address,
            "phone_numbers": institution.phone_numbers or [],
            "fax_numbers": institution.fax_numbers or [],
            "email_addresses": institution.email_addresses or [],
            "institution_type": institution.institution_type,
            "company_affiliated": institution.company_affiliated,
            "ranking_tier_global": institution.ranking_tier_global,
            "ad_promotion_flag": institution.ad_promotion_flag,
            "institution_web_url": institution.institution_web_url,
            "web_links": institution.web_links or [],
            "currency_type": institution.currency_type or "USD",
            "students_count": institution.students_count,
            "accreditation_details": institution.accreditation_details,
            "short_description": institution.short_description,
            "long_description": institution.long_description,
        },
        "campuses": [_campus_payload_from_record(item) for item in campuses],
        "campus": _campus_payload_from_record(campus) if campus else None,
        "colleges": [
            {
                "local_id": str(uuid.uuid4()),
                "code": college.code,
                "name": college.name,
                "category": college.category or "College",
                "dean_name": college.dean_name,
                "web_url": college.web_url,
                "web_links": college.web_links or [],
                "campus_id": college.campus_id,
                "campus_local_id": (
                    str(college.campus_id) if college.campus_id is not None else None
                ),
                "campus_name": college.campus.name if college.campus else None,
                "campus_address": college.campus.address if college.campus else None,
                "campus_location_label": college.campus.location.name if getattr(college.campus, "location", None) else None,
                "linked_campuses": (
                    [
                        {
                            "campus_local_id": str(college.campus_id),
                            "campus_id": college.campus_id,
                            "name": college.campus.name if college.campus else "",
                            "address": college.campus.address if college.campus else None,
                            "location_label": (
                                college.campus.location.name
                                if getattr(college.campus, "location", None)
                                else None
                            ),
                        }
                    ]
                    if college.campus_id is not None
                    else []
                ),
                "phone_numbers": college.phone_numbers or [],
                "email_addresses": college.email_addresses or [],
            }
            for college in hub.list_colleges_admin(db, institution_id=institution_id)
        ],
        "courses": _courses_payload_from_institution(db, institution_id),
        "intakes": _payload_intakes_from_institution(db, institution_id),
        "pictures": [
            {
                "url": picture.url,
                "caption": picture.caption,
                "picture_type": picture.picture_type,
                "college_id": picture.college_id,
                "storage_key": picture.storage_key,
            }
            for picture in pictures
        ],
        "college_picture_overrides": [],
    }
    payload["colleges"] = _dedupe_college_dicts(payload["colleges"])

    completed_steps: list[int] = []
    if payload["institution"] and payload["institution"].get("name"):
        completed_steps.append(1)
    if payload["campuses"]:
        completed_steps.append(2)
    elif payload["campus"] and payload["campus"].get("name") and payload["campus"].get("location_id"):
        completed_steps.append(2)
    if payload["colleges"]:
        completed_steps.append(3)
    if payload["courses"]:
        completed_steps.append(4)
    if payload["intakes"]:
        completed_steps.append(5)
    if payload["pictures"]:
        completed_steps.append(6)

    draft = InstitutionWizardDraft(
        created_by_user_id=user_id,
        institution_id=institution_id,
        title=institution.name.strip() or "Untitled Institution",
        status="draft",
        current_step=1,
        completed_steps=completed_steps,
        payload=payload,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def create_draft_admin(db: Session, *, user_id: int, title: str = "Untitled Institution") -> InstitutionWizardDraft:
    draft = InstitutionWizardDraft(
        created_by_user_id=user_id,
        title=title.strip() or "Untitled Institution",
        status="draft",
        current_step=1,
        completed_steps=[],
        payload=_default_payload(),
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def update_draft_admin(
    db: Session,
    draft_id: int,
    *,
    user_id: int,
    title: str | None = None,
    current_step: int | None = None,
    completed_steps: list[int] | None = None,
    payload: dict[str, Any] | None = None,
) -> InstitutionWizardDraft:
    draft = get_draft_admin(db, draft_id, user_id=user_id)
    if draft.status != "draft":
        raise HTTPException(
            status_code=400,
            detail=(
                "This wizard version is already published and cannot be edited. "
                "Open Edit from Institutions to start a new draft, then publish again."
            ),
        )
    if title is not None:
        draft.title = title.strip() or draft.title
    if current_step is not None:
        draft.current_step = current_step
    if completed_steps is not None:
        draft.completed_steps = completed_steps
    if payload is not None:
        merged = deepcopy(draft.payload or _default_payload())
        merged.update(payload)
        draft.payload = merged
    db.commit()
    db.refresh(draft)
    return draft


def save_wizard_step(
    db: Session,
    draft_id: int,
    *,
    user_id: int,
    request: WizardStepSaveRequest,
) -> InstitutionWizardDraft:
    draft = get_draft_admin(db, draft_id, user_id=user_id)
    if draft.status != "draft":
        raise HTTPException(
            status_code=400,
            detail=(
                "This wizard version is already published and cannot be edited. "
                "Open Edit from Institutions to start a new draft, then publish again."
            ),
        )

    payload = _validate_step_save_payload(
        draft.payload or _default_payload(),
        request,
    )
    if request.step == 1:
        institution_step = _parse_institution_step(request.data)
        _upsert_draft_institution(db, draft, institution_step)
        draft.title = institution_step.name.strip()
    elif request.step == 2:
        campuses_data = payload["campuses"]
        if draft.institution_id:
            _sync_campuses_for_institution(db, draft.institution_id, campuses_data)
    elif request.step == 3:
        colleges_data = payload["colleges"]
        if draft.institution_id:
            _sync_colleges_for_institution(db, draft.institution_id, colleges_data)

    draft.payload = payload
    # Intake calendars are configured via the live intakes API; keep draft JSON in sync.
    if request.step == 5 and draft.institution_id:
        _sync_draft_intakes_payload(db, draft)
        payload = draft.payload or payload
    flag_modified(draft, "payload")
    draft.current_step = request.step
    completed = set(draft.completed_steps or [])
    if request.mark_complete:
        completed.add(request.step)
    draft.completed_steps = sorted(completed)
    flag_modified(draft, "completed_steps")
    _write_wizard_step_audit(db, user_id=user_id, draft=draft, step=request.step, payload=payload)
    db.commit()
    db.refresh(draft)
    return draft


def _validate_step_save_payload(
    current_payload: dict[str, Any],
    request: WizardStepSaveRequest,
) -> dict[str, Any]:
    """Validate the cumulative publish-relevant state before a step is persisted."""
    payload = deepcopy(current_payload or _default_payload())
    try:
        if request.step == 1:
            payload["institution"] = request.data
        elif request.step == 2:
            campuses = (
                request.data
                if isinstance(request.data, list)
                else request.data.get("campuses", [])
            )
            payload["campuses"] = campuses
            payload["campus"] = campuses[0] if campuses else None
        elif request.step == 3:
            colleges = (
                request.data
                if isinstance(request.data, list)
                else request.data.get("colleges", [])
            )
            payload["colleges"] = _dedupe_college_dicts(
                colleges if isinstance(colleges, list) else []
            )
        elif request.step == 4:
            if isinstance(request.data, dict):
                payload["courses"] = request.data.get("courses") or []
                if "college_academic_overrides" in request.data:
                    overrides = request.data.get("college_academic_overrides") or []
                    payload["college_academic_overrides"] = [
                        str(item).strip()
                        for item in overrides
                        if str(item).strip()
                    ]
            else:
                payload["courses"] = request.data if isinstance(request.data, list) else []
        elif request.step == 6:
            if isinstance(request.data, dict):
                payload["pictures"] = request.data.get("pictures") or []
                if "college_picture_overrides" in request.data:
                    overrides = request.data.get("college_picture_overrides") or []
                    payload["college_picture_overrides"] = [
                        str(item).strip()
                        for item in overrides
                        if str(item).strip()
                    ]
            else:
                payload["pictures"] = request.data if isinstance(request.data, list) else []
        else:
            step_key = ["institution", "campus", "colleges", "courses", "intakes", "pictures"][
                request.step - 1
            ]
            payload[step_key] = (
                request.data
                if isinstance(request.data, list)
                else request.data.get(step_key, [])
            )

        parsed = WizardPayload.model_validate(payload)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Step {request.step} validation failed: {exc}",
        ) from exc

    if request.step >= 1 and (
        not parsed.institution or not parsed.institution.name.strip()
    ):
        raise HTTPException(status_code=400, detail="Institution name is required.")
    if request.step >= 2:
        campuses = parsed.resolved_campuses
        if not campuses:
            raise HTTPException(status_code=400, detail="Add at least one campus.")
        for index, campus in enumerate(campuses, start=1):
            if not campus.name.strip():
                raise HTTPException(
                    status_code=400,
                    detail=f"Campus {index} name is required.",
                )
            if not campus.campus_type_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"Campus {index} type is required.",
                )
            if not campus.location_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"Campus {index} city is required.",
                )
    if request.step >= 3 and not parsed.colleges:
        raise HTTPException(status_code=400, detail="Add at least one college.")

    return payload


def _validate_publish_payload(payload: dict[str, Any]) -> WizardPayload:
    try:
        parsed = WizardPayload.model_validate(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid wizard payload: {exc}") from exc
    if not parsed.institution or not parsed.institution.name.strip():
        raise HTTPException(status_code=400, detail="Institution name is required to publish.")
    campuses = parsed.resolved_campuses
    if not campuses:
        raise HTTPException(status_code=400, detail="At least one campus is required to publish.")
    for index, campus_item in enumerate(campuses, start=1):
        if not campus_item.name.strip():
            raise HTTPException(status_code=400, detail=f"Campus {index} name is required to publish.")
        if not campus_item.campus_type_id:
            raise HTTPException(status_code=400, detail=f"Campus {index} type is required to publish.")
        if not campus_item.location_id:
            raise HTTPException(status_code=400, detail=f"Campus {index} city is required to publish.")
    if not parsed.colleges:
        raise HTTPException(status_code=400, detail="At least one college is required to publish.")
    return parsed


def _publish_report_step(
    step: int,
    label: str,
    *,
    started_at: datetime,
    checks: list[dict[str, Any]],
    discrepancies: list[dict[str, Any]] | None = None,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    completed_at = datetime.now(timezone.utc)
    return {
        "step": step,
        "label": label,
        "status": "success",
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "checks": checks,
        "discrepancies": discrepancies or [],
        "result": result or {},
    }


def _passed_check(name: str, details: str) -> dict[str, str]:
    return {"name": name, "status": "passed", "details": details}


def _fixed_discrepancy(description: str, resolution: str) -> dict[str, str]:
    return {
        "description": description,
        "resolution": resolution,
        "status": "fixed",
    }


def _institution_create_from_wizard(step: Any) -> InstitutionCreate:
    return InstitutionCreate(
        name=step.name.strip(),
        code=step.code,
        dean_name=step.dean_name,
        country_id=step.country_id,
        state_id=step.state_id,
        city_id=step.city_id,
        zipcode=step.zipcode,
        address=step.address,
        phone_numbers=step.phone_numbers or [],
        fax_numbers=step.fax_numbers or [],
        email_addresses=step.email_addresses or [],
        institution_type=step.institution_type,
        company_affiliated=step.company_affiliated,
        ranking_tier_global=step.ranking_tier_global,
        ad_promotion_flag=step.ad_promotion_flag,
        institution_web_url=step.institution_web_url,
        web_links=step.web_links or [],
        currency_type=step.currency_type or "USD",
        students_count=step.students_count,
        accreditation_details=step.accreditation_details,
        short_description=step.short_description,
        long_description=step.long_description,
    )


def _parse_institution_step(data: dict[str, Any]) -> WizardInstitutionStep:
    try:
        return WizardInstitutionStep.model_validate(data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid institution data: {exc}") from exc


def _upsert_draft_institution(
    db: Session,
    draft: InstitutionWizardDraft,
    step: WizardInstitutionStep,
) -> Institution:
    if not step.name.strip():
        raise HTTPException(status_code=400, detail="Institution name is required.")

    if step.country_id is not None:
        hub.get_country_admin(db, step.country_id)
    if step.state_id is not None:
        hub.get_state_admin(db, step.state_id)
    if step.city_id is not None:
        hub.get_city_admin(db, step.city_id)

    if draft.institution_id:
        institution = hub.get_institution_admin(db, draft.institution_id)
        _apply_wizard_institution_fields(institution, step)
        db.flush()
        return institution

    institution = Institution(
        **_institution_create_from_wizard(step).model_dump(),
        publish_status="pending",
    )
    db.add(institution)
    db.flush()
    draft.institution_id = institution.id
    return institution


def _apply_wizard_institution_fields(institution: Institution, step: Any) -> None:
    institution.name = step.name.strip()
    institution.code = step.code
    institution.dean_name = step.dean_name
    institution.country_id = step.country_id
    institution.state_id = step.state_id
    institution.city_id = step.city_id
    institution.zipcode = step.zipcode
    institution.address = step.address
    institution.phone_numbers = [
        entry.model_dump() if hasattr(entry, "model_dump") else entry
        for entry in (step.phone_numbers or [])
    ]
    institution.fax_numbers = [
        entry.model_dump() if hasattr(entry, "model_dump") else entry
        for entry in (step.fax_numbers or [])
    ]
    institution.email_addresses = [
        entry.model_dump() if hasattr(entry, "model_dump") else entry
        for entry in (step.email_addresses or [])
    ]
    institution.institution_type = step.institution_type
    institution.company_affiliated = step.company_affiliated
    institution.ranking_tier_global = step.ranking_tier_global
    institution.ad_promotion_flag = step.ad_promotion_flag
    institution.institution_web_url = step.institution_web_url
    institution.web_links = [
        entry.model_dump() if hasattr(entry, "model_dump") else entry
        for entry in (step.web_links or [])
    ]
    institution.currency_type = step.currency_type or "USD"
    institution.students_count = step.students_count
    institution.accreditation_details = step.accreditation_details
    institution.short_description = step.short_description
    institution.long_description = step.long_description


def publish_draft_admin(db: Session, draft_id: int, *, user_id: int) -> InstitutionWizardDraft:
    draft = get_draft_admin(db, draft_id, user_id=user_id)
    if draft.status != "draft":
        raise HTTPException(status_code=400, detail="Draft is already published.")

    old_institution_snapshot = None
    publish_started_at = datetime.now(timezone.utc)
    publish_steps: list[dict[str, Any]] = []

    try:
        step_started_at = datetime.now(timezone.utc)
        parsed = _validate_publish_payload(draft.payload or {})
        if draft.institution_id:
            institution = hub.get_institution_admin(db, draft.institution_id)
            old_institution_snapshot = {
                "id": institution.id,
                "name": institution.name,
                "code": institution.code,
            }
            _apply_wizard_institution_fields(institution, parsed.institution)
            db.flush()
        else:
            institution = hub.create_institution_admin(
                db,
                _institution_create_from_wizard(parsed.institution),
            )

        campus_records: list[Campus] = []
        existing_campuses = (
            hub.list_campuses_admin(db, institution_id=institution.id)
            if draft.institution_id
            else []
        )
        for index, campus_item in enumerate(parsed.resolved_campuses):
            if index < len(existing_campuses):
                campus = hub.update_campus_admin(
                    db,
                    existing_campuses[index].id,
                    _campus_update_from_wizard(campus_item, sort_order=index),
                )
            else:
                campus = hub.create_campus_admin(
                    db,
                    _campus_create_from_wizard(institution.id, campus_item, sort_order=index),
                )
            campus_records.append(campus)
        campus = campus_records[0]
        removed_campus_count = max(0, len(existing_campuses) - len(parsed.resolved_campuses))
        for campus_row in existing_campuses[len(parsed.resolved_campuses) :]:
            hub.delete_campus_admin(db, campus_row.id)
        campus_discrepancies = []
        if removed_campus_count:
            campus_discrepancies.append(
                _fixed_discrepancy(
                    f"{removed_campus_count} live campus record(s) were not present in the wizard payload.",
                    "Removed the obsolete campus records while synchronizing the published structure.",
                )
            )

        publish_steps.append(
            _publish_report_step(
                1,
                "Institution & Campuses",
                started_at=step_started_at,
                checks=[
                    _passed_check("Payload schema", "Institution fields match the required data types and limits."),
                    _passed_check("Required name", f'Institution name "{institution.name}" is present.'),
                    _passed_check("Record synchronization", "Validated institution fields were applied to the live record."),
                    _passed_check("Minimum campus count", f"{len(campus_records)} campus record(s) supplied."),
                    _passed_check("Campus required fields", "Every campus has a name, campus type, and city."),
                    _passed_check("Campus structure synchronization", "Live campus records now match the wizard payload."),
                ],
                discrepancies=campus_discrepancies,
                result={
                    "institution_id": institution.id,
                    "name": institution.name,
                    "operation": "updated" if old_institution_snapshot else "created",
                    "campus_count": len(campus_records),
                    "campuses_created_or_updated": len(campus_records),
                    "campuses_removed": removed_campus_count,
                },
            )
        )

        # Deduped name+campus sync — draft payload can carry duplicate college rows.
        step_started_at = datetime.now(timezone.utc)
        unique_college_dicts = _dedupe_college_dicts(
            [item.model_dump() for item in parsed.colleges]
        )
        duplicate_college_count = len(parsed.colleges) - len(unique_college_dicts)
        _sync_colleges_for_institution(db, institution.id, unique_college_dicts)
        college_ids = [
            college.id for college in hub.list_colleges_admin(db, institution_id=institution.id)
        ]
        college_discrepancies = []
        if duplicate_college_count:
            college_discrepancies.append(
                _fixed_discrepancy(
                    f"{duplicate_college_count} duplicate college row(s) were detected by name.",
                    "Duplicates were merged (including campus links) before synchronizing live college records.",
                )
            )
        publish_steps.append(
            _publish_report_step(
                2,
                "Schools & Colleges",
                started_at=step_started_at,
                checks=[
                    _passed_check("Minimum count", f"{len(unique_college_dicts)} unique college record(s) supplied."),
                    _passed_check("Required names", "Every college has a valid name."),
                    _passed_check("Structure synchronization", "Live college records now match the deduplicated payload."),
                ],
                discrepancies=college_discrepancies,
                result={
                    "college_count": len(college_ids),
                    "duplicates_removed": duplicate_college_count,
                },
            )
        )

        # Wizard Step 4 selects Academic Framework courses (education_courses).
        # InstitutionCourseOffering still FKs target_courses, so only persist
        # rows that resolve to TargetCourse. EducationCourse / scope selections
        # remain in draft.payload and must not block publish.
        existing_offerings = (
            db.query(InstitutionCourseOffering)
            .filter(InstitutionCourseOffering.institution_id == institution.id)
            .all()
        )
        step_started_at = datetime.now(timezone.utc)
        for offering_row in existing_offerings:
            db.delete(offering_row)

        offering_sort = 0
        skipped_framework_course_count = 0
        scope_selection_count = 0
        for offering in parsed.courses:
            if not offering.course_id:
                scope_selection_count += 1
                continue
            target_course = (
                db.query(TargetCourse).filter(TargetCourse.id == offering.course_id).first()
            )
            if not target_course:
                skipped_framework_course_count += 1
                continue
            db.add(
                InstitutionCourseOffering(
                    institution_id=institution.id,
                    campus_id=campus.id,
                    college_id=offering.college_id
                    or (college_ids[0] if college_ids else None),
                    course_id=offering.course_id,
                    sort_order=offering_sort,
                )
            )
            offering_sort += 1
        academic_discrepancies = []
        if skipped_framework_course_count:
            academic_discrepancies.append(
                _fixed_discrepancy(
                    f"{skipped_framework_course_count} selected framework course ID(s) do not map to the legacy target-course table.",
                    "Kept the selections in the published wizard payload and skipped incompatible legacy offering rows.",
                )
            )
        if scope_selection_count:
            academic_discrepancies.append(
                _fixed_discrepancy(
                    f"{scope_selection_count} academic scope row(s) do not represent individual courses.",
                    "Retained them as level/program/major scope selections and excluded them from the course count.",
                )
            )
        publish_steps.append(
            _publish_report_step(
                3,
                "Academics",
                started_at=step_started_at,
                checks=[
                    _passed_check("Payload schema", f"{len(parsed.courses)} academic selection row(s) validated."),
                    _passed_check("Course compatibility", "Compatible legacy course offerings were synchronized."),
                    _passed_check("Scope preservation", "Framework selections remain available in the published payload."),
                ],
                discrepancies=academic_discrepancies,
                result={
                    "selection_count": len(parsed.courses),
                    "course_offering_count": offering_sort,
                    "scope_selection_count": scope_selection_count,
                    "framework_courses_retained_in_payload": skipped_framework_course_count,
                },
            )
        )

        # Intakes are already persisted live by Step 5 hierarchical configure.
        # Never re-insert from the draft payload (that was duplicating calendars).
        step_started_at = datetime.now(timezone.utc)
        live_intakes = _payload_intakes_from_institution(db, institution.id)
        publish_steps.append(
            _publish_report_step(
                4,
                "Intakes",
                started_at=step_started_at,
                checks=[
                    _passed_check("Live calendar source", f"{len(live_intakes)} persisted intake calendar(s) found."),
                    _passed_check("Duplicate prevention", "Existing live calendars were reused instead of inserted again."),
                    _passed_check("No-write safeguard", "Publishing did not recreate or alter intake hierarchy rows."),
                ],
                result={"intake_count": len(live_intakes), "new_duplicate_rows": 0},
            )
        )

        step_started_at = datetime.now(timezone.utc)
        picture_asset_keys = [
            key
            for item in parsed.pictures
            if (key := _picture_asset_key(item))
        ]
        unique_picture_assets = set(picture_asset_keys)
        duplicate_picture_count = max(0, len(picture_asset_keys) - len(unique_picture_assets))
        existing_picture_assets = {
            (row.storage_key or row.url or "").strip().lstrip("/")
            for row in list_institution_pictures(db, institution.id)
        }
        stale_picture_count = len(existing_picture_assets - unique_picture_assets)
        college_local_id_map: dict[str, int] = {}
        live_by_name = {
            (college.name or "").strip().lower(): college.id
            for college in hub.list_colleges_admin(db, institution_id=institution.id)
        }
        for college_dict in unique_college_dicts:
            local_id = str(college_dict.get("local_id") or "").strip()
            name_key = str(college_dict.get("name") or "").strip().lower()
            if local_id and name_key in live_by_name:
                college_local_id_map[local_id] = live_by_name[name_key]
        _sync_pictures_for_institution(
            db,
            institution.id,
            parsed.pictures,
            default_campus_id=campus.id,
            college_local_id_map=college_local_id_map,
        )
        picture_discrepancies = []
        if duplicate_picture_count:
            picture_discrepancies.append(
                _fixed_discrepancy(
                    "Duplicate gallery asset references were found in the payload.",
                    "Stored one live picture row per unique asset+entity pair (shared R2 object).",
                )
            )
        if stale_picture_count:
            picture_discrepancies.append(
                _fixed_discrepancy(
                    f"{stale_picture_count} live gallery reference(s) were no longer in the payload.",
                    "Removed stale references during replace synchronization.",
                )
            )
        publish_steps.append(
            _publish_report_step(
                5,
                "Gallery",
                started_at=step_started_at,
                checks=[
                    _passed_check(
                        "Asset references",
                        f"{len(unique_picture_assets)} unique non-empty picture asset(s) supplied.",
                    ),
                    _passed_check("Replace synchronization", "Live gallery references now match the wizard payload."),
                    _passed_check("Campus assignment", "Pictures without a campus use the primary campus."),
                ],
                discrepancies=picture_discrepancies,
                result={
                    "picture_count": len(unique_picture_assets),
                    "duplicates_removed": duplicate_picture_count,
                    "stale_references_removed": stale_picture_count,
                },
            )
        )

        # Keep a clean colleges list on the published payload for future re-edits.
        publish_payload = deepcopy(draft.payload or {})
        publish_payload["colleges"] = unique_college_dicts
        publish_payload["intakes"] = live_intakes
        draft.payload = publish_payload
        flag_modified(draft, "payload")

        publish_completed_at = datetime.now(timezone.utc)
        discrepancy_count = sum(
            len(step.get("discrepancies") or []) for step in publish_steps
        )
        publish_report = {
            "version": 1,
            "attempt_id": str(uuid.uuid4()),
            "draft_id": draft.id,
            "institution_id": institution.id,
            "actor_user_id": user_id,
            "started_at": publish_started_at.isoformat(),
            "completed_at": publish_completed_at.isoformat(),
            "duration_ms": max(
                0, int((publish_completed_at - publish_started_at).total_seconds() * 1000)
            ),
            "outcome": "success",
            "summary": {
                "steps_total": len(publish_steps),
                "steps_passed": len(publish_steps),
                "checks_passed": sum(len(step.get("checks") or []) for step in publish_steps),
                "discrepancies_found": discrepancy_count,
                "discrepancies_fixed": discrepancy_count,
            },
            "steps": publish_steps,
        }

        audit_service.write_academia_audit(
            db,
            user_id=user_id,
            entity_type="institution",
            entity_id=institution.id,
            action="publish" if not old_institution_snapshot else "update",
            old_data=old_institution_snapshot,
            new_data={
                "institution_id": institution.id,
                "name": institution.name,
                "campus_id": campus.id,
                "campus_count": len(campus_records),
                "college_count": len(college_ids),
                "course_count": offering_sort,
                "academic_selection_count": len(parsed.courses),
                "intake_count": len(publish_payload.get("intakes") or []),
                "picture_count": len(unique_picture_assets),
                "payload": publish_payload,
                "publish_report": publish_report,
            },
        )

        draft.institution_id = institution.id
        draft.status = "published"
        draft.completed_steps = [1, 2, 3, 4, 5, 6]
        institution.publish_status = "success"
        institution.last_publish_attempt_at = datetime.now(timezone.utc)
        institution.last_publish_error = None
        db.commit()
        db.refresh(draft)
        return draft
    except HTTPException as exc:
        db.rollback()
        _record_publish_failure(db, draft_id, str(exc.detail))
        raise
    except Exception as exc:
        db.rollback()
        _record_publish_failure(db, draft_id, str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to publish institution: {exc}") from exc


def _record_publish_failure(db: Session, draft_id: int, error: str) -> None:
    """Persist the latest failed publish attempt after the publish transaction rolls back."""
    try:
        failed_draft = (
            db.query(InstitutionWizardDraft)
            .filter(InstitutionWizardDraft.id == draft_id)
            .first()
        )
        if not failed_draft or not failed_draft.institution_id:
            return
        institution = (
            db.query(Institution)
            .filter(Institution.id == failed_draft.institution_id)
            .first()
        )
        if not institution:
            return
        institution.publish_status = "failure"
        institution.last_publish_attempt_at = datetime.now(timezone.utc)
        institution.last_publish_error = (error or "Publish failed")[:5000]
        db.commit()
    except Exception:
        db.rollback()


def delete_draft_admin(db: Session, draft_id: int, *, user_id: int) -> None:
    draft = get_draft_admin(db, draft_id, user_id=user_id)
    if draft.status != "draft":
        raise HTTPException(status_code=400, detail="Published drafts cannot be deleted.")
    db.delete(draft)
    db.commit()


def list_institution_intakes(db: Session, institution_id: int) -> list[InstitutionIntake]:
    hub.get_institution_admin(db, institution_id)
    return (
        db.query(InstitutionIntake)
        .filter(InstitutionIntake.institution_id == institution_id)
        .order_by(InstitutionIntake.sort_order.asc(), InstitutionIntake.name.asc())
        .all()
    )


def list_institution_pictures(db: Session, institution_id: int) -> list[InstitutionPicture]:
    hub.get_institution_admin(db, institution_id)
    return (
        db.query(InstitutionPicture)
        .filter(InstitutionPicture.institution_id == institution_id)
        .order_by(InstitutionPicture.sort_order.asc())
        .all()
    )


def remove_institution_picture_references(
    db: Session,
    institution_id: int,
    deleted_keys: set[str],
) -> None:
    """Remove deleted storage objects from live picture rows and all wizard drafts."""
    from app.services.institution_asset_storage import storage_key_from_url

    normalized_keys = {key.strip().lstrip("/") for key in deleted_keys if key}
    if not normalized_keys:
        return

    picture_rows = (
        db.query(InstitutionPicture)
        .filter(InstitutionPicture.institution_id == institution_id)
        .all()
    )
    for row in picture_rows:
        if storage_key_from_url(row.url) in normalized_keys:
            db.delete(row)

    drafts = (
        db.query(InstitutionWizardDraft)
        .filter(InstitutionWizardDraft.institution_id == institution_id)
        .all()
    )
    for draft in drafts:
        payload = deepcopy(draft.payload or _default_payload())
        pictures = payload.get("pictures") or []
        filtered = [
            item
            for item in pictures
            if not (
                isinstance(item, dict)
                and storage_key_from_url(item.get("url")) in normalized_keys
            )
        ]
        if len(filtered) != len(pictures):
            payload["pictures"] = filtered
            draft.payload = payload
            flag_modified(draft, "payload")

    db.commit()
