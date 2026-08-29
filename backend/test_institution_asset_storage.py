from types import SimpleNamespace
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.services.institution_asset_storage import (
    ALLOWED_ASSET_TYPES,
    INSTITUTION_PICTURES_ROOT,
    build_r2_object_key,
    institution_asset_prefix,
    institution_nick_folder,
    normalize_asset_type,
    sanitize_asset_filename,
)


def test_normalize_asset_type_accepts_banner_and_legacy_campus():
    assert normalize_asset_type("banner") == "banner"
    assert normalize_asset_type("campus") == "banner"
    assert normalize_asset_type("logo") == "logo"


def test_normalize_asset_type_rejects_unknown_values():
    with pytest.raises(HTTPException) as exc:
        normalize_asset_type("hero")
    assert "Invalid asset type" in exc.value.detail


def test_r2_account_id_rejects_api_tokens(monkeypatch):
    from app.services import institution_asset_storage as storage

    monkeypatch.setattr(storage.settings, "R2_ACCOUNT_ID", "cfat_not_an_account_id")
    with pytest.raises(HTTPException) as exc:
        storage._validate_r2_settings()
    assert "Account ID" in exc.value.detail


def test_institution_asset_prefix_uses_pictures_root_and_id_nick():
    institution = SimpleNamespace(id=7, code="jhu", name="Johns Hopkins University")
    assert institution_nick_folder(institution) == "INS-7-JHU"
    assert institution_asset_prefix(institution) == f"{INSTITUTION_PICTURES_ROOT}/INS-7-JHU"

    institution = SimpleNamespace(id=6, code="UCLA", name="University of California Los Angeles")
    assert institution_nick_folder(institution) == "INS-6-UCLA"
    assert institution_asset_prefix(institution) == f"{INSTITUTION_PICTURES_ROOT}/INS-6-UCLA"

    institution = SimpleNamespace(id=58, code=None, name="Johns Hopkins University")
    assert institution_nick_folder(institution) == "INS-58-JOHNSHOPKINSUNIVERSITY"
    assert institution_asset_prefix(institution) == (
        f"{INSTITUTION_PICTURES_ROOT}/INS-58-JOHNSHOPKINSUNIVERSITY"
    )


def test_sanitize_asset_filename_lowercases_and_hyphenates():
    assert sanitize_asset_filename("Consultancy Team Meeting 1800x600.webp") == (
        "consultancy-team-meeting-1800x600.webp"
    )
    assert sanitize_asset_filename("IMG_5921.JPG") == "img-5921.jpg"


def test_build_r2_object_key_uses_prefix_type_and_sanitized_filename():
    key = build_r2_object_key(f"{INSTITUTION_PICTURES_ROOT}/INS-7-JHU", "banner", "Hero Main.webp")
    assert key == f"{INSTITUTION_PICTURES_ROOT}/INS-7-JHU/banner/hero-main.webp"


def test_public_url_uses_media_proxy_for_private_s3_host(monkeypatch):
    from app.services import institution_asset_storage as storage

    monkeypatch.setattr(
        storage.settings,
        "R2_PUBLIC_BASE_URL",
        "https://4b5bef12f702ca8e5cf57fe5ecd90da1.r2.cloudflarestorage.com",
    )
    monkeypatch.setattr(storage.settings, "API_V1_STR", "/api/v1")
    key = f"{INSTITUTION_PICTURES_ROOT}/INS-7-JHU/logo/primary-logo.svg"
    assert storage.public_url_for_key(key) == f"/api/v1/academia/media/{key}"


def test_rewrite_media_url_from_private_s3_host(monkeypatch):
    from app.services import institution_asset_storage as storage

    monkeypatch.setattr(storage.settings, "API_V1_STR", "/api/v1")
    monkeypatch.setattr(
        storage.settings,
        "R2_PUBLIC_BASE_URL",
        "https://4b5bef12f702ca8e5cf57fe5ecd90da1.r2.cloudflarestorage.com",
    )
    key = f"{INSTITUTION_PICTURES_ROOT}/INS-7-JHU/logo/primary-logo.svg"
    rewritten = storage.rewrite_media_url(
        f"https://4b5bef12f702ca8e5cf57fe5ecd90da1.r2.cloudflarestorage.com/{key}"
    )
    assert rewritten == f"/api/v1/academia/media/{key}"


def test_normalize_upload_content_type_accepts_jpg_aliases():
    from app.services.institution_asset_storage import normalize_upload_content_type

    assert normalize_upload_content_type("image/jpg", "photo.jpg") == "image/jpeg"
    assert normalize_upload_content_type("", "photo.jpeg") == "image/jpeg"
    assert normalize_upload_content_type("application/octet-stream", "campus.webp") == (
        "image/webp"
    )


def test_delete_institution_asset_rejects_foreign_prefix():
    from app.services import institution_asset_storage as storage

    institution = SimpleNamespace(id=1, code="jhu", name="Johns Hopkins University")
    with pytest.raises(HTTPException) as exc:
        storage.delete_institution_asset(
            institution=institution,
            object_key=f"{INSTITUTION_PICTURES_ROOT}/INS-2-UCLA/logo/logo.png",
        )
    assert "does not belong" in exc.value.detail


def test_delete_all_institution_assets_removes_local_files(monkeypatch):
    from app.services import institution_asset_storage as storage

    monkeypatch.setattr(storage.settings, "R2_ACCOUNT_ID", "")
    monkeypatch.setattr(storage.settings, "R2_ACCESS_KEY_ID", "")
    monkeypatch.setattr(storage.settings, "R2_SECRET_ACCESS_KEY", "")
    monkeypatch.setattr(storage.settings, "R2_BUCKET_NAME", "")

    uploads_root = Path(storage.__file__).resolve().parents[2] / "uploads"
    institution = SimpleNamespace(id=99, code="jhu-test-delete", name="Test")
    prefix = storage.institution_asset_prefix(institution)
    institution_dir = uploads_root.joinpath(*prefix.split("/"))
    logo_dir = institution_dir / "logo"
    logo_dir.mkdir(parents=True, exist_ok=True)
    target = logo_dir / "primary-logo.png"
    target.write_bytes(b"png-bytes")

    # Also plant a legacy local prefix so cleanup covers both layouts.
    legacy_dir = uploads_root / "jhu-test-delete" / "logo"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    legacy_target = legacy_dir / "old-logo.png"
    legacy_target.write_bytes(b"png-bytes")

    result = storage.delete_all_institution_assets(institution)
    assert result["ok"] is True
    assert result["deleted"] >= 2
    assert not target.exists()
    assert not legacy_target.exists()
