# Nexus UAT (Playwright + TypeScript)

Pre-staging User Acceptance Testing for core Nexus workflows:

- Auth / shell access
- Student profile surfaces
- University matching score generation & shortlist results
- Appointment booking / counselling schedule
- WhatsApp counselling queue & journey / exception visibility
- Screen-by-screen SIT (`tests/sit/`) — profile, shortlist, counsellor dashboard
- New modules (`tests/06-new-modules.spec.ts`) — IntelX, FlowX, Book Appointment, Session workspace (Aspirations, Future Insights, ROI Calculator)
- Post-deploy gates (`tests/07-post-deploy-gates.spec.ts`) — booking notify + TOEFL save + critical routes (2026-08-08 BAU burns)

Full 5-phase pre-staging gate (SIT + Pytest + WhatsApp mocks + RBAC + E2E/load):
see `qa/PRE_STAGING_AGENT_PROMPT.md` and `qa/run_pre_staging.ps1`.

## Setup

```powershell
cd E:\NEXUS\uat
npm install
npx playwright install chromium
copy .env.example .env
# Edit .env — set UAT_PASSWORD (required)
```

### Local development (default)

1. Start the local stack (backend `:8002`, frontend `:5175`), e.g. `python scripts/run_dev.py --no-tunnel` from `backend/`.
2. In `uat/.env`:

```env
UAT_BASE_URL=http://127.0.0.1:5175
UAT_EMAIL=ishq@edutrust.in
UAT_PASSWORD=your-local-password
UAT_LEAD_ID=27
```

The Vite app proxies `/api` to the local backend, so Playwright only needs the frontend origin.

### Staging

```env
UAT_BASE_URL=https://nexus-dev.edutrust.in
```

## Case catalog

Full numbered list of the **47 application cases** (+ auth setup): [`CASE_CATALOG.md`](./CASE_CATALOG.md).

## Run (headless)

```powershell
cd E:\NEXUS\uat
npm test
npm run summary
```

Expect **48** Playwright entries (1 setup + 47 cases). Reports:

| Artifact | Path |
|----------|------|
| HTML | `uat/reports/html/index.html` |
| JSON | `uat/reports/results.json` |
| Markdown summary | `uat/reports/summary.md` |

```powershell
npm run test:report
```

### Staging smoke (API + Meta templates + DB sequences)

```powershell
cd E:\NEXUS\uat
npm run smoke:staging
```

Or:

```powershell
cd E:\NEXUS\backend
.\.venv\Scripts\python.exe scripts\staging_post_deploy_smoke.py --base-url https://nexus-dev.edutrust.in
```

On the VPS, `hostinger-staging.sh` runs `verify-staging-deploy.sh`, which **fails the deploy** if this smoke is red.

## Environment

| Variable | Purpose |
|----------|---------|
| `UAT_BASE_URL` | App under test (local default `http://127.0.0.1:5175`) |
| `UAT_EMAIL` | Login email |
| `UAT_PASSWORD` | Login password |
| `UAT_LEAD_ID` | Known lead for profile / journey / shortlist checks (default `27`) |
| `UAT_BOOKING_ID` | Optional session workspace booking |

## Constraint note

This package **executes and reports** only. Failures are recorded as-is; do not treat this suite as an automatic fixer for application defects.
