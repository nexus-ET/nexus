"""Framework /academia/degrees offering filters (country / institution)."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Query, sessionmaker

from app.models.program import Program
from app.services.academia_hub_service import _program_offering_match_exists


def _compile(clause) -> str:
    engine = create_engine("sqlite://")
    db = sessionmaker(bind=engine)()
    try:
        sql = str(
            Query(Program.id, session=db)
            .filter(clause)
            .statement.compile(compile_kwargs={"literal_binds": True})
        )
    finally:
        db.close()
    return sql.lower()


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
