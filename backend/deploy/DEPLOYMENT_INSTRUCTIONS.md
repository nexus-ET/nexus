# Staging deployment instructions — 2026-07-26 release

Target: **Nexus Staging** (`nexus-dev.edutrust.in` / Hostinger Nexus-Dev-1).  
Branch intent: merge this develop package → `staging` (or deploy from a release PR).

Follow `STAGING_DEPLOYMENT_AGENT_PROMPT.md` for Hostinger SMTP, seeds, R2, and default data. This file is the **release-specific** checklist for the current uncommitted package.

---

## Summary of what this release ships

| Area | What |
|------|------|
| Exception Report | `exception_logs` (+ `resolution_comment`), Insights UI, auto-resolve, retention, email alerts |
| University matching (Phase 1) | Weight profiles + shortlist runs/items; candidate shortlist tab |
| Lead queues | Server pagination + **Contact status** filter; contact-first sort; Recently replied fix |
| Meta lead sync | Page-token / rate-limit hardening; lock recovery |
| Appointments | Period agenda shell on My Bookings + Counselling (UI preview samples removed) |
| Nav | Exception Report under Audit; Leads mega-menu ordering (All Prospects, Archive) |

Alembic path:

```
c4d7e0f53g6h  →  d5e8f1a64h7i  →  e6x9c2eption01  →  f7y0d3esolution (head)
```

---

## Pre-flight (before push / deploy)

1. **Do not commit** `backend/.env`, `frontend/.env`, `.dev-stack.lock`, `__pycache__`, `frontend/dist`.
2. Confirm LOGIN DEBUG print is removed from `login.py` (QA cleanup).
3. Confirm UI preview sample banner/routes are removed (temp booking seeders).
4. Confirm Twilio “radar” stdout dumps in `api/v1/leads.py` are replaced with logger (QA cleanup).
5. Review `STAGING_CONFIG_REQUIREMENTS.md` and apply SMTP / `ALERT_EMAIL` / R2 on Staging manually.
6. Prefer **Alembic** over hand SQL: `alembic upgrade head`.  
   Hand SQL fallback: `backend/deploy/staging_release_2026-07-26_migration.sql`.

---

## Step-by-step deploy

### A. Package & GitHub

1. Commit the release on `develop` (or a release branch) including:
   - App/frontend changes
   - Alembic revisions `d5e8f1a64h7i`, `e6x9c2eption01`, `f7y0d3esolution`
   - Deploy docs under `backend/deploy/`
2. Open PR → `staging` (or merge develop → staging per your process).
3. Push; let Hostinger / CI pull, or SSH and `git pull` on the Staging app root.

### B. Database

On the Staging host, with Staging `DATABASE_URL`:

```bash
cd /path/to/NEXUS/backend
source .venv/bin/activate   # or project venv
alembic current
alembic upgrade head
alembic current             # expect: f7y0d3esolution
```

If Alembic cannot run, apply `staging_release_2026-07-26_migration.sql` once, then stamp:

```bash
alembic stamp f7y0d3esolution
```

### C. Navigation RBAC (Exception Report menu)

```bash
# From backend/, Staging DB URL in env
python scripts/ensure_navigation_rbac.py
# Or re-seed users/nav if Staging nav is empty:
# python scripts/seed_staging_users.py
```

Confirm Super Admins can see **Insights → Audit → Exception Report**.

### D. Config (manual)

1. Apply items from `STAGING_CONFIG_REQUIREMENTS.md` (SMTP, `ALERT_EMAIL`, R2 staging bucket).
2. Restart backend after env changes:

```bash
sudo systemctl restart nexus-backend
# wait for health
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8002/docs
```

### E. Frontend

Build/serve Staging frontend as usual (Hostinger static / Vite build). Hard-refresh browsers after deploy.

### F. Default data (if Staging sparse)

Per staging rule:

- `python scripts/seed_staging_users.py`
- Academia copy if needed: `copy_academia_to_staging.py`
- Default student lead 27: `copy_student_to_staging.py --lead-id 27`

---

## Verification section

### Schema

- [ ] `alembic current` → `f7y0d3esolution`
- [ ] Tables exist: `matching_weight_profiles`, `matching_shortlist_runs`, `matching_shortlist_items`, `exception_logs`
- [ ] `exception_logs.resolution_comment` column exists
- [ ] Weight profiles `default` and `research_masters` present

### Exception Report / status ops

- [ ] Open `/reports/exceptions` as admin — list loads, filters work
- [ ] Retention setting visible; GET/PUT retention API works
- [ ] Trigger a harmless client/network error → row appears (or POST `/api/v1/reports/exception-logs`)
- [ ] Manual Resolve requires comment; Resolved shows comment
- [ ] Auto-resolve endpoint / Cursor agent path works for known IDs
- [ ] With SMTP + `ALERT_EMAIL`: new exception triggers email; resolve confirmation email optional/expected per design

### Lead queues (pagination + contact status)

- [ ] **AI Active / Handoffs / All Prospects:** Previous/Next visible; “Viewing X–Y of Z records” correct
- [ ] Contact status **Chat started** / **Not contacted yet** / **All** — switching back to **All** restores full set (no sticky filter race)
- [ ] Sort: contacted first, then not contacted
- [ ] Prospects **Recently replied** only shows leads with inbound candidate messages

### Meta sync

- [ ] Manual Meta sync completes without immediate `#4` from `/me/accounts` (page-token path)
- [ ] Sync lock recovery does not leave permanent 409 “already in progress”

### Journey / status tracking

- [ ] Open Student Journey panel for a known lead (e.g. lead 27) — timeline renders
- [ ] Status transitions still available where expected (counselling / pipeline)
- [ ] After WhatsApp reset (if tested on Staging only): stage/intake clear as designed; journey history still coherent

### University matching

- [ ] Weight profiles API returns seeded profiles
- [ ] From a booking / candidate profile: generate or view university shortlist without 500s

### Appointments

- [ ] My Bookings + Counselling: period/multi-date agenda works
- [ ] **No** “UI preview samples” banner on either page

### Nav

- [ ] Exception Report under Audit (not main Insights featured row)
- [ ] Leads: AI Active → Handoffs → All Prospects → Archive (Archive last in featured)
- [ ] Directories no longer lists All Prospects / Archive as primary featured items

### Smoke

- [ ] Login with Staging Super Admin (email lowercase OK)
- [ ] `/docs` and key APIs return 200 with auth
- [ ] No SMTP “not configured” spam in journal if alerts expected

---

## Rollback notes

1. Code: redeploy previous Staging git SHA.
2. Schema: Alembic downgrade `f7y0d3esolution` → `c4d7e0f53g6h` **only if** you accept dropping matching tables / exception data.
3. Prefer forward-fix for Exception Report; table drop loses operational logs.

---

## Conflicts / risks identified

See also `STAGING_RELEASE_PACKAGE.md` § Conflicts.
