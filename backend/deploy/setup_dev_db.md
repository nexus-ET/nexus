# Development database setup — Hostinger KVM 1 (`nexus_dev`)

One-time schema bootstrap when moving **local development** (`E:\NEXUS`, branch `develop`) off Neon **still-paper** onto a dedicated Hostinger PostgreSQL database — same pattern as staging’s move to `nexus_edutrust`.

| Item | Placeholder (you provide) |
|------|---------------------------|
| Database | **`nexus_dev`** (or your chosen name) |
| User | **`nexus_dev_admin`** (full privileges on that DB) |
| Host | Hostinger hPanel DB host, or `127.0.0.1` if Postgres is on the same VPS |
| Port | `5432` (default) |
| App path (local) | `E:\NEXUS\backend` |
| Alembic head (develop, 2026-08-28) | **`yy5z6asupermaj`** |
| Expected public table count | **110** (`information_schema.tables` where `table_schema = 'public'`) |

**Scope:** schema migration (tables, indexes, Alembic/bootstrap seeds). **Optional:** copy data from legacy Neon still-paper (see §6).

**Do not commit** passwords, real hostnames, or `backend/.env` into git. Use [`.env.development.example`](../.env.development.example) as the template.

---

## Current vs target development database

| | **Current (legacy)** | **Target (new dev)** |
|---|----------------------|----------------------|
| Provider | Neon — project **still-paper** | Hostinger KVM 1 PostgreSQL (or your chosen Postgres host) |
| Host pattern | `ep-still-paper-…-pooler.….aws.neon.tech` | `YOUR_DB_HOST` (hPanel / VPS IP / `127.0.0.1`) |
| Database | `neondb` | **`nexus_dev`** (placeholder) |
| User | `neondb_owner` | **`nexus_dev_admin`** (placeholder) |
| URL extras | `?sslmode=require` (+ Neon may add `channel_binding=require`; app strips it) | Usually none for local/co-located Postgres; add `?sslmode=require` only if remote TLS |
| Staging sibling | — | Staging uses **`nexus_edutrust`** / **`nexus_et_admin`** — do not reuse |

Staging setup (for comparison): [setup_staging_db.md](./setup_staging_db.md).

---

## What you need to provide

Before editing `.env`, create the database in hPanel (or on the VPS) and note:

1. **Database name** — e.g. `nexus_dev`
2. **DB user** — e.g. `nexus_dev_admin` with password
3. **Host** — hPanel “Host” or VPS IP (not the Neon pooler hostname)
4. **Port** — usually `5432`
5. **Password** — URL-encode special characters (`@`, `:`, `/`, `#`, etc.) in `DATABASE_URL`

---

## `DATABASE_URL` format (development)

Preferred scheme (matches `normalize_database_url()` in `app/config.py`):

```env
DATABASE_URL=postgresql+psycopg://nexus_dev_admin:YOUR_PASSWORD@YOUR_DB_HOST:5432/nexus_dev
```

Co-located Postgres on the same machine as the app:

```env
DATABASE_URL=postgresql+psycopg://nexus_dev_admin:YOUR_PASSWORD@127.0.0.1:5432/nexus_dev
```

Remote Hostinger Postgres with TLS:

```env
DATABASE_URL=postgresql+psycopg://nexus_dev_admin:YOUR_PASSWORD@YOUR_DB_HOST:5432/nexus_dev?sslmode=require
```

**Do not use for new dev:**

- Neon still-paper (`ep-still-paper-…` / `still-paper`) — legacy develop only until you switch
- Old Neon staging URLs (`Nexus-Dev-1`, `sparkling-violet`, `ep-broad-breeze-…`)
- Staging database **`nexus_edutrust`** (keep develop and staging separate)

Bare `postgresql://` URLs work; Settings normalizes them to `postgresql+psycopg://`.

---

## 1. Create database and user (hPanel or VPS)

On the Postgres server (example — adjust names/passwords):

```bash
sudo -u postgres psql
```

```sql
CREATE USER nexus_dev_admin WITH PASSWORD 'CHOOSE_A_STRONG_PASSWORD';
CREATE DATABASE nexus_dev OWNER nexus_dev_admin;
GRANT ALL PRIVILEGES ON DATABASE nexus_dev TO nexus_dev_admin;
\c nexus_dev
GRANT ALL ON SCHEMA public TO nexus_dev_admin;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO nexus_dev_admin;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO nexus_dev_admin;
\q
```

Connectivity smoke test:

```bash
psql "postgresql://nexus_dev_admin:YOUR_PASSWORD@YOUR_DB_HOST:5432/nexus_dev" -c "SELECT 1"
```

---

## 2. Update local `backend/.env` (manual — not committed)

Edit **only** on your PC:

```powershell
notepad E:\NEXUS\backend\.env
```

Set (fill password and host):

```env
DATABASE_URL=postgresql+psycopg://nexus_dev_admin:YOUR_PASSWORD@YOUR_DB_HOST:5432/nexus_dev
```

Keep develop identity keys unchanged:

```env
NEXUS_INSTANCE=development
ENVIRONMENT=development
NEXUS_PORT=8002
NEXUS_FRONTEND_PORT=5175
```

**Optional — keep legacy Neon URL for one-time data copy** (do not point `DATABASE_URL` at both):

```env
# LEGACY_DEV_SOURCE_URL=postgresql+psycopg://neondb_owner:...@ep-still-paper-...-pooler.../neondb?sslmode=require
```

See [`.env.dev-source.example`](../.env.dev-source.example).

Copy other keys from [`.env.development.example`](../.env.development.example) if you are bootstrapping a fresh `.env`.

---

## 3. Run migrations (schema only)

PowerShell from develop tree:

```powershell
cd E:\NEXUS\backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -q
pip install "psycopg[binary]" -q
```

### Recommended — fresh empty database

`bootstrap_alembic.py` detects an empty DB, runs `create_all` + column sync, stamps Alembic head, and seeds reference catalogs:

```powershell
python scripts\verify_staging_database.py --env dev --migrate
# equivalent:
python scripts\bootstrap_alembic.py
```

### Alternative — plain Alembic (only if DB already has legacy schema + `alembic_version`)

```powershell
python -m alembic upgrade head
```

Expected after success:

```powershell
python -m alembic current
# yy5z6asupermaj (head)

python -m alembic heads
# yy5z6asupermaj (head)   ← exactly one head
```

Post-migration seeds (run manually on first setup if needed):

```powershell
python scripts\ensure_navigation_rbac.py
python scripts\ensure_id_sequences.py
python scripts\seed_staging_users.py
```

(`seed_staging_users.py` works on any Postgres target; it reads `DATABASE_URL` from `.env`.)

Restart local backend if it is running:

```powershell
# however you usually start uvicorn / run-nexus-backend
```

---

## 4. Verify table count and Alembic head

```powershell
cd E:\NEXUS\backend
python scripts\verify_staging_database.py --env dev
```

Expect:

- `Connected OK`
- `Public tables: 110` (±1–2 worth investigating)
- `Alembic current: yy5z6asupermaj (head)`
- No warning about legacy Neon still-paper

SQL cross-check:

```powershell
# Requires psql and DATABASE_URL in environment, or paste connection string locally
psql "postgresql://nexus_dev_admin:YOUR_PASSWORD@YOUR_DB_HOST:5432/nexus_dev" -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';"
psql "postgresql://nexus_dev_admin:YOUR_PASSWORD@YOUR_DB_HOST:5432/nexus_dev" -c "SELECT version_num FROM alembic_version;"
```

Compare staging (same script, staging `.env` or `--env staging`):

```powershell
python scripts\verify_staging_database.py --env staging
```

---

## 5. Alembic health (before switching develop)

```powershell
cd E:\NEXUS\backend
python -m alembic heads      # must show exactly ONE head
python -m alembic branches   # branchpoints OK if they merge to single head
```

Current single head: **`yy5z6asupermaj`**.

Config notes:

- `alembic.ini` — placeholder `sqlalchemy.url`; real URL comes from `backend/.env` via `alembic/env.py` → `settings.DATABASE_URL`
- `app/db/database.py` — uses `normalize_database_url(settings.DATABASE_URL)`; pool recycle 300s for Postgres (Neon idle timeout pattern; fine on Hostinger too)

---

## 6. Optional — copy data from legacy Neon still-paper

Not required for schema parity. Use when you want academia catalogs, institutions, or demo students on the new dev DB.

| Goal | Script | Source | Target |
|------|--------|--------|--------|
| Academia / geography / LMPC / institutions | `copy_academia_to_staging.py` | `--source` = still-paper Neon URL | `--target` = new dev `DATABASE_URL` |
| Demo student (lead 27) | `copy_student_to_staging.py --lead-id 27` | default: local `.env` if still on Neon, or `--source` | `--target` = new dev URL |
| Super Admins / nav RBAC | `seed_staging_users.py` | — | new dev via updated `.env` |

**Workflow:** temporarily set `LEGACY_DEV_SOURCE_URL` (or pass `--source`) to still-paper; set `DATABASE_URL` to the **new** dev Hostinger DB; run copy scripts with `--target` matching new dev.

Example (academia — both URLs explicit):

```powershell
cd E:\NEXUS\backend
python scripts\copy_academia_to_staging.py `
  --source "postgresql+psycopg://neondb_owner:...@ep-still-paper-...-pooler.../neondb?sslmode=require" `
  --target "postgresql+psycopg://nexus_dev_admin:...@YOUR_DB_HOST:5432/nexus_dev"
```

Example (student lead 27):

```powershell
python scripts\copy_student_to_staging.py --lead-id 27 `
  --source "postgresql+psycopg://...@ep-still-paper-.../neondb?sslmode=require" `
  --target "postgresql+psycopg://nexus_dev_admin:...@YOUR_DB_HOST:5432/nexus_dev"
```

R2/upload binaries are **not** copied by these scripts.

---

## Hardcoded legacy Neon / still-paper references

These mention still-paper or old Neon hosts in **docs or report metadata** — update after you decommission Neon develop:

| Location | Notes |
|----------|--------|
| `backend/.env` | **Your machine only** — currently still-paper; update manually (never commit) |
| `backend/.env.development.example` | Template; should use Hostinger placeholders (not Neon) |
| `backend/deploy/setup_staging_db.md` | Dev row — points here for new dev DB |
| `backend/deploy/env.staging.example` | `STAGING_USERS_SOURCE_URL` example still-paper (optional copy source) |
| `backend/deploy/STAGING_ENV_CHANGES.md` | Historical Neon vs Hostinger comparison |
| `backend/scripts/_audit_nz_submajor_mappings.py` | Report JSON `"database": "still-paper (direct, non-pooler)"` |
| `backend/scripts/_audit_au_submajor_mappings.py` | Same hardcoded label |
| `backend/scripts/copy_academia_to_staging.py` | Docstring examples use old Neon hostnames |
| `backend/scripts/copy_student_to_staging.py` | Docstring mentions Nexus-Dev-1 |
| `backend/scripts/bootstrap_alembic.py` | Comments reference Neon / Nexus-Dev-1 empty DB path |

No application code **requires** still-paper; only `DATABASE_URL` in `.env` binds develop to a host.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Script prints `DATABASE_URL` + `Environment: dev` then **hangs** (no `Connected OK`) | **Port 5432 is blocked from your PC.** Hostinger Postgres is not exposed to the public internet. See **§7 — PC cannot reach Postgres** below. |
| App feels 2–3× slower than Neon after switching to Hostinger via SSH tunnel | **Expected.** Tunnel doubles RTT (~460 ms `SELECT 1` vs ~165 ms Neon). Prefer backend-on-VPS or firewall home-IP. Run `ANALYZE;` after restore. See Option B performance notes. |
| `connection refused` | Confirm hPanel host/port; on VPS use `127.0.0.1:5432`, not the public VPS IP |
| `password authentication failed` | Reset DB user password; URL-encode `@` as `%40` in `.env` (e.g. `Nexus@ET@2026@Dev` → `Nexus%40ET%402026%40Dev`) |
| `verify_staging_database.py` warns “legacy Neon still-paper” | Update `DATABASE_URL` to Hostinger dev URL |
| Duplicate column/table during migrate | Fresh DB → use `bootstrap_alembic.py`, not raw `upgrade head` from revision 0 on empty DB |
| Table count << 110 | Re-run `bootstrap_alembic.py`; check logs for failed `create_all` |
| Empty login after fresh schema | Run `seed_staging_users.py`; set `STAGING_ADMIN_PASSWORD` in `.env` if needed |

---

## 7. PC cannot reach Postgres (hang / timeout on `187.127.186.63:5432`)

`verify_staging_database.py` prints `DATABASE_URL` and `Environment`, then calls SQLAlchemy `engine.connect()`. If TCP to port **5432** is blocked, the script **appears frozen** — there is no timeout in the script itself.

Quick test from PowerShell:

```powershell
python -c "import socket; socket.create_connection(('187.127.186.63',5432), timeout=8)"
```

`TimeoutError` = firewall/network block (expected from a home/office PC).

### Option A — Run migrations on the VPS (recommended)

On the VPS, `.env` must use **`127.0.0.1:5432`** (Postgres on the same machine), not the public IP:

```env
DATABASE_URL=postgresql+psycopg://nexus_dev_et_admin:YOUR_URL_ENCODED_PASSWORD@127.0.0.1:5432/nexus_edutrust_dev
```

SSH in and run:

```bash
sudo bash /var/www/nexus/backend/deploy/migrate_on_vps.sh --env dev
```

Or manually:

```bash
cd /var/www/nexus/backend
source .venv/bin/activate
python scripts/verify_staging_database.py --env dev --migrate
```

### Option B — SSH tunnel from Windows (local app + migrate from PC)

Keep Postgres closed to the internet; tunnel through SSH:

```powershell
# Terminal 1 — leave running (any free local port; 5433 or 15432 are common)
ssh -N -L 15432:127.0.0.1:5432 root@187.127.186.63
```

Point local `backend/.env` at the tunnel:

```env
DATABASE_URL=postgresql+psycopg://nexus_dev_et_admin:YOUR_URL_ENCODED_PASSWORD@127.0.0.1:15432/nexus_edutrust_dev
```

Then in Terminal 2:

```powershell
cd E:\NEXUS\backend
python scripts\verify_staging_database.py --env dev --migrate
```

**Expected slowness:** every SQL round-trip is doubled (PC → SSH → Postgres → SSH → PC). Measured from a home PC (UTC+9) after the Neon→Hostinger restore:

| Path | `SELECT 1` median | Server exec time |
|------|-------------------|------------------|
| Hostinger via SSH tunnel (`127.0.0.1:15432`) | ~460 ms | ~0.01 ms |
| Neon pooler (still-paper, us-east-2) | ~165 ms | (network-bound) |

So the app feels 2–3× slower than Neon even when indexes and stats are fine. Framework Summary / institution hierarchy are already batched (not N+1), but each page still issues **many** queries — at ~460 ms RTT that adds up to multi-second pages.

**After every `pg_restore`**, refresh planner stats (safe, no data change):

```powershell
psql "postgresql://USER:PASS@127.0.0.1:15432/nexus_edutrust_dev" -c "ANALYZE;"
```

**Reduce tunnel handshake overhead** (does not cut per-query RTT, but reconnects / new SSH sessions are faster) — OpenSSH `ControlMaster` in `~/.ssh/config`:

```
Host hostinger-nexus
  HostName 187.127.186.63
  User root
  ControlMaster auto
  ControlPath ~/.ssh/cm-%r@%h:%p
  ControlPersist 10m

# Then:
# ssh -N -L 15432:127.0.0.1:5432 hostinger-nexus
```

**Speed ranking (best → worst for local develop):**

1. **Run the backend on the VPS** next to Postgres (`DATABASE_URL=…@127.0.0.1:5432/…`) — DB RTT ~1 ms.
2. **Allow Postgres from your home IP only** (firewall + `pg_hba.conf`) — one RTT, no SSH double-hop; keep the allowlist tight.
3. **SSH tunnel** — secure default, but expect hundreds of ms per query.

SQLAlchemy (`app/db/database.py`) uses `pool_size=10`, `pool_pre_ping=True`. Pre-ping is one extra `SELECT 1` after idle; over a tunnel that costs another ~RTT. Optional: set `PG_STATEMENT_TIMEOUT_MS=60000` in `.env` so hung queries fail visibly instead of hanging forever (`statement_timeout` defaults to `0`).

### Option C — Open port 5432 to your home IP only

Preferable to a permanent tunnel for day-to-day local develop if you accept the security tradeoff: allow TCP 5432 from **your current public IP only** in Hostinger/hPanel firewall **and** configure `pg_hba.conf` / Postgres `listen_addresses`. Do not open 5432 to `0.0.0.0/0`. For production traffic, prefer Option A (backend on VPS).

### Correct `DATABASE_URL` format (local `.env`)

All three parts matter; the verify script’s redacted line omits port on purpose:

```env
DATABASE_URL=postgresql+psycopg://nexus_dev_et_admin:YOUR_URL_ENCODED_PASSWORD@127.0.0.1:15432/nexus_edutrust_dev
# Optional: fail hung queries after 60s (visible errors vs infinite hang over tunnel)
# PG_STATEMENT_TIMEOUT_MS=60000
```

- **Driver:** `postgresql+psycopg://` (Settings normalizes bare `postgresql://`)
- **Password:** URL-encode `@`, `:`, `/`, `#` — raw `@` breaks the URL parser
- **Port:** always include `:5432` (on VPS) or your local tunnel port (`:15432` / `:5433`)
- **Host:** `127.0.0.1` via tunnel or on VPS; public VPS IP only works if firewall allows 5432

---

## Related docs

- [`.env.development.example`](../.env.development.example) — develop `.env` template (placeholders)
- [`.env.dev-source.example`](../.env.dev-source.example) — optional legacy Neon source for copy scripts
- [setup_staging_db.md](./setup_staging_db.md) — staging Hostinger bootstrap (`nexus_edutrust`)
- [README.md](./README.md) — deploy overview
- [STAGING_DATABASE_MIGRATIONS.md](./STAGING_DATABASE_MIGRATIONS.md) — Alembic chain reference
