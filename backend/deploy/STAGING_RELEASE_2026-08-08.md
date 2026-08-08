# Staging release — 2026-08-08

Promote package for **IntelX**, **FlowX**, **Book Appointment**, intake **Session** workspace (Aspirations / Future Insights / ROI), counselling notification/reschedule fixes, and related Alembic heads.

**Follow-up promote (same day):** counselling session status updates, Students counselling full session workspace, Meta template error clarity, Hostinger deploy hardening (nav RBAC + frontend markers + env presence checks).

**No develop or staging `.env` files are modified by this package.** Apply optional new keys on the Hostinger staging `.env` manually using `STAGING_CONFIG_REQUIREMENTS.md` / `env.staging.example`.

---

## Suggested promote message

```
Staging redeploy 2026-08-08: session workspace + booking notify harden

Ship Students counselling IntakeSession tabs (Future Insights / ROI), session
pipeline status updates without cancelled-booking blockers, Meta template error
clarity, and Hostinger deploy checks (nav RBAC seed, frontend markers, env
presence). Do not overwrite staging .env.
```

---

## Feature inventory (this release)

| Area | What ships |
|------|------------|
| **IntelX** | `/nexus-intel/*` — Knowledge Hub, AI Assistant, Workflows, scrapers, glossary, academy |
| **FlowX** | `/flowx/*` — Ops, journeys, country/master workflows, enrollments, pathway registry |
| **Book Appointment** | `/book-appointment` staff booking + week availability matrix + session purposes |
| **Session workspace** | Intake tabs: Session, Aspirations, Future Insights, ROI Calculator, Shortlist, Personal, … |
| **Students counselling** | `/students/counselling` embeds the same IntakeSessionWorkspace (not profile-only) |
| **Session status** | Allow Prospect Qualified / Finished updates from session; default lifecycle comment |
| **Notifications** | Multi-channel staff-book alerts; WA utility templates; clearer Meta template errors |
| **WhatsApp reschedule** | Latest booking summary; keep `reschedule_in_progress` through date→time pickers |
| **Deploy** | `hostinger-staging.sh` runs `ensure_navigation_rbac.py`, frontend marker checks, env presence |
| **Data sync** | `students_master.email` → `leads` + booking `candidate_email` on profile save |
| **UAT** | `uat/CASE_CATALOG.md` — 44 cases (+ setup); `tests/06-new-modules.spec.ts` |

---

## Database (Alembic)

Hostinger `deploy.sh` / `hostinger-staging.sh` runs **`bootstrap_alembic.py`** (then `alembic upgrade head` fallback).

**Target head after this promote:** `jj0k1lbizlogo`

Includes (among others since prior staging tip):

- **IntelX tables:** `intel_glossary`, `intel_trivia*`, `intel_user_preferences`, `intel_scraper_config`, `intel_academy_modules`, `intel_scrape_reviews`, `intel_ai_chat_logs` (+ thread indexes / seeds)
- **FlowX tables:** pipelines/tracks/tasks/audit, country workflows, stages, task templates, enrollments, pathway registry, subprocess links, checklist/optional/nested brick columns
- **Study years:** `full_time_study_years` + education links
- **Counselling:** `counselling_bookings.intake_assessment`
- **Business:** `businesses.logo_path`
- Timestamptz / scraper retargets / glossary expansion data migrations

Full table: `STAGING_DATABASE_MIGRATIONS.md` (refreshed by `promote_to_staging.py`).

### After migrate on VPS

```bash
cd /var/www/nexus/backend
source .venv/bin/activate
alembic current   # expect jj0k1lbizlogo (head)
python scripts/ensure_navigation_rbac.py   # also run by hostinger-staging.sh
```

---

## Nav / RBAC (must seed)

`navigation_rbac` already defines:

- `/book-appointment` — Book Appointment  
- `/nexus-intel` — Nexus Intel / IntelX  
- `/flowx` — FlowX  

If the top menu is empty or missing these after deploy → run `ensure_navigation_rbac.py` (Super Admin).

---

## Staging `.env` — confirm only (do not overwrite from develop)

See **`STAGING_CONFIG_REQUIREMENTS.md`** section “2026-08-08 additions”.

New **optional** keys (manual on server if missing):

| Key | Purpose |
|-----|---------|
| `SMTP_FROM_NAME` | Display name for booking emails (default in code: Nexus Counselling) |
| `WHATSAPP_BOOKING_TEMPLATE` | `et_booking_confirmation` (UTILITY; Meta must APPROVE) |
| `WHATSAPP_BOOKING_TEMPLATE_LANGUAGE` | Match Meta exactly (`en` or `en_US`) |
| `WHATSAPP_ADMIN_BOOKING_TEMPLATE` | `et_booking_assigned` |
| `WHATSAPP_ADMIN_BOOKING_TEMPLATE_LANGUAGE` | Match Meta exactly (`en` or `en_US`) |

Never copy develop tunnel / ngrok into staging `.env`.  
Confirm `SMTP_PASSWORD` is **not** a placeholder.  
Confirm `R2_BUCKET_NAME=nexus-edutrust-staging` (not shared develop bucket).

---

## Deploy steps (Hostinger)

1. Promote already pushed `origin/staging` (this package).
2. On VPS (preferred full path — rebuilds frontend every time):

```bash
sudo bash /var/www/nexus/backend/deploy/hostinger-staging.sh
```

3. Post-deploy checklist: `STAGING_DEPLOYMENT_AGENT_PROMPT.md` (SMTP, nav RBAC, academia/student copy if empty DB, R2 staging bucket).
4. Smoke: login → mega-nav present → IntelX → FlowX → Book Appointment → `/students/counselling` Session tabs (Future Insights / ROI) → hard-refresh Ctrl+Shift+R.
5. Booking notify smoke: create staff booking; expect email `sent` / WhatsApp may still `failed` until template language matches Meta.

---

## Do not ship

- `backend/.env`, `frontend/.env`, `uat/.env`
- `backend/.env.bloated*`, local tunnel credentials
- `Regenerator script ENEXUSdatagenera.txt`, `Service URI.txt`
- `__pycache__`, `frontend/dist` (build on server)
