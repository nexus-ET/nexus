"""Focused tests for document requirements CRUD and is_global country sync."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    func,
)
from sqlalchemy.orm import registry, relationship, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import require_academia_admin
from app.api.v1.document_requirements import router as document_requirements_router
from app.db.database import get_db
from app.schemas.document_requirement import (
    DocumentRequirementCreate,
    DocumentRequirementUpdate,
)
from app.services import document_requirement_service as service

metadata = MetaData()
mapper_registry = registry(metadata=metadata)

countries = Table(
    "countries",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("iso2", String(2), nullable=False),
    Column("name", String(100), nullable=False),
    Column("dial_code", String(6), nullable=False),
    Column("is_active", Boolean, default=True, nullable=False),
    Column("sort_order", Integer, default=0, nullable=False),
)

document_templates = Table(
    "document_templates",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("template_name", String(150), nullable=False),
    Column("file_url", Text, nullable=False),
    Column("file_size", Integer, nullable=True),
    Column("uploaded_by", Integer, nullable=True),
    Column("created_at", DateTime, server_default=func.now(), nullable=False),
)

document_requirements = Table(
    "document_requirements",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("is_global", Boolean, default=False, nullable=False),
    Column("document_name", String(150), nullable=False),
    Column("description", Text, nullable=True),
    Column("accepted_format", Text, nullable=True),
    Column("is_mandatory", Boolean, default=True, nullable=False),
    Column("template_id", Integer, ForeignKey("document_templates.id"), nullable=True),
    Column("created_at", DateTime, server_default=func.now(), nullable=False),
    Column("updated_at", DateTime, server_default=func.now(), nullable=False),
)

document_requirement_countries = Table(
    "document_requirement_countries",
    metadata,
    Column(
        "requirement_id",
        Integer,
        ForeignKey("document_requirements.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "country_id",
        Integer,
        ForeignKey("countries.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

document_requirement_levels = Table(
    "document_requirement_levels",
    metadata,
    Column(
        "requirement_id",
        Integer,
        ForeignKey("document_requirements.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("program_level", String(50), primary_key=True),
)


class Country:
    pass


class DocumentTemplate:
    pass


class DocumentRequirementLevel:
    pass


class DocumentRequirement:
    pass


mapper_registry.map_imperatively(Country, countries)
mapper_registry.map_imperatively(DocumentTemplate, document_templates)
mapper_registry.map_imperatively(DocumentRequirementLevel, document_requirement_levels)
mapper_registry.map_imperatively(
    DocumentRequirement,
    document_requirements,
    properties={
        "template": relationship(
            DocumentTemplate, foreign_keys=[document_requirements.c.template_id]
        ),
        "countries": relationship(Country, secondary=document_requirement_countries),
        "level_rows": relationship(
            DocumentRequirementLevel,
            cascade="all, delete-orphan",
        ),
    },
)


def _patch_service_models(monkeypatch):
    monkeypatch.setattr(service, "Country", Country)
    monkeypatch.setattr(service, "DocumentRequirement", DocumentRequirement)
    monkeypatch.setattr(service, "DocumentRequirementLevel", DocumentRequirementLevel)
    monkeypatch.setattr(service, "DocumentTemplate", DocumentTemplate)
    monkeypatch.setattr(service, "document_requirement_countries", document_requirement_countries)


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal(), engine


def _levels(row) -> list[str]:
    return sorted(level.program_level for level in (row.level_rows or []))


def test_create_global_requirement_clears_countries(monkeypatch):
    _patch_service_models(monkeypatch)
    db, engine = _session()
    try:
        db.add(Country(id=1, iso2="AU", name="Australia", dial_code="+61", is_active=True, sort_order=0))
        db.commit()

        row = service.create_document_requirement(
            db,
            DocumentRequirementCreate(
                document_name="Passport",
                description="Bio page",
                program_levels=["Undergraduate", "Graduate"],
                is_mandatory=True,
                is_global=True,
                country_ids=[1],
            ),
        )
        assert row.is_global is True
        assert row.countries == []
        assert row.document_name == "Passport"
        assert _levels(row) == ["Graduate", "Undergraduate"]
        payload = service.serialize_requirement(row)
        assert payload["program_levels"] == ["Undergraduate", "Graduate"]
    finally:
        db.close()
        engine.dispose()


def test_create_with_countries_and_toggle_global_clears_junction(monkeypatch):
    _patch_service_models(monkeypatch)
    db, engine = _session()
    try:
        db.add_all(
            [
                Country(id=1, iso2="AU", name="Australia", dial_code="+61", is_active=True, sort_order=0),
                Country(id=2, iso2="NZ", name="New Zealand", dial_code="+64", is_active=True, sort_order=0),
            ]
        )
        db.commit()

        row = service.create_document_requirement(
            db,
            DocumentRequirementCreate(
                document_name="Marksheets",
                description=None,
                program_levels=["Graduate"],
                is_mandatory=True,
                is_global=False,
                country_ids=[1, 2],
            ),
        )
        assert row.is_global is False
        assert sorted(c.id for c in row.countries) == [1, 2]
        assert _levels(row) == ["Graduate"]

        updated = service.update_document_requirement(
            db,
            row.id,
            DocumentRequirementUpdate(is_global=True),
        )
        assert updated.is_global is True
        assert updated.countries == []
        assert _levels(updated) == ["Graduate"]
    finally:
        db.close()
        engine.dispose()


def test_template_upload_rejects_without_auth():
    app = FastAPI()
    app.include_router(document_requirements_router, prefix="/api/v1")
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/api/v1/document-requirements/1/template",
        files={"file": ("sample.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert response.status_code in {401, 403}


def test_create_via_api_with_admin_override(monkeypatch):
    _patch_service_models(monkeypatch)
    db, engine = _session()
    try:
        db.add(Country(id=3, iso2="IN", name="India", dial_code="+91", is_active=True, sort_order=0))
        db.commit()

        app = FastAPI()
        app.include_router(document_requirements_router, prefix="/api/v1")

        def _override_db():
            try:
                yield db
            finally:
                pass

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[require_academia_admin] = lambda: SimpleNamespace(id=99)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/v1/document-requirements",
            json={
                "document_name": "SOP",
                "description": "Statement of purpose",
                "program_levels": ["Foundation", "Undergraduate"],
                "is_mandatory": False,
                "is_global": False,
                "country_ids": [3],
            },
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["document_name"] == "SOP"
        assert body["is_global"] is False
        assert body["program_levels"] == ["Foundation", "Undergraduate"]
        assert body["program_level"] == "Foundation"
        assert [c["id"] for c in body["countries"]] == [3]
    finally:
        db.close()
        engine.dispose()
