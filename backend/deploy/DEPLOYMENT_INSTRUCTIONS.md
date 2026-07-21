# Deploy Nexus to Hostinger staging

Target: **nexus-dev.edutrust.in**  
App root: `/var/www/nexus`  
Git branch: `staging`  
Database: Neon **Nexus-Dev-1** (staging only)

Secrets stay on the VPS. This guide never overwrites local `.env` files.

---

## Before you start

1. Read and apply [STAGING_CONFIG_REQUIREMENTS.md](./STAGING_CONFIG_REQUIREMENTS.md)  
   — especially `DATABASE_URL` → **Nexus-Dev-1**
2. Confirm Meta WhatsApp webhook is  
   `https://nexus-dev.edutrust.in/api/webhook`
3. Confirm welcome template `et_student_welcome` is greeting-only (no continue/full-name nudge)
4. All Alembic migrations under `backend/alembic/versions/` that belong to this release must be **committed and pushed** to `staging` (many academia migrations are new — promote them before VPS deploy)

---

## A. Prepare code on your PC

```powershell
cd E:\NEXUS

# Review what will ship (do not commit .env)
git status

# Promote develop → staging (updates migration docs, pushes GitHub)
python backend/scripts/promote_to_staging.py --message "Staging release: Nexus-Dev-1 + intake/outreach updates"

# Or manually merge/push staging, then on VPS pull
```

Do **not** push `backend/.env` or Neon passwords.

---

## B. One-time: point staging at Nexus-Dev-1

SSH:

```bash
ssh root@YOUR_VPS_IP
sudo nano /var/www/nexus/backend/.env
```

Set `DATABASE_URL` to the **Nexus-Dev-1** pooled `postgresql+psycopg://...` URL (see STAGING_CONFIG_REQUIREMENTS.md).

Save, then:

```bash
sudo systemctl restart nexus-backend
```

---

## C. Full staging deploy (code + migrations + frontend)

On the VPS:

```bash
sudo bash /var/www/nexus/backend/deploy/hostinger-staging.sh
```

This:

1. `git pull` branch `staging`
2. Installs Python/Node deps
3. Runs `python scripts/bootstrap_alembic.py`  
   — empty Nexus-Dev-1 → full `alembic upgrade head`
4. Builds frontend
5. Restarts `nexus-backend` + nginx
6. Syncs WhatsApp webhook to `PUBLIC_TUNNEL_BASE`

Alternatives:

```bash
# Migrations only skipped (UI-only hotfix)
sudo bash /var/www/nexus/backend/deploy/hostinger-staging.sh --skip-migrations

# Frontend only
sudo bash /var/www/nexus/backend/deploy/hostinger-staging.sh --frontend-only

# Env-only restart
sudo bash /var/www/nexus/backend/deploy/restart-staging-services.sh
```

From Windows (optional):

```powershell
.\backend\deploy\hostinger-staging.ps1 -VpsHost root@YOUR_VPS_IP
```

---

## D. Fresh Nexus-Dev-1 checklist

| Step | Command / action |
|------|------------------|
| 1 | Neon: create **Nexus-Dev-1**, copy pooled URI |
| 2 | VPS `.env`: set `DATABASE_URL` (psycopg + sslmode) |
| 3 | Allow VPS IP in Neon if required |
| 4 | `sudo bash .../hostinger-staging.sh` |
| 5 | `alembic current` matches `alembic heads` |
| 6 | Open `https://nexus-dev.edutrust.in` and log in |
| 7 | `python scripts/sync_whatsapp_webhook.py --status` → owned by this environment |

Empty DB note: first boot creates all tables via Alembic (academia hub, students, calendar, etc.). No dump from the old full Neon DB is required unless you want data migrated separately.

---

## E. Verification

```bash
cd /var/www/nexus/backend
source .venv/bin/activate

# Health
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8002/docs
curl -sS -o /dev/null -w "%{http_code}\n" https://nexus-dev.edutrust.in/

# DB migrations
alembic heads
alembic current

# Webhook ownership
python scripts/sync_whatsapp_webhook.py --status

# Optional packaged verify
sudo bash /var/www/nexus/backend/deploy/verify-staging-deploy.sh
```

### Product checks (AI Active / WhatsApp)

1. Start AI outreach on a test lead → **welcome only** (no “drop us a quick hi/hello” follow-up)
2. Student replies `hi` → degree picker (no “Current location” / full-name booking line)
3. AI Active intake card has **no Current location** field
4. Inbound replies appear on AI Active (webhook must own staging URL)

---

## F. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| DB connection errors | Wrong/old Neon URL or IP blocked | Update `DATABASE_URL` to Nexus-Dev-1; allow VPS IP |
| `alembic upgrade` fails duplicate table | Pointing at old partially migrated DB | Use empty Nexus-Dev-1 or stamp carefully |
| Inbound WhatsApp silent | Webhook still on dead tunnel | `sync_whatsapp_webhook.py` + Meta callback = staging URL |
| Continue nudge still sent | Old code or `SKIP` false | Pull latest; set `WHATSAPP_OUTREACH_SKIP_INTAKE_FOLLOWUP=true` |
| Migrations missing on VPS | Uncommitted local migration files | Commit/push all `alembic/versions/*.py` to `staging` |

---

## Related files

| File | Purpose |
|------|---------|
| [STAGING_CONFIG_REQUIREMENTS.md](./STAGING_CONFIG_REQUIREMENTS.md) | Env keys to edit on VPS |
| [STAGING_DATABASE_MIGRATIONS.md](./STAGING_DATABASE_MIGRATIONS.md) | Alembic chain / head |
| [env.staging.example](./env.staging.example) | Staging `.env` template |
| [hostinger-staging.sh](./hostinger-staging.sh) | Preferred VPS deploy |
| `../scripts/bootstrap_alembic.py` | Fresh or legacy DB migrate helper |
| `../scripts/promote_to_staging.py` | PC → GitHub staging promote |
