"""Clear WhatsApp message history for a phone number and reset intake for a fresh start."""
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


def clear_whatsapp_data(phone: str) -> int:
    digits = re.sub(r"\D", "", phone)
    normalized = f"+{digits}" if digits else phone.strip()

    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        raise SystemExit("DATABASE_URL is not set in .env")

    with psycopg.connect(_pg_conninfo(database_url)) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, full_name, phone_number, intake_step
                FROM leads
                WHERE phone_number = %s OR phone_number = %s OR phone_number LIKE %s
                ORDER BY id DESC
                LIMIT 5
                """,
                (normalized, digits, f"%{digits[-10:] if len(digits) >= 10 else digits}%"),
            )
            leads = cur.fetchall()
            if not leads:
                print(f"No lead found for {normalized}")
                return 1

            for lead_id, name, lead_phone, intake_step in leads:
                print(
                    f"Lead id={lead_id} name={name!r} phone={lead_phone!r} intake_step={intake_step!r}"
                )

                cur.execute(
                    "SELECT wa_message_id FROM message_history WHERE lead_id = %s AND wa_message_id IS NOT NULL",
                    (lead_id,),
                )
                wa_ids = [row[0] for row in cur.fetchall()]

                cur.execute("DELETE FROM messages WHERE lead_id = %s", (lead_id,))
                deleted_messages = cur.rowcount

                cur.execute("DELETE FROM message_history WHERE lead_id = %s", (lead_id,))
                deleted_hist_lead = cur.rowcount

                cur.execute(
                    "DELETE FROM message_history WHERE sender_phone IN (%s, %s, %s)",
                    (normalized, digits, f"+{digits}"),
                )
                deleted_hist_phone = cur.rowcount

                deleted_proc = 0
                if wa_ids:
                    cur.execute(
                        "DELETE FROM processed_messages WHERE message_id = ANY(%s)",
                        (wa_ids,),
                    )
                    deleted_proc = cur.rowcount

                cur.execute(
                    "UPDATE consultation_slots SET lead_id = NULL WHERE lead_id = %s",
                    (lead_id,),
                )
                released_slots = cur.rowcount

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
                        stage = 'AI_ACTIVE',
                        is_human_locked = FALSE
                    WHERE id = %s
                    """,
                    (lead_id,),
                )

                print(f"  deleted messages: {deleted_messages}")
                print(f"  deleted message_history (lead): {deleted_hist_lead}")
                print(f"  deleted message_history (phone): {deleted_hist_phone}")
                print(f"  deleted processed_messages: {deleted_proc}")
                print(f"  released consultation slots: {released_slots}")
                print("  reset intake/profile fields for fresh start")

        conn.commit()

    print("Done.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Clear WhatsApp messages for a phone number")
    parser.add_argument("phone", nargs="?", default="+918754545407", help="E.164 phone number")
    args = parser.parse_args()
    return clear_whatsapp_data(args.phone)


if __name__ == "__main__":
    raise SystemExit(main())
