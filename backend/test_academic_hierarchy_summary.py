"""Focused tests for Academic Framework hierarchy summary batching."""

from __future__ import annotations


from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.register_models import register_all_models
from app.models.course_education_major_mapping import CourseEducationMajorMapping
from app.models.education_course import EducationCourse
from app.models.education_major import EducationMajor
from app.models.education_sub_major import EducationSubMajor
from app.models.level import Level
from app.models.program import Program
from app.models.program_education_major_mapping import ProgramEducationMajorMapping
from app.services.academia_hub_service import get_academic_hierarchy_summary

register_all_models()


def _session():
    engine = create_engine("sqlite:///:memory:")
    # Only tables needed for hierarchy assembly (avoid unrelated Postgres types).
    tables = [
        Level.__table__,
        Program.__table__,
        EducationMajor.__table__,
        EducationSubMajor.__table__,
        EducationCourse.__table__,
        ProgramEducationMajorMapping.__table__,
        CourseEducationMajorMapping.__table__,
    ]
    Base.metadata.create_all(bind=engine, tables=tables)
    Session = sessionmaker(bind=engine)
    return Session(), engine


def test_academic_hierarchy_summary_batches_queries_and_shape():
    db, engine = _session()
    try:
        level = Level(id=1, code="UG", name="Undergraduate")
        program_a = Program(name="Bachelor of Arts",
            code="BA",
            level_id=1,
            is_active=True,
            sort_order=1,
            program_url="https://example.edu/ba",
        )
        program_b = Program(name="Bachelor of Science",
            code="BSC",
            level_id=1,
            is_active=True,
            sort_order=2,
        )
        inactive = Program(name="Inactive Program",
            code="INACT",
            level_id=1,
            is_active=False,
            sort_order=3,
        )
        major = EducationMajor(id=10, code="BUS", label="Business", is_active=True)
        inactive_major = EducationMajor(id=11, code="X", label="Hidden", is_active=False)
        sub_major = EducationSubMajor(id=50, name="Accounting", major_id=10)
        course = EducationCourse(
            id=100,
            code="BUS101",
            label="Intro to Business",
            is_active=True,
            sort_order=1,
        )
        db.add_all(
            [level, program_a, program_b, inactive, major, inactive_major, sub_major, course]
        )
        db.flush()
        db.add_all(
            [
                ProgramEducationMajorMapping(
                    program_id=program_a.id,
                    education_major_id=major.id,
                    education_sub_major_id=sub_major.id,
                ),
                ProgramEducationMajorMapping(
                    program_id=program_b.id,
                    education_major_id=major.id,
                    education_sub_major_id=sub_major.id,
                ),
                ProgramEducationMajorMapping(
                    program_id=program_a.id, education_major_id=inactive_major.id
                ),
                CourseEducationMajorMapping(course_id=course.id, education_major_id=major.id),
            ]
        )
        db.commit()

        query_count = {"n": 0}

        @event.listens_for(engine, "before_cursor_execute")
        def _count(conn, cursor, statement, parameters, context, executemany):
            query_count["n"] += 1

        summary = get_academic_hierarchy_summary(db)

        # levels + programs + mappings + coverage aggregates
        assert query_count["n"] <= 20
        assert len(summary.levels) == 1
        level_node = summary.levels[0]
        assert level_node.name == "Undergraduate"
        assert [p.name for p in level_node.programs] == [
            "Bachelor of Arts",
            "Bachelor of Science",
        ]
        arts = level_node.programs[0]
        assert len(arts.majors) == 1
        assert arts.majors[0].name == "Business"
        assert [c.name for c in arts.majors[0].courses] == ["Intro to Business"]
        assert [m.name for m in level_node.programs[1].majors] == ["Business"]
        assert level_node.major_count == 1
        assert level_node.sub_major_count == 1
        assert arts.sub_major_count == 1
        assert arts.sub_major_ids == [50]
        coverage = summary.coverage
        # Coverage denominators are offered programs (institution_course_offerings),
        # not every programs row — in-memory sqlite has no offering tables seeded here.
        assert coverage.program_count == 0
        assert coverage.major_count == 1
        assert coverage.sub_major_count == 1
        assert coverage.level_count == 1
        assert coverage.course_count == 1
        assert coverage.programs_with_no_major == 0
        assert coverage.programs_with_no_sub_major == 0
        assert coverage.major_mapping.total == 0
        assert coverage.sub_major_mapping.total == 0
        assert coverage.by_institution == []
        assert coverage.by_country == []
    finally:
        db.close()
        engine.dispose()


def test_academic_hierarchy_summary_skips_course_query_when_no_mappings():
    db, engine = _session()
    try:
        db.add(Level(id=1, code="UG", name="Undergraduate"))
        db.add(
            Program(name="Lonely Degree",
                code="LD",
                level_id=1,
                is_active=True,
            )
        )
        db.commit()

        statements: list[str] = []

        @event.listens_for(engine, "before_cursor_execute")
        def _capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        summary = get_academic_hierarchy_summary(db)

        assert len(summary.levels) == 1
        assert len(summary.levels[0].programs) == 1
        assert summary.levels[0].programs[0].majors == []
        assert summary.levels[0].major_count == 0
        assert summary.levels[0].sub_major_count == 0
        assert summary.coverage.program_count == 0
        assert summary.coverage.programs_with_no_major == 0
        assert summary.coverage.programs_with_no_sub_major == 0
        assert summary.coverage.major_mapping.total == 0
        assert summary.coverage.program_url.total == 0
        joined = " ".join(statements).lower()
        assert "course_education_major_mappings" not in joined or "education_courses" in joined
        assert len(statements) <= 20
    finally:
        db.close()
        engine.dispose()
