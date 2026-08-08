# Staging release — 2026-08-08

Promote package for **IntelX**, **FlowX**, **Book Appointment**, intake **Session** workspace (Aspirations / Future Insights / ROI), counselling notification/reschedule fixes, and related Alembic heads.

**No develop or staging `.env` files are modified by this package.** Apply optional new keys on the Hostinger staging `.env` manually using `STAGING_CONFIG_REQUIREMENTS.md` / `env.staging.example`.

---

## Suggested promote message

```
Staging release 2026-08-08: IntelX, FlowX, Book Appointment, Session insights/ROI

Ship Nexus Intel + FlowX operational modules, staff Book Appointment, intake
session workspace (Aspirations / Future Insights / ROI), booking notification
and WhatsApp reschedule fixes, and UAT harness (44 application cases).
```

---

## Feature inventory (this release)

| Area | What ships |
|------|------------|
| **IntelX** | `/nexus-intel/*` — Knowledge Hub, AI Assistant, Workflows, scrapers, glossary, academy |
| **FlowX** | `/flowx/*` — Ops, journeys, country/master workflows, enrollments, pathway registry |
| **Book Appointment** | `/book-appointment` staff booking + week availability matrix + session purposes |
| **Session workspace** | Intake tabs: Session, Aspirations, Future Insights, ROI Calculator, Shortlist, Personal, … |
| **Notifications** | Multi-channel staff-book alerts; WA utility templates; email deliverability headers |
| **WhatsApp reschedule** | Latest booking summary; keep `reschedule_in_progress` through date→time pickers |
| **Data sync** | `students_master.email` → `leads` + booking `candidate_email` on profile save |
| **UAT** | `uat/CASE_CATALOG.md` — 44 cases (+ setup); `tests/06-new-modules.spec.ts` |

---

## Database (Alembic)

Hostinger `deploy.sh` / `hostinger-staging.sh` runs **`alembic upgrade head`**.

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
python scripts/ensure_navigation_rbac.py   # Book Appointment, Nexus Intel, FlowX routes
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
| `WHATSAPP_BOOKING_TEMPLATE_LANGUAGE` | `en` |
| `WHATSAPP_ADMIN_BOOKING_TEMPLATE` | `et_booking_assigned` |
| `WHATSAPP_ADMIN_BOOKING_TEMPLATE_LANGUAGE` | `en` |

Never copy develop tunnel / ngrok into staging `.env`.

---

## Deploy steps (Hostinger)

1. Promote already pushed `origin/staging` (this package).
2. On VPS (preferred full path):

```bash
sudo bash /var/www/nexus/backend/deploy/hostinger-staging.sh
```

Or pull + migrate + frontend build + restart:

```bash
sudo bash /var/www/nexus/backend/deploy/deploy.sh
# ensure frontend rebuilt if deploy.sh alone is code-only:
sudo bash /var/www/nexus/backend/deploy/hostinger-staging.sh --frontend-only
```

3. Post-deploy checklist: `STAGING_DEPLOYMENT_AGENT_PROMPT.md` (SMTP, nav RBAC, academia/student copy if empty DB, R2 staging bucket).
4. Smoke: login → IntelX → FlowX → Book Appointment → open Session for lead 27 → Future Insights / ROI.
5. Optional: UAT against staging (`uat/.env` `UAT_BASE_URL=https://nexus-dev.edutrust.in`).

---

## Do not ship

- `backend/.env`, `frontend/.env`, `uat/.env`
- `backend/.env.bloated*`, local tunnel credentials
- `Regenerator script ENEXUSdatagenera.txt`, `Service URI.txt`
- `__pycache__`, `frontend/dist` (build on server)
