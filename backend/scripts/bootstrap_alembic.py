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
# Legacy stamp chain used only for databases provisioned before Alembic tracking.
# Fresh Neon projects (e.g. Nexus-Dev-1) take the "Fresh database" path → upgrade head.
# Revisions AFTER this list (academia hub, matching, exception_logs, …) are handled by
# plain `alembic upgrade head` — never require them in this list.
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


def _alembic_head_revision() -> str:
    """Resolve current Alembic head dynamically (do not hardcode)."""
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        cwd=BACKEND_ROOT,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = (result.stdout or "") + (result.stderr or "")
    for line in output.splitlines():
        token = line.strip().split()[0] if line.strip() else ""
        if token and len(token) >= 8 and all(ch.isalnum() for ch in token):
            return token
    raise RuntimeError(f"Could not resolve alembic head from: {output!r}")


HEAD_REVISION = "s5p8q1r54s0m"  # fallback only; overwritten in main()


def _load_database_url() -> str:
    sys.path.insert(0, str(BACKEND_ROOT))
    from app.config import settings

    return settings.DATABASE_URL


def _revision_index(revision: str) -> int | None:
    """Index in the legacy stamp chain, or None if the revision is past/outside it."""
    try:
        return ORDERED_REVISIONS.index(revision)
    except ValueError:
        return None


def _next_revision(revision: str) -> str | None:
    index = _revision_index(revision)
    if index is None:
        return None
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


def _database_looks_orm_provisioned(inspector: Inspector) -> bool:
    """True when schema was built via create_all (modern tables present)."""
    present = set(inspector.get_table_names())
    modern = {"students_master", "institutions", "status_definitions", "levels"}
    return _database_has_legacy_schema(inspector) and bool(present & modern)


def _run_alembic(*args: str) -> None:
    cmd = [sys.executable, "-m", "alembic", *args]
    print(f"  {' '.join(cmd)}")
    subprocess.run(cmd, cwd=BACKEND_ROOT, check=True)


def _seed_fresh_reference_data(engine) -> None:
    """Apply catalog rows that Alembic data migrations would have inserted."""
    from sqlalchemy.orm import sessionmaker

    from app.models.country import Country
    from app.models.education_degree import EducationDegree
    from app.models.gpa_cgpa_score import GpaCgpaScore
    from app.models.level import Level
    from app.models.academia_institution import CampusType
    from app.models.status_definition import StatusDefinition
    from app.models.status_transition import StatusTransition, TransitionType
    from app.services.countries import DEFAULT_COUNTRIES
    from app.services.education_degrees import DEFAULT_EDUCATION_DEGREES, LEVEL_CODE_TO_ID
    from app.services.gpa_cgpa_scores import DEFAULT_GPA_CGPA_SCORES
    from app.services.status_definitions_seed import V3_INSERT_SQL

    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        if db.query(StatusDefinition).count() == 0:
            print("  Seeding status_definitions v3...")
            db.execute(text(V3_INSERT_SQL))
            db.execute(
                text(
                    "SELECT setval('status_definitions_id_seq', "
                    "(SELECT COALESCE(MAX(id), 1) FROM status_definitions))"
                )
            )
            db.commit()

        if db.query(StatusTransition).count() == 0 and db.query(StatusDefinition).count() > 0:
            print("  Seeding status_transitions...")
            for row in db.query(StatusDefinition).filter(StatusDefinition.next_stage_id.isnot(None)):
                db.add(
                    StatusTransition(
                        from_status_id=row.id,
                        to_status_id=row.next_stage_id,
                        transition_type=TransitionType.FORWARD,
                    )
                )
            for from_id, to_id in ((1, 12), (3, 18), (13, 28)):
                db.add(
                    StatusTransition(
                        from_status_id=from_id,
                        to_status_id=to_id,
                        transition_type=TransitionType.EXPRESS,
                    )
                )
            db.add(
                StatusTransition(
                    from_status_id=44,
                    to_status_id=45,
                    transition_type=TransitionType.RELAUNCH,
                )
            )
            db.flush()
            forwards = (
                db.query(StatusTransition)
                .filter(StatusTransition.transition_type == TransitionType.FORWARD)
                .all()
            )
            for row in forwards:
                db.add(
                    StatusTransition(
                        from_status_id=row.to_status_id,
                        to_status_id=row.from_status_id,
                        transition_type=TransitionType.BACKWARD,
                    )
                )
            db.commit()

        if db.query(Country).count() == 0:
            print("  Seeding countries...")
            for item in DEFAULT_COUNTRIES:
                db.add(Country(**item, is_active=True))
            db.commit()

        level_rows = [
            (1, "FOUNDATIONAL", "Foundational", "Secondary, Pre-university and foundational pathways."),
            (2, "UNDERGRAD", "Undergraduate", "Undergraduate and bachelor-level study."),
            (3, "GRADUATE", "Graduate", "Master's and post-bachelor graduate study."),
            (4, "DOCTORAL", "Doctoral", "Doctorate and research-intensive doctoral study."),
        ]
        if db.query(Level).count() == 0:
            print("  Seeding levels...")
            for level_id, code, name, description in level_rows:
                db.add(Level(id=level_id, code=code, name=name, description=description))
            db.flush()
            db.execute(
                text(
                    "SELECT setval(pg_get_serial_sequence('levels', 'id'), "
                    "(SELECT COALESCE(MAX(id), 1) FROM levels))"
                )
            )
            db.commit()

        campus_type_rows = [
            ("MAIN", "Main", "The primary, flagship location housing central administration."),
            ("SATELLITE", "Satellite", "A secondary location serving specific regions or demographics."),
            ("SPECIALIZED", "Specialized", "A location dedicated to a specific academic niche."),
            ("INTERNATIONAL", "International", "A branch campus located outside the home country."),
            ("VIRTUAL", "Virtual", "An online-only platform for digital course delivery."),
        ]
        if db.query(CampusType).count() == 0:
            print("  Seeding campus_types...")
            for code, name, description in campus_type_rows:
                db.add(CampusType(code=code, name=name, description=description))
            db.commit()

        if db.query(EducationDegree).count() == 0:
            print("  Seeding education_degrees...")
            for item in DEFAULT_EDUCATION_DEGREES:
                level_code = str(item.get("course_level") or "ENTRY").upper()
                level_id = LEVEL_CODE_TO_ID.get(level_code, 1)
                db.add(
                    EducationDegree(
                        level_id=level_id,
                        code=str(item["code"]),
                        label=str(item["label"]),
                        is_other=bool(item.get("is_other", False)),
                        is_active=True,
                        sort_order=int(item.get("sort_order") or 0),
                    )
                )
            db.commit()

        if db.query(GpaCgpaScore).count() == 0:
            print("  Seeding gpa_cgpa_scores...")
            for item in DEFAULT_GPA_CGPA_SCORES:
                db.add(
                    GpaCgpaScore(
                        code=str(item["code"]),
                        label=str(item["label"]),
                        is_other=bool(item.get("is_other", False)),
                        is_active=True,
                        sort_order=int(item.get("sort_order") or 0),
                    )
                )
            db.commit()
    finally:
        db.close()

    _seed_staging_login_users()


def _seed_staging_login_users() -> None:
    """Ensure at least one Super Admin exists for staging UI login."""
    import os

    cmd = [sys.executable, "scripts/seed_staging_users.py"]
    source = (os.getenv("STAGING_USERS_SOURCE_URL") or "").strip()
    if source:
        cmd.extend(["--copy-from", source])
        if (os.getenv("STAGING_ADMIN_PASSWORD") or "").strip():
            cmd.append("--force-admin")
    else:
        if not (os.getenv("STAGING_ADMIN_PASSWORD") or "").strip():
            os.environ["STAGING_ADMIN_PASSWORD"] = "StagingAdmin!ChangeMe"
            print(
                "  Seeding 3 Super Admins (ishq@ / arunpk@ / admin@ edutrust.in) "
                "with StagingAdmin!ChangeMe — change after login."
            )
    print("  Ensuring staging login users...")
    subprocess.run(cmd, cwd=BACKEND_ROOT, check=False)


def _bootstrap_fresh_database(engine) -> None:
    """
    Nexus Alembic history starts with ALTER-only revisions (schema originally came
    from SQLAlchemy create_all). Empty Neon DBs (e.g. Nexus-Dev-1) must not run
    `alembic upgrade head` from revision 0.
    """
    print(
        "Fresh database detected — creating schema from ORM models, "
        "then stamping Alembic head (early migrations ALTER existing tables)."
    )
    from app.db.database import Base, sync_schema_columns
    from app.db.register_models import register_all_models

    register_all_models()
    Base.metadata.create_all(bind=engine)
    # sync_schema_columns uses the app-global engine (same DATABASE_URL).
    sync_schema_columns()
    _run_alembic("stamp", "head")
    _seed_fresh_reference_data(engine)


def _stamp_if_behind_schema(inspector: Inspector, current: str | None) -> str | None:
    """Stamp forward when create_all() already applied tables/columns."""
    # Already past the legacy stamp chain (e.g. c4d7… / f7y0…) — do not compare
    # against ORDERED_REVISIONS; alembic upgrade head owns the rest.
    if current and _revision_index(current) is None:
        print(
            f"Alembic at {current} (beyond legacy stamp chain ending "
            f"{ORDERED_REVISIONS[-1]}); skipping schema-detection stamp."
        )
        return current

    detected = _detect_sequential_schema_revision(inspector)
    if not detected:
        return current

    detected_idx = _revision_index(detected)
    current_idx = _revision_index(current) if current else None
    if detected_idx is None:
        return current
    if current_idx is None or detected_idx > current_idx:
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
        # Outside legacy chain → nothing more to stamp via schema probes.
        if _revision_index(current) is None:
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
    current = _current_alembic_revision()

    # Post-legacy revisions: one upgrade is enough; no stamp-loop needed.
    if current and _revision_index(current) is None and current != HEAD_REVISION:
        print(f"Upgrading from {current} to head via Alembic…")
        _run_alembic("upgrade", "head")
        final = _current_alembic_revision()
        if final != HEAD_REVISION:
            raise RuntimeError(
                f"Expected Alembic head {HEAD_REVISION}, got {final or 'empty'}"
            )
        return

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
    global HEAD_REVISION
    HEAD_REVISION = _alembic_head_revision()
    print(f"Alembic head target: {HEAD_REVISION}")

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
        _bootstrap_fresh_database(engine)
    elif _database_looks_orm_provisioned(inspector):
        print(
            "ORM-provisioned schema without alembic_version — "
            "stamping head and ensuring reference seeds."
        )
        _run_alembic("stamp", "head")
        _seed_fresh_reference_data(engine)
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
    if final and final != HEAD_REVISION:
        # Later academia migrations may exist beyond the legacy ORDERED_REVISIONS stamp chain.
        print(f"Running final alembic upgrade head (target {HEAD_REVISION})...")
        _run_alembic("upgrade", "head")
        final = _current_alembic_revision()
        print(f"Done. Alembic revision is now: {final or 'unknown'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: alembic command failed with exit code {exc.returncode}", file=sys.stderr)
        raise SystemExit(exc.returncode) from exc
