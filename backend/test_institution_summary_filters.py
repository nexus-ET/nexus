"""Institution summary list filters (program / major / sub-major / type)."""

import inspect
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import require_academia_admin
from app.api.v1 import academia as academia_api
from app.api.v1.academia import router as academia_router
from app.db.database import get_db
from app.db.register_models import register_all_models
from app.models.academia_geography import GeographyCity, GeographyState
from app.models.academia_institution import Institution, InstitutionType
from app.models.country import Country
from app.models.program_education_major_mapping import ProgramEducationMajorMapping
from app.services.academia_hub_service import (
    _live_offering_catalog_counts,
    _mapping_major_metrics_query,
    _offering_catalog_metrics_query,
    _offering_institution_filter_query,
    list_institutions_summary_admin,
)

register_all_models()

TECHNICAL_INSTITUTE_ID = 4


def test_institution_types_route_is_registered():
    paths = {getattr(route, "path", "") for route in academia_router.routes}
    assert "/academia/institution-types" in paths


def test_summary_does_not_select_dropped_institution_type_column():
    assert "institution_type" not in Institution.__table__.c
    assert "institution_type_id" in Institution.__table__.c
    params = inspect.signature(list_institutions_summary_admin).parameters
    assert "institution_type_ids" in params
    assert "institution_type" not in params


def test_summary_admin_accepts_sub_major_ids():
    params = inspect.signature(list_institutions_summary_admin).parameters
    assert "sub_major_ids" in params


def test_program_mapping_has_education_sub_major_id():
    assert "education_sub_major_id" in ProgramEducationMajorMapping.__table__.c
    column = ProgramEducationMajorMapping.__table__.c.education_sub_major_id
    assert column.nullable is True


def test_offering_filter_query_joins_sub_major_mapping():
    engine = create_engine("sqlite://")
    db = sessionmaker(bind=engine)()
    query = _offering_institution_filter_query(db, sub_major_ids=[12])
    sql = str(query.statement.compile(compile_kwargs={"literal_binds": True})).lower()
    assert "program_education_major_mappings" in sql
    assert "education_sub_major_id" in sql
    assert "12" in sql


def test_mapping_metrics_query_counts_distinct_sub_majors():
    engine = create_engine("sqlite://")
    db = sessionmaker(bind=engine)()
    query = _mapping_major_metrics_query(db, [6])
    sql = str(query.statement.compile(compile_kwargs={"literal_binds": True})).lower()
    assert "education_sub_major_id" in sql
    assert "count(distinct" in sql.replace(" ", "")


def test_offering_catalog_metrics_query_includes_sub_major_count():
    engine = create_engine("sqlite://")
    db = sessionmaker(bind=engine)()
    query = _offering_catalog_metrics_query(db, [55, 56, 155])
    sql = str(query.statement.compile(compile_kwargs={"literal_binds": True})).lower()
    assert "education_sub_major_id" in sql
    assert "sub_major_metrics" in sql
    assert "qualification_program_id" in sql


def test_live_offering_sub_major_counts_match_offerings_sql():
    """QUT / WSU / Griffith must not report 0 when offerings have mapped sub-majors."""
    from sqlalchemy import text

    from app.db.database import SessionLocal

    db = SessionLocal()
    try:
        catalog = _live_offering_catalog_counts(db, [55, 56, 155])
        rows = db.execute(
            text(
                """
                SELECT ico.institution_id AS institution_id,
                       COUNT(DISTINCT pem.education_sub_major_id) AS sub_major_count
                FROM institution_course_offerings ico
                JOIN target_courses tc ON tc.id = ico.course_id
                JOIN program_education_major_mappings pem
                  ON pem.program_id = tc.qualification_program_id
                WHERE ico.institution_id IN (55, 56, 155)
                  AND ico.is_active IS TRUE
                  AND pem.education_sub_major_id IS NOT NULL
                GROUP BY ico.institution_id
                """
            )
        ).mappings()
        expected = {int(row["institution_id"]): int(row["sub_major_count"]) for row in rows}
        for institution_id, sub_major_count in expected.items():
            assert sub_major_count > 0
            assert catalog[institution_id]["sub_major_count"] == sub_major_count
    finally:
        db.close()


def test_offering_filter_query_major_only_skips_sub_major_join():
    engine = create_engine("sqlite://")
    db = sessionmaker(bind=engine)()
    query = _offering_institution_filter_query(db, major_ids=[3])
    sql = str(query.statement.compile(compile_kwargs={"literal_binds": True})).lower()
    assert "education_major_id" in sql
    assert "education_sub_major_id" not in sql


def _seed_type_filter_db(engine) -> None:
    Country.__table__.create(bind=engine, checkfirst=True)
    GeographyState.__table__.create(bind=engine, checkfirst=True)
    GeographyCity.__table__.create(bind=engine, checkfirst=True)
    InstitutionType.__table__.create(bind=engine, checkfirst=True)
    Institution.__table__.create(bind=engine, checkfirst=True)
    db = sessionmaker(bind=engine)()
    try:
        db.add_all(
            [
                InstitutionType(
                    id=1,
                    code="PUBLIC_STATE",
                    name="Public / State",
                    is_active=True,
                    sort_order=1,
                ),
                InstitutionType(
                    id=TECHNICAL_INSTITUTE_ID,
                    code="TECHNICAL_INSTITUTE",
                    name="Technical Institute",
                    is_active=True,
                    sort_order=4,
                ),
                Institution(
                    id=10,
                    name="State U",
                    institution_type_id=1,
                    is_active=True,
                ),
                Institution(
                    id=20,
                    name="Tech Institute Alpha",
                    institution_type_id=TECHNICAL_INSTITUTE_ID,
                    is_active=True,
                ),
            ]
        )
        db.commit()
    finally:
        db.close()


def test_summary_admin_filters_by_technical_institute_type_id():
    engine = create_engine("sqlite://")
    _seed_type_filter_db(engine)
    db = sessionmaker(bind=engine)()
    try:
        rows, total = list_institutions_summary_admin(
            db,
            institution_type_ids=[TECHNICAL_INSTITUTE_ID],
            page=1,
            page_size=25,
            sort_by="created_at",
            sort_order="desc",
        )
        assert total == 1
        assert [row.id for row in rows] == [20]
        assert rows[0].institution_type_id == TECHNICAL_INSTITUTE_ID

        empty_rows, empty_total = list_institutions_summary_admin(
            db,
            institution_type_ids=[3],
            page=1,
            page_size=25,
        )
        assert empty_total == 0
        assert empty_rows == []

        public_rows, public_total = list_institutions_summary_admin(
            db,
            institution_type_ids=[1],
            page=1,
            page_size=25,
        )
        assert public_total == 1
        assert [row.id for row in public_rows] == [10]
    finally:
        db.close()


def test_summary_endpoint_accepts_institution_type_id_list_without_500(monkeypatch):
    """Regression: Query(ge=1) on list[int] applied ge to the list → TypeError 500."""
    engine = create_engine("sqlite://")
    _seed_type_filter_db(engine)
    SessionLocal = sessionmaker(bind=engine)

    tech = Institution(
        id=20,
        name="Tech Institute Alpha",
        institution_type_id=TECHNICAL_INSTITUTE_ID,
        is_active=True,
        sort_order=0,
        publish_status="pending",
    )
    # Detached stub row for response serialization (avoid metrics table fan-out).
    tech.country = None
    tech.state = None
    tech.city = None
    tech.institution_type_ref = InstitutionType(
        id=TECHNICAL_INSTITUTE_ID,
        code="TECHNICAL_INSTITUTE",
        name="Technical Institute",
        is_active=True,
        sort_order=4,
    )

    captured: dict[str, object] = {}

    def _fake_list(db, **kwargs):
        captured["institution_type_ids"] = kwargs.get("institution_type_ids")
        type_ids = kwargs.get("institution_type_ids") or []
        if TECHNICAL_INSTITUTE_ID in type_ids:
            return [tech], 1
        if type_ids:
            return [], 0
        return [tech], 1

    monkeypatch.setattr(
        academia_api.service,
        "list_institutions_summary_admin",
        _fake_list,
    )
    monkeypatch.setattr(
        academia_api.service,
        "get_institution_status_counts",
        lambda db: (1, 0),
    )
    monkeypatch.setattr(
        academia_api.service,
        "institution_summary_metrics",
        lambda db, ids: {
            institution_id: {
                "campus_count": 0,
                "college_count": 0,
                "level_count": 0,
                "program_count": 0,
                "major_count": 0,
                "sub_major_count": 0,
                "course_count": 0,
                "intake_count": 0,
                "picture_count": 0,
            }
            for institution_id in ids
        },
    )

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
        "/api/v1/academia/institutions/summary",
        params={
            "institution_type_id": TECHNICAL_INSTITUTE_ID,
            "page": 1,
            "page_size": 25,
            "sort_by": "created_at",
            "sort_order": "desc",
        },
    )
    assert response.status_code == 200, response.text
    assert captured["institution_type_ids"] == [TECHNICAL_INSTITUTE_ID]
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == 20
    assert payload["items"][0]["institution_type_id"] == TECHNICAL_INSTITUTE_ID

    empty = client.get(
        "/api/v1/academia/institutions/summary",
        params={"institution_type_id": 3, "page": 1, "page_size": 25},
    )
    assert empty.status_code == 200, empty.text
    assert empty.json()["total"] == 0
    assert empty.json()["items"] == []

    public = client.get(
        "/api/v1/academia/institutions/summary",
        params={"institution_type_id": 1, "page": 1, "page_size": 25},
    )
    assert public.status_code == 200, public.text
    assert public.json()["total"] == 0