# NEXUS develop → staging release (2026-07-03)

Promote the current **NEXUS Development** work (`E:\NEXUS`, branch `develop`) to **NEXUS-Staging** (`E:\NEXUS-staging`, branch `staging`, Hostinger `nexus-dev.edutrust.in`).

**Alembic head after deploy:** `q3m6n1o25p7k`  
**Previous staging head (last promoted):** `j6f9g4h58i0d`

---

## What is in this release

### Pipeline & status system
- Event-driven `status_definitions`, `status_history`, and `system_logs`
- Central `update_student_status` service with transition guardrails
- Repeat logging for reschedule/cancel (statuses 5 & 6)
- WhatsApp closure messages for Lead: Cancelled (No Answer / Not Interested) and Lead: Deferred
- Admin pipeline dropdown on Prospects; session outcome on My Bookings

### My Bookings / sessions UI
- Activity Log drawer removed; session modal includes **Update Session Outcome** + **Data Exchange**
- **View Interaction** and **View Journey** open as right-side panels
- Status dropdown shows description + current status; Counselling: Scheduled limits next-stage options

### AI Active & WhatsApp
- Duplicate AI outreach blocked when conversation already started
- Journey link separated from Send AI Conversation button
- Outreach status commits fixed (`commit=True` on automation hooks)
- AI outreach delivery wait / template follow-up timing

### Backend scripts (ops)
- `scripts/reset_lead_for_guardrail_testing.py` — also clears location + test scores
- `scripts/validate_status_consistency.py`
- `scripts/sync_whatsapp_webhook.py` — preflight reachability check

### Database (7 new migrations)
See [STAGING_DATABASE_MIGRATIONS.md](./STAGING_DATABASE_MIGRATIONS.md).

---

## Prerequisites

| Item | Notes |
|------|--------|
| Git worktrees | `E:\NEXUS` (develop) + `E:\NEXUS-staging` (staging) — run `.\setup-instances.ps1` once if missing |
| Staging Neon DB | Separate from dev; `DATABASE_URL` on VPS must point to **staging** Neon |
| Env updates | Apply [STAGING_ENV_CHANGES.md](./STAGING_ENV_CHANGES.md) manually — **not** copied by promote |
| VPS `deploy.config` | Must set `GIT_BRANCH=staging` (see `deploy.config.example`) |

---

## Step 1 — Commit develop (on your PC)

From `E:\NEXUS`:

```powershell
git add .
git status
git commit -m "Release: status pipeline, session UI, WhatsApp guardrails, closure notifications"
```

Review the diff before committing. Do **not** commit `backend/.env` (gitignored).

---

## Step 2 — Promote to staging (GitHub + worktree)

**Dry run first:**

```powershell
cd E:\NEXUS
python backend/scripts/promote_to_staging.py --message "Release 2026-07-03: status pipeline and session UI" --dry-run
```

**Execute promote:**

```powershell
python backend/scripts/promote_to_staging.py --message "Release 2026-07-03: status pipeline and session UI"
```

This will:
1. Refresh `STAGING_DATABASE_MIGRATIONS.md`
2. Push `develop` to GitHub
3. Merge into `E:\NEXUS-staging` and push `staging`

**Optional — promote + deploy in one step:**

```powershell
python backend/scripts/promote_to_staging.py --message "Release 2026-07-03" --vps root@YOUR_VPS_IP
```

---

## Step 3 — Update staging environment (manual)

Edit **on the VPS** only:

```bash
sudo nano /var/www/nexus/backend/.env
```

Apply every item in [STAGING_ENV_CHANGES.md](./STAGING_ENV_CHANGES.md).  
Do not copy dev `PUBLIC_TUNNEL_BASE` or quick-tunnel settings to staging.

For **local** staging worktree (`E:\NEXUS-staging\backend\.env`), apply the same keys with staging-local ports (8003 / 5176).

---

## Step 4 — Deploy on Hostinger (VPS)

SSH to the server:

```bash
sudo bash /var/www/nexus/backend/deploy/deploy.sh
```

Or use the staging wrapper (checks branch config):

```bash
sudo bash /var/www/nexus/backend/deploy/deploy-staging.sh
```

`deploy.sh` automatically runs:
- `git pull` (branch from `deploy.config`, should be `staging`)
- `pip install -r requirements.txt`
- `alembic upgrade head` (applies migrations through `q3m6n1o25p7k`)
- `npm ci && npm run build`
- `systemctl restart nexus-backend`
- `python scripts/sync_whatsapp_webhook.py`

---

## Step 5 — Verify deployment

On the VPS:

```bash
sudo bash /var/www/nexus/backend/deploy/verify-staging-deploy.sh
```

Manual checks:

| Check | Command / action |
|-------|------------------|
| Alembic head | `cd /var/www/nexus/backend && source .venv/bin/activate && alembic current` → `q3m6n1o25p7k` |
| Backend health | `curl -sf http://127.0.0.1:8002/` |
| Webhook info | `curl -sf https://nexus-dev.edutrust.in/api/webhook/info` |
| WhatsApp webhook | `python scripts/sync_whatsapp_webhook.py --status` → `owned_by_this_environment: true` |
| UI | Open My Bookings → Session modal shows outcome + data exchange |
| Status API | `GET /api/v1/leads/status-definitions` returns 39 stages |
| Journey panel | View Journey opens right panel (not centered modal) |

---

## Rollback (if needed)

```bash
cd /var/www/nexus
git log -1 --oneline          # note current commit
git checkout staging
git reset --hard ORIGIN_STAGING_SHA_BEFORE_DEPLOY
sudo bash backend/deploy/deploy.sh
# Alembic downgrade only if migrations must be reversed — contact dev before downgrading
```

Database downgrades for data migrations (`n0j3k8l92m4h` reseed) are **destructive** — prefer forward fixes.

---

## Related files

| File | Purpose |
|------|---------|
| [STAGING_DATABASE_MIGRATIONS.md](./STAGING_DATABASE_MIGRATIONS.md) | Alembic chain + this release |
| [STAGING_ENV_CHANGES.md](./STAGING_ENV_CHANGES.md) | Manual `.env` updates (not auto-applied) |
| [releases/20260703-develop-to-staging.md](./releases/20260703-develop-to-staging.md) | Migration snapshot for this release |
| [promote_to_staging.py](../scripts/promote_to_staging.py) | Git promote automation |
| [deploy-staging.sh](./deploy-staging.sh) | VPS deploy wrapper for staging branch |
| [verify-staging-deploy.sh](./verify-staging-deploy.sh) | Post-deploy health checks |
