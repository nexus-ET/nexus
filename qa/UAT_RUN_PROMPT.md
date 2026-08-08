# Nexus UAT — Run Prompt (45 Playwright entries = 1 setup + 44 cases)

Case catalog for the next run: [`uat/CASE_CATALOG.md`](../uat/CASE_CATALOG.md).

Two ways to use this file:

- **Simple prompt** — paste the one-liner below into a Cursor chat.
- **Full prompt** — paste the fenced block under "Full agent prompt" for guided run + auto-fix + summary.

---

## Simple prompt (paste this next time)

```
Run the Nexus UAT suite per qa/UAT_RUN_PROMPT.md and uat/CASE_CATALOG.md.
Ask me LOCAL or STAGING first, run all 44 application cases (+ auth setup),
and end with the pasted UAT Summary table.
```

---

## Quick commands (no agent)

```powershell
cd E:\NEXUS\uat
npm test
npm run summary
```

- LOCAL: `uat/.env` → `UAT_BASE_URL=http://127.0.0.1:5175` (dev stack must be running on :5175 / :8002)
- STAGING: `uat/.env` → `UAT_BASE_URL=https://nexus-dev.edutrust.in` (restore to local after)

---

## Full agent prompt

```
Run the full Nexus UAT suite (45 Playwright entries: auth setup + 44 cases
listed in uat/CASE_CATALOG.md, including IntelX, FlowX, Book Appointment,
and Session / Aspirations / Future Insights / ROI) and report results.

## Target
Ask me first: LOCAL or STAGING.
- LOCAL   → uat/.env must have UAT_BASE_URL=http://127.0.0.1:5175
- STAGING → uat/.env must have UAT_BASE_URL=https://nexus-dev.edutrust.in

If STAGING: change UAT_BASE_URL for the run, then restore it to the local
value when finished. Never commit uat/.env or print UAT_PASSWORD.

## Preconditions
- LOCAL only: dev stack must already be running (frontend :5175, backend :8002).
  If run_dev.py reports "dev stack already running (pid N)", that is fine —
  verify :5175 and :8002 respond and do NOT start a second instance.
- uat/.env has UAT_BASE_URL, UAT_EMAIL, UAT_PASSWORD, UAT_LEAD_ID, UAT_BOOKING_ID.
  UAT_LEAD_ID must be a lead that exists on the target with a counselling booking.
  UAT_BOOKING_ID is required for Session / Future Insights / ROI cases.
- Do not invent credentials. If uat/.env is missing values, stop and tell me.

## Run
cd E:\NEXUS\uat
npm test
npm run summary

## On failure
Distinguish the two cases and say which:
1. Product bug  → fix the root cause in app code (not the test), re-run to green.
2. Environment/data gap (empty shortlist, missing booking, slow staging nav)
   → explain it, do not mask it by weakening an assertion.

Known context so you don't rediscover it:
- JWT lives in sessionStorage; storageState mirrors it to localStorage
  (uat/src/helpers/auth.ts). Do not "fix" this.
- Full profile + SHORTLIST tab route is /students/counselling/:leadId
- Generate Shortlist may need click({ force: true }) — sticky footer intercepts.
- Staging is slower than local; gotoAppPath already retries once.

## Required output
End your reply with a pasted UAT Summary — do not just link to files:

## UAT Summary
Target: <local | staging URL>
| Status | Count |
| --- | ---: |
| Passed | N |
| Failed | N |
| Skipped | N |
| Total | N |

### Cases
- PASSED — ...
- FAILED — ... (with one-line reason)
- SKIPPED — ... (with why)

HTML: uat/reports/html/index.html
JSON: uat/reports/results.json
```

---

Related: full 5-phase pre-staging gate is in `qa/PRE_STAGING_AGENT_PROMPT.md`.
