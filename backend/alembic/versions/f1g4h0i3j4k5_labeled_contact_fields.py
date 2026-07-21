"""Add college contact fields and normalize campus contact JSON structure.

Revision ID: f1g4h0i3j4k5
Revises: e9f2g8h0i1j2
Create Date: 2026-07-11 13:10:00.000000

"""
from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f1g4h0i3j4k5"
down_revision: Union[str, Sequence[str], None] = "e9f2g8h0i1j2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _normalize_contacts(raw: object, *, default_type: str, fallback_type: str) -> list[dict[str, str]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        return []

    normalized: list[dict[str, str]] = []
    for index, item in enumerate(raw):
        if isinstance(item, str):
            value = item.strip()
            if not value:
                continue
            contact_type = default_type if index == 0 else fallback_type
            normalized.append({"type": contact_type, "value": value})
            continue
        if isinstance(item, dict):
            value = str(item.get("value") or "").strip()
            if not value:
                continue
            contact_type = str(item.get("type") or "").strip() or (
                default_type if index == 0 else fallback_type
            )
            normalized.append({"type": contact_type, "value": value})
    return normalized


def upgrade() -> None:
    bind = op.get_bind()

    op.add_column("colleges", sa.Column("phone_numbers", sa.JSON(), nullable=True))
    op.add_column("colleges", sa.Column("email_addresses", sa.JSON(), nullable=True))

    campuses = bind.execute(sa.text("SELECT id, phone_numbers, email_addresses FROM campuses")).mappings().all()
    for row in campuses:
        phone_numbers = _normalize_contacts(
            json.loads(row["phone_numbers"]) if isinstance(row["phone_numbers"], str) else row["phone_numbers"],
            default_type="Main",
            fallback_type="Other",
        )
        email_addresses = _normalize_contacts(
            json.loads(row["email_addresses"]) if isinstance(row["email_addresses"], str) else row["email_addresses"],
            default_type="General",
            fallback_type="Other",
        )
        bind.execute(
            sa.text(
                "UPDATE campuses SET phone_numbers = :phone_numbers, email_addresses = :email_addresses WHERE id = :id"
            ),
            {
                "id": row["id"],
                "phone_numbers": json.dumps(phone_numbers),
                "email_addresses": json.dumps(email_addresses),
            },
        )

    bind.execute(
        sa.text(
            """
            UPDATE colleges
            SET phone_numbers = '[]'::json,
                email_addresses = '[]'::json
            WHERE phone_numbers IS NULL OR email_addresses IS NULL
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()

    campuses = bind.execute(sa.text("SELECT id, phone_numbers, email_addresses FROM campuses")).mappings().all()
    for row in campuses:
        raw_phones = (
            json.loads(row["phone_numbers"]) if isinstance(row["phone_numbers"], str) else row["phone_numbers"]
        ) or []
        raw_emails = (
            json.loads(row["email_addresses"]) if isinstance(row["email_addresses"], str) else row["email_addresses"]
        ) or []
        phone_numbers = [
            str(item.get("value") if isinstance(item, dict) else item).strip()
            for item in raw_phones
            if str(item.get("value") if isinstance(item, dict) else item).strip()
        ]
        email_addresses = [
            str(item.get("value") if isinstance(item, dict) else item).strip()
            for item in raw_emails
            if str(item.get("value") if isinstance(item, dict) else item).strip()
        ]
        bind.execute(
            sa.text(
                "UPDATE campuses SET phone_numbers = :phone_numbers, email_addresses = :email_addresses WHERE id = :id"
            ),
            {
                "id": row["id"],
                "phone_numbers": json.dumps(phone_numbers),
                "email_addresses": json.dumps(email_addresses),
            },
        )

    op.drop_column("colleges", "email_addresses")
    op.drop_column("colleges", "phone_numbers")
