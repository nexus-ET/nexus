#!/usr/bin/env python3
"""
Bootstrap Alembic on databases that were created before migration tracking.

NEXUS staging/production was originally provisioned with SQLAlchemy create_all()
and sync_schema_columns(), so alembic_version may be empty while tables already
exist. Running `alembic upgrade head` from scratch then fails with duplicate
column/table errors.

This script inspects the live schema, stamps Alembic to the highest revision
already reflected in the database, then runs only the remaining migrations.

Used automatically from deploy.sh; can also be run manually on the VPS.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Inspector

BACKEND_ROOT = Path(__file__).resolve().parents[1]
LEGACY_BASELINE_REVISION = "d9a4b2c81f0e"
HEAD_REVISION = "s5p8q1r54s0m"

ORDERED_REVISIONS: list[str] = [
    "d9a4b2c81f0e",
    "e1f3a8b92c4d",
    "f2a4b9c03d5e",
    "g3c6d1e25f7a",
    "h4d7e2f36g8b",
    "i5e8f3g47h9c",
    "j6f9g4h58i0d",
    "k7g0h5i69j1e",
    "l8h1i6j70k2f",
    "m9i2j7k81l3g",
    "n0j3k8l92m4h",
    "o1k4l9m03n5i",
    "p2l5m0n14o6j",
    "q3m6n1o25p7k",
    "r4n7o2p36q8l",
    "s5p8q1r54s0m",
]


def _load_database_url() -> str:
    sys.path.insert(0, str(BACKEND_ROOT))
    from app.config import settings

    return settings.DATABASE_URL


def _revision_index(revision: str) -> int:
    return ORDERED_REVISIONS.index(revision)


def _next_revision(revision: str) -> str | None:
    index = _revision_index(revision)
    if index + 1 >= len(ORDERED_REVISIONS):
        return None
    return ORDERED_REVISIONS[index + 1]


def _has_table(inspector: Inspector, table_name: str) -> bool:
    return inspector.has_table(table_name)


def _has_column(inspector: Inspector, table_name: str, column_name: str) -> bool:
    if not _has_table(inspector, table_name):
        return False
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _session_cancelled_allows_rebook(inspector: Inspector) -> bool:
    if not _has_table(inspector, "status_definitions"):
        return False
    bind = inspector.bind
    if bind is None:
        return False
    with bind.connect() as conn:
        row = conn.execute(
            text("SELECT next_stage_id FROM status_definitions WHERE id = 6")
        ).fetchone()
    return row is not None and row[0] in (3, 4)


def _status_definitions_v3_seeded(inspector: Inspector) -> bool:
    if not _has_table(inspector, "status_definitions"):
        return False
    bind = inspector.bind
    if bind is None:
        return False
    with bind.connect() as conn:
        marketing = conn.execute(
            text(
                "SELECT 1 FROM status_definitions "
                "WHERE stage_name = 'Lead: Marketing Enabled' LIMIT 1"
            )
        ).fetchone()
        relaunch = conn.execute(
            text("SELECT 1 FROM status_definitions WHERE id = 45 LIMIT 1")
        ).fetchone()
    return marketing is not None and relaunch is not None


def _revision_checks() -> dict[str, Callable[[Inspector], bool]]:
    return {
        "d9a4b2c81f0e": lambda i: _has_table(i, "agent_configs")
        and _has_column(i, "leads", "assigned_advisor_id"),
        "e1f3a8b92c4d": lambda i: _has_table(i, "countries"),
        "f2a4b9c03d5e": lambda i: _has_table(i, "education_degrees"),
        "g3c6d1e25f7a": lambda i: _has_table(i, "gpa_cgpa_scores"),
        "h4d7e2f36g8b": lambda i: _has_table(i, "target_programs")
        and _has_table(i, "target_courses"),
        "i5e8f3g47h9c": lambda i: _has_column(i, "messages", "ai_confidence")
        and _has_column(i, "leads", "handoff_ai_confidence")
        and _has_column(i, "leads", "handoff_reason"),
        "j6f9g4h58i0d": lambda i: _has_table(i, "conversation_audit_logs"),
        "k7g0h5i69j1e": lambda i: _has_table(i, "counselling_notes"),
        "l8h1i6j70k2f": lambda i: _has_table(i, "status_definitions")
        and _has_table(i, "lead_status_history")
        and _has_column(i, "leads", "status_definition_id"),
        "m9i2j7k81l3g": lambda i: _has_column(i, "leads", "status_definition_id"),
        "n0j3k8l92m4h": lambda i: _has_table(i, "status_definitions")
        and not _has_column(i, "status_definitions", "sort_order"),
        "o1k4l9m03n5i": lambda i: _has_table(i, "status_history")
        and _has_column(i, "status_history", "changed_by_type"),
        "p2l5m0n14o6j": lambda i: _has_table(i, "system_logs"),
        "q3m6n1o25p7k": _session_cancelled_allows_rebook,
        "r4n7o2p36q8l": lambda i: _has_table(i, "status_transitions"),
        "s5p8q1r54s0m": lambda i: _status_definitions_v3_seeded(i),
    }


def _revision_applied(inspector: Inspector, revision: str) -> bool:
    return _revision_checks()[revision](inspector)


def _detect_sequential_schema_revision(inspector: Inspector) -> str | None:
    """Highest revision whose chain is fully satisfied from d9 onward."""
    detected: str | None = None
    for revision in ORDERED_REVISIONS:
        if _revision_applied(inspector, revision):
            detected = revision
        else:
            break
    return detected


def _current_alembic_revision() -> str | None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        cwd=BACKEND_ROOT,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (result.stdout or "") + (result.stderr or "")
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("INFO"):
            continue
        token = line.split()[0]
        if len(token) >= 8 and token.isalnum():
            return token
    return None


def _database_has_legacy_schema(inspector: Inspector) -> bool:
    required = {"users", "leads", "clients"}
    present = set(inspector.get_table_names())
    return required.issubset(present)


def _run_alembic(*args: str) -> None:
    cmd = [sys.executable, "-m", "alembic", *args]
    print(f"  {' '.join(cmd)}")
    subprocess.run(cmd, cwd=BACKEND_ROOT, check=True)


def _stamp_if_behind_schema(inspector: Inspector, current: str | None) -> str | None:
    """Stamp forward when create_all() already applied tables/columns."""
    detected = _detect_sequential_schema_revision(inspector)
    if detected and (not current or _revision_index(detected) > _revision_index(current)):
        print(
            f"Schema already includes changes through {detected}; "
            f"stamping Alembic from {current or 'empty'}."
        )
        _run_alembic("stamp", detected)
        return detected
    return current


def _stamp_next_applied_revisions(inspector: Inspector) -> bool:
    """Stamp individual later revisions already present (e.g. create_all tables)."""
    stamped = False
    while True:
        current = _current_alembic_revision()
        if not current or current == HEAD_REVISION:
            break
        next_revision = _next_revision(current)
        if not next_revision or not _revision_applied(inspector, next_revision):
            break
        print(
            f"Schema already reflects {next_revision}; "
            "stamping without re-running migration SQL."
        )
        _run_alembic("stamp", next_revision)
        stamped = True
    return stamped


def _migrate_to_head(inspector: Inspector) -> None:
    current = _current_alembic_revision()
    current = _stamp_if_behind_schema(inspector, current)
    _stamp_next_applied_revisions(inspector)

    attempts = len(ORDERED_REVISIONS) + 2
    for _ in range(attempts):
        current = _current_alembic_revision()
        if current == HEAD_REVISION:
            return

        _stamp_next_applied_revisions(inspector)
        if _current_alembic_revision() == HEAD_REVISION:
            return

        try:
            _run_alembic("upgrade", "head")
        except subprocess.CalledProcessError:
            if _stamp_next_applied_revisions(inspector):
                continue
            raise

        if _current_alembic_revision() == HEAD_REVISION:
            return

    final = _current_alembic_revision()
    if final != HEAD_REVISION:
        raise RuntimeError(f"Expected Alembic head {HEAD_REVISION}, got {final or 'empty'}")


def main() -> int:
    database_url = _load_database_url()
    engine = create_engine(database_url)
    inspector = inspect(engine)

    current = _current_alembic_revision()
    if current == HEAD_REVISION:
        print(f"Alembic already at head ({HEAD_REVISION}).")
        return 0

    if current:
        print(f"Alembic revision: {current}")
        _migrate_to_head(inspector)
    elif not _database_has_legacy_schema(inspector):
        print("Fresh database detected — running full alembic upgrade head.")
        _run_alembic("upgrade", "head")
    else:
        print("No alembic_version recorded; legacy schema detected.")
        detected = _detect_sequential_schema_revision(inspector)
        start_revision = detected or LEGACY_BASELINE_REVISION
        if not detected:
            print(
                "Core tables exist but post-baseline objects missing; "
                f"stamping baseline {LEGACY_BASELINE_REVISION}."
            )
        else:
            print(f"Schema matches through {detected}; stamping that revision.")
        _run_alembic("stamp", start_revision)
        _migrate_to_head(inspector)

    final = _current_alembic_revision()
    print(f"Done. Alembic revision is now: {final or 'unknown'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: alembic command failed with exit code {exc.returncode}", file=sys.stderr)
        raise SystemExit(exc.returncode) from exc
