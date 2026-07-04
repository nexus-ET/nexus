# NEXUS develop → staging release (2026-07-04)

Safe deployment checklist for **NEXUS-Staging** (`nexus-dev.edutrust.in`).

**Previous staging head:** `q3m6n1o25p7k`  
**New Alembic head:** `r4n7o2p36q8l`

---

## What is in this release

### Flexible lifecycle transitions (Prospects)
- New `status_transitions` table (forward, backward, express, relaunch)
- `GET /api/v1/leads/{id}/valid-transitions` — allowed next steps per role
- Pipeline UI: **Next step**, **Jump to…** (express), **Revert** (backward) instead of full 39-stage dropdown
- Express transitions auto-log skip comments on View Journey
- Permissions: Student Manager / Web Admin / Super Admin for express, backward, relaunch

### Counselling Session modal (My Bookings)
- Modal no longer closes on backdrop click or DatePicker portal clicks
- Only the **X** close button dismisses the session panel

### Clear WhatsApp script
- `scripts/clear_whatsapp_messages.py` also deletes counselling bookings, notes, and related notification logs for the lead

### Database (1 new migration)

| Revision | File | Changes |
|----------|------|---------|
| `r4n7o2p36q8l` | `r4n7o2p36q8l_add_status_transitions_table.py` | New table `status_transitions`; enum `status_transition_type`; seeds forward/express/backward/relaunch rows |

Migration is **idempotent** (skips enum/table if already present from a partial run).

---

## Pre-deploy checklist (Windows PC)

- [ ] All changes committed on `develop`
- [ ] `python backend/scripts/promote_to_staging.py --dry-run` shows 1 migration `r4n7o2p36q8l`
- [ ] Tests pass: `pytest test_status_lifecycle_transitions.py test_status_transitions.py -q`
- [ ] Staging `.env` on VPS updated manually (see [STAGING_ENV_CHANGES.md](./STAGING_ENV_CHANGES.md)) — **not** in git

---

## Step 1 — Promote to GitHub (Windows PC)

```powershell
cd E:\NEXUS
python backend/scripts/promote_to_staging.py --message "Release 2026-07-04: lifecycle transitions, session modal, clear script bookings"
```

This commits dirty `develop`, pushes `origin/develop`, merges into `E:\NEXUS-staging`, pushes `origin/staging`, and refreshes `STAGING_DATABASE_MIGRATIONS.md`.

---

## Step 2 — Apply env on VPS (manual)

Add or verify the parameters listed in **STAGING_ENV_CHANGES.md** (section “New in this release”). Do **not** copy dev `.env`.

---

## Step 3 — Deploy on Hostinger VPS

```bash
cd /var/www/nexus
git fetch origin staging
git log -1 --oneline origin/staging   # confirm latest promote commit

sudo bash /var/www/nexus/backend/deploy/deploy-staging.sh
```

`deploy-staging.sh` → `deploy.sh` runs:
1. `git pull origin staging`
2. `pip install -r requirements.txt`
3. `python scripts/bootstrap_alembic.py` → **`alembic upgrade head`**
4. `npm ci && npm run build`
5. Restart `nexus-backend`, reload nginx
6. WhatsApp webhook sync

---

## Step 4 — Verify after deploy

```bash
cd /var/www/nexus/backend && source .venv/bin/activate

# Database
alembic current
# Expected: r4n7o2p36q8l (head)

python -c "
from sqlalchemy import create_engine, inspect, text
import os
from dotenv import load_dotenv
load_dotenv()
e = create_engine(os.environ['DATABASE_URL'].replace('postgresql+psycopg://','postgresql://').replace('postgresql://','postgresql+psycopg://'))
with e.connect() as c:
    assert inspect(e).has_table('status_transitions')
    n = c.execute(text('SELECT COUNT(*) FROM status_transitions')).scalar()
    print(f'status_transitions rows: {n}')
"

# Backend health
curl -sf http://127.0.0.1:8002/ && echo OK

# Frontend (browser)
# - Prospects → open lead → Next step / Jump to / Revert visible per role
# - My Bookings → Counselling Session modal stays open until X clicked
```

---

## Rollback (if needed)

```bash
cd /var/www/nexus
git log --oneline -5 origin/staging
git checkout staging
git reset --hard <previous-staging-commit>   # e.g. before this promote
git push origin staging --force-with-lease   # only if agreed with team

# DB: alembic downgrade q3m6n1o25p7k  (drops status_transitions)
sudo systemctl restart nexus-backend
```

---

## Files changed in this release

**Backend:** lifecycle API/services, migration, clear script, tests  
**Frontend:** ProspectDetailPanel, useStudentStatus, adminAccess, MyBookings, CounsellingSessionPanel, ProspectsPage.css  
**Deploy docs:** STAGING_DATABASE_MIGRATIONS.md (auto-updated by promote script)
