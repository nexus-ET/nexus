#!/usr/bin/env python3
"""
Copy one students_master record + related lead graph from develop → staging.

Default target student: Ishan Ahmed (students_master / lead email ishq@erxa.in).

Copies (when present):
  - leads
  - counselling_bookings
  - messages, message_history, conversation_audit_logs
  - candidate_educations, candidate_test_scores
  - work_experiences, research_projects, non_academic_activities
  - digital_presence_links, counselling_notes, candidate_tasks
  - admission_history, status_history, consultation_slots
  - students_master

User FKs (assigned_advisor_id, updated_by_user_id, etc.) are remapped by email
(fallback: ishq@edutrust.in / first superuser on target).

Usage (Windows — develop DATABASE_URL is source):
  python scripts/copy_student_to_staging.py --lead-id 27 --target 'postgresql+psycopg://…Nexus-Dev-1…'
  python scripts/copy_student_to_staging.py --email ishq@erxa.in --target '…'
  python scripts/copy_student_to_staging.py --name 'Ishan Ahmed' --target '…'

Default with only --target: copies lead_id=27 (Ishan Ahmed / ishq@erxa.in).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Json

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(BACKEND_ROOT / ".env")

from app.config import normalize_database_url  # noqa: E402

# Child tables keyed by lead_id (copied after lead + bookings).
LEAD_CHILD_TABLES: list[str] = [
    "counselling_bookings",
    "messages",
    "message_history",
    "conversation_audit_logs",
    "candidate_educations",
    "candidate_test_scores",
    "work_experiences",
    "research_projects",
    "non_academic_activities",
    "digital_presence_links",
    "counselling_notes",
    "candidate_tasks",
    "admission_history",
    "consultation_slots",
    "team_chat_messages",
]

USER_FK_COLUMNS = {
    "assigned_advisor_id",
    "updated_by_user_id",
    "created_by_user_id",
    "user_id",
    "advisor_id",
    "admin_id",
}


def _pg_conninfo(url: str) -> str:
    raw = normalize_database_url((url or "").strip().strip('"').strip("'"))
    for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://", "postgres://"):
        if raw.startswith(prefix):
            raw = "postgresql://" + raw[len(prefix) :]
            break
    return raw


def _summarize(url: str) -> str:
    try:
        host = url.split("@", 1)[1].split("/", 1)[0]
        db = url.rstrip("/").rsplit("/", 1)[-1].split("?", 1)[0]
        return f"{host}/{db}"
    except Exception:
        return "(unparseable)"


def _table_exists(conn: psycopg.Connection, table: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
            """,
            (table,),
        )
        return cur.fetchone() is not None


def _columns(conn: psycopg.Connection, table: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table,),
        )
        return [r[0] for r in cur.fetchall()]


def _json_cols(conn: psycopg.Connection, table: str) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
              AND (data_type = 'json' OR data_type = 'jsonb' OR udt_name IN ('json', 'jsonb'))
            """,
            (table,),
        )
        return {r[0] for r in cur.fetchall()}


def _resolve_user_map(src: psycopg.Connection, dst: psycopg.Connection) -> tuple[dict[int, int], int]:
    with dst.cursor() as dc:
        dc.execute("SELECT id FROM users WHERE lower(email) = 'ishq@edutrust.in' LIMIT 1")
        row = dc.fetchone()
        if not row:
            dc.execute(
                "SELECT id FROM users WHERE is_superuser IS TRUE ORDER BY id ASC LIMIT 1"
            )
            row = dc.fetchone()
        if not row:
            dc.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1")
            row = dc.fetchone()
        if not row:
            raise RuntimeError("No users on target — seed staging users first.")
        fallback = int(row[0])
        dc.execute("SELECT id, lower(email) FROM users")
        by_email = {str(e): int(i) for i, e in dc.fetchall() if e}

    with src.cursor() as sc:
        sc.execute("SELECT id, lower(email) FROM users")
        mapping = {
            int(i): by_email.get(str(e) if e else "", fallback) for i, e in sc.fetchall()
        }
    return mapping, fallback


def _wrap_row(
    shared: list[str],
    row: tuple,
    *,
    json_cols: set[str],
    user_map: dict[int, int],
    fallback_user: int,
) -> tuple:
    values = list(row)
    for i, col in enumerate(shared):
        val = values[i]
        if col in USER_FK_COLUMNS and val is not None:
            values[i] = user_map.get(int(val), fallback_user)
        elif col in json_cols and val is not None and not isinstance(val, Json):
            if isinstance(val, (dict, list)):
                values[i] = Json(val)
            elif isinstance(val, str):
                values[i] = Json(json.loads(val))
            else:
                values[i] = Json(val)
    return tuple(values)


def _upsert_rows(
    src: psycopg.Connection,
    dst: psycopg.Connection,
    table: str,
    where_sql: str,
    params: tuple,
    *,
    user_map: dict[int, int],
    fallback_user: int,
) -> int:
    if not _table_exists(src, table) or not _table_exists(dst, table):
        print(f"  skip missing table: {table}")
        return 0

    src_cols = _columns(src, table)
    dst_cols = set(_columns(dst, table))
    shared = [c for c in src_cols if c in dst_cols]
    if not shared:
        print(f"  skip no shared cols: {table}")
        return 0

    json_cols = _json_cols(src, table) | _json_cols(dst, table)
    col_list = ", ".join(f'"{c}"' for c in shared)
    placeholders = ", ".join(["%s"] * len(shared))
    updates = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in shared if c != "id")

    with src.cursor() as sc:
        sc.execute(f'SELECT {col_list} FROM "{table}" WHERE {where_sql}', params)
        rows = sc.fetchall()
    if not rows:
        print(f"  {table}: 0")
        return 0

    payload = [
        _wrap_row(
            shared, row, json_cols=json_cols, user_map=user_map, fallback_user=fallback_user
        )
        for row in rows
    ]

    sql = (
        f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders}) '
        f"ON CONFLICT (id) DO UPDATE SET {updates}"
    )
    with dst.cursor() as dc:
        try:
            dc.executemany(sql, payload)
        except Exception as exc:
            # Soft-fail optional tables with hard FK deps (e.g. consultation_slots).
            print(f"  ! {table}: {exc.__class__.__name__}: {exc}")
            dst.rollback()
            return 0
    dst.commit()
    print(f"  {table}: {len(payload)}")
    return len(payload)


def _find_student(
    src: psycopg.Connection,
    *,
    student_id: int | None,
    lead_id: int | None,
    email: str | None,
    name: str | None,
) -> dict:
    with src.cursor() as sc:
        if lead_id:
            sc.execute(
                "SELECT id, lead_id, booking_id, first_name, last_name, email "
                "FROM students_master WHERE lead_id = %s "
                "ORDER BY id ASC LIMIT 1",
                (lead_id,),
            )
            row = sc.fetchone()
            if not row:
                # Fall back: treat id as lead only (create graph from lead row).
                sc.execute(
                    "SELECT id, full_name, email FROM leads WHERE id = %s",
                    (lead_id,),
                )
                lead = sc.fetchone()
                if not lead:
                    raise RuntimeError(f"Lead id={lead_id} not found on source DB.")
                return {
                    "id": None,
                    "lead_id": int(lead[0]),
                    "booking_id": None,
                    "first_name": (lead[1] or "").split(" ")[0] or None,
                    "last_name": None,
                    "email": lead[2],
                }
        elif student_id:
            sc.execute(
                "SELECT id, lead_id, booking_id, first_name, last_name, email "
                "FROM students_master WHERE id = %s",
                (student_id,),
            )
            row = sc.fetchone()
        elif email:
            sc.execute(
                "SELECT id, lead_id, booking_id, first_name, last_name, email "
                "FROM students_master WHERE lower(email) = lower(%s) "
                "ORDER BY id ASC LIMIT 1",
                (email.strip(),),
            )
            row = sc.fetchone()
        else:
            parts = (name or "Ishan Ahmed").strip().split()
            first = parts[0] if parts else "Ishan"
            last = parts[-1] if len(parts) > 1 else "Ahmed"
            sc.execute(
                "SELECT id, lead_id, booking_id, first_name, last_name, email "
                "FROM students_master "
                "WHERE first_name ILIKE %s AND last_name ILIKE %s "
                "ORDER BY id ASC LIMIT 1",
                (first, last),
            )
            row = sc.fetchone()

        if not row:
            raise RuntimeError("Student not found on source DB.")
        return {
            "id": int(row[0]),
            "lead_id": int(row[1]) if row[1] is not None else None,
            "booking_id": int(row[2]) if row[2] is not None else None,
            "first_name": row[3],
            "last_name": row[4],
            "email": row[5],
        }


def _ensure_status_definition(src: psycopg.Connection, dst: psycopg.Connection, lead_id: int) -> None:
    if not _table_exists(src, "status_definitions") or not _table_exists(dst, "status_definitions"):
        return
    with src.cursor() as sc:
        sc.execute("SELECT status_definition_id FROM leads WHERE id = %s", (lead_id,))
        row = sc.fetchone()
        if not row or row[0] is None:
            return
        status_id = int(row[0])
    _upsert_rows(
        src,
        dst,
        "status_definitions",
        "id = %s",
        (status_id,),
        user_map={},
        fallback_user=1,
    )


def copy_student(
    *,
    source_url: str,
    target_url: str,
    student_id: int | None,
    lead_id: int | None,
    email: str | None,
    name: str | None,
    dry_run: bool,
) -> int:
    source = _pg_conninfo(source_url)
    target = _pg_conninfo(target_url)
    if not source or not target:
        print("Need --source/--target (or DATABASE_URL + --target).", file=sys.stderr)
        return 1
    if source == target:
        print("Source and target are the same — aborting.", file=sys.stderr)
        return 1

    print(f"Source: {_summarize(source)}")
    print(f"Target: {_summarize(target)}")

    with psycopg.connect(source, connect_timeout=60) as src, psycopg.connect(
        target, connect_timeout=60
    ) as dst:
        student = _find_student(
            src,
            student_id=student_id,
            lead_id=lead_id,
            email=email,
            name=name,
        )
        print(
            f"Student id={student['id']} "
            f"{student['first_name']} {student['last_name']} "
            f"email={student['email']} lead_id={student['lead_id']}"
        )
        if dry_run:
            return 0

        user_map, fallback_user = _resolve_user_map(src, dst)
        resolved_lead_id = student["lead_id"]
        if not resolved_lead_id:
            if not student["id"]:
                raise RuntimeError("Nothing to copy — no students_master id and no lead_id.")
            print("Student has no lead_id — copying students_master only.")
            _upsert_rows(
                src,
                dst,
                "students_master",
                "id = %s",
                (student["id"],),
                user_map=user_map,
                fallback_user=fallback_user,
            )
            return 0

        _ensure_status_definition(src, dst, resolved_lead_id)

        _upsert_rows(
            src,
            dst,
            "leads",
            "id = %s",
            (resolved_lead_id,),
            user_map=user_map,
            fallback_user=fallback_user,
        )

        for table in LEAD_CHILD_TABLES:
            _upsert_rows(
                src,
                dst,
                table,
                "lead_id = %s",
                (resolved_lead_id,),
                user_map=user_map,
                fallback_user=fallback_user,
            )

        if _table_exists(src, "status_history"):
            _upsert_rows(
                src,
                dst,
                "status_history",
                "student_id = %s",
                (resolved_lead_id,),
                user_map=user_map,
                fallback_user=fallback_user,
            )

        if student["id"] is not None:
            _upsert_rows(
                src,
                dst,
                "students_master",
                "id = %s",
                (student["id"],),
                user_map=user_map,
                fallback_user=fallback_user,
            )

    print("\nDone. Lead/student data upserted onto staging.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Copy one student + related lead data to staging")
    parser.add_argument(
        "--source",
        default=os.getenv("DATABASE_URL", ""),
        help="Source DB (default: local DATABASE_URL / develop)",
    )
    parser.add_argument(
        "--target",
        default=os.getenv("STAGING_DATABASE_URL", ""),
        help="Target staging DATABASE_URL",
    )
    parser.add_argument("--student-id", type=int, default=None, help="students_master.id")
    parser.add_argument(
        "--lead-id",
        type=int,
        default=None,
        help="leads.id (Ishan Ahmed on develop is lead_id=27)",
    )
    parser.add_argument("--email", default="", help="e.g. ishq@erxa.in")
    parser.add_argument("--name", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.target:
        print("Pass --target <staging Neon URL>", file=sys.stderr)
        return 1

    use_student_id = args.student_id
    use_lead_id = args.lead_id
    use_email = (args.email or "").strip() or None
    use_name = (args.name or "").strip() or None

    # Default: Ishan Ahmed = lead 27 on develop
    if use_student_id is None and use_lead_id is None and not use_email and not use_name:
        use_lead_id = 27

    return copy_student(
        source_url=args.source,
        target_url=args.target,
        student_id=use_student_id,
        lead_id=use_lead_id,
        email=use_email,
        name=use_name,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())


if __name__ == "__main__":
    raise SystemExit(main())
