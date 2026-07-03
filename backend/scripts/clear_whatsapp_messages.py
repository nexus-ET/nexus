"""
Clear WhatsApp message history for a lead and reset intake for a fresh AI session.

Removes all messages and pipeline status rows except **Lead: New** (View Journey baseline).

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
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM status_history sh
                    JOIN status_definitions sd ON sd.id = sh.status_id
                    WHERE sh.student_id = %s AND sd.stage_name <> 'Lead: New'
                    """,
                    (lead_pk,),
                )
                status_history_count = cur.fetchone()[0]

                print(f"  would delete messages: {message_count}")
                print(f"  would delete message_history (lead): {history_lead_count}")
                print(f"  would delete message_history (phone): {history_phone_count}")
                print(f"  would delete processed_messages: {processed_count}")
                print(f"  would delete conversation_audit_logs: {audit_count}")
                print(f"  would release consultation slots: {slot_count}")
                print(f"  would delete status_history (except Lead: New): {status_history_count}")
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
                cur.execute(
                    """
                    DELETE FROM status_history sh
                    USING status_definitions sd
                    WHERE sh.status_id = sd.id
                      AND sh.student_id = %s
                      AND sd.stage_name <> 'Lead: New'
                    """,
                    (lead_pk,),
                )
                cur.execute(
                    """
                    SELECT sd.id
                    FROM status_definitions sd
                    WHERE sd.stage_name = 'Lead: New'
                    LIMIT 1
                    """,
                )
                lead_new_row = cur.fetchone()
                lead_new_status_id = lead_new_row[0] if lead_new_row else 1
                cur.execute(
                    """
                    SELECT 1
                    FROM status_history sh
                    JOIN status_definitions sd ON sd.id = sh.status_id
                    WHERE sh.student_id = %s AND sd.stage_name = 'Lead: New'
                    LIMIT 1
                    """,
                    (lead_pk,),
                )
                if cur.fetchone() is None:
                    cur.execute(
                        """
                        INSERT INTO status_history (
                            student_id,
                            status_id,
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
        description="Clear WhatsApp messages for a phone number or lead id"
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
