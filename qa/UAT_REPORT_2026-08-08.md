# Nexus UAT Report — 8 August 2026 (LOCAL)

## Execution

| Item | Value |
| --- | --- |
| Target | LOCAL — `http://127.0.0.1:5175` (API `:8002`) |
| Suite | `uat/` Playwright — 32 cases (`npm test`) |
| Lead fixture | `UAT_LEAD_ID=27` |
| Operator | Super Admin (`UAT_EMAIL` from `uat/.env`) |
| Result artifacts | `uat/reports/html/index.html`, `uat/reports/results.json`, `uat/reports/summary.md` |
| Generated | 2026-08-08T05:20:47Z |

## UAT Summary

| Status | Count |
| --- | ---: |
| Passed | 30 |
| Failed | 0 |
| Skipped | 2 |
| Total | 32 |

### Cases

- **PASSED** — authenticate as UAT counsellor / admin (setup)
- **PASSED** — Auth & shell — dashboard shell (not login)
- **PASSED** — Auth & shell — AI Active route
- **PASSED** — Auth & shell — My Bookings route
- **PASSED** — All Prospects page loads
- **PASSED** — known UAT lead profile route opens candidate detail
- **PASSED** — candidate profile tabs on Counselling Students profile
- **PASSED** — Aspirations and Personal tabs render editable surfaces
- **PASSED** — Academia tab exposes education history
- **PASSED** — My Bookings surfaces booking cards / empty-state
- **PASSED** — University Shortlist tab reachable
- **PASSED** — Generate shortlist produces multi-category scores
- **SKIPPED** — Safe / Target / Reach band filtering *(no shortlist institutions to filter for lead 27 on this run)*
- **PASSED** — weight profiles API reachable
- **PASSED** — Counselling schedule dashboard loads
- **PASSED** — My Bookings past / today / upcoming sections
- **PASSED** — period agenda / calendar navigation on counselling
- **PASSED** — booking interaction surfaces (session / journey)
- **PASSED** — schedule grid bookable / pending surfaces
- **PASSED** — View Interaction communication trail
- **PASSED** — AI Active queue contact-status controls
- **PASSED** — Handoffs queue page
- **PASSED** — Messaging Hub reachable
- **PASSED** — known UAT lead journey timeline
- **PASSED** — Exception Report reachable
- **PASSED** — AI Active contact-status filter
- **PASSED** — SIT — mandatory profile surfaces
- **PASSED** — SIT — Aspirations preference inputs
- **PASSED** — SIT — shortlist category breakdown / band filters after generation
- **SKIPPED** — SIT — Fit score UI bounds 0–100 *(depends on shortlist rows; skipped when empty)*
- **PASSED** — SIT — counsellor dashboard calendar / pending digest
- **PASSED** — SIT — My Bookings session notes / interaction preview

## UAT harness updates made during this run

Login UI and profile tab labels changed since the last UAT; harness was aligned (not product weakened):

1. `uat/src/helpers/auth.ts` — expect **Sign in to Nexus Intel** / **Sign In** (was “NEXUS Login” / “Sign in to Nexus”).
2. `uat/tests/01-auth-shell.spec.ts` — same login heading check.
3. Profile tab **Personal** (was “PERSONAL PROFILE”) in `02-student-profile.spec.ts` and `sit/01-screen-sit.spec.ts`.

## Scope covered by automation (existing 32)

Auth/shell · Student profile · University matching / shortlist · Appointment booking / counselling schedule · WhatsApp counselling queues · SIT screens (profile, shortlist, counsellor dashboard).

## Delta since last UAT — new modules & enhancements (manual / partial coverage)

These landed after the previous UAT baseline and are **not all fully covered** by the 32 Playwright cases yet. Recommended follow-up cases are noted.

### Navigation & product modules

| Area | What changed | UAT coverage today |
| --- | --- | --- |
| **Book Appointment** | New Appointments submenu → `/book-appointment`; staff booking with week matrix, purposes from settings, existing/new candidate, contact duplicate checks | Partial via schedule / My Bookings cases; **no dedicated Book Appointment page case yet** |
| **IntelX** | Top-nav Intel module (country intel / scrapers / AI chat) | Not in Playwright suite |
| **FlowX** | Operational enrollment / pathway / SLA workflows | Not in Playwright suite |
| **Login / brand** | Nexus Intel + FlowX Operational Core login redesign | Covered (auth setup) |
| **Intake session workspace** | Wider session drawer; tabs: Aspirations, Shortlist, Personal, Academia, … Profile Pulse | Profile/SIT cases updated for **Personal** |
| **Future Insights** | Session tab with habitat / metro insight packs | Not automated |
| **ROI Calculator** | Session tab with FX conversion for NPV / investment | Not automated |

### Booking & notifications

| Enhancement | Notes | Suggested UAT |
| --- | --- | --- |
| Multi-channel staff-book notifications | Candidate + counsellor WhatsApp & email; channel isolation | Manual: book → check notification_logs + inboxes |
| WhatsApp **utility templates** | `et_booking_confirmation` / `et_booking_assigned` for outside 24h window | Manual after Meta **APPROVED** |
| Email deliverability | Display name, Message-ID, HTML alternative, less spammy subject | Manual: candidate external mailbox (spam vs inbox) |
| Staff book supersedes prior actives | Cancels older PENDING/SCHEDULED; syncs `consultation_scheduled_at` | Manual: multiple books then WhatsApp “my appointment” |
| WhatsApp reschedule uses **latest** booking | Fixes stale `consultation_scheduled_at` summary | Manual: Reschedule → expect current slot |
| Reschedule time-slot regression | `reschedule_in_progress` no longer cleared on begin; date → time menu | Manual: Reschedule → pick date → **must** get time list |

### Data integrity

| Enhancement | Notes | Suggested UAT |
| --- | --- | --- |
| `students_master.email` → `leads.email` (+ bookings) | Sync on profile/full save; 409 on duplicate lead email | Manual: edit Personal email → verify Leads row |

### Backend / ops (observed during period)

- Local `.env` bloat recovery (dev stack hang) — ops hygiene, not product UAT.
- Duplicate uvicorn on `:8002` — keep a single backend process for stable UAT.

## Recommended next UAT cases (add to `uat/tests/`)

1. Navigate **Appointments → Book Appointment**; create booking for lead 27; assert success + channel status UI.
2. Open session workspace → **Future Insights** / **ROI Calculator** tabs render with aspirations countries.
3. Smoke **IntelX** and **FlowX** landing routes for Super Admin (RBAC).
4. After staff book outside 24h WhatsApp window: assert template path (or clear failure message if template PENDING).
5. WhatsApp reschedule E2E (date list → time list → confirm) against lead 27.

## Addendum — new-module UAT executed (same day)

The first pass of this report only ran the baseline 32 cases and listed IntelX / FlowX / Session / Future Insights / ROI / Book Appointment as **recommended** follow-ups — they were **not** executed then.

A dedicated suite was added and run:

```
uat/tests/06-new-modules.spec.ts
npx playwright test tests/06-new-modules.spec.ts
```

| Status | Count |
| --- | ---: |
| Passed | 14 |
| Failed | 0 |
| Skipped | 0 |
| Total | 14 |

### Cases executed

**IntelX**
- PASSED — Knowledge Hub (`/nexus-intel/knowledge`)
- PASSED — AI Assistant (`/nexus-intel/ai-assistant`)
- PASSED — Workflows (`/nexus-intel/workflows`)

**FlowX**
- PASSED — Ops Dashboard (`/flowx/ops`)
- PASSED — Student Journeys (`/flowx/journeys`)
- PASSED — Country Workflows (`/flowx/countries`)
- PASSED — Master Workflow (`/flowx/master`)

**Book Appointment**
- PASSED — Staff booking form (`/book-appointment`)

**Intake Session workspace** (booking `UAT_BOOKING_ID=101` / lead 27)
- PASSED — Tabs present: Session, Aspirations, Future Insights, ROI Calculator
- PASSED — Aspirations editable surface
- PASSED — Session notes / status surface
- PASSED — Future Insights tab content (or aspirations prerequisite message)
- PASSED — ROI Calculator tab content (or aspirations prerequisite message)

Combined with baseline: **44 cases defined** (32 baseline + 14 new-module); latest new-module run **14/14 green**.

## Verdict

**LOCAL UAT: PASS** for baseline (30/32 green, 2 data skips) **and** new-module suite (14/14 green).

Harness adapted to Nexus Intel login and Personal tab; new-module Playwright coverage added for IntelX, FlowX, Book Appointment, and Session workspace tabs.
