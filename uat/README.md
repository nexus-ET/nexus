# Nexus UAT (Playwright + TypeScript)

Pre-staging User Acceptance Testing for core Nexus workflows:

- Auth / shell access
- Student profile surfaces
- University matching score generation & shortlist results
- Appointment booking / counselling schedule
- WhatsApp counselling queue & journey / exception visibility
- Screen-by-screen SIT (`tests/sit/`) — profile, shortlist, counsellor dashboard

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

### Staging (later)

```env
UAT_BASE_URL=https://nexus-dev.edutrust.in
```

## Run (headless)

```powershell
cd E:\NEXUS\uat
npm test
npm run summary
```

Reports:

| Artifact | Path |
|----------|------|
| HTML | `uat/reports/html/index.html` |
| JSON | `uat/reports/results.json` |
| Markdown summary | `uat/reports/summary.md` |

Open HTML report:

```powershell
npm run test:report
```

## Environment

| Variable | Purpose |
|----------|---------|
| `UAT_BASE_URL` | App under test (local default `http://127.0.0.1:5175`) |
| `UAT_EMAIL` | Login email |
| `UAT_PASSWORD` | Login password |
| `UAT_LEAD_ID` | Known lead for profile / journey / shortlist checks (default `27`) |

## Constraint note

This package **executes and reports** only. Failures are recorded as-is; do not treat this suite as an automatic fixer for application defects.
