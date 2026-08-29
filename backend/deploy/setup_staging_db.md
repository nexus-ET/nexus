# Staging database setup — Hostinger KVM 1 (`nexus_edutrust`)

Bootstrap and refresh for the **Hostinger KVM 1** PostgreSQL database used by `https://nexus-dev.edutrust.in`.

| Item | Value |
|------|--------|
| Database | `nexus_edutrust` |
| User | `nexus_et_admin` (full privileges) |
| Host on VPS | `127.0.0.1:5432` |
| App path on VPS | `/var/www/nexus/backend` |
| Alembic head (develop, 2026-08-29) | `zz6a7bbizctc` |
| Expected public tables | **110** (match `nexus_edutrust_dev`) |
| Preferred data source | Hostinger **`nexus_edutrust_dev`** (full clone) |

**Do not commit** passwords or real connection strings into git. Fill secrets only in `/var/www/nexus/backend/.env` on the VPS (or local tunnel `.env`).

---

## Development vs staging database

| Environment | Host | Database | Notes |
|-------------|------|----------|--------|
| **Development** (local `E:\NEXUS`) | VPS Postgres via SSH tunnel `127.0.0.1:15432` (or on-VPS `127.0.0.1:5432`) | **`nexus_edutrust_dev`** / **`nexus_dev_et_admin`** | See [setup_dev_db.md](./setup_dev_db.md) |
| **Staging** (Hostinger KVM 1) | VPS Postgres `127.0.0.1:5432` | **`nexus_edutrust`** / **`nexus_et_admin`** | No Neon `sslmode` / `channel_binding` |

---

## `DATABASE_URL` format (staging)

On the VPS (backend + Postgres co-located):

```env
DATABASE_URL=postgresql+psycopg://nexus_et_admin:YOUR_URL_ENCODED_PASSWORD@127.0.0.1:5432/nexus_edutrust
```

**URL-encode** special characters in the password (`!` → `%21`, `#` → `%23`, `@` → `%40`, etc.).

**Do not use:**

- Develop Neon URL (`ep-still-paper-…`)
- Old staging Neon URLs (`sparkling-violet`, `ep-broad-breeze-…`, `ep-round-rain-…`)
- `&channel_binding=require` (Neon-only)
- Develop tunnel port (`:15432`) on the VPS `.env`

---

## Recommended: full clone from `nexus_edutrust_dev`

When staging should match development content (schema + all rows), run the one-shot script **on the VPS** (both DBs are local — fastest):

```bash
# From your PC — copy script if VPS tree is behind:
scp E:/NEXUS/backend/deploy/clone_dev_to_staging_db.sh root@YOUR_VPS_IP:/tmp/

ssh root@YOUR_VPS_IP
export STAGING_DB_PASSWORD='YOUR_STAGING_DB_PASSWORD'   # plaintext nexus_et_admin password
sudo -E bash /tmp/clone_dev_to_staging_db.sh
# Prefer after git pull:
# sudo -E bash /var/www/nexus/backend/deploy/clone_dev_to_staging_db.sh
```

What the script does:

1. Grants `nexus_et_admin` ownership + `CREATE` on `public` (same pattern as `nexus_dev_et_admin`)
2. `pg_dump -Fc --no-owner --no-acl` from `nexus_edutrust_dev`
3. `DROP SCHEMA public CASCADE` on staging → recreate → `pg_restore`
4. Re-owns objects to `nexus_et_admin` (**tables/views first**; PG16 identity sequences follow table owner — do not `ALTER SEQUENCE OWNER` on linked seqs), realigns sequences
5. Backs up `/var/www/nexus/backend/.env`, replaces `DATABASE_URL` with Hostinger staging URL (URL-encodes password), strips CRLF
6. Restarts `nexus-backend` and prints table/alembic/key-row counts

If step 4 failed mid-run with `cannot change owner of sequence … Sequence is linked to table` (data already restored), finish with:

```bash
export STAGING_DB_PASSWORD='YOUR_STAGING_DB_PASSWORD'
sudo -E bash /tmp/fix_staging_ownership.sh
# or: sudo -E bash /var/www/nexus/backend/deploy/fix_staging_ownership.sh
```

Expected:

- Public tables equal on both DBs (~110)
- `alembic_version` = `zz6a7bbizctc` on both
- `systemctl is-active nexus-backend` → `active`
- Health: `curl -sf http://127.0.0.1:8002/`

---

## 1. SSH to Hostinger KVM 1

```powershell
ssh root@YOUR_VPS_IP
# Optional key (after installing pubkey in root authorized_keys):
# ssh -i $env:USERPROFILE\.ssh\nexus_vps root@YOUR_VPS_IP
```

App root: `/var/www/nexus`.

---

## 2. Privileges (if not using the clone script)

As `postgres` on the VPS:

```bash
sudo -u postgres psql -d nexus_edutrust <<'SQL'
ALTER DATABASE nexus_edutrust OWNER TO nexus_et_admin;
ALTER SCHEMA public OWNER TO nexus_et_admin;
GRANT ALL ON SCHEMA public TO nexus_et_admin;
GRANT CREATE ON SCHEMA public TO nexus_et_admin;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO nexus_et_admin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO nexus_et_admin;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO nexus_et_admin;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO nexus_et_admin;
SQL
```

Smoke test:

```bash
psql "postgresql://nexus_et_admin:YOUR_PASSWORD@127.0.0.1:5432/nexus_edutrust" -c "SELECT 1"
```

---

## 3. Set `DATABASE_URL` on the VPS

```bash
sudo cp -a /var/www/nexus/backend/.env /var/www/nexus/backend/.env.bak.$(date +%Y%m%d%H%M%S)
sudo nano /var/www/nexus/backend/.env
```

```env
DATABASE_URL=postgresql+psycopg://nexus_et_admin:YOUR_URL_ENCODED_PASSWORD@127.0.0.1:5432/nexus_edutrust
```

```bash
sudo sed -i 's/\r$//' /var/www/nexus/backend/.env
sudo chown www-data:www-data /var/www/nexus/backend/.env
sudo chmod 640 /var/www/nexus/backend/.env
```

Keep other staging keys (identity, WhatsApp, SMTP, R2). See [env.staging.example](./env.staging.example) / [STAGING_ENV_CHANGES.md](./STAGING_ENV_CHANGES.md).

---

## 4. Schema-only bootstrap (empty DB — skip if cloning from dev)

Prefer the full clone above when you want develop data. For an **empty** staging DB only:

```bash
cd /var/www/nexus/backend
source .venv/bin/activate
# Sync alembic versions if VPS is behind (include zz6a7bbizctc)
git pull   # or scp missing alembic/versions/*.py
python scripts/verify_staging_database.py --migrate
# or: python scripts/bootstrap_alembic.py
python -m alembic current   # expect zz6a7bbizctc (head)
```

`alembic/env.py` must escape `%` in URLs (`settings.DATABASE_URL.replace("%", "%%")`) so URL-encoded passwords work.

Then:

```bash
python scripts/ensure_navigation_rbac.py
python scripts/ensure_id_sequences.py
python scripts/seed_staging_users.py
sudo systemctl restart nexus-backend
```

---

## 5. Manual dump / restore (same as clone script)

```bash
sudo -u postgres pg_dump -Fc --no-owner --no-acl -d nexus_edutrust_dev -f /tmp/nexus_edutrust_dev.dump
sudo -u postgres psql -d nexus_edutrust -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; ALTER SCHEMA public OWNER TO nexus_et_admin; GRANT ALL ON SCHEMA public TO nexus_et_admin; GRANT CREATE ON SCHEMA public TO nexus_et_admin;"
sudo -u postgres pg_restore --no-owner --no-acl -d nexus_edutrust /tmp/nexus_edutrust_dev.dump
# Re-grant + sequences (or re-run clone script steps 4–7)
```

From Windows via SSH tunnel (`ssh -N -L 15432:127.0.0.1:5432 root@YOUR_VPS_IP`):

```powershell
$pg = "C:\Program Files\PostgreSQL\18\bin"
& "$pg\pg_dump.exe" -Fc --no-owner --no-acl -h 127.0.0.1 -p 15432 -U nexus_dev_et_admin -d nexus_edutrust_dev -f $env:TEMP\nexus_edutrust_dev.dump
# DROP SCHEMA / restore still needs a role that can recreate schema — prefer on-VPS postgres.
```

---

## 6. Verify

On VPS:

```bash
sudo -u postgres psql -d nexus_edutrust_dev -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'; SELECT version_num FROM alembic_version;"
sudo -u postgres psql -d nexus_edutrust -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'; SELECT version_num FROM alembic_version;"
# Key tables should match: users, leads, students_master, institutions, programs, …
curl -sf http://127.0.0.1:8002/ && echo OK
systemctl is-active nexus-backend
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `permission denied for schema public` | Run §2 grants (`GRANT CREATE ON SCHEMA public`) |
| `password authentication failed` | Reset password; URL-encode `!` `#` `@` in `.env` |
| `502` after `.env` edit | `sed -i 's/\r$//' .env`; use [run-nexus-backend.sh](./run-nexus-backend.sh) |
| Alembic ConfigParser `%` error | `env.py` must `.replace("%", "%%")` |
| PC cannot reach `:5432` | Use SSH tunnel `15432` or run scripts on VPS |
| SSH `Permission denied (publickey)` | Password login, or install `~/.ssh/nexus_vps.pub` into VPS `authorized_keys` |

---

## Related docs

- [clone_dev_to_staging_db.sh](./clone_dev_to_staging_db.sh) — one-shot VPS clone + `.env` + restart
- [fix_staging_ownership.sh](./fix_staging_ownership.sh) — finish ownership/`.env`/restart if clone failed on PG16 identity sequences
- [setup_dev_db.md](./setup_dev_db.md) — develop Hostinger bootstrap (`nexus_edutrust_dev`)
- [migrate_on_vps.sh](./migrate_on_vps.sh) — schema migrate on VPS without dump
- [env.staging.example](./env.staging.example) — template `.env` (placeholders only)
- [hostinger-staging.sh](./hostinger-staging.sh) — full deploy including migrations
