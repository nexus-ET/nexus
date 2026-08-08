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
IntakeCalendarSystemOption = Literal["SEMESTER", "TRIMESTER", "QUARTER"]
IntakeTermOption = Literal["FALL", "SPRING", "WINTER", "Q1", "Q2", "Q3", "Q4"]
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
PostStudyGoalOption = Literal[
    "RETURN_HOME",
    "PSW_WORK_EXPERIENCE",
    "PATHWAY_PR",
    "UNDECIDED",
    "OTHER",
]
CountryPriorityOption = Literal["TOP_CHOICE", "ALTERNATIVE"]

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
_INTAKE_CALENDAR_ALLOWED = {"SEMESTER", "TRIMESTER", "QUARTER"}
_INTAKE_TERMS_BY_SYSTEM: dict[str, set[str]] = {
    "SEMESTER": {"FALL", "SPRING"},
    "TRIMESTER": {"FALL", "WINTER", "SPRING"},
    "QUARTER": {"Q1", "Q2", "Q3", "Q4"},
}
_INTAKE_TERM_ALLOWED = {"FALL", "SPRING", "WINTER", "Q1", "Q2", "Q3", "Q4"}


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

    calendar_raw = migrated.get("intake_calendar_system")
    calendar_system = ""
    if isinstance(calendar_raw, str):
        token = calendar_raw.strip().upper()
        if token == "QUARTERLY":
            token = "QUARTER"
        if token in _INTAKE_CALENDAR_ALLOWED:
            calendar_system = token
    migrated["intake_calendar_system"] = calendar_system or None

    terms_raw = migrated.get("intake_terms") or []
    allowed_terms = (
        _INTAKE_TERMS_BY_SYSTEM.get(calendar_system, _INTAKE_TERM_ALLOWED)
        if calendar_system
        else _INTAKE_TERM_ALLOWED
    )
    normalized_terms: list[str] = []
    if isinstance(terms_raw, list):
        for item in terms_raw:
            token = str(item or "").strip().upper().replace(" ", "_")
            if token in allowed_terms and token not in normalized_terms:
                normalized_terms.append(token)
    migrated["intake_terms"] = normalized_terms

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
        migrated["programs"] = normalized_programs[:4]

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

    level_code = migrated.get("study_level_code")
    if isinstance(level_code, str):
        migrated["study_level_code"] = level_code.strip().upper() or None
    elif level_code is not None:
        migrated["study_level_code"] = None

    standing = migrated.get("academic_standing_code")
    if isinstance(standing, str):
        migrated["academic_standing_code"] = standing.strip().upper() or None

    level_id = migrated.get("current_level_id")
    if level_id is not None and level_id != "":
        try:
            migrated["current_level_id"] = int(level_id)
        except (TypeError, ValueError):
            migrated["current_level_id"] = None
    else:
        migrated["current_level_id"] = None

    study_years = migrated.get("current_full_time_study_years")
    if isinstance(study_years, str):
        migrated["current_full_time_study_years"] = study_years.strip() or None

    program_code = migrated.get("current_program_code")
    if isinstance(program_code, str):
        migrated["current_program_code"] = program_code.strip().upper() or None

    major = migrated.get("current_major")
    if isinstance(major, str):
        migrated["current_major"] = major.strip() or None

    post_study_goals = migrated.get("post_study_goals")
    if not isinstance(post_study_goals, list) or not post_study_goals:
        legacy_goal = migrated.get("post_study_goal")
        if isinstance(legacy_goal, str) and legacy_goal.strip():
            migrated["post_study_goals"] = [legacy_goal.strip().upper()]
    else:
        migrated["post_study_goals"] = [
            str(item).strip().upper()
            for item in post_study_goals
            if str(item or "").strip()
        ]

    target_countries = migrated.get("target_countries")
    if not isinstance(target_countries, list) or not target_countries:
        countries = migrated.get("study_countries_iso2") or []
        if isinstance(countries, list):
            migrated["target_countries"] = [
                {
                    "iso2": str(item).strip().upper(),
                    "priority": "TOP_CHOICE" if index == 0 else "ALTERNATIVE",
                }
                for index, item in enumerate(countries)
                if str(item or "").strip()
            ][:6]
            migrated["study_countries_iso2"] = [
                item["iso2"] for item in migrated["target_countries"]
            ]
    else:
        normalized_targets = []
        for index, item in enumerate(target_countries):
            if isinstance(item, dict):
                iso2 = str(item.get("iso2") or "").strip().upper()
                priority = item.get("priority")
            else:
                iso2 = str(getattr(item, "iso2", "") or "").strip().upper()
                priority = getattr(item, "priority", None)
            if not iso2:
                continue
            if priority not in {"TOP_CHOICE", "ALTERNATIVE"}:
                priority = "TOP_CHOICE" if index == 0 else "ALTERNATIVE"
            normalized_targets.append({"iso2": iso2, "priority": priority})
        migrated["target_countries"] = normalized_targets[:6]
        migrated["study_countries_iso2"] = [item["iso2"] for item in normalized_targets[:6]]

    return migrated


class FundingSourceSelection(BaseModel):
    source: FundingSourceOption
    coverage: GrantScholarshipTypeOption


class TargetCountrySelection(BaseModel):
    iso2: str
    priority: CountryPriorityOption = "ALTERNATIVE"

    @field_validator("iso2", mode="before")
    @classmethod
    def normalize_iso2(cls, value: str | None) -> str:
        return (value or "").strip().upper()


class StudentAspirationsData(BaseModel):
    why_study_abroad: list[WhyStudyAbroadOption] = Field(default_factory=list)
    why_study_abroad_other: str | None = Field(default=None, max_length=100)
    post_study_goal: PostStudyGoalOption | None = None
    post_study_goals: list[PostStudyGoalOption] = Field(default_factory=list)
    post_study_goal_other: str | None = Field(default=None, max_length=200)
    study_countries_iso2: list[str] = Field(default_factory=list)
    study_countries_other: str | None = Field(default=None, max_length=100)
    target_countries: list[TargetCountrySelection] = Field(default_factory=list)
    institution_type: list[InstitutionTypeOption] = Field(default_factory=list)
    global_ranking: list[GlobalRankingOption] = Field(default_factory=list)
    budget: list[BudgetOption] = Field(default_factory=list)
    intake_seasons: list[IntakeSeasonOption] = Field(default_factory=list)
    intake_season_other: str | None = None
    intake_calendar_system: IntakeCalendarSystemOption | None = None
    intake_terms: list[IntakeTermOption] = Field(default_factory=list)
    intake_years: list[int] = Field(default_factory=list)
    study_level_code: str | None = None
    discipline_university_college: list[str] = Field(default_factory=list)
    discipline_pre_college: list[str] = Field(default_factory=list)
    programs: list[str] = Field(default_factory=list)
    programs_other: str | None = Field(default=None, max_length=50)
    academic_standing_code: str | None = None
    academic_standing_other: str | None = None
    current_level_id: int | None = None
    current_full_time_study_years: str | None = None
    current_program_code: str | None = None
    current_major: str | None = None
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
