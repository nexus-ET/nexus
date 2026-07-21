from __future__ import annotations

from enum import Enum

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.academia_geography import GeographyCity, GeographyState
from app.models.academia_institution import Campus, College, Institution
from app.models.country import Country


class GeographyEntityType(str, Enum):
    country = "country"
    state = "state"
    city = "city"


class GeographyStatusImpactRead(BaseModel):
    entity_type: GeographyEntityType
    entity_id: int
    entity_name: str
    current_is_active: bool
    proposed_is_active: bool
    states: int = 0
    cities: int = 0
    institutions: int = 0
    campuses: int = 0
    colleges: int = 0
    has_links: bool = False
    message: str = Field(default="")


def _join_parts(parts: list[str]) -> str:
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"


def _build_message(
    *,
    entity_label: str,
    proposed_is_active: bool,
    states: int,
    cities: int,
    institutions: int,
    campuses: int,
    colleges: int,
) -> str:
    parts: list[str] = []
    if states:
        parts.append(f"{states} state{'s' if states != 1 else ''}")
    if cities:
        parts.append(f"{cities} cit{'ies' if cities != 1 else 'y'}")
    if institutions:
        parts.append(f"{institutions} institution{'s' if institutions != 1 else ''}")
    if campuses:
        parts.append(f"{campuses} campus{'es' if campuses != 1 else ''}")
    if colleges:
        parts.append(f"{colleges} college{'s' if colleges != 1 else ''}")

    linked = _join_parts(parts)
    if proposed_is_active:
        if not linked:
            return (
                f"Reactivating this {entity_label} will make it available again in geography "
                "pickers and dial-code lists."
            )
        return (
            f"Reactivating this {entity_label} will not automatically change {linked} linked to it. "
            "Review those records separately if needed."
        )

    if not linked:
        return (
            f"Set this {entity_label} to Inactive? It will be hidden from active geography "
            "pickers and dial-code lists."
        )
    return (
        f"This {entity_label} is linked to {linked}. Setting it Inactive will hide it from "
        "active geography pickers and dial-code lists, but will not change those linked records. "
        "Confirm only if you intend to stop using this location for new selections."
    )


def get_geography_status_impact(
    db: Session,
    *,
    entity_type: GeographyEntityType,
    entity_id: int,
    proposed_is_active: bool,
) -> GeographyStatusImpactRead:
    states = 0
    cities = 0
    institutions = 0
    campuses = 0
    colleges = 0

    if entity_type == GeographyEntityType.country:
        record = db.query(Country).filter(Country.id == entity_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Country not found.")
        entity_name = record.name
        current_is_active = bool(record.is_active)
        states = (
            db.query(GeographyState).filter(GeographyState.country_id == entity_id).count()
        )
        cities = (
            db.query(GeographyCity).filter(GeographyCity.country_id == entity_id).count()
        )
        institutions = (
            db.query(Institution).filter(Institution.country_id == entity_id).count()
        )
        campuses = db.query(Campus).filter(Campus.country_id == entity_id).count()
        colleges = (
            db.query(College)
            .outerjoin(Campus, Campus.id == College.campus_id)
            .outerjoin(Institution, Institution.id == College.institution_id)
            .filter(
                (Campus.country_id == entity_id) | (Institution.country_id == entity_id)
            )
            .distinct()
            .count()
        )
        entity_label = "country"
    elif entity_type == GeographyEntityType.state:
        record = db.query(GeographyState).filter(GeographyState.id == entity_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="State not found.")
        entity_name = record.name
        current_is_active = bool(record.is_active)
        cities = db.query(GeographyCity).filter(GeographyCity.state_id == entity_id).count()
        institutions = (
            db.query(Institution).filter(Institution.state_id == entity_id).count()
        )
        campuses = db.query(Campus).filter(Campus.state_id == entity_id).count()
        colleges = (
            db.query(College)
            .outerjoin(Campus, Campus.id == College.campus_id)
            .outerjoin(Institution, Institution.id == College.institution_id)
            .filter((Campus.state_id == entity_id) | (Institution.state_id == entity_id))
            .distinct()
            .count()
        )
        entity_label = "state"
    else:
        record = db.query(GeographyCity).filter(GeographyCity.id == entity_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="City not found.")
        entity_name = record.name
        current_is_active = bool(record.is_active)
        institutions = (
            db.query(Institution).filter(Institution.city_id == entity_id).count()
        )
        campuses = db.query(Campus).filter(Campus.location_id == entity_id).count()
        colleges = (
            db.query(College)
            .outerjoin(Campus, Campus.id == College.campus_id)
            .outerjoin(Institution, Institution.id == College.institution_id)
            .filter(
                (Campus.location_id == entity_id) | (Institution.city_id == entity_id)
            )
            .distinct()
            .count()
        )
        entity_label = "city"

    has_links = any(
        count > 0 for count in (states, cities, institutions, campuses, colleges)
    )
    return GeographyStatusImpactRead(
        entity_type=entity_type,
        entity_id=entity_id,
        entity_name=entity_name,
        current_is_active=current_is_active,
        proposed_is_active=proposed_is_active,
        states=states,
        cities=cities,
        institutions=institutions,
        campuses=campuses,
        colleges=colleges,
        has_links=has_links,
        message=_build_message(
            entity_label=entity_label,
            proposed_is_active=proposed_is_active,
            states=states,
            cities=cities,
            institutions=institutions,
            campuses=campuses,
            colleges=colleges,
        ),
    )
