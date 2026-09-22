"""Framework /academia/degrees offering filters (country / institution / pem_gap)."""

from sqlalchemy.dialects import postgresql

# Import relationship targets so Program/Level mappers can configure in isolation.
from app.models.education_degree import EducationDegree  # noqa: F401
from app.models.level import Level  # noqa: F401
from app.models.program import Program  # noqa: F401
from app.services.academia_hub_service import (
    _program_offering_match_exists,
    _program_pem_gap_filter,
)


def _compile(clause) -> str:
    return str(
        clause.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()


def test_institution_filter_uses_inner_offering_join_not_left():
    sql = _compile(_program_offering_match_exists(institution_ids=[42]))
    assert "exists" in sql
    assert "institution_course_offerings" in sql
    assert "target_courses" in sql
    assert "qualification_program_id" in sql
    assert "institution_id" in sql
    assert "42" in sql
    assert "left outer join" not in sql


def test_country_filter_joins_institutions():
    sql = _compile(_program_offering_match_exists(country_ids=[7]))
    assert "exists" in sql
    assert "institution_course_offerings" in sql
    assert "institutions" in sql
    assert "country_id" in sql
    assert "7" in sql
    assert "left outer join" not in sql


def test_institution_and_country_filters_are_both_applied():
    sql = _compile(
        _program_offering_match_exists(country_ids=[7], institution_ids=[42])
    )
    assert "42" in sql
    assert "7" in sql
    assert "institution_id" in sql
    assert "country_id" in sql


def test_pem_gap_both_requires_no_major_and_no_sub():
    sql = _compile(_program_pem_gap_filter("both"))
    assert "program_education_major_mappings" in sql
    assert "exists" in sql
    assert "not exists" in sql or "not (exists" in sql


def test_pem_gap_major_requires_no_major_pem():
    sql = _compile(_program_pem_gap_filter("major"))
    assert "program_education_major_mappings" in sql
    assert "not exists" in sql or "not (exists" in sql


def test_pem_gap_sub_major_is_major_only():
    sql = _compile(_program_pem_gap_filter("sub_major"))
    assert "program_education_major_mappings" in sql
    assert "exists" in sql
    assert "not exists" in sql or "not (exists" in sql
    assert "education_sub_major_id" in sql


def test_pem_gap_empty_returns_none():
    assert _program_pem_gap_filter(None) is None
    assert _program_pem_gap_filter("") is None
    assert _program_pem_gap_filter("  ") is None
