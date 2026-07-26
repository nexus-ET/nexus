#!/usr/bin/env python3
"""
Copy Academia Hub catalog + institution wizard data (steps 1–5) between Neon DBs.

Includes:
  - Countries / states / cities (geography)
  - Academic framework: levels, programs, majors, courses (+ mappings, target catalogs)
  - Institutions tree: campus types, institutions, campuses, colleges,
    course offerings, intakes, program intake assignments, pictures
  - institution_wizard_drafts (step 4 course mappings live here; user FK remapped by email)

Does NOT copy:
  - academia_audit_logs / calendar alert logs
  - R2 / uploads binary assets (picture rows are copied; files must be synced separately)

Usage (VPS — staging DATABASE_URL is the target):
  cd /var/www/nexus/backend && source .venv/bin/activate
  python scripts/copy_academia_to_staging.py \\
    --source 'postgresql+psycopg://USER:PASS@ep-shy-pine-.../neondb?sslmode=require'

Usage (local — develop is source from .env):
  python scripts/copy_academia_to_staging.py \\
    --target 'postgresql+psycopg://USER:PASS@ep-broad-breeze-.../neondb?sslmode=require'
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

# Parents before children. Self-FK intakes handled via 2-pass copy.
ACADEMIA_TABLES: list[str] = [
    # Geography
    "countries",
    "geography_states",
    "geography_cities",
    # Academic framework (LPMC)
    "levels",
    "programs",
    "education_majors",
    "education_major_levels",
    "program_education_major_mappings",
    "education_courses",
    "course_education_major_mappings",
    "education_degrees",
    "target_programs",
    "target_courses",
    # Lookups / calendar
    "campus_types",
    "global_academic_templates",
    # Institution wizard live data (steps 1–5 + pictures metadata)
    "institutions",
    "campuses",
    "colleges",
    "institution_course_offerings",
    "institution_intakes",
    "program_intake_assignments",
    "institution_pictures",
    # Step 4 course selections (and other wizard payload) — after institutions + users exist
    "institution_wizard_drafts",
]


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


def _table_columns(conn: psycopg.Connection, table: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table,),
        )
        return [row[0] for row in cur.fetchall()]


def _reset_sequences(conn: psycopg.Connection, tables: list[str]) -> None:
    with conn.cursor() as cur:
        for table in tables:
            cur.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                  AND column_default LIKE 'nextval%%'
                """,
                (table,),
            )
            for (col,) in cur.fetchall():
                cur.execute(
                    f"""
                    SELECT setval(
                        pg_get_serial_sequence(%s, %s),
                        COALESCE((SELECT MAX("{col}") FROM "{table}"), 1),
                        (SELECT MAX("{col}") IS NOT NULL FROM "{table}")
                    )
                    """,
                    (table, col),
                )
    conn.commit()


def _copy_table(
    src: psycopg.Connection,
    dst: psycopg.Connection,
    table: str,
) -> int:
    src_cols = _table_columns(src, table)
    dst_cols = _table_columns(dst, table)
    shared = [c for c in src_cols if c in set(dst_cols)]
    if not shared:
        raise RuntimeError(f"{table}: no shared columns")

    # Neon disallows session_replication_role; self-FK intakes need a 2-pass load.
    if table == "institution_intakes" and "parent_intake_id" in shared:
        return _copy_institution_intakes(src, dst, shared)
    if table == "institution_wizard_drafts":
        return _copy_wizard_drafts(src, dst, shared)

    col_list = ", ".join(f'"{c}"' for c in shared)
    with src.cursor() as sc, dst.cursor() as dc:
        if src_cols == dst_cols:
            with sc.copy(f'COPY "{table}" TO STDOUT') as copy_out:
                with dc.copy(f'COPY "{table}" FROM STDIN') as copy_in:
                    for chunk in copy_out:
                        copy_in.write(chunk)
        else:
            missing_dst = [c for c in src_cols if c not in set(dst_cols)]
            missing_src = [c for c in dst_cols if c not in set(src_cols)]
            if missing_dst or missing_src:
                print(
                    f"  ! {table}: column drift "
                    f"(src-only={missing_dst or '-'}, dst-only={missing_src or '-'}); "
                    f"copying {len(shared)} shared cols"
                )
            with sc.copy(f'COPY "{table}" ({col_list}) TO STDOUT') as copy_out:
                with dc.copy(f'COPY "{table}" ({col_list}) FROM STDIN') as copy_in:
                    for chunk in copy_out:
                        copy_in.write(chunk)

    with src.cursor() as sc:
        sc.execute(f'SELECT count(*) FROM "{table}"')
        return int(sc.fetchone()[0])


def _copy_institution_intakes(
    src: psycopg.Connection,
    dst: psycopg.Connection,
    shared: list[str],
) -> int:
    """
    Load intakes via COPY (preserves jsonb), with parent_intake_id nulled,
    then restore parent links. Avoids Neon session_replication_role + array/jsonb casts.
    """
    select_exprs: list[str] = []
    for col in shared:
        if col == "parent_intake_id":
            select_exprs.append("NULL::integer AS parent_intake_id")
        elif col == "level_ids":
            # Source may be int[]; staging is jsonb — normalize for COPY.
            select_exprs.append('to_jsonb("level_ids") AS level_ids')
        else:
            select_exprs.append(f'"{col}"')
    select_sql = ", ".join(select_exprs)
    col_list = ", ".join(f'"{c}"' for c in shared)

    with src.cursor() as sc, dst.cursor() as dc:
        with sc.copy(
            f'COPY (SELECT {select_sql} FROM "institution_intakes") TO STDOUT'
        ) as copy_out:
            with dc.copy(
                f'COPY "institution_intakes" ({col_list}) FROM STDIN'
            ) as copy_in:
                for chunk in copy_out:
                    copy_in.write(chunk)

        sc.execute(
            'SELECT id, parent_intake_id FROM "institution_intakes" '
            "WHERE parent_intake_id IS NOT NULL"
        )
        parents = sc.fetchall()
        for intake_id, parent_id in parents:
            dc.execute(
                'UPDATE "institution_intakes" SET parent_intake_id = %s WHERE id = %s',
                (parent_id, intake_id),
            )

        sc.execute('SELECT count(*) FROM "institution_intakes"')
        return int(sc.fetchone()[0])


def _resolve_target_user_id_map(
    src: psycopg.Connection, dst: psycopg.Connection
) -> tuple[dict[int, int], int]:
    """Map source users.id → target users.id by email; missing emails → fallback user."""
    with dst.cursor() as dc:
        dc.execute(
            "SELECT id FROM users WHERE lower(email) = 'ishq@edutrust.in' LIMIT 1"
        )
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
            raise RuntimeError(
                "No users on target DB. Seed staging users before copying wizard drafts."
            )
        fallback_id = int(row[0])

        dc.execute("SELECT id, lower(email) FROM users")
        dst_by_email = {str(email): int(uid) for uid, email in dc.fetchall() if email}

    with src.cursor() as sc:
        sc.execute("SELECT id, lower(email) FROM users")
        src_rows = sc.fetchall()

    mapping: dict[int, int] = {}
    for src_id, email in src_rows:
        mapping[int(src_id)] = dst_by_email.get(str(email) if email else "", fallback_id)
    return mapping, fallback_id


def _copy_wizard_drafts(
    src: psycopg.Connection,
    dst: psycopg.Connection,
    shared: list[str],
) -> int:
    """
    Copy wizard drafts (holds step-4 course mappings). Remap created_by_user_id
    by email so FK to staging users succeeds.
    """
    user_map, fallback_id = _resolve_target_user_id_map(src, dst)
    col_list = ", ".join(f'"{c}"' for c in shared)
    placeholders = ", ".join(["%s"] * len(shared))
    json_cols = {"payload", "completed_steps"}
    user_idx = shared.index("created_by_user_id") if "created_by_user_id" in shared else -1

    with src.cursor() as sc:
        sc.execute(f'SELECT {col_list} FROM "institution_wizard_drafts"')
        rows = sc.fetchall()

    if not rows:
        return 0

    payload: list[tuple] = []
    for row in rows:
        values = list(row)
        if user_idx >= 0:
            src_uid = values[user_idx]
            values[user_idx] = user_map.get(int(src_uid), fallback_id)
        for i, col in enumerate(shared):
            if col in json_cols and values[i] is not None and not isinstance(values[i], Json):
                raw = values[i]
                if isinstance(raw, (dict, list)):
                    values[i] = Json(raw)
                elif isinstance(raw, str):
                    values[i] = Json(json.loads(raw))
                else:
                    values[i] = Json(raw)
        payload.append(tuple(values))

    with dst.cursor() as dc:
        dc.executemany(
            f'INSERT INTO "institution_wizard_drafts" ({col_list}) VALUES ({placeholders})',
            payload,
        )
    print(f"  (wizard drafts: remapped created_by_user_id by email; {len(payload)} rows)")
    return len(payload)


def copy_academia(*, source_url: str, target_url: str, dry_run: bool = False) -> int:
    source = _pg_conninfo(source_url)
    target = _pg_conninfo(target_url)
    if not source or not target:
        print("Both --source and --target (or env defaults) are required.", file=sys.stderr)
        return 1
    if source == target:
        print("Source and target URLs resolve to the same database — aborting.", file=sys.stderr)
        return 1

    print(f"Source: {_summarize(source)}")
    print(f"Target: {_summarize(target)}")

    with psycopg.connect(source, connect_timeout=60) as src, psycopg.connect(
        target, connect_timeout=60
    ) as dst:
        tables = [t for t in ACADEMIA_TABLES if _table_exists(src, t) and _table_exists(dst, t)]
        missing_src = [t for t in ACADEMIA_TABLES if not _table_exists(src, t)]
        missing_dst = [t for t in ACADEMIA_TABLES if not _table_exists(dst, t)]
        if missing_src:
            print(f"Skip (missing on source): {', '.join(missing_src)}")
        if missing_dst:
            print(f"Skip (missing on target): {', '.join(missing_dst)}")
        if not tables:
            print("No tables to copy.", file=sys.stderr)
            return 1

        print(f"Tables ({len(tables)}): {', '.join(tables)}")
        if dry_run:
            for table in tables:
                with src.cursor() as sc:
                    sc.execute(f'SELECT count(*) FROM "{table}"')
                    print(f"  {table}: {sc.fetchone()[0]} rows (dry-run)")
            return 0

        # Neon forbids session_replication_role. One TRUNCATE listing all tables
        # skips FK checks among them; intakes use a 2-pass copy for self-FK.
        with dst.cursor() as cur:
            quoted = ", ".join(f'"{t}"' for t in tables)
            cur.execute(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE")
        dst.commit()

        for table in tables:
            count = _copy_table(src, dst, table)
            dst.commit()
            print(f"  {table}: {count} rows")

        _reset_sequences(dst, tables)

        print("\nVerify target counts:")
        with dst.cursor() as cur:
            for table in tables:
                cur.execute(f'SELECT count(*) FROM "{table}"')
                print(f"  {table}: {cur.fetchone()[0]}")

    print(
        "\nDone. Picture rows copied; if logos/banners 404, sync R2/uploads separately."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copy academia geography + framework + institutions to staging"
    )
    parser.add_argument(
        "--source",
        default=os.getenv("ACADEMIA_COPY_SOURCE_URL") or os.getenv("DATABASE_URL", ""),
        help="Source DATABASE_URL (default: local DATABASE_URL / develop)",
    )
    parser.add_argument(
        "--target",
        default=os.getenv("ACADEMIA_COPY_TARGET_URL")
        or os.getenv("STAGING_DATABASE_URL")
        or "",
        help="Target DATABASE_URL (default: STAGING_DATABASE_URL, or omit on VPS and pass explicitly)",
    )
    parser.add_argument(
        "--target-from-env",
        action="store_true",
        help="On VPS: use DATABASE_URL as target and require --source for develop",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    source = args.source
    target = args.target
    if args.target_from_env:
        target = os.getenv("DATABASE_URL", "")
        if not args.source or args.source == os.getenv("DATABASE_URL"):
            # Prefer explicit develop URL via --source
            pass

    if not target:
        print(
            "Pass --target <staging Neon URL>, or --target-from-env on the VPS "
            "(uses DATABASE_URL), or set STAGING_DATABASE_URL.",
            file=sys.stderr,
        )
        return 1

    return copy_academia(source_url=source, target_url=target, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
