"""Seed / reset FlowX Student Journey demo data for a lead (US / CA / GB).

Tagged Academia rows use code prefix FXTEST{lead_id}_ so they can be removed
without touching production catalog institutions.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.academia_geography import GeographyCity, GeographyState
from app.models.academia_institution import Campus, CampusType, College, Institution
from app.models.academia_wizard import InstitutionIntake
from app.models.country import Country
from app.models.flowx import FlowxEnrollment
from app.models.lead import Lead
from app.models.program import Program
from app.services import flowx as flowx_service
from app.utils.timezone import utc_now

DEFAULT_LEAD_ID = 27


def _markers(lead_id: int) -> tuple[str, str, str]:
    code_prefix = f"FXTEST{lead_id}_"
    desc_tag = f"[flowx_journey_test:lead{lead_id}]"
    geo_region = f"FXTEST{lead_id}"
    return code_prefix, desc_tag, geo_region


def _country(db: Session, iso2: str) -> Country:
    row = db.query(Country).filter(func.upper(Country.iso2) == iso2.upper()).first()
    if not row:
        raise ValueError(f"Country {iso2} not found in Academia countries table")
    return row


def _ensure_geo(
    db: Session,
    *,
    country: Country,
    state_name: str,
    city_name: str,
    geo_region: str,
) -> tuple[GeographyState, GeographyCity]:
    state = (
        db.query(GeographyState)
        .filter(
            GeographyState.country_id == country.id,
            GeographyState.name == state_name,
        )
        .first()
    )
    if not state:
        state = GeographyState(
            country_id=country.id,
            name=state_name,
            region_code=geo_region,
            is_active=True,
            sort_order=900,
        )
        db.add(state)
        db.flush()

    city = (
        db.query(GeographyCity)
        .filter(
            GeographyCity.country_id == country.id,
            GeographyCity.state_id == state.id,
            GeographyCity.name == city_name,
        )
        .first()
    )
    if not city:
        city = GeographyCity(
            country_id=country.id,
            state_id=state.id,
            name=city_name,
            is_active=True,
            sort_order=900,
        )
        db.add(city)
        db.flush()
    return state, city


def _campus_type_id(db: Session) -> int | None:
    row = db.query(CampusType).order_by(CampusType.id.asc()).first()
    return row.id if row else None


def _program(db: Session, code: str) -> Program:
    row = db.query(Program).filter(Program.code == code, Program.is_active.is_(True)).first()
    if not row:
        raise ValueError(f"Qualification program code={code} not found — seed Academia programs first")
    return row


def _delete_tagged_academia(db: Session, lead_id: int) -> dict[str, int]:
    code_prefix, desc_tag, geo_region = _markers(lead_id)
    institutions = (
        db.query(Institution)
        .filter(
            or_(
                Institution.code.ilike(f"{code_prefix}%"),
                Institution.short_description.ilike(f"%{desc_tag}%"),
            )
        )
        .all()
    )
    inst_ids = [i.id for i in institutions]
    counts = {
        "institutions": len(inst_ids),
        "intakes": 0,
        "colleges": 0,
        "campuses": 0,
        "states": 0,
        "cities": 0,
    }
    if inst_ids:
        counts["intakes"] = (
            db.query(InstitutionIntake)
            .filter(InstitutionIntake.institution_id.in_(inst_ids))
            .delete(synchronize_session=False)
        )
        counts["colleges"] = (
            db.query(College)
            .filter(College.institution_id.in_(inst_ids))
            .delete(synchronize_session=False)
        )
        counts["campuses"] = (
            db.query(Campus)
            .filter(Campus.institution_id.in_(inst_ids))
            .delete(synchronize_session=False)
        )
        db.query(Institution).filter(Institution.id.in_(inst_ids)).delete(synchronize_session=False)

    # Only remove geography created for this pack (never stamp/delete pre-existing states).
    test_states = (
        db.query(GeographyState)
        .filter(
            GeographyState.region_code == geo_region,
            GeographyState.sort_order == 900,
        )
        .all()
    )
    state_ids = [s.id for s in test_states]
    if state_ids:
        counts["cities"] = (
            db.query(GeographyCity)
            .filter(
                GeographyCity.state_id.in_(state_ids),
                GeographyCity.sort_order == 900,
            )
            .delete(synchronize_session=False)
        )
        counts["states"] = (
            db.query(GeographyState)
            .filter(GeographyState.id.in_(state_ids))
            .delete(synchronize_session=False)
        )
    return counts


def _delete_lead_enrollments(db: Session, lead_id: int) -> int:
    rows = db.query(FlowxEnrollment).filter(FlowxEnrollment.lead_id == lead_id).all()
    n = len(rows)
    for enrollment in rows:
        db.delete(enrollment)
    return n


def reset_journey_test_data(db: Session, lead_id: int) -> dict[str, Any]:
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise ValueError(f"Lead {lead_id} not found")
    n_enroll = _delete_lead_enrollments(db, lead_id)
    academia = _delete_tagged_academia(db, lead_id)
    db.commit()
    return {
        "lead_id": lead_id,
        "lead_name": lead.full_name,
        "enrollments_deleted": n_enroll,
        "academia": academia,
    }


def _create_institution(
    db: Session,
    *,
    country: Country,
    state: GeographyState,
    city: GeographyCity,
    code: str,
    name: str,
    campus_name: str,
    colleges: list[tuple[str, str]],
    intakes: list[tuple[str, str, int]],
    desc_tag: str,
) -> tuple[Institution, Campus, list[College], list[InstitutionIntake]]:
    existing = db.query(Institution).filter(Institution.code == code).first()
    if existing:
        db.query(InstitutionIntake).filter(InstitutionIntake.institution_id == existing.id).delete(
            synchronize_session=False
        )
        db.query(College).filter(College.institution_id == existing.id).delete(synchronize_session=False)
        db.query(Campus).filter(Campus.institution_id == existing.id).delete(synchronize_session=False)
        inst = existing
        inst.name = name
        inst.country_id = country.id
        inst.state_id = state.id
        inst.city_id = city.id
        inst.short_description = f"{desc_tag} Temporary journey-test institution"
        inst.is_active = True
        inst.publish_status = "published"
    else:
        iso = (country.iso2 or "").upper()
        inst = Institution(
            name=name,
            code=code,
            country_id=country.id,
            state_id=state.id,
            city_id=city.id,
            short_description=f"{desc_tag} Temporary journey-test institution",
            is_active=True,
            publish_status="published",
            currency_type="USD" if iso == "US" else ("CAD" if iso == "CA" else "GBP"),
            sort_order=900,
        )
        db.add(inst)
        db.flush()

    campus = Campus(
        institution_id=inst.id,
        name=campus_name,
        country_id=country.id,
        state_id=state.id,
        location_id=city.id,
        campus_type_id=_campus_type_id(db),
        city=city.name,
        is_active=True,
        sort_order=1,
    )
    db.add(campus)
    db.flush()

    college_rows: list[College] = []
    for idx, (col_code, col_name) in enumerate(colleges):
        college = College(
            institution_id=inst.id,
            campus_id=campus.id,
            code=col_code,
            name=col_name,
            is_active=True,
            sort_order=idx + 1,
        )
        db.add(college)
        college_rows.append(college)
    db.flush()

    intake_rows: list[InstitutionIntake] = []
    for idx, (iname, term, year) in enumerate(intakes):
        intake = InstitutionIntake(
            institution_id=inst.id,
            campus_id=campus.id,
            entity_type="institution",
            entity_id=inst.id,
            name=iname,
            term_name=term,
            year=year,
            intake_type="Fixed",
            status="Open",
            intake_code=f"{code}_{term}_{year}".replace(" ", "")[:50],
            start_date=date(year, 9 if "Fall" in term or "Autumn" in term else 1, 1),
            application_deadline=date(year, 1 if "Fall" in term or "Autumn" in term else 10, 15),
            level_ids=[2, 3],
            is_active=True,
            sort_order=idx + 1,
        )
        db.add(intake)
        intake_rows.append(intake)
    db.flush()
    return inst, campus, college_rows, intake_rows


def seed_journey_test_data(db: Session, lead_id: int) -> dict[str, Any]:
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.archived_at.is_(None)).first()
    if not lead:
        raise ValueError(f"Lead {lead_id} not found (or archived)")

    code_prefix, desc_tag, geo_region = _markers(lead_id)
    n_cleared = _delete_lead_enrollments(db, lead_id)
    # Drop previous tagged academia so institutions rebuild cleanly
    academia_cleared = _delete_tagged_academia(db, lead_id)
    db.flush()

    us = _country(db, "US")
    ca = _country(db, "CA")
    gb = _country(db, "GB")

    mi, ann = _ensure_geo(db, country=us, state_name="Michigan", city_name="Ann Arbor", geo_region=geo_region)
    on, tor = _ensure_geo(db, country=ca, state_name="Ontario", city_name="Toronto", geo_region=geo_region)
    bc, van = _ensure_geo(
        db, country=ca, state_name="British Columbia", city_name="Vancouver", geo_region=geo_region
    )
    eng, lon = _ensure_geo(db, country=gb, state_name="England", city_name="London", geo_region=geo_region)
    _eng2, man = _ensure_geo(
        db, country=gb, state_name="England", city_name="Manchester", geo_region=geo_region
    )
    ny_state, nyc = _ensure_geo(
        db, country=us, state_name="New York", city_name="New York City", geo_region=geo_region
    )

    beng = _program(db, "BENG")
    meng = _program(db, "MENG")
    mba = _program(db, "MBA")
    ba = _program(db, "BA")
    ma = _program(db, "MA")

    catalog: list[tuple] = []

    umich, umich_campus, umich_cols, umich_intakes = _create_institution(
        db,
        country=us,
        state=mi,
        city=ann,
        code=f"{code_prefix}UMICH",
        name="University of Michigan (FX Test)",
        campus_name="Ann Arbor Central",
        colleges=[
            (f"{code_prefix}UMICH_ENG", "College of Engineering"),
            (f"{code_prefix}UMICH_LSA", "College of Literature, Science, and the Arts"),
        ],
        intakes=[("Fall 2026", "Fall", 2026), ("Winter 2027", "Winter", 2027)],
        desc_tag=desc_tag,
    )
    catalog.append(
        ("US", umich, umich_campus, umich_cols, umich_intakes, beng, "Common App", "centralized_national_portal")
    )

    nyu, nyu_campus, nyu_cols, nyu_intakes = _create_institution(
        db,
        country=us,
        state=ny_state,
        city=nyc,
        code=f"{code_prefix}NYU",
        name="New York University (FX Test)",
        campus_name="Washington Square",
        colleges=[
            (f"{code_prefix}NYU_STERN", "Stern School of Business"),
            (f"{code_prefix}NYU_TANDON", "Tandon School of Engineering"),
        ],
        intakes=[("Fall 2026", "Fall", 2026), ("Spring 2027", "Spring", 2027)],
        desc_tag=desc_tag,
    )
    catalog.append(
        ("US", nyu, nyu_campus, nyu_cols, nyu_intakes, mba, "Common App", "centralized_national_portal")
    )

    uoft, uoft_campus, uoft_cols, uoft_intakes = _create_institution(
        db,
        country=ca,
        state=on,
        city=tor,
        code=f"{code_prefix}UOFT",
        name="University of Toronto (FX Test)",
        campus_name="St. George",
        colleges=[
            (f"{code_prefix}UOFT_ARTSCI", "Faculty of Arts & Science"),
            (f"{code_prefix}UOFT_ENG", "Faculty of Applied Science & Engineering"),
        ],
        intakes=[("Fall 2026", "Fall", 2026), ("Winter 2027", "Winter", 2027)],
        desc_tag=desc_tag,
    )
    catalog.append(
        ("CA", uoft, uoft_campus, uoft_cols, uoft_intakes, ba, "OUAC", "centralized_national_portal")
    )

    ubc, ubc_campus, ubc_cols, ubc_intakes = _create_institution(
        db,
        country=ca,
        state=bc,
        city=van,
        code=f"{code_prefix}UBC",
        name="University of British Columbia (FX Test)",
        campus_name="Point Grey",
        colleges=[
            (f"{code_prefix}UBC_SCI", "Faculty of Science"),
            (f"{code_prefix}UBC_SAUDER", "Sauder School of Business"),
        ],
        intakes=[("Winter 2026", "Winter", 2026), ("Fall 2026", "Fall", 2026)],
        desc_tag=desc_tag,
    )
    catalog.append(
        ("CA", ubc, ubc_campus, ubc_cols, ubc_intakes, meng, "OUAC", "centralized_national_portal")
    )

    ucl, ucl_campus, ucl_cols, ucl_intakes = _create_institution(
        db,
        country=gb,
        state=eng,
        city=lon,
        code=f"{code_prefix}UCL",
        name="University College London (FX Test)",
        campus_name="Bloomsbury",
        colleges=[
            (f"{code_prefix}UCL_ENG", "Faculty of Engineering Sciences"),
            (f"{code_prefix}UCL_LAW", "Faculty of Laws"),
        ],
        intakes=[("Autumn 2026", "Autumn", 2026), ("January 2027", "January", 2027)],
        desc_tag=desc_tag,
    )
    catalog.append(
        ("GB", ucl, ucl_campus, ucl_cols, ucl_intakes, ma, "UCAS", "centralized_national_portal")
    )

    manchester, man_campus, man_cols, man_intakes = _create_institution(
        db,
        country=gb,
        state=eng,
        city=man,
        code=f"{code_prefix}UMAN",
        name="University of Manchester (FX Test)",
        campus_name="Oxford Road",
        colleges=[
            (f"{code_prefix}UMAN_ENG", "Faculty of Science and Engineering"),
            (f"{code_prefix}UMAN_HUM", "Faculty of Humanities"),
        ],
        intakes=[("Autumn 2026", "Autumn", 2026), ("January 2027", "January", 2027)],
        desc_tag=desc_tag,
    )
    catalog.append(
        ("GB", manchester, man_campus, man_cols, man_intakes, beng, "UCAS", "centralized_national_portal")
    )

    db.flush()

    statuses = [
        "drafting",
        "submitted",
        "under_review",
        "conditional_offer",
        "drafting",
        "submitted",
    ]
    fee_plans = [
        ("pending_payment", 75.0, "USD"),
        ("paid", 80.0, "USD"),
        ("pending_payment", 150.0, "CAD"),
        ("fee_waiver", 0.0, "CAD"),
        ("pending_payment", 28.5, "GBP"),
        ("paid", 28.5, "GBP"),
    ]

    created: list[dict[str, Any]] = []
    now = utc_now()
    for idx, (iso2, inst, campus, colleges, intakes, program, pathway_name, pathway_type) in enumerate(
        catalog
    ):
        college = colleges[idx % len(colleges)]
        intake = intakes[0]
        app_status = statuses[idx % len(statuses)]
        fee_status, fee_amount, fee_currency = fee_plans[idx % len(fee_plans)]
        flowx_service.ensure_country_workflow(db, iso2)
        enrollment = flowx_service.enroll_lead(
            db,
            country_hint=iso2,
            lead_id=lead_id,
            institution_id=inst.id,
            college_id=college.id,
            campus_id=campus.id,
            level_id=program.level_id,
            qualification_program_id=program.id,
            intake_id=intake.id,
            pathway_type=pathway_type,
            pathway_name=pathway_name,
            portal_url=f"https://example.test/apply/{(inst.code or '').lower()}",
            portal_username=f"lead{lead_id}@{iso2.lower()}.test",
            portal_password_hint="team-hint-fx-test",
            institutional_app_id=f"{iso2}-{lead_id}-{(inst.code or '')[-4:]}",
            application_status=app_status,
            fee_status=fee_status,
            fee_amount=fee_amount,
            fee_currency=fee_currency,
            internal_target_date=now + timedelta(days=14 + idx * 3),
            official_deadline=now + timedelta(days=45 + idx * 5),
        )
        created.append(
            {
                "iso2": iso2,
                "enrollment_id": str(enrollment["id"]),
                "university": inst.name,
                "college": college.name,
                "program": program.name,
                "intake": intake.name,
                "status": app_status,
            }
        )

    db.commit()
    return {
        "lead_id": lead_id,
        "lead_name": lead.full_name,
        "enrollments_cleared": n_cleared,
        "academia_cleared": academia_cleared,
        "applications": created,
        "total": len(created),
    }
