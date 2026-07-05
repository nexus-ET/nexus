# NEXUS develop → staging release (2026-07-05)

Safe deployment checklist for **NEXUS-Staging** (`nexus-dev.edutrust.in`).

**Previous staging head (Alembic):** `r4n7o2p36q8l` (or earlier if VPS DB not yet upgraded)  
**Alembic head after deploy:** `s5p8q1r54s0m`  
**Application changes:** No new Alembic files in this promote — intake, bookings, and session-outcome updates are code-only.

---

## What is in this release

### WhatsApp AI Active intake (backend)
- Extended intake after name: **degree → major/program → country** before slot booking
- Character limits on intake replies; **bold** WhatsApp copy (`*text*`)
- Session profile fields preserved during **PICK_TIME** and **reschedule** (date/time no longer cleared)
- Study plan collection uses **rule-based extraction** when `NEXUS_APPOINTMENTS_ONLY=true` (no LLM required on staging)
- New service: `study_plan_extraction.py` (rule-based + optional LLM fallback when appointments-only is off)

### AI Active page (`/ai-active`)
- Target program, major, country fields on intake profile panel
- Faster lead switching: abort stale fetches, `mergeLeadSnapshot`, eager detail apply
- Session date/time loads immediately when switching leads (`key={selectedLead.id}` on profile panel)
- Sidebar filters component (`LeadQueueSidebarFilters`)

### My Bookings (`/my-bookings`)
- **Overview metrics:** Past / Today / Upcoming cards; click filters list to that section
- Lists **all handled bookings** (all statuses), not only `SCHEDULED`
- **Super Admin / Web Admin:** see all team bookings + **Counsellor** column
- Counsellors: own assigned bookings only
- New API: `GET /api/v1/bookings/mine/overview`
- Updated: `GET /api/v1/bookings/mine` (grouped past/today/upcoming, `view_all_bookings` flag)

### Counselling Session modal — Session Outcome
- Current status shown **right-aligned and bold**
- **Next Stage** dropdown lists all stages except current; preselects `next_stage_id`
- Panel stays visible when lead is linked (`can_update_status`)
- **Forward** stage changes blocked when appointment date is after today; **backward** allowed
- Warning on dropdown when forward pick is blocked; API returns `forward_status_changes_blocked`, `backward_status_ids`, `previous_stage_id`, `appointment_date`, `calendar_today`

### Handoffs (`/handoffs`) & Counselling Dashboard (`/counselling`)
- Queue sidebar filter UX aligned with AI Active
- Minor dashboard layout/refresh improvements

### Notifications & security audit
- Security audit IDOR checks updated for `_my_bookings_view_all` / `_get_viewable_booking`
- Notification service tweaks for audit alert gating

---

## Database (Alembic)

| Revision | File | When needed |
|----------|------|-------------|
| `s5p8q1r54s0m` | `s5p8q1r54s0m_reseed_status_definitions_v3.py` | Reseeds **45** lifecycle stages in `status_definitions` (v3) |

**No new tables or columns** in this application release. Intake and session UI use existing lead columns (`target_degree`, `target_program`, `preferred_country`, `consultation_session_date`, etc.) and `status_definitions.next_stage_id`.

If staging DB is already at `s5p8q1r54s0m`, `alembic upgrade head` is a no-op.

Post-migration verify (optional):

```bash
cd /var/www/nexus/backend && source .venv/bin/activate
python scripts/verify_status_definitions_v3.py
```

---

## Pages deployed (full frontend build)

All routes in `frontend/src/App.tsx` are rebuilt and served by nginx. **Smoke-test these after deploy:**

| Route | Page | Focus for this release |
|-------|------|------------------------|
| `/` | Nexus Dashboard | Loads, nav links work |
| `/ai-active` | AI Active | Degree/major/country intake fields; lead switch session date/time |
| `/handoffs` | Handoffs | Sidebar filters |
| `/my-bookings` | My Bookings | Overview cards; admin counsellor column; session modal outcome |
| `/counselling` | Counselling Dashboard | Schedule grid |
| `/prospects` | Prospects | Lifecycle transitions (prior release) |
| `/offline-leads` | Offline Leads | Unchanged smoke |
| `/archive` | Archive | Unchanged smoke |
| `/users` | Users | Unchanged smoke |
| `/analytics` | Analytics | Unchanged smoke |
| `/agents` | Agents | Unchanged smoke |
| `/command-center` | Admin Command Center | Unchanged smoke |
| `/messaging-hub` | Messaging Hub | Unchanged smoke |
| `/my-profile` | My Profile | Unchanged smoke |
| `/settings` | App Settings | Unchanged smoke |
| `/reports/meta-leads` | Meta Leads Report | Unchanged smoke |
| `/reports/audit-logs` | Audit Logs | Unchanged smoke |
| `/quarantine` | Quarantine | Unchanged smoke |
| `/security-audit` | Security Audit | Unchanged smoke |
| `/access-control` | Access Control | Unchanged smoke |
| `/login` | Login | Auth flow |

---

## Pre-deploy checklist (Windows PC)

- [ ] All changes committed on `develop`
- [ ] `python backend/scripts/promote_to_staging.py --dry-run` — confirm migration head `s5p8q1r54s0m`
- [ ] Tests (recommended):  
  `pytest backend/test_my_bookings.py backend/test_intake_degree_major.py backend/test_inbound_whatsapp_intake.py backend/test_reschedule_whatsapp.py -q`
- [ ] Staging `.env` updated **manually** on VPS — see [STAGING_ENV_CHANGES.md](./STAGING_ENV_CHANGES.md) section **Release 2026-07-05** (do **not** commit `.env`)

---

## Step 1 — Promote to GitHub (Windows PC)

```powershell
cd E:\NEXUS
python backend/scripts/promote_to_staging.py --message "Release 2026-07-05: intake degree/major/country, My Bookings overview, session outcome forward-block"
```

Alternative: GitHub Actions → **Promote develop to staging** → Run workflow.

This commits dirty `develop`, pushes `origin/develop`, merges into `E:\NEXUS-staging`, pushes `origin/staging`, and refreshes `STAGING_DATABASE_MIGRATIONS.md`.

---

## Step 2 — Apply env on VPS (manual)

Edit **`/var/www/nexus/backend/.env`** only on the server. Do **not** copy dev `.env`.

Required keys for this release are listed in **STAGING_ENV_CHANGES.md** → **Release 2026-07-05**.

After editing:

```bash
sudo systemctl restart nexus-backend
cd /var/www/nexus/backend && source .venv/bin/activate
python scripts/sync_whatsapp_webhook.py --status
```

---

## Step 3 — Deploy on Hostinger VPS

```bash
cd /var/www/nexus
git fetch origin staging
git log -1 --oneline origin/staging   # confirm latest promote commit

sudo bash /var/www/nexus/backend/deploy/deploy-staging.sh
```

`deploy-staging.sh` runs: git pull → pip install → `alembic upgrade head` → `npm ci && npm run build` → restart backend → reload nginx → WhatsApp webhook sync.

---

## Step 4 — Verify after deploy

```bash
cd /var/www/nexus/backend && source .venv/bin/activate

# Database
alembic current
# Expected: s5p8q1r54s0m (head)

python scripts/verify_status_definitions_v3.py

# Backend health
curl -sf http://127.0.0.1:8002/ && echo OK
```

**Browser checks:**
1. **AI Active** — open lead → confirm target degree/program/country; switch leads → session date/time stable
2. **My Bookings** — Past/Today/Upcoming cards; click each section; open session → Session Outcome dropdown and forward-block before appointment day
3. **WhatsApp test line** — reply with name → degree → major → country → book slot (staging business number)
4. **Admin My Bookings** — Super Admin sees all counsellors’ bookings + Counsellor column

---

## Rollback (if needed)

```bash
cd /var/www/nexus
git log --oneline -5 origin/staging
git checkout staging
git reset --hard <previous-staging-commit>
git push origin staging --force-with-lease   # team agreement only

# DB downgrade only if v3 reseed must be reversed (destructive to stage labels):
# alembic downgrade r4n7o2p36q8l

sudo systemctl restart nexus-backend
```

---

## Files changed in this release

**Backend:** `admissions_intake_flow.py`, `intake_templates.py`, `study_plan_extraction.py`, `counselling_service.py`, `counselling.py`, `leads.py`, `status_transition_service.py`, `notification_service.py`, tests  
**Frontend:** `AiActiveView.tsx`, `MyBookings.tsx`, `BookingOverviewMetrics.tsx`, `SessionOutcomeSection.tsx`, `HandoffsView.tsx`, `CounsellingDashboard.tsx`, `LeadQueueSidebarFilters.tsx`, `leadQueueFilters.ts`  
**Deploy docs:** this file, `STAGING_ENV_CHANGES.md`, `STAGING_DATABASE_MIGRATIONS.md`
