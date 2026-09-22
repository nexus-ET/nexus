"""Light tests for education super-majors service helpers."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services.education_super_majors import (
    _slugify_code,
    delete_education_super_major,
    ensure_super_major_deletable,
    format_super_major_delete_block_detail,
)


def test_slugify_super_major_code():
    assert (
        _slugify_code("Computer Science & Information Technology")
        == "COMPUTER_SCIENCE_INFORMATION_TECHNOLOGY"
    )
    assert _slugify_code("Mathematics") == "MATHEMATICS"
    assert _slugify_code("  Arts, Humanities & Social Sciences ") == (
        "ARTS_HUMANITIES_SOCIAL_SCIENCES"
    )


def test_format_super_major_delete_block_detail_allows_empty():
    assert (
        format_super_major_delete_block_detail(
            {
                "majors": 0,
                "sub_majors": 0,
                "program_mappings": 0,
                "programs": 0,
                "target_courses": 0,
            }
        )
        is None
    )


def test_format_super_major_delete_block_detail_lists_counts():
    detail = format_super_major_delete_block_detail(
        {
            "majors": 2,
            "sub_majors": 5,
            "program_mappings": 10,
            "programs": 8,
            "target_courses": 3,
        }
    )
    assert detail is not None
    assert "Cannot delete this super-major" in detail
    assert "2 majors" in detail
    assert "5 sub-majors" in detail
    assert "8 programs (10 mappings)" in detail
    assert "3 target courses" in detail
    assert "Remap or remove" in detail


def test_format_super_major_delete_block_detail_singular_and_no_targets():
    detail = format_super_major_delete_block_detail(
        {
            "majors": 1,
            "sub_majors": 1,
            "program_mappings": 1,
            "programs": 1,
            "target_courses": 0,
        }
    )
    assert detail is not None
    assert "1 major," in detail
    assert "1 sub-major," in detail
    assert "1 program (1 mapping)" in detail
    assert "target course" not in detail


def test_ensure_super_major_deletable_blocks_when_dependents_exist(monkeypatch):
    monkeypatch.setattr(
        "app.services.education_super_majors.count_super_major_dependents",
        lambda db, super_major_id: {
            "majors": 4,
            "sub_majors": 9,
            "program_mappings": 20,
            "programs": 15,
            "target_courses": 0,
        },
    )
    with pytest.raises(HTTPException) as exc:
        ensure_super_major_deletable(MagicMock(), 42)
    assert exc.value.status_code == 409
    assert "4 majors" in exc.value.detail


def test_delete_education_super_major_blocked_before_delete(monkeypatch):
    record = SimpleNamespace(id=7, name="Allied Health")
    monkeypatch.setattr(
        "app.services.education_super_majors.get_education_super_major",
        lambda db, super_major_id: record,
    )
    monkeypatch.setattr(
        "app.services.education_super_majors.count_super_major_dependents",
        lambda db, super_major_id: {
            "majors": 1,
            "sub_majors": 0,
            "program_mappings": 0,
            "programs": 0,
            "target_courses": 0,
        },
    )
    db = MagicMock()
    with pytest.raises(HTTPException) as exc:
        delete_education_super_major(db, 7)
    assert exc.value.status_code == 409
    db.delete.assert_not_called()
    db.commit.assert_not_called()


def test_delete_education_super_major_allows_when_empty(monkeypatch):
    record = SimpleNamespace(id=9, name="Empty Super")
    monkeypatch.setattr(
        "app.services.education_super_majors.get_education_super_major",
        lambda db, super_major_id: record,
    )
    monkeypatch.setattr(
        "app.services.education_super_majors.count_super_major_dependents",
        lambda db, super_major_id: {
            "majors": 0,
            "sub_majors": 0,
            "program_mappings": 0,
            "programs": 0,
            "target_courses": 0,
        },
    )
    db = MagicMock()
    delete_education_super_major(db, 9)
    db.delete.assert_called_once_with(record)
    db.commit.assert_called_once()
