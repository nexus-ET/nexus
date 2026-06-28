"""Tests for admin user deletion."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.users import delete_admin_user


def test_delete_admin_user_blocks_self_delete():
    current_user = SimpleNamespace(id=5)

    with pytest.raises(HTTPException) as exc:
        delete_admin_user(5, db=object(), current_user=current_user)  # type: ignore[arg-type]
    assert exc.value.status_code == 400
    assert "your own account" in exc.value.detail


def test_delete_admin_user_blocks_last_super_admin(monkeypatch):
    current_user = SimpleNamespace(id=1)
    target_user = SimpleNamespace(id=2, is_superuser=True)

    monkeypatch.setattr(
        "app.api.v1.users._get_admin_user_or_404",
        lambda user_id, db: target_user,
    )
    monkeypatch.setattr(
        "app.api.v1.users._remaining_super_admin_count",
        lambda db, exclude_user_id: 0,
    )

    with pytest.raises(HTTPException) as exc:
        delete_admin_user(2, db=object(), current_user=current_user)  # type: ignore[arg-type]
    assert exc.value.status_code == 400
    assert "last Super Admin" in exc.value.detail
