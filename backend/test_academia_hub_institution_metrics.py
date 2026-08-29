"""Focused tests for Academia Hub institution list catalog counts."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.register_models import register_all_models
from app.services.academia_hub_service import (
    _COUNT_SORT_SUBQUERIES,
    _course_count_sort_subq,
    _coverage_pair,
    _education_course_ids_in,
    _institution_coverage_row,
    _mapped_count,
    _offering_catalog_metrics_query,
    accumulate_offering_catalog_row,
    _empty_catalog_sets,
)

register_all_models()


def test_level_count_is_registered_for_summary_sort():
    assert "level_count" in _COUNT_SORT_SUBQUERIES
    assert "course_count" in _COUNT_SORT_SUBQUERIES


def test_accumulate_offering_catalog_row_counts_distinct_chain():
    catalog = {1: _empty_catalog_sets()}
    program_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    program_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

    accumulate_offering_catalog_row(
        catalog,
        1,
        program_id=program_a,
        course_id=10,
        major_id=2,
        level_id=2,
    )
    accumulate_offering_catalog_row(
        catalog,
        1,
        program_id=program_a,
        course_id=10,
        major_id=2,
        level_id=2,
    )
    accumulate_offering_catalog_row(
        catalog,
        1,
        program_id=program_b,
        course_id=11,
        major_id=3,
        level_id=3,
    )

    level_ids, program_ids, major_ids, course_ids = catalog[1]
    assert len(level_ids) == 2
    assert len(program_ids) == 2
    assert len(major_ids) == 2
    assert len(course_ids) == 2
    assert catalog[1][3] == {10, 11}


def test_offering_catalog_metrics_query_stays_aggregated():
    engine = create_engine("sqlite://")
    db = sessionmaker(bind=engine)()
    query = _offering_catalog_metrics_query(db, [1, 2, 3])
    sql = str(query.statement.compile(compile_kwargs={"literal_binds": True})).lower()
    assert "group by" in sql
    assert "count(" in sql
    assert "institution_course_offerings" in sql
    assert "target_courses" in sql


def test_offering_catalog_metrics_query_excludes_program_clone_courses():
    """Courses must not equal programs when offerings are 1:1 program clones."""
    engine = create_engine("sqlite://")
    db = sessionmaker(bind=engine)()
    query = _offering_catalog_metrics_query(db, [1, 2, 3])
    sql = str(query.statement.compile(compile_kwargs={"literal_binds": True})).lower()
    assert "education_courses" in sql
    assert "is distinct from" in sql
    # Must not count every offering.course_id as a course.
    assert "count(distinct(institution_course_offerings.course_id))" not in sql.replace(
        " ", ""
    ).replace("\n", "")


def test_course_count_sort_also_excludes_program_clones():
    engine = create_engine("sqlite://")
    db = sessionmaker(bind=engine)()
    sql = str(_course_count_sort_subq(db).compile(compile_kwargs={"literal_binds": True})).lower()
    assert "education_courses" in sql
    assert "is distinct from" in sql


def test_education_course_ids_in_returns_empty_without_rows():
    engine = create_engine("sqlite://")
    db = sessionmaker(bind=engine)()
    assert _education_course_ids_in(db, set()) == set()


def test_coverage_numerator_is_intersection_not_global_mapped_len():
    """All-tab used len(global mapped) capped to total, hiding offering-level gaps."""
    offered = {1, 2, 3}
    mapped_elsewhere = {1, 2, 3, 99, 100}
    assert _mapped_count(offered, mapped_elsewhere) == 3
    pair = _coverage_pair(mapped=len(mapped_elsewhere), total=len(offered))
    assert pair.mapped == 3
    assert pair.unmapped == 0
    real = _coverage_pair(mapped=_mapped_count({1, 2, 3}, {1}), total=3)
    assert real.mapped == 1
    assert real.unmapped == 2


def test_institution_coverage_uses_that_institution_program_set():
    row = _institution_coverage_row(
        institution_id=55,
        name="QUT",
        country_id=6,
        country_name="Australia",
        program_ids={10, 11, 12},
        with_major={10, 11, 12, 999},
        with_sub_major={10, 11, 12},
        with_course=set(),
        with_level={10, 11, 12},
        with_url={10, 11, 12},
    )
    assert row.program_count == 3
    assert row.without_major == 0
    assert row.without_sub_major == 0
    assert row.without_major_pct == 0.0
    gap = _institution_coverage_row(
        institution_id=50,
        name="Other",
        country_id=6,
        country_name="Australia",
        program_ids={1, 2},
        with_major={1},
        with_sub_major=set(),
        with_course=set(),
        with_level={1, 2},
        with_url={1, 2},
    )
    assert gap.without_major == 1
    assert gap.without_sub_major == 2
    assert gap.without_major_pct == 50.0
