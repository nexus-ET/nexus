#!/usr/bin/env python3
"""Reset a lead to a clean 'Lead: New' baseline for status guardrail testing.

Clears bookings, communications, intake progress, and profile fields used during
WhatsApp intake (current location, English, GRE, and GMAT scores).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(BACKEND_ROOT / ".env")

STATUS_LEAD_NEW = 1


def _pg_conninfo(url: str) -> str:
    raw = (url or "").strip().strip('"').strip("'")
    for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://", "postgres://"):
        if raw.startswith(prefix):
            raw = "postgresql://" + raw[len(prefix) :]
            break
    return raw.replace("postgresql://", "postgres://")


def _normalize_phone(phone: str | None) -> tuple[str, str]:
    digits = re.sub(r"\D", "", phone or "")
    normalized = f"+{digits}" if digits else (phone or "").strip()
    return normalized, digits


def reset_lead_for_guardrail_testing(*, lead_id: int, dry_run: bool) -> int:
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        raise SystemExit("DATABASE_URL is not set in .env")

    with psycopg.connect(_pg_conninfo(database_url)) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, full_name, phone_number, status_definition_id, stage::text, admission_stage,
                       current_location, english_test_scores, gre_score, gmat_score
                FROM leads WHERE id = %s
                """,
                (lead_id,),
            )
            lead = cur.fetchone()
            if not lead:
                print(f"Lead id={lead_id} not found.")
                return 1

            (
                _,
                name,
                phone,
                status_id,
                stage,
                admission_stage,
                current_location,
                english_test_scores,
                gre_score,
                gmat_score,
            ) = lead
            normalized, digits = _normalize_phone(phone)
            print(f"Lead {lead_id}: {name!r} phone={phone!r} status={status_id} stage={stage} admission={admission_stage}")
            print(f"  current_location: {current_location!r}")
            print(f"  english_test_scores: {english_test_scores!r}")
            print(f"  gre_score: {gre_score!r}")
            print(f"  gmat_score: {gmat_score!r}")

            cur.execute("SELECT id FROM counselling_bookings WHERE lead_id = %s", (lead_id,))
            booking_ids = [row[0] for row in cur.fetchall()]
            print(f"  bookings to delete: {len(booking_ids)} {booking_ids}")

            cur.execute("SELECT COUNT(*) FROM status_history WHERE student_id = %s", (lead_id,))
            print(f"  status_history rows: {cur.fetchone()[0]}")

            cur.execute("SELECT COUNT(*) FROM messages WHERE lead_id = %s", (lead_id,))
            print(f"  messages: {cur.fetchone()[0]}")

            cur.execute("SELECT COUNT(*) FROM message_history WHERE lead_id = %s", (lead_id,))
            print(f"  message_history (lead): {cur.fetchone()[0]}")

            cur.execute(
                """
                SELECT COUNT(*) FROM message_history
                WHERE sender_phone IN (%s, %s, %s)
                """,
                (normalized, digits, f"+{digits}"),
            )
            print(f"  message_history (phone): {cur.fetchone()[0]}")

            cur.execute("SELECT COUNT(*) FROM conversation_audit_logs WHERE lead_id = %s", (lead_id,))
            print(f"  conversation_audit_logs: {cur.fetchone()[0]}")

            cur.execute("SELECT COUNT(*) FROM consultation_slots WHERE lead_id = %s", (lead_id,))
            print(f"  consultation_slots linked: {cur.fetchone()[0]}")

            if dry_run:
                print("Dry run only — no changes made.")
                return 0

            if booking_ids:
                cur.execute(
                    "DELETE FROM counselling_notes WHERE booking_id = ANY(%s)",
                    (booking_ids,),
                )
                cur.execute(
                    """
                    DELETE FROM notification_logs
                    WHERE booking_id = ANY(%s)
                    """,
                    (booking_ids,),
                )
                cur.execute(
                    "DELETE FROM counselling_bookings WHERE id = ANY(%s)",
                    (booking_ids,),
                )

            cur.execute("DELETE FROM status_history WHERE student_id = %s", (lead_id,))
            cur.execute("DELETE FROM messages WHERE lead_id = %s", (lead_id,))
            cur.execute("DELETE FROM message_history WHERE lead_id = %s", (lead_id,))
            if normalized or digits:
                cur.execute(
                    """
                    DELETE FROM message_history
                    WHERE sender_phone IN (%s, %s, %s)
                    """,
                    (normalized, digits, f"+{digits}"),
                )
            cur.execute("DELETE FROM conversation_audit_logs WHERE lead_id = %s", (lead_id,))
            cur.execute(
                "UPDATE consultation_slots SET lead_id = NULL WHERE lead_id = %s",
                (lead_id,),
            )
            cur.execute("DELETE FROM system_logs WHERE student_id = %s", (lead_id,))

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            cur.execute(
                """
                UPDATE leads SET
                    status_definition_id = %s,
                    status_entered_at = %s,
                    admission_stage = NULL,
                    admission_stage_entered_at = NULL,
                    intake_step = NULL,
                    intake_context = NULL,
                    wants_consultation_call = NULL,
                    consultation_scheduled_at = NULL,
                    calendar_booking_id = NULL,
                    current_location = NULL,
                    english_test_scores = NULL,
                    gre_score = NULL,
                    gmat_score = NULL,
                    handoff_ai_confidence = NULL,
                    handoff_reason = NULL,
                    stage = 'AI_ACTIVE',
                    is_human_locked = FALSE,
                    updated_at = %s
                WHERE id = %s
                """,
                (STATUS_LEAD_NEW, now, now, lead_id),
            )
            cur.execute(
                """
                INSERT INTO status_history (
                    student_id, status_id, changed_by_user_id, changed_by_type, comments, booking_id, created_at
                ) VALUES (%s, %s, NULL, 'system', %s, NULL, %s)
                """,
                (
                    lead_id,
                    STATUS_LEAD_NEW,
                    "Reset for status guardrail testing.",
                    now,
                ),
            )

        conn.commit()

    print(
        f"Lead {lead_id} reset to Lead: New with communications, bookings, "
        "location, and test scores cleared."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset a lead for status guardrail testing.")
    parser.add_argument("--lead-id", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    if not args.dry_run and not args.yes:
        print("Refusing to modify the database without --yes.", file=sys.stderr)
        return 2

    return reset_lead_for_guardrail_testing(lead_id=args.lead_id, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
