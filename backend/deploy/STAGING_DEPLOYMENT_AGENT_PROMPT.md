# Staging deployment agent prompt (Hostinger / nexus-dev)

**How to use:** Before or during every staging deploy, paste everything below the line into Cursor (or give it to an agent) together with any release notes. The agent must work through the checklist in order, verify each item with evidence (commands/output), and stop with a clear blocker list if anything fails.

---

You are assisting with a **NEXUS Hostinger staging deployment** for `https://nexus-dev.edutrust.in`.

## Non-negotiables

1. **Never overwrite** local develop `E:\NEXUS\backend\.env` with staging values, or staging `/var/www/nexus/backend/.env` with develop tunnel/ngrok values.
2. **Never print or paste secrets** into chat (Neon passwords, R2 keys, SMTP passwords, WhatsApp tokens). Refer to them by env var name only. If a secret was exposed, remind the operator to rotate it.
3. Prefer **DB data fixes / env edits / restarts** over unnecessary full redeploys when the code is already on `staging`.
4. On Windows PowerShell: `Read-Host "text"` uses `text` as the **prompt label**, not the value. Never tell the user to put a URL/password inside the Read-Host prompt string.
5. Never tell the user to type placeholder text (`PASSWORD`, `REAL_PASSWORD_HERE`, `PASTE_…`) as a real credential.
6. `scp E:\...` must be run from **Windows**, not from the VPS shell (Linux will treat `E:` as a hostname).

---

## Context — failures we already hit (must not repeat)

Work through these as a **preflight + postflight** checklist. Each item caused real staging pain.

### A. Database / Postgres

| # | Issue | Prevention / verify |
|---|--------|---------------------|
| A1 | Staging pointed at **wrong DB** (develop Neon still-paper, old Neon Nexus-Dev-1 / sparkling-violet) | Confirm `DATABASE_URL` is **Hostinger KVM 1**: `postgresql+psycopg://nexus_et_admin:…@127.0.0.1:5432/nexus_edutrust`. See [setup_staging_db.md](./setup_staging_db.md). |
| A2 | Neon `channel_binding=require` or systemd 502 from bad `.env` parsing | Hostinger Postgres: no Neon query params. Unit must `ExecStart` the dotenv wrapper ([run-nexus-backend.sh](./run-nexus-backend.sh)). Strip CRLF: `sed -i 's/\r$//' .env`. |
| A3 | Fresh DB: early Alembic revisions are ALTER-only → fail on empty DB | Use `python scripts/bootstrap_alembic.py` (create_all + stamp head + seeds) on empty DBs, not blind `alembic upgrade head` alone. |
| A4 | Fresh DB had **no users** → login impossible | After bootstrap: `python scripts/seed_staging_users.py --password '…'` (real password). Canonical admins: `ishq@edutrust.in`, `arunpk@edutrust.in`, `admin@edutrust.in`. |
| A5 | Seed used example password `YourSecurePass` → **401 login** | Document the password that was actually set; never leave example strings. Verify with local `curl` to `/api/v1/login` expecting 200. |
| A6 | Login email case | Backend should lowercase email on lookup; still advise lowercase emails. |

### B. RBAC / UI blank after login

| # | Issue | Prevention / verify |
|---|--------|---------------------|
| B1 | Top **header mega-nav empty** | Fresh DB missing `navigation_pages` / `role_page_permissions`. Run nav seed / `ensure_navigation_rbac` (or inline seed using `DEFAULT_NAVIGATION_PAGES`). Super Admin UI nav depends on those rows (or superuser route bypass if deployed). |
| B2 | `GET /api/v1/permissions/my-role` returns only `["/"]` | Same as B1 — fix before calling deploy “done”. |
| B3 | **Company / Settings page blank or sparse** | Ensure `businesses` id=1 (EduTrust profile), `dynamic_settings` defaults, `countries` catalog. Settings APIs require `is_superuser=true`. |
| B4 | Monitoring downtime emails silent | **SMTP env + monitoring DB keys** — see mandatory section **F** below. Restart backend after SMTP env change. |

### C. Academia Hub data

| # | Issue | Prevention / verify |
|---|--------|---------------------|
| C1 | Empty institutions / geography / LMPC on fresh staging | Copy from develop with `scripts/copy_academia_to_staging.py` (run from **Windows** where the script exists, or scp script to VPS first). |
| C2 | Script missing on VPS (`No such file`) | Script lives on develop tree; `git pull` / scp from Windows, or run copy from `E:\NEXUS\backend`. |
| C3 | Neon denies `session_replication_role` | Copy script must use multi-table `TRUNCATE …` + 2-pass intakes — not replication role. |
| C4 | `institution_intakes.level_ids` type mismatch (array vs jsonb) | Copy intakes via `COPY` + `to_jsonb(level_ids)`. |
| C5 | JHU/UCLA **Levels/Programs/Majors/Courses** “removed” | Published `institution_course_offerings` may be **0**; mappings live in `institution_wizard_drafts`. Copy script **must include drafts** and remap `created_by_user_id` by email. Re-copy if drafts were skipped. |
| C6 | PowerShell `$pw` disasters | Password length ~24, starts with `npg_`, **no spaces**. Extract with regex from full URL if needed. Never use placeholder strings. Prefer: `$pw = 'npg_…'` or extract `neondb_owner:([^@]+)@`. |

### D. Cloudflare R2 / pictures

| # | Issue | Prevention / verify |
|---|--------|---------------------|
| D1 | Develop + staging shared `nexus-edutrust` → deletes/uploads affect both | Staging must use **`R2_BUCKET_NAME=nexus-edutrust-staging`** (isolated bucket). Keep same account/endpoint/keys only if token allows the new bucket. |
| D2 | Copied local **tunnel** Cloudflare settings onto staging | Staging must keep `PUBLIC_TUNNEL_BASE=https://nexus-dev.edutrust.in`, `FRONTEND_URL=https://nexus-dev.edutrust.in`, `NEXUS_TUNNEL_ENABLED=false`. Do **not** copy `NEXUS_TUNNEL_MODE`, ngrok URLs, or `NEXUS_TUNNEL_ENABLED=true`. |
| D3 | Logo visible in UI but **not in R2 bucket** | Upload landed in `/var/www/nexus/backend/uploads/…` because R2 wasn’t configured/restarted yet. After env change: restart → probe `put_object` to staging bucket → re-upload. Objects appear under `{institution-slug}/logo/`, not bucket root. |
| D4 | Unlink in staging DB ≠ delete in R2 (and shared bucket deletes hurt develop) | Explain shared vs isolated; after isolation, DB-only clears leave old-bucket orphans alone. |

### E. Runtime / WhatsApp / deploy process

| # | Issue | Prevention / verify |
|---|--------|---------------------|
| E1 | Backend slow to bind; curl to `:8002` too early | Wait up to ~3 min after restart (cold Neon bootstrap); check `ss -lntp \| grep 8002`, `systemctl status nexus-backend`, `journalctl -u nexus-backend -n 100`. |
| E1b | **502 after DB URL change** while `seed_staging_users.py` works | Scripts use python-dotenv; old unit used `EnvironmentFile=` (CRLF/`&`/quotes diverge). Fix `.env` to clean URL, install wrapper unit from `deploy/nexus-backend.service`, `daemon-reload`, restart. |
| E2 | WhatsApp webhook 502 / hairpin NAT | Prefer loopback verify (`127.0.0.1:8002`); `sync_whatsapp_webhook.py` should try loopback first. Confirm `PUBLIC_TUNNEL_BASE` is staging HTTPS host. |
| E3 | Long “simple” deploys from missing seeds | Treat **users + nav RBAC + settings/SMTP + academia copy (+ drafts) + R2 staging bucket** as part of deploy, not optional cleanup. |

### F. Mandatory every deploy — SMTP + default data tables

**Do not mark the deploy done until every row below is verified with counts or config evidence.**

#### F1. Email SMTP (website downtime monitoring)

Staging `/var/www/nexus/backend/.env` must include (values from develop SMTP; do not print secrets):

| Variable | Required |
|----------|----------|
| `SMTP_HOST` | yes (e.g. GoDaddy SMTP host) |
| `SMTP_PORT` | yes (`465` SSL or `587` STARTTLS) |
| `SMTP_USE_TLS` | yes |
| `SMTP_USER` | yes |
| `SMTP_PASSWORD` | yes |
| `SMTP_FROM_EMAIL` | yes |

DB `dynamic_settings` (Settings UI / monitoring panel):

| Key | Expected on staging |
|-----|---------------------|
| `MONITORING_STATUS` | `Active` |
| `UPTIME_TARGET_URL` | `https://nexus-dev.edutrust.in/` (or health URL) |
| `ALERT_EMAIL` | one or more real alert recipients |

After SMTP env edits: `sudo systemctl restart nexus-backend`. Confirm journals are **not** logging `SMTP is not configured`.

#### F2. Default / reference data (copy or seed if missing)

| Domain | What must exist | How to ensure |
|--------|-----------------|---------------|
| **Nexus users** | Super Admins: `ishq@edutrust.in`, `arunpk@edutrust.in`, `admin@edutrust.in`; `is_superuser=true`; `admin_role_id` set; can login (HTTP 200) | `python scripts/seed_staging_users.py --password '<real>'` |
| **Nav RBAC** | `navigation_pages` + `role_page_permissions` so header menu is not empty | `ensure_navigation_rbac` / nav seed after users |
| **Levels** | rows in `levels` | academia copy from develop |
| **Programs** | rows in `programs` | academia copy |
| **Majors** | rows in `education_majors` (+ mappings as on develop) | academia copy |
| **Courses** | rows in `education_courses` (+ `target_courses` / mappings as on develop) | academia copy |
| **Institution course links** | wizard step-4 selections for JHU/UCLA etc. | **`institution_wizard_drafts` must be copied** (offerings table alone may be 0) |
| **Countries** | `countries` (dial/catalog + academia) | academia copy / country seed |
| **States** | `geography_states` | academia copy |
| **Cities** | `geography_cities` | academia copy |
| **Institutions tree** | `institutions`, `campuses`, `colleges`, intakes, pictures metadata | academia copy |
| **Default student (lead id 27)** | Lead **`id=27`** + `students_master` **Ishan Ahmed** (`lead_id=27`, email `ishq@erxa.in`) and full related graph: bookings, messages, message_history, candidate_educations, candidate_test_scores, work_experiences, non_academic_activities, digital_presence_links, status_history, conversation audits, aspirations on `students_master` | **Required every full staging refresh:** `python scripts/copy_student_to_staging.py --lead-id 27 --target 'postgresql+psycopg://nexus_et_admin:…@HOST:5432/nexus_edutrust'` (from Windows; default with only `--target` is also lead 27). Verify staging has `leads.id=27` and `students_master` where `lead_id=27`. |

**Primary tool for geography + LMPC + institutions + drafts:**

`python scripts/copy_academia_to_staging.py --target 'postgresql+psycopg://nexus_et_admin:…@HOST:5432/nexus_edutrust'`

(from Windows; password = `npg_…` only). Expect non-zero counts for `levels`, `programs`, `education_majors`, `education_courses`, `countries`, `geography_states`, `geography_cities`, `institutions`, `institution_wizard_drafts`.

Minimum sanity (adjust if catalog grows; **zero is a fail** for a full staging refresh):

```text
users >= 3
navigation_pages >= 20
levels >= 1
programs >= 1
education_majors >= 1
education_courses >= 1
countries >= 1
geography_states >= 1
geography_cities >= 1
institutions >= 1
institution_wizard_drafts >= 1   # if develop has course mappings in drafts
leads id=27 present             # default student lead (Ishan Ahmed)
students_master where lead_id=27 # Ishan Ahmed profile + aspirations
```

---

## G. Release packaging, branch promotion & Alembic (2026-07-26 lessons)

Real misses from the 2026-07-26 staging deploy. Treat each as a **preflight gate** for future releases.

| # | Issue we hit | Prevention / verify |
|---|--------------|---------------------|
| G1 | **Dual migration sources.** Packaging produced both Alembic revisions *and* a consolidated `*_migration.sql`. Running both risks double-apply. | **Alembic is the single source of truth.** Any hand SQL file is **reference/DBA-fallback only** and must say so at the top. On staging run **`alembic upgrade head`** — never the SQL and Alembic together. If SQL was applied by hand, `alembic stamp head` instead of upgrade. |
| G2 | **Branch divergence.** `develop` was behind `staging` (old merge-base); promote was **not** a fast-forward and needed a real merge in the staging worktree. | Before promote: `git fetch`, then `git merge-base origin/staging origin/develop` and `git log --oneline origin/staging..origin/develop` / `origin/develop..origin/staging`. Expect and plan a **merge** (use the `E:\NEXUS-staging` worktree), not a push of `develop:staging`. Resolve/inspect, push `staging` only when clean. |
| G3 | **Multiple Alembic heads risk.** New revisions branched off a mid-chain revision (`c4d7e0f53g6h`) while staging carried many more migrations. | After merge, verify a **single linear head**: `python -m alembic heads` (or scan `down_revision` graph). Must be exactly **1 head, 0 branch points** before deploy. |
| G4 | **`bootstrap_alembic.py` used to break on new revisions.** `ORDERED_REVISIONS` legacy stamp list did not contain post-`s5p8q1r54s0m` revisions → `ValueError: '<rev>' is not in list` inside `deploy.sh`. | **Fixed (2026-07-26):** revisions outside the legacy list skip stamp comparison and fall through to `alembic upgrade head`. On an already-migrated staging DB you can still prefer plain `alembic upgrade head`; `bootstrap_alembic.py` remains safe for both fresh and post-legacy DBs. |
| G5 | **New nav page invisible.** Exception Report (`/reports/exceptions`) shipped but the menu link was missing until `navigation_pages` / `role_page_permissions` were seeded. | **Any new navigation route requires an RBAC seed.** Add the route to `DEFAULT_NAVIGATION_PAGES` + `DEFAULT_ROLE_PAGE_ACCESS`, then run `python scripts/ensure_navigation_rbac.py` as a **mandatory post-deploy step** whenever nav changed. Hard-refresh / re-login to pick it up. |
| G6 | **Debug / PII in logs.** `print()` "radar" dumps (incl. WhatsApp message bodies), a LOGIN DEBUG print, and leftover preview tooling reached the release branch. | QA scan must grep for `print(`, `console.log(`, `breakpoint(`, `pdb`, `TODO/FIXME/HACK`, hardcoded tunnels/IPs, and **PII in logs**. Route diagnostics through `logging`, never stdout message bodies. Re-scan after the final commit. |
| G7 | **Deploy docs must match the real mechanism.** Generic "run the SQL / restart" steps didn't match `deploy.sh` + `bootstrap_alembic.py` + nav seed reality. | `DEPLOYMENT_INSTRUCTIONS.md` must reflect the **actual** path: promote → `deploy.sh` (or manual pull+build) → `alembic upgrade head` → `ensure_navigation_rbac.py` → config/env → restart → verify. Call out G4 explicitly. |

### Promote (develop → staging) — exact sequence

```powershell
# From E:\NEXUS (develop). Staging lives in the E:\NEXUS-staging worktree.
git -C E:\NEXUS push origin develop
git -C E:\NEXUS-staging fetch origin develop staging
git -C E:\NEXUS-staging merge --no-ff origin/develop -m "Merge develop into staging: <release>"
# Resolve if needed, then verify single alembic head BEFORE pushing:
cd E:\NEXUS-staging\backend; python -m alembic heads    # expect exactly 1 head
git -C E:\NEXUS-staging push origin staging
```

### Migrate on the VPS (already-tracked staging DB)

```bash
cd /var/www/nexus/backend && source .venv/bin/activate
alembic upgrade head        # NOT the consolidated SQL; NOT bootstrap on a tracked DB
alembic current             # expect the release head
python scripts/ensure_navigation_rbac.py   # if nav changed (new pages/links)
```

---

## Required staging `.env` shape (verify, don’t dump secrets)

Confirm these **keys** exist and are staging-correct (print names + non-secret values only):

```text
DATABASE_URL=postgresql+psycopg://nexus_et_admin:…@127.0.0.1:5432/nexus_edutrust
# Or Hostinger hPanel DB host instead of 127.0.0.1
ENVIRONMENT=staging
NEXUS_INSTANCE=nexus-dev
FRONTEND_URL=https://nexus-dev.edutrust.in
PUBLIC_TUNNEL_BASE=https://nexus-dev.edutrust.in
NEXUS_TUNNEL_ENABLED=false
NEXUS_PORT=8002
NEXUS_BIND_HOST=127.0.0.1

# SMTP (downtime alerts)
SMTP_HOST=…
SMTP_PORT=465
SMTP_USE_TLS=true
SMTP_USER=…
SMTP_PASSWORD=***
SMTP_FROM_EMAIL=…

# R2 staging-only bucket
R2_ACCOUNT_ID=…
R2_ENDPOINT_URL=https://<account>.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=***
R2_SECRET_ACCESS_KEY=***
R2_BUCKET_NAME=nexus-edutrust-staging
R2_PUBLIC_BASE_URL=…   # private S3 host OK → app uses media proxy
```

**Forbidden on staging:** develop `DATABASE_URL`, ngrok/`trycloudflare` public bases, `NEXUS_TUNNEL_ENABLED=true`, develop R2 bucket name `nexus-edutrust` (unless intentionally sharing — default is isolated staging bucket).

---

## Deployment runbook (agent must execute / instruct in this order)

### 1. Preflight (before code push)

- [ ] Confirm target branch `staging` and VPS path `/var/www/nexus`
- [ ] Confirm Hostinger KVM 1 Postgres (`nexus_edutrust` / `nexus_et_admin`) — not develop Neon or old staging Neon
- [ ] Confirm local develop `.env` will not be overwritten
- [ ] **Branch divergence (G2):** `git fetch` + check `git merge-base` / `git log origin/staging..origin/develop` — expect a **merge**, not fast-forward
- [ ] **Single Alembic head (G3):** after merging, `python -m alembic heads` → exactly 1 head, 0 branch points
- [ ] **One migration source (G1):** deploy via `alembic upgrade head`; any `*_migration.sql` is fallback-only, never both
- [ ] **Nav changes (G5):** if new routes/pages, they are in `DEFAULT_NAVIGATION_PAGES` + `DEFAULT_ROLE_PAGE_ACCESS`, and `ensure_navigation_rbac.py` is in the deploy plan
- [ ] **QA scan (G6):** no `print(` / `console.log` / debug / PII-in-logs / hardcoded tunnels or IDs left in the diff
- [ ] List new Alembic revisions since last staging deploy; note if DB is empty → bootstrap path

### 1b. Promote develop → staging (G2)

- [ ] Push `develop`; merge `origin/develop` into the `E:\NEXUS-staging` worktree (`--no-ff`)
- [ ] Verify single Alembic head (G3) **before** pushing `staging`
- [ ] Push `staging` only when merge is clean

### 2. Code deploy

- [ ] Pull/promote to staging; run Hostinger deploy script if used
- [ ] **Migrations (G1/G4):** on a tracked staging DB prefer **`alembic upgrade head`** (not the SQL). `bootstrap_alembic.py` (used by `deploy.sh`) now tolerates post-legacy revisions and falls through to upgrade head — no longer crashes with `ValueError: '<rev>' is not in list`.
- [ ] **`alembic current`** → matches the release head
- [ ] **Nav RBAC (G5):** `python scripts/ensure_navigation_rbac.py` if nav changed; hard-refresh / re-login
- [ ] `sudo systemctl restart nexus-backend` after env or code changes
- [ ] Wait until `curl -sS http://127.0.0.1:8002/` succeeds

### 3. Fresh or empty DB?

If empty / new Neon:

- [ ] `python scripts/bootstrap_alembic.py`
- [ ] `python scripts/seed_staging_users.py --password '<real>'`
- [ ] Seed navigation RBAC (`ensure_navigation_rbac` / nav pages + role permissions)
- [ ] Seed business profile + `dynamic_settings` + countries (company settings)
- [ ] Copy academia from develop including **wizard drafts**:  
  `python scripts/copy_academia_to_staging.py --target 'postgresql+psycopg://…'`  
  (from Windows; password = `npg_…` only)
- [ ] Copy **default student lead id 27** (Ishan Ahmed + related data):  
  `python scripts/copy_student_to_staging.py --lead-id 27 --target 'postgresql+psycopg://…'`  
  Verify: `SELECT id,email FROM leads WHERE id=27` and `SELECT id,first_name,last_name,lead_id FROM students_master WHERE lead_id=27`

If DB already populated: only migrate + selective seeds; don’t blind truncate production-like data.

### 4. Auth / shell UI smoke

- [ ] Login 200 for a known admin
- [ ] Header mega-nav shows modules (not empty)
- [ ] `/settings` loads business profile + settings (not blank / not 403)
- [ ] `permissions/my-role` returns many routes, not only `/`

### 5. Academia smoke

- [ ] Institutions list shows expected schools (e.g. JHU, UCLA)
- [ ] Wizard step 4 still has Levels/Programs/Majors/Courses mappings (drafts copied)
- [ ] Geography countries/states/cities present

### 5b. Default student smoke (lead id 27)

- [ ] Lead `id=27` exists on staging (`ishq@erxa.in` / Ishan profile)
- [ ] `students_master` row with `lead_id=27` (Ishan Ahmed) including aspirations
- [ ] Related rows present (e.g. candidate_educations / test_scores / messages for `lead_id=27`)

### 6. R2 smoke

- [ ] Python: `settings.R2_BUCKET_NAME == 'nexus-edutrust-staging'` and `r2_configured True`
- [ ] Probe `put_object` to staging bucket succeeds
- [ ] Upload one logo in UI → object appears under `{slug}/logo/` in **staging** bucket (not only under `backend/uploads/`)
- [ ] If file only under `uploads/`, R2 was skipped — fix env/restart/re-upload

### 7. WhatsApp / public URL

- [ ] `PUBLIC_TUNNEL_BASE` / webhook callback = `https://nexus-dev.edutrust.in/...`
- [ ] Webhook verify via loopback if needed; Meta ownership as expected
- [ ] No develop tunnel URL left in staging env

### 8. Monitoring

- [ ] SMTP configured; monitoring settings Active + staging uptime URL + alert emails
- [ ] Optional: trigger a test or confirm service logs don’t say “SMTP is not configured”

### 9. Close-out report

Return a short report:

1. What changed (code / env / DB)
2. Checklist results (pass/fail per section)
3. Remaining risks
4. Any secrets that were exposed → rotate reminder
5. Exact commands the operator still must run manually (if any)

---

## Quick command pack (VPS)

```bash
cd /var/www/nexus/backend && source .venv/bin/activate

# Env sanity (redact secrets)
grep -E '^(DATABASE_URL|ENVIRONMENT|NEXUS_INSTANCE|FRONTEND_URL|PUBLIC_TUNNEL|NEXUS_TUNNEL_ENABLED|R2_BUCKET|SMTP_HOST|SMTP_PORT)=' .env \
  | sed -E 's#(://[^:]+:)[^@]+@#\1***@#; s/(PASSWORD|SECRET|KEY)=.*/\1=***/'

sudo systemctl restart nexus-backend
sleep 5
curl -sS http://127.0.0.1:8002/ | head -c 300

# Counts
python - <<'PY'
from sqlalchemy import text
from app.db.database import SessionLocal
from app.db.register_models import register_all_models
register_all_models()
db = SessionLocal()
for t in [
  "users","navigation_pages","role_page_permissions","businesses","dynamic_settings",
  "countries","institutions","campuses","colleges","institution_wizard_drafts",
  "institution_course_offerings","levels","programs","education_majors","education_courses",
]:
    try:
        print(t, db.execute(text(f'SELECT COUNT(*) FROM {t}')).scalar())
    except Exception as e:
        db.rollback()
        print(t, "ERR", e)
try:
    print("lead_27", db.execute(text("SELECT id, email, full_name FROM leads WHERE id=27")).fetchone())
    print("student_lead_27", db.execute(text(
        "SELECT id, first_name, last_name, email, lead_id FROM students_master WHERE lead_id=27"
    )).fetchone())
    print("msgs_lead_27", db.execute(text("SELECT COUNT(*) FROM messages WHERE lead_id=27")).scalar())
except Exception as e:
    db.rollback()
    print("lead_27 ERR", e)
db.close()
PY

# R2
python - <<'PY'
from app.config import settings
print("bucket", settings.R2_BUCKET_NAME)
print("configured", bool(settings.R2_ACCOUNT_ID and settings.R2_ACCESS_KEY_ID and settings.R2_SECRET_ACCESS_KEY and settings.R2_BUCKET_NAME))
PY
```

## Quick command pack (Windows — academia + default student lead 27)

```powershell
cd E:\NEXUS\backend
.\.venv\Scripts\Activate.ps1
$target = "postgresql+psycopg://nexus_et_admin:YOUR_PASSWORD@YOUR_VPS_IP_OR_DB_HOST:5432/nexus_edutrust"

python scripts/copy_academia_to_staging.py --target $target
# Expect institution_wizard_drafts: N rows

python scripts/copy_student_to_staging.py --lead-id 27 --target $target
# Expect lead 27 + Ishan Ahmed students_master + messages/educations/test scores/etc.
```

---

## Definition of done

Staging deploy is **not done** until:

1. API health OK on `:8002` and public site loads  
2. Admin can log in (seeded Nexus users)  
3. Top nav is visible (navigation RBAC seeded) — **including any new pages from this release (G5)**  
4. Settings/company profile loads  
5. **SMTP configured** and monitoring Active + staging uptime URL + `ALERT_EMAIL`  
6. **Default data present:** Levels, Programs, Majors, Courses, Countries, States, Cities, institutions + wizard drafts (course mappings)  
7. **Default student lead id 27** copied (Ishan Ahmed + related lead/profile data)  
8. R2 staging bucket receives a test upload  
9. WhatsApp public URL points at `nexus-dev.edutrust.in` (not a tunnel)  
10. **`alembic current` == release head, single head (G1/G3)**, and the consolidated SQL was **not** run alongside Alembic  

If any item fails, **do not** report success — fix or list blockers with the exact command to run next.

---

## H. 2026-08-08 BAU burn — mandatory hard gates

~2 hours of post-deploy firefighting. These are now **hard failures** in `hostinger-staging.sh` → `verify-staging-deploy.sh` → `scripts/staging_post_deploy_smoke.py`.

| # | Issue we hit | Prevention / verify |
|---|--------------|---------------------|
| H1 | **Booking WhatsApp Failed** while AI Active “worked”. Free-form session msgs ≠ booking UTILITY templates. Templates lived on **test** WABA only; staging sends from **business** WABA. Language `en_US` vs Meta `en`. | Smoke checks Meta for `et_booking_confirmation` / `et_booking_assigned` on **BUSINESS** WABA, **APPROVED**, language matches `*_TEMPLATE_LANGUAGE`. Register with `register_whatsapp_booking_templates.py` against business WABA. |
| H2 | **TOEFL capture HTTP 500** — `UniqueViolation candidate_test_scores_pkey` (sequence stuck at 1 after imported rows). | Deploy runs `ensure_id_sequences.py`. Smoke fails if sequence ≤ MAX(id). |
| H3 | **verify-staging-deploy.sh was non-blocking** (`\|\| true`) so “Deploy complete” lied. | Deploy **exits 1** if verify/smoke fails. Do not wrap with `\|\| true`. |
| H4 | **Env drift** (local FRONTEND_URL, tunnel flags, missing booking template language keys). | Critical env EMPTY/MISSING/PLACEHOLDER fails deploy. |
| H5 | **UI markers missing** in `frontend/dist` after partial deploys. | Dist must contain Book Appointment, Future Insights, ROI, Aspirations, Exception Report. |
| H6 | **UAT was page-load only** — never exercised notify dict or TOEFL POST. | `uat/tests/07-post-deploy-gates.spec.ts` + `npm run smoke:staging`. |

### Mandatory post-deploy (VPS)

```bash
sudo bash /var/www/nexus/backend/deploy/hostinger-staging.sh
# must end with exit 0 — if not, BAU is blocked on purpose

cd /var/www/nexus/backend && source .venv/bin/activate
python scripts/staging_post_deploy_smoke.py --base-url https://nexus-dev.edutrust.in
```

Put smoke credentials on the server `.env` (never commit):

```text
STAGING_SMOKE_EMAIL=…
STAGING_SMOKE_PASSWORD=…
STAGING_SMOKE_PHONE=+91…   # optional; enables candidate WhatsApp path
```

### Pre-BAU UAT (laptop)

```powershell
cd E:\NEXUS\uat
# UAT_BASE_URL=https://nexus-dev.edutrust.in in .env
npm run test:gates
npm run smoke:staging
```
