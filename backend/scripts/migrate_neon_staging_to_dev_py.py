"""
Copy all public table data from Nexus-Staging to Nexus-dev (no Docker required).

Reads STAGING_DATABASE_URL from .env.staging-source and DATABASE_URL from .env.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_ROOT / ".env")
load_dotenv(BACKEND_ROOT / ".env.staging-source")


def _pg_conninfo(url: str) -> str:
    raw = (url or "").strip().strip('"').strip("'")
    for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://", "postgres://"):
        if raw.startswith(prefix):
            raw = "postgresql://" + raw[len(prefix) :]
            break
    return raw.replace("postgresql://", "postgres://")


def _list_tables(conn: psycopg.Connection) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
            """
        )
        return [row[0] for row in cur.fetchall()]


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


def _copy_table(src: psycopg.Connection, dst: psycopg.Connection, table: str) -> int:
    src_cols = _table_columns(src, table)
    dst_cols = _table_columns(dst, table)
    if src_cols == dst_cols:
        with src.cursor() as sc, dst.cursor() as dc:
            with sc.copy(f'COPY "{table}" TO STDOUT') as copy_out:
                with dc.copy(f'COPY "{table}" FROM STDIN') as copy_in:
                    for chunk in copy_out:
                        copy_in.write(chunk)
        dst.commit()
        with src.cursor() as sc:
            sc.execute(f'SELECT count(*) FROM "{table}"')
            return sc.fetchone()[0]

    if table == "audit_logs":
        with src.cursor() as sc:
            sc.execute(
                """
                SELECT id, user_id, action, resource, resource_id,
                       ip_address, user_agent, status, detail, created_at
                FROM audit_logs
                """
            )
            rows = sc.fetchall()
        payload = []
        for r in rows:
            detail = r[8]
            details_json = (
                json.dumps({"legacy_detail": detail})
                if detail not in (None, "")
                else None
            )
            payload.append(
                (
                    r[0],
                    r[1],
                    r[2],
                    r[3],
                    r[4],
                    details_json,
                    r[5],
                    r[9],
                    r[6],
                    r[7],
                    detail,
                )
            )
        with dst.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO audit_logs (
                    id, user_id, action_type, target_resource, resource_id,
                    details, ip_address, created_at, session_id, sync_mode,
                    user_agent, status, detail
                ) VALUES (
                    %s, %s, %s, %s, %s, %s::jsonb, %s, %s, NULL, NULL, %s, %s, %s
                )
                """,
                payload,
            )
        dst.commit()
        return len(rows)

    raise RuntimeError(
        f"Schema mismatch for {table}: staging={src_cols}, dev={dst_cols}"
    )


def _sort_tables_for_copy(conn: psycopg.Connection, tables: list[str]) -> list[str]:
    table_set = set(tables)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT tc.table_name, ccu.table_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.constraint_column_usage ccu
              ON ccu.constraint_name = tc.constraint_name
             AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = 'public'
            """
        )
        edges = cur.fetchall()

    deps: dict[str, set[str]] = {table: set() for table in tables}
    for child, parent in edges:
        if child in table_set and parent in table_set and child != parent:
            deps[child].add(parent)

    ordered: list[str] = []
    remaining = set(tables)
    while remaining:
        ready = sorted(t for t in remaining if deps[t].issubset(set(ordered)))
        if not ready:
            ready = sorted(remaining)
        for table in ready:
            ordered.append(table)
            remaining.remove(table)
    return ordered


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
            cols = [row[0] for row in cur.fetchall()]
            for col in cols:
                cur.execute(
                    f"""
                    SELECT setval(
                        pg_get_serial_sequence(%s, %s),
                        COALESCE((SELECT MAX({col}) FROM {table}), 1),
                        (SELECT MAX({col}) IS NOT NULL FROM {table})
                    )
                    """,
                    (table, col),
                )
    conn.commit()


def migrate() -> None:
    source = _pg_conninfo(os.getenv("STAGING_DATABASE_URL", ""))
    target = _pg_conninfo(os.getenv("DATABASE_URL", ""))
    if not source or not target:
        print("Missing STAGING_DATABASE_URL or DATABASE_URL", file=sys.stderr)
        raise SystemExit(1)

    print("Connecting to staging and Nexus-dev...")
    with psycopg.connect(source, connect_timeout=30) as src, psycopg.connect(
        target, connect_timeout=30
    ) as dst:
        tables = _sort_tables_for_copy(src, _list_tables(src))
        print(f"Copying {len(tables)} tables...")

        with dst.cursor() as cur:
            quoted = ", ".join(f'"{t}"' for t in tables)
            cur.execute(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE")
        dst.commit()

        for table in tables:
            count = _copy_table(src, dst, table)
            print(f"  {table}: {count} rows")

        _reset_sequences(dst, tables)

        with dst.cursor() as cur:
            cur.execute("SELECT count(*) FROM users")
            users = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM leads")
            leads = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM messages")
            messages = cur.fetchone()[0]
        print(f"Done. Nexus-dev now has users={users}, leads={leads}, messages={messages}")


if __name__ == "__main__":
    try:
        migrate()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
