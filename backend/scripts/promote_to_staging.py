#!/usr/bin/env python3
"""
Promote NEXUS develop -> staging (GitHub + local NEXUS-staging worktree).

Typical workflow (run from repo root or anywhere):

    python backend/scripts/promote_to_staging.py --message "Release notes here"
    python backend/scripts/promote_to_staging.py --message "Hotfix" --vps root@187.127.186.63
    python backend/scripts/promote_to_staging.py --dry-run

What it does:
  1. Scans Alembic migrations (new since origin/staging) and refreshes deploy docs
  2. Commits uncommitted changes on develop (if any)
  3. Pushes develop to GitHub
  4. Fast-forwards/merges develop into the staging worktree (E:\\NEXUS-staging)
  5. Pushes staging to GitHub
  6. Optionally SSH to Hostinger and runs deploy.sh (includes alembic upgrade head)

Secrets (.env) are never copied — verify server .env separately.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_DEVELOP_BRANCH = "develop"
DEFAULT_STAGING_BRANCH = "staging"
DEFAULT_STAGING_ROOT = Path(r"E:\NEXUS-staging")
MIGRATIONS_DIR = Path("backend/alembic/versions")
MIGRATIONS_DOC = Path("backend/deploy/STAGING_DATABASE_MIGRATIONS.md")
RELEASE_NOTES_DIR = Path("backend/deploy/releases")


@dataclass
class MigrationChange:
    kind: str  # "table", "column", "index", "data", "other"
    detail: str


@dataclass
class MigrationInfo:
    revision: str
    slug: str
    title: str
    down_revision: str | None
    changes: list[MigrationChange] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if not self.changes:
            return self.title
        parts: list[str] = []
        tables = [c.detail for c in self.changes if c.kind == "table"]
        columns = [c.detail for c in self.changes if c.kind == "column"]
        if tables:
            parts.append("New table(s): " + ", ".join(f"`{t}`" for t in tables))
        if columns:
            parts.append("Alter: " + "; ".join(columns))
        others = [c.detail for c in self.changes if c.kind not in {"table", "column"}]
        parts.extend(others)
        return "; ".join(parts) if parts else self.title


class PromoteError(RuntimeError):
    pass


def _run(
    args: list[str],
    *,
    cwd: Path,
    dry_run: bool = False,
    check: bool = True,
    label: str | None = None,
) -> subprocess.CompletedProcess[str]:
    display = label or " ".join(args)
    print(f"  {display}")
    if dry_run:
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
    result = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise PromoteError(f"Command failed ({result.returncode}): {display}\n{detail}")
    return result


def git(cwd: Path, *git_args: str, dry_run: bool = False, check: bool = True) -> str:
    result = _run(
        ["git", *git_args],
        cwd=cwd,
        dry_run=dry_run,
        check=check,
        label=f"git {' '.join(git_args)}",
    )
    return (result.stdout or "").strip()


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[2]


def detect_staging_root(develop_root: Path, explicit: Path | None) -> Path:
    if explicit and explicit.exists():
        return explicit.resolve()
    if DEFAULT_STAGING_ROOT.exists():
        return DEFAULT_STAGING_ROOT.resolve()
    listing = git(develop_root, "worktree", "list", "--porcelain", check=False)
    for line in listing.splitlines():
        if line.startswith("worktree "):
            path = Path(line.split(" ", 1)[1].strip())
        elif line.strip() == f"branch refs/heads/{DEFAULT_STAGING_BRANCH}":
            return path.resolve()
    raise PromoteError(
        f"Staging worktree not found. Create it once:\n"
        f"  cd {develop_root}\n"
        f"  .\\setup-instances.ps1\n"
        f"Or pass --staging-root E:\\NEXUS-staging"
    )


def parse_migration_file(path: Path) -> MigrationInfo | None:
    text = path.read_text(encoding="utf-8")
    rev_match = re.search(r'^revision:\s*str\s*=\s*["\']([^"\']+)["\']', text, re.M)
    down_match = re.search(r'^down_revision:.*=\s*(.+)$', text, re.M)
    if not rev_match:
        return None

    revision = rev_match.group(1)
    down_revision: str | None = None
    if down_match:
        raw = down_match.group(1).strip()
        if raw not in {"None", "null"}:
            m = re.search(r'["\']([^"\']+)["\']', raw)
            down_revision = m.group(1) if m else None

    doc = re.match(r'^"""([^"]*)', text, re.S)
    title = (doc.group(1).strip().splitlines()[0] if doc else path.stem).strip()

    upgrade_match = re.search(r"def upgrade\(\)[^:]*:\s*(.*?)(?=\ndef downgrade|\Z)", text, re.S)
    upgrade_body = upgrade_match.group(1) if upgrade_match else ""

    changes: list[MigrationChange] = []
    for table in re.findall(r'create_table\(\s*["\']([^"\']+)["\']', upgrade_body):
        changes.append(MigrationChange("table", table))
    for match in re.finditer(
        r'add_column\(\s*["\']([^"\']+)["\']\s*,\s*sa\.Column\(\s*["\']([^"\']+)["\']',
        upgrade_body,
    ):
        changes.append(MigrationChange("column", f"`{match.group(1)}.{match.group(2)}`"))
    for match in re.finditer(r'drop_column\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']', upgrade_body):
        changes.append(MigrationChange("column", f"drop `{match.group(1)}.{match.group(2)}`"))
    if "op.execute(" in upgrade_body and not changes:
        changes.append(MigrationChange("data", "SQL data migration"))
    if not changes and "drop_table(" in upgrade_body:
        for table in re.findall(r'drop_table\(\s*["\']([^"\']+)["\']', upgrade_body):
            changes.append(MigrationChange("other", f"drop table `{table}`"))

    return MigrationInfo(
        revision=revision,
        slug=path.stem,
        title=title,
        down_revision=down_revision,
        changes=changes,
    )


def load_all_migrations(develop_root: Path) -> dict[str, MigrationInfo]:
    versions_dir = develop_root / MIGRATIONS_DIR
    migrations: dict[str, MigrationInfo] = {}
    for path in sorted(versions_dir.glob("*.py")):
        info = parse_migration_file(path)
        if info:
            migrations[info.revision] = info
    return migrations


def find_head(migrations: dict[str, MigrationInfo]) -> str:
    all_revs = set(migrations.keys())
    pointed = {m.down_revision for m in migrations.values() if m.down_revision}
    heads = all_revs - pointed
    if len(heads) != 1:
        raise PromoteError(f"Expected one Alembic head, found: {sorted(heads)}")
    return next(iter(heads))


def chain_to_head(migrations: dict[str, MigrationInfo], head: str) -> list[MigrationInfo]:
    ordered: list[MigrationInfo] = []
    current: str | None = head
    seen: set[str] = set()
    while current:
        if current in seen:
            raise PromoteError(f"Migration cycle detected at {current}")
        seen.add(current)
        info = migrations.get(current)
        if not info:
            break
        ordered.append(info)
        current = info.down_revision
    ordered.reverse()
    return ordered


def migrations_since_revision(
    migrations: dict[str, MigrationInfo],
    head: str,
    since_revision: str | None,
) -> list[MigrationInfo]:
    chain = chain_to_head(migrations, head)
    if not since_revision:
        return chain
    try:
        idx = next(i for i, m in enumerate(chain) if m.revision == since_revision)
        return chain[idx + 1 :]
    except StopIteration:
        return []


def staging_db_revision_on_remote(develop_root: Path, staging_branch: str, dry_run: bool) -> str | None:
    del dry_run
    try:
        git(develop_root, "fetch", "origin", staging_branch)
    except PromoteError:
        return None

    # List migration files on remote staging tip
    files = git(
        develop_root,
        "ls-tree",
        "-r",
        "--name-only",
        f"origin/{staging_branch}",
        "backend/alembic/versions",
        check=False,
    )
    if not files:
        return None
    remote_migrations: dict[str, MigrationInfo] = {}
    for rel in files.splitlines():
        if not rel.endswith(".py"):
            continue
        content = git(
            develop_root,
            "show",
            f"origin/{staging_branch}:{rel}",
            check=False,
        )
        if not content:
            continue
        tmp = develop_root / ".promote_tmp_migration.py"
        try:
            tmp.write_text(content, encoding="utf-8")
            info = parse_migration_file(tmp)
            if info:
                remote_migrations[info.revision] = info
        finally:
            if tmp.exists():
                tmp.unlink()
    if not remote_migrations:
        return None
    return find_head(remote_migrations)


def new_migration_files_since_staging(
    develop_root: Path,
    staging_branch: str,
    dry_run: bool,
) -> list[str]:
    del dry_run  # fetch/diff are read-only
    git(develop_root, "fetch", "origin", staging_branch)
    diff = git(
        develop_root,
        "diff",
        "--name-only",
        f"origin/{staging_branch}..HEAD",
        "--",
        "backend/alembic/versions",
        check=False,
    )
    return [line for line in diff.splitlines() if line.endswith(".py")]


def render_migrations_doc(
    *,
    head: str,
    full_chain: list[MigrationInfo],
    release_migrations: list[MigrationInfo],
    generated_at: str,
) -> str:
    lines = [
        "# Staging database migrations (Alembic)",
        "",
        "Auto-maintained by `backend/scripts/promote_to_staging.py`.",
        "",
        "Hostinger `deploy.sh` runs `alembic upgrade head` on every deploy.",
        "",
        f"**Current head:** `{head}`",
        f"**Doc generated:** {generated_at}",
        "",
    ]

    if release_migrations:
        lines.extend(
            [
                "## Migrations in this release",
                "",
                "| Revision | Migration | Changes |",
                "|----------|-----------|---------|",
            ]
        )
        for m in release_migrations:
            lines.append(f"| `{m.revision}` | {m.slug} | {m.summary} |")
        lines.append("")

    lines.extend(
        [
            "## Full migration chain (at head)",
            "",
            "| Revision | Migration | Changes |",
            "|----------|-----------|---------|",
        ]
    )
    for m in full_chain:
        lines.append(f"| `{m.revision}` | {m.slug} | {m.summary} |")

    lines.extend(
        [
            "",
            "## Manual run (VPS or local)",
            "",
            "```bash",
            "cd /var/www/nexus/backend",
            "source .venv/bin/activate",
            "alembic current",
            "alembic upgrade head",
            "```",
            "",
            "## Verify after deploy",
            "",
            "```bash",
            "alembic current",
            f"# Expected: {head} (head)",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def write_release_notes(
    develop_root: Path,
    *,
    message: str,
    head: str,
    release_migrations: list[MigrationInfo],
    dry_run: bool,
) -> Path | None:
    if not release_migrations:
        return None
    RELEASE_NOTES_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = develop_root / RELEASE_NOTES_DIR / f"{stamp}_migrations.md"
    lines = [
        f"# Release migrations — {stamp}",
        "",
        f"**Promote message:** {message}",
        f"**Alembic head:** `{head}`",
        "",
        "| Revision | File | Summary |",
        "|----------|------|---------|",
    ]
    for m in release_migrations:
        lines.append(f"| `{m.revision}` | {m.slug} | {m.summary} |")
    lines.append("")
    if not dry_run:
        path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n  Release notes: {path.relative_to(develop_root)}")
    return path


def print_migration_summary(release_migrations: list[MigrationInfo], head: str) -> None:
    print("\n=== Database migrations ===")
    if not release_migrations:
        print("  No new Alembic migration files since origin/staging.")
        print(f"  Current head (local): {head}")
        return
    print(f"  {len(release_migrations)} new migration(s) will run on deploy (alembic upgrade head):\n")
    for m in release_migrations:
        print(f"  • {m.revision}  {m.title}")
        print(f"    {m.summary}")
    print(f"\n  Target head: {head}")


def ensure_clean_staging(staging_root: Path, staging_branch: str) -> None:
    branch = git(staging_root, "branch", "--show-current")
    if branch != staging_branch:
        raise PromoteError(f"{staging_root} is on '{branch}', expected '{staging_branch}'")
    status = git(staging_root, "status", "--porcelain")
    if status:
        print(status)
        raise PromoteError(
            f"Staging worktree has uncommitted changes in {staging_root}. "
            "Commit or stash before promoting."
        )


def commit_if_dirty(root: Path, branch: str, message: str, dry_run: bool) -> bool:
    current = git(root, "branch", "--show-current")
    if current != branch:
        print(f"  WARNING: {root} is on '{current}', expected '{branch}'.")
    status = git(root, "status", "--porcelain")
    if not status:
        print(f"  No uncommitted changes on {branch}.")
        return False
    print(f"  Committing changes on {branch}...")
    git(root, "add", "-A", dry_run=dry_run)
    git(root, "commit", "-m", message, dry_run=dry_run)
    return True


def build_commit_message(base_message: str, release_migrations: list[MigrationInfo], head: str) -> str:
    if not release_migrations:
        return base_message
    lines = [base_message, "", "Database (Alembic):"]
    for m in release_migrations:
        lines.append(f"- {m.revision}: {m.summary}")
    lines.append(f"Alembic head: {head}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Promote NEXUS develop to staging (GitHub + NEXUS-staging worktree + migration docs)."
    )
    parser.add_argument(
        "-m",
        "--message",
        default="Promote develop to staging",
        help="Git commit / merge message",
    )
    parser.add_argument(
        "--develop-root",
        type=Path,
        default=None,
        help="Develop repo root (default: auto-detect from script location)",
    )
    parser.add_argument(
        "--staging-root",
        type=Path,
        default=None,
        help=f"Staging worktree (default: {DEFAULT_STAGING_ROOT} or git worktree list)",
    )
    parser.add_argument("--develop-branch", default=DEFAULT_DEVELOP_BRANCH)
    parser.add_argument("--staging-branch", default=DEFAULT_STAGING_BRANCH)
    parser.add_argument(
        "--vps",
        default="",
        help="SSH target for Hostinger deploy, e.g. root@187.127.186.63",
    )
    parser.add_argument("--skip-develop-push", action="store_true")
    parser.add_argument("--skip-deploy", action="store_true")
    parser.add_argument("--skip-migration-doc", action="store_true", help="Do not refresh STAGING_DATABASE_MIGRATIONS.md")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    develop_root = (args.develop_root or repo_root_from_script()).resolve()
    if not (develop_root / ".git").exists():
        raise PromoteError(f"Not a git repository: {develop_root}")

    staging_root = detect_staging_root(develop_root, args.staging_root)
    dry_run = args.dry_run

    print("=== NEXUS promote to staging ===")
    print(f"  Develop:  {develop_root} [{args.develop_branch}]")
    print(f"  Staging:  {staging_root} [{args.staging_branch}]")
    if dry_run:
        print("  DRY RUN — no writes, commits, or pushes")

    if "origin" not in git(develop_root, "remote"):
        raise PromoteError("No 'origin' remote. Add GitHub: git remote add origin https://github.com/nexus-ET/nexus.git")

    # --- Migrations analysis ---------------------------------------------------
    migrations = load_all_migrations(develop_root)
    head = find_head(migrations)
    full_chain = chain_to_head(migrations, head)

    new_files = new_migration_files_since_staging(develop_root, args.staging_branch, dry_run)
    remote_head = staging_db_revision_on_remote(develop_root, args.staging_branch, dry_run)

    # Prefer explicit new/changed migration files in this promote (develop vs origin/staging)
    if new_files:
        release_revs: list[str] = []
        for rel in new_files:
            info = parse_migration_file(develop_root / rel)
            if info:
                release_revs.append(info.revision)
        release_migrations = [m for m in full_chain if m.revision in release_revs]
    else:
        release_migrations = (
            migrations_since_revision(migrations, head, remote_head) if remote_head else []
        )

    print_migration_summary(release_migrations, head)

    if not args.skip_migration_doc:
        doc_path = develop_root / MIGRATIONS_DOC
        doc_content = render_migrations_doc(
            head=head,
            full_chain=full_chain,
            release_migrations=release_migrations,
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        )
        if not dry_run:
            doc_path.parent.mkdir(parents=True, exist_ok=True)
            doc_path.write_text(doc_content, encoding="utf-8")
        print(f"\n  Updated {MIGRATIONS_DOC.as_posix()}")

    write_release_notes(
        develop_root,
        message=args.message,
        head=head,
        release_migrations=release_migrations,
        dry_run=dry_run,
    )

    commit_message = build_commit_message(args.message, release_migrations, head)

    # --- Develop: commit + push ----------------------------------------------
    print("\n=== Step 1: develop ===")
    commit_if_dirty(develop_root, args.develop_branch, commit_message, dry_run)

    if not args.skip_develop_push:
        print(f"  Pushing {args.develop_branch} to origin...")
        git(develop_root, "push", "origin", args.develop_branch, dry_run=dry_run)
    else:
        print("  Skipping develop push (--skip-develop-push)")

    # --- Staging worktree: merge + push --------------------------------------
    print("\n=== Step 2: staging worktree ===")
    if not dry_run:
        ensure_clean_staging(staging_root, args.staging_branch)

    print("  Fetching origin...")
    git(staging_root, "fetch", "origin", args.develop_branch, args.staging_branch, dry_run=dry_run)

    print(f"  Merging origin/{args.develop_branch} into {args.staging_branch}...")
    try:
        git(
            staging_root,
            "merge",
            f"origin/{args.develop_branch}",
            "-m",
            commit_message,
            dry_run=dry_run,
        )
    except PromoteError as exc:
        print("\n  Merge failed. Resolve conflicts in staging worktree, then:")
        print(f"    cd {staging_root}")
        print("    git merge --continue")
        print(f"    git push origin {args.staging_branch}")
        raise exc

    print(f"  Pushing {args.staging_branch} to origin...")
    git(staging_root, "push", "origin", args.staging_branch, dry_run=dry_run)

    # --- Optional VPS deploy -------------------------------------------------
    if args.vps and not args.skip_deploy:
        print(f"\n=== Step 3: Hostinger deploy ({args.vps}) ===")
        deploy_cmd = "sudo bash /var/www/nexus/backend/deploy/deploy.sh"
        _run(["ssh", args.vps, deploy_cmd], cwd=develop_root, dry_run=dry_run)
    elif not args.skip_deploy:
        print("\n=== Step 3: Hostinger deploy ===")
        print("  Skipped (pass --vps root@YOUR_IP to deploy automatically)")
        print("  Manual: ssh root@YOUR_VPS_IP \"sudo bash /var/www/nexus/backend/deploy/deploy.sh\"")

    print("\n=== Done ===")
    print(f"  GitHub: origin/{args.staging_branch} updated from {args.develop_branch}")
    print(f"  Local:  {staging_root} is in sync")
    if release_migrations:
        print(f"  Database: run alembic upgrade head on server ({len(release_migrations)} new migration(s))")
    print("  Note: .env files are not in git — verify server secrets separately.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PromoteError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
