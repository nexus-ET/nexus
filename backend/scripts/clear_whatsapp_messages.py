"""
Clear WhatsApp message history for a lead and reset intake for a fresh AI session.

Removes all messages, counselling bookings (My Bookings / session data), and pipeline
status rows except **Lead: New** (View Journey baseline).

Local:
  python scripts/clear_whatsapp_messages.py +918754545407 --dry-run
  python scripts/clear_whatsapp_messages.py +918754545407 --yes

Hostinger VPS:
  sudo bash /var/www/nexus/backend/deploy/clear-whatsapp-messages.sh +918754545407 --dry-run
  sudo bash /var/www/nexus/backend/deploy/clear-whatsapp-messages.sh +918754545407 --yes

Or directly:
  cd /var/www/nexus/backend && source .venv/bin/activate
  python scripts/clear_whatsapp_messages.py +918754545407 --yes
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(BACKEND_ROOT / ".env")


def _pg_conninfo(url: str) -> str:
    raw = (url or "").strip().strip('"').strip("'")
    for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://", "postgres://"):
        if raw.startswith(prefix):
            raw = "postgresql://" + raw[len(prefix) :]
            break
    return raw.replace("postgresql://", "postgres://")


def _normalize_phone(phone: str) -> tuple[str, str]:
    digits = re.sub(r"\D", "", phone)
    normalized = f"+{digits}" if digits else phone.strip()
    return normalized, digits


def _find_leads(cur, *, phone: str | None, lead_id: int | None) -> list[tuple]:
    if lead_id is not None:
        cur.execute(
            """
            SELECT id, full_name, phone_number, intake_step, stage::text
            FROM leads
            WHERE id = %s
            """,
            (lead_id,),
        )
        row = cur.fetchone()
        return [row] if row else []

    if not phone:
        return []

    normalized, digits = _normalize_phone(phone)
    suffix = digits[-10:] if len(digits) >= 10 else digits
    cur.execute(
        """
        SELECT id, full_name, phone_number, intake_step, stage::text
        FROM leads
        WHERE phone_number = %s OR phone_number = %s OR phone_number LIKE %s
        ORDER BY id DESC
        LIMIT 5
        """,
        (normalized, digits, f"%{suffix}%"),
    )
    return cur.fetchall()


def _status_history_layout(cur) -> tuple[str, str, str]:
    """Return (table_name, student_fk_column, status_fk_column)."""
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name IN ('status_history', 'lead_status_history')
        ORDER BY CASE table_name WHEN 'status_history' THEN 0 ELSE 1 END
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if not row:
        raise SystemExit("ERROR: status_history / lead_status_history table not found.")

    table = row[0]
    if table == "status_history":
        return table, "student_id", "status_id"
    return table, "lead_id", "status_definition_id"


def _lead_new_status_id(cur) -> int:
    cur.execute(
        """
        SELECT id FROM status_definitions
        WHERE trim(stage_name) = 'Lead: New'
        ORDER BY id ASC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if row:
        return int(row[0])
    cur.execute(
        """
        SELECT id FROM status_definitions
        WHERE stage_name ILIKE 'lead:%new%'
        ORDER BY id ASC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    return int(row[0]) if row else 1


def _count_status_history_rows(cur, table: str, student_col: str, lead_pk: int) -> int:
    cur.execute(
        f"SELECT COUNT(*) FROM {table} WHERE {student_col} = %s",
        (lead_pk,),
    )
    return int(cur.fetchone()[0])


def _count_non_lead_new_status_rows(
    cur,
    table: str,
    student_col: str,
    status_col: str,
    lead_pk: int,
    lead_new_status_id: int,
) -> int:
    cur.execute(
        f"""
        SELECT COUNT(*)
        FROM {table} sh
        WHERE sh.{student_col} = %s
          AND sh.{status_col} <> %s
        """,
        (lead_pk, lead_new_status_id),
    )
    return int(cur.fetchone()[0])


def _delete_non_lead_new_status_rows(
    cur,
    table: str,
    student_col: str,
    status_col: str,
    lead_pk: int,
    lead_new_status_id: int,
) -> int:
    cur.execute(
        f"""
        DELETE FROM {table}
        WHERE {student_col} = %s
          AND {status_col} <> %s
        """,
        (lead_pk, lead_new_status_id),
    )
    return cur.rowcount


def _ensure_lead_new_status_row(
    cur,
    table: str,
    student_col: str,
    status_col: str,
    lead_pk: int,
    lead_new_status_id: int,
) -> None:
    cur.execute(
        f"""
        SELECT 1 FROM {table}
        WHERE {student_col} = %s AND {status_col} = %s
        LIMIT 1
        """,
        (lead_pk, lead_new_status_id),
    )
    if cur.fetchone() is not None:
        return

    if table == "lead_status_history":
        cur.execute(
            f"""
            INSERT INTO {table} (
                {student_col},
                {status_col},
                notes,
                created_at
            )
            SELECT
                %s,
                %s,
                'Lead record created.',
                COALESCE(l.created_at, NOW())
            FROM leads l
            WHERE l.id = %s
            """,
            (lead_pk, lead_new_status_id, lead_pk),
        )
        return

    cur.execute(
        f"""
        INSERT INTO {table} (
            {student_col},
            {status_col},
            changed_by_type,
            comments,
            created_at
        )
        SELECT
            %s,
            %s,
            'system',
            'Lead record created.',
            COALESCE(l.created_at, NOW())
        FROM leads l
        WHERE l.id = %s
        """,
        (lead_pk, lead_new_status_id, lead_pk),
    )


def _booking_ids_for_lead(cur, lead_pk: int) -> list[int]:
    cur.execute(
        "SELECT id FROM counselling_bookings WHERE lead_id = %s ORDER BY id",
        (lead_pk,),
    )
    return [int(row[0]) for row in cur.fetchall()]


def _delete_counselling_bookings(cur, booking_ids: list[int]) -> int:
    if not booking_ids:
        return 0
    cur.execute(
        "DELETE FROM counselling_notes WHERE booking_id = ANY(%s)",
        (booking_ids,),
    )
    cur.execute(
        "DELETE FROM notification_logs WHERE booking_id = ANY(%s)",
        (booking_ids,),
    )
    cur.execute(
        "DELETE FROM counselling_bookings WHERE id = ANY(%s)",
        (booking_ids,),
    )
    return len(booking_ids)


def clear_whatsapp_data(
    *,
    phone: str | None,
    lead_id: int | None,
    dry_run: bool,
) -> int:
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        raise SystemExit("DATABASE_URL is not set in .env")

    if not phone and lead_id is None:
        raise SystemExit("Provide a phone number or --lead-id")

    with psycopg.connect(_pg_conninfo(database_url)) as conn:
        with conn.cursor() as cur:
            leads = _find_leads(cur, phone=phone, lead_id=lead_id)
            if not leads:
                target = f"lead id={lead_id}" if lead_id is not None else phone
                print(f"No lead found for {target}")
                return 1

            normalized, digits = _normalize_phone(phone or leads[0][2] or "")
            status_table, student_col, status_col = _status_history_layout(cur)
            lead_new_status_id = _lead_new_status_id(cur)
            print(
                f"Using {status_table}.{student_col} / {status_col} "
                f"(Lead: New status_id={lead_new_status_id})"
            )

            for row in leads:
                lead_pk, name, lead_phone, intake_step, stage = row
                print(
                    f"Lead id={lead_pk} name={name!r} phone={lead_phone!r} "
                    f"intake_step={intake_step!r} stage={stage!r}"
                )

                cur.execute(
                    """
                    SELECT wa_message_id FROM message_history
                    WHERE lead_id = %s AND wa_message_id IS NOT NULL
                    """,
                    (lead_pk,),
                )
                wa_ids = [item[0] for item in cur.fetchall()]

                cur.execute("SELECT COUNT(*) FROM messages WHERE lead_id = %s", (lead_pk,))
                message_count = cur.fetchone()[0]
                cur.execute(
                    "SELECT COUNT(*) FROM message_history WHERE lead_id = %s",
                    (lead_pk,),
                )
                history_lead_count = cur.fetchone()[0]
                cur.execute(
                    """
                    SELECT COUNT(*) FROM message_history
                    WHERE sender_phone IN (%s, %s, %s)
                    """,
                    (normalized, digits, f"+{digits}"),
                )
                history_phone_count = cur.fetchone()[0]
                if wa_ids:
                    cur.execute(
                        "SELECT COUNT(*) FROM processed_messages WHERE message_id = ANY(%s)",
                        (wa_ids,),
                    )
                    processed_count = cur.fetchone()[0]
                else:
                    processed_count = 0
                cur.execute(
                    "SELECT COUNT(*) FROM conversation_audit_logs WHERE lead_id = %s",
                    (lead_pk,),
                )
                audit_count = cur.fetchone()[0]
                cur.execute(
                    "SELECT COUNT(*) FROM consultation_slots WHERE lead_id = %s",
                    (lead_pk,),
                )
                slot_count = cur.fetchone()[0]
                status_total = _count_status_history_rows(cur, status_table, student_col, lead_pk)
                status_history_count = _count_non_lead_new_status_rows(
                    cur,
                    status_table,
                    student_col,
                    status_col,
                    lead_pk,
                    lead_new_status_id,
                )
                booking_ids = _booking_ids_for_lead(cur, lead_pk)

                print(f"  would delete messages: {message_count}")
                print(f"  would delete message_history (lead): {history_lead_count}")
                print(f"  would delete message_history (phone): {history_phone_count}")
                print(f"  would delete processed_messages: {processed_count}")
                print(f"  would delete conversation_audit_logs: {audit_count}")
                print(f"  would release consultation slots: {slot_count}")
                print(
                    f"  would delete counselling bookings: {len(booking_ids)}"
                    + (f" {booking_ids}" if booking_ids else "")
                )
                print(
                    f"  would delete {status_table} (except Lead: New): "
                    f"{status_history_count} of {status_total} row(s)"
                )
                print("  would reset intake/profile/handoff fields and pipeline to Lead: New")

                if dry_run:
                    continue

                cur.execute("DELETE FROM messages WHERE lead_id = %s", (lead_pk,))
                cur.execute("DELETE FROM message_history WHERE lead_id = %s", (lead_pk,))
                cur.execute(
                    "DELETE FROM message_history WHERE sender_phone IN (%s, %s, %s)",
                    (normalized, digits, f"+{digits}"),
                )
                if wa_ids:
                    cur.execute(
                        "DELETE FROM processed_messages WHERE message_id = ANY(%s)",
                        (wa_ids,),
                    )
                cur.execute(
                    "DELETE FROM conversation_audit_logs WHERE lead_id = %s",
                    (lead_pk,),
                )
                cur.execute(
                    "UPDATE consultation_slots SET lead_id = NULL WHERE lead_id = %s",
                    (lead_pk,),
                )
                deleted_bookings = _delete_counselling_bookings(cur, booking_ids)
                if deleted_bookings:
                    print(f"  deleted counselling bookings: {deleted_bookings}")
                deleted_status_rows = _delete_non_lead_new_status_rows(
                    cur,
                    status_table,
                    student_col,
                    status_col,
                    lead_pk,
                    lead_new_status_id,
                )
                _ensure_lead_new_status_row(
                    cur,
                    status_table,
                    student_col,
                    status_col,
                    lead_pk,
                    lead_new_status_id,
                )
                remaining_status = _count_status_history_rows(
                    cur, status_table, student_col, lead_pk
                )
                print(
                    f"  deleted {status_table} rows (non Lead: New): {deleted_status_rows}; "
                    f"remaining: {remaining_status}"
                )
                cur.execute(
                    """
                    UPDATE leads SET
                        phone_number = trim(both E' \t\r\n' from phone_number),
                        intake_step = NULL,
                        intake_context = NULL,
                        wants_consultation_call = NULL,
                        consultation_scheduled_at = NULL,
                        calendar_booking_id = NULL,
                        current_location = NULL,
                        preferred_country = NULL,
                        english_test_scores = NULL,
                        gre_score = NULL,
                        gmat_score = NULL,
                        test_scores = NULL,
                        handoff_ai_confidence = NULL,
                        handoff_reason = NULL,
                        stage = 'AI_ACTIVE',
                        is_human_locked = FALSE,
                        status_definition_id = %s,
                        status_entered_at = COALESCE(created_at, status_entered_at, NOW())
                    WHERE id = %s
                    """,
                    (lead_new_status_id, lead_pk),
                )

        if dry_run:
            print("Dry run only — no changes made.")
        else:
            conn.commit()
            print("Done.")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Clear WhatsApp messages and counselling bookings for a phone number or lead id"
        )
    )
    parser.add_argument(
        "phone",
        nargs="?",
        help="E.164 phone number, e.g. +918754545407",
    )
    parser.add_argument(
        "--lead-id",
        type=int,
        help="Clear by lead id instead of phone number",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without changing the database",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required to apply changes (omit for dry-run preview only)",
    )
    args = parser.parse_args()

    if not args.dry_run and not args.yes:
        print(
            "Refusing to modify the database without --yes.\n"
            "Preview first:  python scripts/clear_whatsapp_messages.py <phone> --dry-run\n"
            "Then apply:     python scripts/clear_whatsapp_messages.py <phone> --yes",
            file=sys.stderr,
        )
        return 2

    return clear_whatsapp_data(
        phone=args.phone,
        lead_id=args.lead_id,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
