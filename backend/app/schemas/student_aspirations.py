from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

WhyStudyAbroadOption = Literal[
    "INTERNATIONAL_REPUTATION",
    "BETTER_JOB_PROSPECTS",
    "BETTER_COURSE_QUALITY",
    "BETTER_RESEARCH",
    "LIFE_CHANGE",
    "OTHER",
]

InstitutionTypeOption = Literal[
    "PUBLIC_STATE_UNIVERSITY",
    "PRIVATE_UNIVERSITY",
    "COMMUNITY_COLLEGE_TECHNICAL",
    "ANY",
]
GlobalRankingOption = Literal[
    "TOP_100_GLOBAL_ELITE",
    "TOP_300_RESEARCH_INTENSIVE",
    "TOP_500_BROAD_ACADEMIC",
    "ANY_INCLUSIVE",
]
BudgetOption = Literal[
    "BUDGET_FRIENDLY",
    "MID_RANGE",
    "PREMIUM",
    "HIGH_INVESTMENT",
    "NEEDS_FULL_FUNDING",
]
IntakeSeasonOption = Literal[
    "JAN_FEB_SPRING",
    "APR_MAY_SUMMER",
    "JUL_AUG_SEP_OCT_AUTUMN",
    "FEB_MAR_SEM1_AUS_NZ",
    "JUL_AUG_SEM2_AUS_NZ",
    "APRIL_JAPAN",
    "OTHER",
]
EnglishTestOption = Literal[
    "IELTS",
    "TOEFL",
    "PTE",
    "DUOLINGO",
    "CAMBRIDGE_C1_C2",
    "NOT_TAKEN_YET_PLANNING",
    "WAIVER_NOT_REQUIRED",
]
AptitudeTestOption = Literal[
    "GRE",
    "GMAT",
    "SAT",
    "ACT",
    "LSAT_MCAT",
    "NOT_TAKEN_YET_PLANNING",
    "NOT_REQUIRED_TEST_OPTIONAL",
]
FundingSourceOption = Literal["FAMILY_SPONSORED", "EDUCATIONAL_LOAN", "GRANT_SCHOLARSHIP"]
GrantScholarshipTypeOption = Literal["FULL", "PARTIAL", "NOT_REQUIRED"]
UniversityManagedAccommodationOption = Literal["ON_CAMPUS", "DORM"]
OffCampusIndependentAccommodationOption = Literal["PRIVATE_ROOM", "PRIVATE_APARTMENT"]
SharedLivingAccommodationOption = Literal["SHARED_NATIVE", "SHARED_INTERNATIONAL"]
ImmersiveFamilyAccommodationOption = Literal["HOMESTAYS", "HOST_FAMILY"]
FutureLocationOption = Literal["HOME_COUNTRY", "STUDY_COUNTRY", "ANOTHER_COUNTRY"]

_LEGACY_BUDGET_MAP = {
    "UPTO_30L": "BUDGET_FRIENDLY",
    "BETWEEN_30_50L": "MID_RANGE",
    "ABOVE_50L": "HIGH_INVESTMENT",
    "NO_FUNDING": "NEEDS_FULL_FUNDING",
}
_BUDGET_ALLOWED = set(_LEGACY_BUDGET_MAP.values()) | {"PREMIUM"}

_LEGACY_GLOBAL_RANKING_MAP = {
    "TOP_100": "TOP_100_GLOBAL_ELITE",
    "TOP_300": "TOP_300_RESEARCH_INTENSIVE",
    "ANY": "ANY_INCLUSIVE",
}
_GLOBAL_RANKING_ALLOWED = {
    "TOP_100_GLOBAL_ELITE",
    "TOP_300_RESEARCH_INTENSIVE",
    "TOP_500_BROAD_ACADEMIC",
    "ANY_INCLUSIVE",
}

_LEGACY_INSTITUTION_TYPE_MAP = {
    "PUBLIC": "PUBLIC_STATE_UNIVERSITY",
    "PRIVATE": "PRIVATE_UNIVERSITY",
}
_INSTITUTION_TYPE_ALLOWED = {
    "PUBLIC_STATE_UNIVERSITY",
    "PRIVATE_UNIVERSITY",
    "COMMUNITY_COLLEGE_TECHNICAL",
    "ANY",
}

_LEGACY_INTAKE_MAP = {
    "FALL": "JUL_AUG_SEP_OCT_AUTUMN",
    "SUMMER": "APR_MAY_SUMMER",
    "WINTER": "JAN_FEB_SPRING",
}
_INTAKE_ALLOWED = {
    "JAN_FEB_SPRING",
    "APR_MAY_SUMMER",
    "JUL_AUG_SEP_OCT_AUTUMN",
    "FEB_MAR_SEM1_AUS_NZ",
    "JUL_AUG_SEM2_AUS_NZ",
    "APRIL_JAPAN",
    "OTHER",
}


def _normalize_option_list(
    value: list[str] | None,
    *,
    legacy_map: dict[str, str],
    allowed: set[str],
) -> list[str]:
    if not value:
        return []
    normalized: list[str] = []
    for item in value:
        token = legacy_map.get(str(item).strip().upper(), str(item).strip().upper())
        if token in allowed and token not in normalized:
            normalized.append(token)
    return normalized


def migrate_legacy_aspirations_data(data: object) -> object:
    """Normalize legacy enum values before Pydantic literal validation."""
    if not isinstance(data, dict):
        return data

    migrated = dict(data)

    if migrated.get("funding_sources"):
        pass
    elif migrated.get("funding_source"):
        migrated = {
            **migrated,
            "funding_sources": [
                {
                    "source": migrated.get("funding_source"),
                    "coverage": migrated.get("grant_scholarship_type") or "FULL",
                }
            ],
        }

    if migrated.get("accommodation_university_managed") is None:
        on_campus = migrated.get("accommodation_on_campus") or []
        off_campus = migrated.get("accommodation_off_campus") or []
        homestays = migrated.get("accommodation_homestays") or []

        university_managed: list[str] = []
        if "DORM" in on_campus:
            university_managed.append("DORM")
        if "ON_CAMPUS" in on_campus:
            university_managed.append("ON_CAMPUS")

        off_campus_independent: list[str] = []
        if "PRIVATE_ROOM" in on_campus:
            off_campus_independent.append("PRIVATE_ROOM")
        if "PRIVATE_APARTMENT" in off_campus:
            off_campus_independent.append("PRIVATE_APARTMENT")

        shared_living = [
            item for item in off_campus if item in {"SHARED_NATIVE", "SHARED_INTERNATIONAL"}
        ]

        immersive_family: list[str] = []
        if "HOST_FAMILY" in homestays:
            immersive_family.append("HOST_FAMILY")
        if "HOMESTAYS" in homestays:
            immersive_family.append("HOMESTAYS")

        migrated = {
            **migrated,
            "accommodation_university_managed": university_managed,
            "accommodation_off_campus_independent": off_campus_independent,
            "accommodation_shared_living": shared_living,
            "accommodation_immersive_family": immersive_family,
        }
        migrated.pop("accommodation_on_campus", None)
        migrated.pop("accommodation_off_campus", None)
        migrated.pop("accommodation_homestays", None)

    migrated["budget"] = _normalize_option_list(
        migrated.get("budget"),
        legacy_map=_LEGACY_BUDGET_MAP,
        allowed=_BUDGET_ALLOWED,
    )
    migrated["global_ranking"] = _normalize_option_list(
        migrated.get("global_ranking"),
        legacy_map=_LEGACY_GLOBAL_RANKING_MAP,
        allowed=_GLOBAL_RANKING_ALLOWED,
    )
    migrated["institution_type"] = _normalize_option_list(
        migrated.get("institution_type"),
        legacy_map=_LEGACY_INSTITUTION_TYPE_MAP,
        allowed=_INSTITUTION_TYPE_ALLOWED,
    )
    migrated["intake_seasons"] = _normalize_option_list(
        migrated.get("intake_seasons"),
        legacy_map=_LEGACY_INTAKE_MAP,
        allowed=_INTAKE_ALLOWED,
    )

    programs = migrated.get("programs") or []
    if isinstance(programs, list):
        normalized_programs: list[str] = []
        for item in programs:
            token = (item or "").strip()
            if not token:
                continue
            if token.lower() == "other":
                token = "OTHER"
            if token not in normalized_programs:
                normalized_programs.append(token)
        migrated["programs"] = normalized_programs

    countries = migrated.get("study_countries_iso2") or []
    if isinstance(countries, list):
        migrated["study_countries_iso2"] = [
            item.strip().upper() for item in countries if (item or "").strip()
        ]

    for field_name in ("discipline_university_college", "discipline_pre_college"):
        values = migrated.get(field_name) or []
        if isinstance(values, list):
            migrated[field_name] = [
                item.strip().upper() for item in values if (item or "").strip()
            ]

    return migrated


class FundingSourceSelection(BaseModel):
    source: FundingSourceOption
    coverage: GrantScholarshipTypeOption


class StudentAspirationsData(BaseModel):
    why_study_abroad: list[WhyStudyAbroadOption] = Field(default_factory=list)
    why_study_abroad_other: str | None = Field(default=None, max_length=100)
    study_countries_iso2: list[str] = Field(default_factory=list)
    study_countries_other: str | None = Field(default=None, max_length=100)
    institution_type: list[InstitutionTypeOption] = Field(default_factory=list)
    global_ranking: list[GlobalRankingOption] = Field(default_factory=list)
    budget: list[BudgetOption] = Field(default_factory=list)
    intake_seasons: list[IntakeSeasonOption] = Field(default_factory=list)
    intake_season_other: str | None = None
    intake_years: list[int] = Field(default_factory=list)
    discipline_university_college: list[str] = Field(default_factory=list)
    discipline_pre_college: list[str] = Field(default_factory=list)
    programs: list[str] = Field(default_factory=list)
    programs_other: str | None = Field(default=None, max_length=50)
    english_tests: list[EnglishTestOption] = Field(default_factory=list)
    aptitude_tests: list[AptitudeTestOption] = Field(default_factory=list)
    funding_sources: list[FundingSourceSelection] = Field(default_factory=list)
    funding_source: FundingSourceOption | None = None
    grant_scholarship_type: GrantScholarshipTypeOption | None = None
    accommodation_university_managed: list[UniversityManagedAccommodationOption] = Field(
        default_factory=list
    )
    accommodation_off_campus_independent: list[OffCampusIndependentAccommodationOption] = Field(
        default_factory=list
    )
    accommodation_shared_living: list[SharedLivingAccommodationOption] = Field(default_factory=list)
    accommodation_immersive_family: list[ImmersiveFamilyAccommodationOption] = Field(
        default_factory=list
    )
    future_job: list[FutureLocationOption] = Field(default_factory=list)
    future_study: list[FutureLocationOption] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_values(cls, data):
        return migrate_legacy_aspirations_data(data)

    @field_validator("study_countries_iso2", mode="before")
    @classmethod
    def normalize_country_codes(cls, value: list[str] | None) -> list[str]:
        if not value:
            return []
        return [item.strip().upper() for item in value if (item or "").strip()]

    @field_validator("programs", mode="before")
    @classmethod
    def migrate_legacy_programs(cls, value: list[str] | None) -> list[str]:
        if not value:
            return []
        normalized: list[str] = []
        for item in value:
            token = (item or "").strip()
            if not token:
                continue
            if token.lower() == "other":
                token = "OTHER"
            if token not in normalized:
                normalized.append(token)
        return normalized

    @field_validator(
        "discipline_university_college",
        "discipline_pre_college",
        mode="before",
    )
    @classmethod
    def normalize_degree_codes(cls, value: list[str] | None) -> list[str]:
        if not value:
            return []
        return [item.strip().upper() for item in value if (item or "").strip()]


class StudentAspirationsSaveRequest(BaseModel):
    aspirations: StudentAspirationsData


class StudentAspirationsResponse(BaseModel):
    students_master_id: int | None = None
    booking_id: int | None = None
    aspirations: StudentAspirationsData
    saved_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
