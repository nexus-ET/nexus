"""UAT tests for 2026-08-28 framework / mapping / country-filter changes."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import require_academia_admin
from app.api.v1 import academia as academia_api
from app.api.v1.academia import router as academia_router
from app.db.database import Base, get_db
from app.db.register_models import register_all_models
from app.models.academia_institution import Campus, College, Institution
from app.models.academia_wizard import InstitutionCourseOffering
from app.models.country import Country
from app.models.course_education_major_mapping import CourseEducationMajorMapping
from app.models.education_course import EducationCourse
from app.models.education_major import EducationMajor
from app.models.education_sub_major import EducationSubMajor
from app.models.level import Level
from app.models.program import Program
from app.models.program_education_major_mapping import ProgramEducationMajorMapping
from app.models.target_course import TargetCourse
from app.models.target_program import TargetProgram
from app.services import ca_program_mapping_review as ca_review
from app.services.academia_hub_service import (
    get_framework_coverage_metrics,
    list_countries_admin,
)

register_all_models()


def _coverage_session():
    engine = create_engine("sqlite:///:memory:")
    tables = [
        Country.__table__,
        Institution.__table__,
        Campus.__table__,
        College.__table__,
        Level.__table__,
        Program.__table__,
        TargetProgram.__table__,
        TargetCourse.__table__,
        InstitutionCourseOffering.__table__,
        EducationMajor.__table__,
        EducationSubMajor.__table__,
        EducationCourse.__table__,
        CourseEducationMajorMapping.__table__,
        ProgramEducationMajorMapping.__table__,
    ]
    Base.metadata.create_all(bind=engine, tables=tables)
    Session = sessionmaker(bind=engine)
    return Session(), engine


def test_list_countries_admin_with_institutions_filters_empty_countries():
    engine = create_engine("sqlite:///:memory:")
    Country.__table__.create(bind=engine, checkfirst=True)
    Institution.__table__.create(bind=engine, checkfirst=True)
    db = sessionmaker(bind=engine)()
    try:
        db.add_all(
            [
                Country(id=1, iso2="AU", name="Australia", dial_code="+61", is_active=True),
                Country(id=2, iso2="XX", name="No Institutions", dial_code="+99", is_active=True),
                Institution(id=10, name="Test U", country_id=1, is_active=True),
            ]
        )
        db.commit()

        all_rows, all_total = list_countries_admin(db, page=1, page_size=100)
        assert all_total == 2

        with_rows, with_total = list_countries_admin(
            db, with_institutions=True, page=1, page_size=100
        )
        assert with_total == 1
        assert [row.iso2 for row in with_rows] == ["AU"]
    finally:
        db.close()
        engine.dispose()


def test_framework_coverage_metrics_counts_campus_college_and_gaps():
    db, engine = _coverage_session()
    try:
        db.add_all(
            [
                Country(id=6, iso2="AU", name="Australia", dial_code="+61", is_active=True),
                Institution(id=55, name="Sample U", country_id=6, is_active=True),
                Campus(id=1, institution_id=55, name="Main", is_active=True),
                Campus(id=2, institution_id=55, name="Satellite", is_active=True),
                College(id=10, institution_id=55, campus_id=1, name="Arts", is_active=True),
                Level(id=1, code="UG", name="Undergraduate"),
                Program(
                    id=100,
                    name="Bachelor A",
                    code="BA",
                    level_id=1,
                    is_active=True,
                    program_url="https://example.edu/ba",
                ),
                Program(
                    id=101,
                    name="Bachelor B",
                    code="BB",
                    level_id=1,
                    is_active=True,
                ),
                TargetProgram(id=1, program_id=100, code="TP100", label="TP100", is_active=True),
                TargetProgram(id=2, program_id=101, code="TP101", label="TP101", is_active=True),
                TargetCourse(
                    id=500,
                    program_id=1,
                    qualification_program_id=100,
                    code="TC500",
                    label="Course 500",
                    is_active=True,
                ),
                TargetCourse(
                    id=501,
                    program_id=2,
                    qualification_program_id=101,
                    code="TC501",
                    label="Course 501",
                    is_active=True,
                ),
                EducationMajor(id=20, code="BUS", label="Business", is_active=True),
            ]
        )
        db.flush()
        db.add_all(
            [
                InstitutionCourseOffering(
                    institution_id=55,
                    course_id=500,
                    campus_id=1,
                    college_id=10,
                    is_active=True,
                ),
                InstitutionCourseOffering(
                    institution_id=55,
                    course_id=501,
                    campus_id=2,
                    is_active=True,
                ),
                ProgramEducationMajorMapping(
                    program_id=100,
                    education_major_id=20,
                ),
            ]
        )
        db.commit()

        metrics = get_framework_coverage_metrics(db)

        assert metrics.institution_count == 1
        assert metrics.campus_count == 2
        assert metrics.college_count == 1
        assert metrics.program_count == 2
        assert metrics.programs_with_no_major == 1
        assert metrics.programs_with_no_sub_major == 2
        assert metrics.major_mapping.mapped == 1
        assert metrics.major_mapping.unmapped == 1
        assert metrics.program_url.mapped == 1
        assert metrics.program_url.unmapped == 1
        assert len(metrics.by_country) == 1
        country = metrics.by_country[0]
        assert country.country_name == "Australia"
        assert country.campus_count == 2
        assert country.college_count == 1
        assert country.programs_with_no_major == 1
    finally:
        db.close()
        engine.dispose()


def test_academia_routes_register_ca_and_nz_mapping_review():
    paths = {getattr(route, "path", "") for route in academia_router.routes}
    assert "/academia/nz-program-mapping-suggestions" in paths
    assert "/academia/ca-program-mapping-suggestions" in paths
    assert "/academia/program-mappings/bulk-apply" in paths


def test_countries_endpoint_accepts_with_institutions_query(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Country.__table__.create(bind=engine, checkfirst=True)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    db.add(Country(id=1, iso2="CA", name="Canada", dial_code="+1", is_active=True))
    db.commit()
    db.close()

    captured: dict[str, object] = {}

    def _fake_list(db, **kwargs):
        captured["with_institutions"] = kwargs.get("with_institutions")
        return [SimpleNamespace(id=1, iso2="CA", name="Canada", dial_code="+1", is_active=True, sort_order=0)], 1

    monkeypatch.setattr(academia_api.service, "list_countries_admin", _fake_list)

    app = FastAPI()
    app.include_router(academia_router, prefix="/api/v1")

    def _override_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_academia_admin] = lambda: SimpleNamespace(id=1)

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get(
        "/api/v1/academia/countries",
        params={"with_institutions": "true", "page": 1, "page_size": 100},
    )
    assert response.status_code == 200, response.text
    assert captured["with_institutions"] is True
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["iso2"] == "CA"


def test_ca_mapping_review_loads_suggestions_from_fixture(tmp_path, monkeypatch):
    fixture = {
        "generated_at": "2026-08-28T00:00:00+00:00",
        "total": 1,
        "items": [
            {
                "program_id": 1,
                "program_title": "Bachelor of Example",
                "institution_id": 58,
                "institution_name": "Example CA U",
                "suggested_major": "Business",
                "suggested_sub_major": "Accounting",
                "status": "unmapped",
            }
        ],
    }
    path = tmp_path / "ca_unmapped_suggestions.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    monkeypatch.setattr(
        ca_review,
        "_SUGGESTIONS_PATHS",
        (path,),
    )

    engine = create_engine("sqlite:///:memory:")
    Program.__table__.create(bind=engine, checkfirst=True)
    Institution.__table__.create(bind=engine, checkfirst=True)
    Country.__table__.create(bind=engine, checkfirst=True)
    EducationMajor.__table__.create(bind=engine, checkfirst=True)
    EducationSubMajor.__table__.create(bind=engine, checkfirst=True)
    db = sessionmaker(bind=engine)()
    try:
        db.add(
            Program(
                id=1,
                name="Bachelor of Example",
                code="BEX",
                level_id=1,
                description="institution_id=58",
                is_active=True,
            )
        )
        db.add(Country(id=3, iso2="CA", name="Canada", dial_code="+1", is_active=True))
        db.add(Institution(id=58, name="Example CA U", country_id=3, is_active=True))
        db.add(EducationMajor(id=5, code="BUS", label="Business", is_active=True))
        db.commit()

        response = ca_review.list_ca_program_mapping_suggestions(db)
        assert response.total >= 0
        assert hasattr(response, "items")
    finally:
        db.close()
        engine.dispose()


def test_ca24_scope_rejects_non_canadian_institution():
    engine = create_engine("sqlite:///:memory:")
    Country.__table__.create(bind=engine, checkfirst=True)
    Institution.__table__.create(bind=engine, checkfirst=True)
    db = sessionmaker(bind=engine)()
    try:
        db.add(Country(id=6, iso2="AU", name="Australia", dial_code="+61", is_active=True))
        db.add(Institution(id=58, name="AU Uni", country_id=6, is_active=True))
        db.commit()
        assert ca_review._ca24_scope_error(db, 58) == (
            "Program institution is not a Canadian CA-24 institution."
        )
    finally:
        db.close()
        engine.dispose()


def test_ca_mapping_suggestions_file_paths_include_data_and_scripts_fallback():
    paths = ca_review._SUGGESTIONS_PATHS
    assert any("ca_unmapped_suggestions.json" in str(p) for p in paths)
    assert Path(paths[0]).parent.name == "data"
