"""Institution type lookup catalog sync."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import INSTITUTION_TYPE_CATALOG, _ensure_institution_types_catalog
from app.db.register_models import register_all_models
from app.models.academia_institution import Institution, InstitutionType
from app.services.academia_hub_service import list_institution_types_admin

register_all_models()

EXPECTED_CODES = (
    "PUBLIC_STATE",
    "PRIVATE",
    "COMMUNITY_COLLEGE",
    "TECHNICAL_INSTITUTE",
    "OTHERS",
)


def _seed_legacy_split_catalog(engine) -> None:
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
                    id=2,
                    code="PRIVATE",
                    name="Private",
                    is_active=True,
                    sort_order=2,
                ),
                InstitutionType(
                    id=3,
                    code="COMMUNITY_COLLEGE",
                    name="Community College",
                    is_active=True,
                    sort_order=3,
                ),
                InstitutionType(
                    id=4,
                    code="TECHNICAL_INSTITUTE",
                    name=" Technical Institute",
                    is_active=True,
                    sort_order=4,
                ),
                InstitutionType(
                    id=5,
                    code="OTHERS",
                    name="Others",
                    is_active=True,
                    sort_order=4,
                ),
            ]
        )
        db.add(
            Institution(
                id=1,
                name="Legacy Tech School",
                institution_type_id=4,
            )
        )
        db.commit()
    finally:
        db.close()


def test_institution_types_catalog_keeps_technical_institute_visible():
    engine = create_engine("sqlite://")
    _seed_legacy_split_catalog(engine)

    _ensure_institution_types_catalog(engine)

    db = sessionmaker(bind=engine)()
    try:
        active = list_institution_types_admin(db)
        active_by_code = {row.code: row for row in active}

        assert [row.code for row in active] == list(EXPECTED_CODES)
        assert len(active) == len(INSTITUTION_TYPE_CATALOG)
        assert active_by_code["COMMUNITY_COLLEGE"].name == "Community College"
        assert active_by_code["TECHNICAL_INSTITUTE"].is_active is True
        assert active_by_code["TECHNICAL_INSTITUTE"].name == "Technical Institute"
        assert active_by_code["TECHNICAL_INSTITUTE"].sort_order == 4
        assert active_by_code["OTHERS"].sort_order == 5

        kept = db.query(Institution).filter(Institution.id == 1).one()
        assert kept.institution_type_id == active_by_code["TECHNICAL_INSTITUTE"].id
    finally:
        db.close()


def test_institution_types_catalog_reactivates_inactive_catalog_rows():
    engine = create_engine("sqlite://")
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
                    id=2,
                    code="PRIVATE",
                    name="Private",
                    is_active=True,
                    sort_order=2,
                ),
                InstitutionType(
                    id=3,
                    code="COMMUNITY_COLLEGE",
                    name="Community College",
                    is_active=True,
                    sort_order=3,
                ),
                InstitutionType(
                    id=4,
                    code="TECHNICAL_INSTITUTE",
                    name="Technical Institute",
                    is_active=False,
                    sort_order=4,
                ),
                InstitutionType(
                    id=5,
                    code="OTHERS",
                    name="Others",
                    is_active=False,
                    sort_order=4,
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    _ensure_institution_types_catalog(engine)

    db = sessionmaker(bind=engine)()
    try:
        active = list_institution_types_admin(db)
        active_by_code = {row.code: row for row in active}

        assert len(active) == len(INSTITUTION_TYPE_CATALOG)
        assert set(active_by_code) == set(EXPECTED_CODES)
        assert active_by_code["OTHERS"].is_active is True
        assert active_by_code["OTHERS"].name == "Others"
        assert active_by_code["TECHNICAL_INSTITUTE"].is_active is True
    finally:
        db.close()


def test_institution_types_catalog_preserves_existing_names():
    engine = create_engine("sqlite://")
    InstitutionType.__table__.create(bind=engine, checkfirst=True)
    Institution.__table__.create(bind=engine, checkfirst=True)

    db = sessionmaker(bind=engine)()
    try:
        db.add(
            InstitutionType(
                id=1,
                code="COMMUNITY_COLLEGE",
                name="Community College",
                is_active=True,
                sort_order=99,
            )
        )
        db.commit()
    finally:
        db.close()

    _ensure_institution_types_catalog(engine)

    db = sessionmaker(bind=engine)()
    try:
        row = (
            db.query(InstitutionType)
            .filter(InstitutionType.code == "COMMUNITY_COLLEGE")
            .one()
        )
        assert row.name == "Community College"
        assert row.sort_order == 3
        assert row.is_active is True
    finally:
        db.close()


def test_institution_types_catalog_preserves_custom_display_name():
    engine = create_engine("sqlite://")
    InstitutionType.__table__.create(bind=engine, checkfirst=True)
    Institution.__table__.create(bind=engine, checkfirst=True)

    db = sessionmaker(bind=engine)()
    try:
        db.add(
            InstitutionType(
                id=1,
                code="COMMUNITY_COLLEGE",
                name="Community Colleges",
                is_active=True,
                sort_order=3,
            )
        )
        db.commit()
    finally:
        db.close()

    _ensure_institution_types_catalog(engine)

    db = sessionmaker(bind=engine)()
    try:
        row = (
            db.query(InstitutionType)
            .filter(InstitutionType.code == "COMMUNITY_COLLEGE")
            .one()
        )
        assert row.name == "Community Colleges"
        assert row.is_active is True
    finally:
        db.close()
