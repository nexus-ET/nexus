# Nexus UAT — Case catalog (save for next run)

**Suite size:** 45 Playwright entries = **1 auth setup** + **44 application cases**.  
**Command:** `cd E:\NEXUS\uat` → `npm test` → `npm run summary`  
**Env:** `uat/.env` — `UAT_BASE_URL`, `UAT_EMAIL`, `UAT_PASSWORD`, `UAT_LEAD_ID=27`, `UAT_BOOKING_ID` (session workspace).

Do not commit secrets. Keep this catalog in sync when adding/removing specs under `uat/tests/`.

---

## Setup (1)

| # | File | Case |
| ---: | --- | --- |
| S1 | `tests/auth.setup.ts` | authenticate as UAT counsellor / admin |

---

## Auth & shell (3) — `tests/01-auth-shell.spec.ts`

| # | Case |
| ---: | --- |
| 1 | authenticated session reaches dashboard shell (not login) |
| 2 | AI Active route is reachable under authenticated session |
| 3 | My Bookings route is reachable under authenticated session |

---

## Student profile (5) — `tests/02-student-profile.spec.ts`

| # | Case |
| ---: | --- |
| 4 | All Prospects page loads prospect list / detail shell |
| 5 | known UAT lead profile route opens candidate detail |
| 6 | candidate profile tabs are available on Counselling Students profile |
| 7 | Aspirations and Personal Profile tabs render editable student info surfaces |
| 8 | Academia tab exposes education history for matching inputs |

---

## University matching & shortlist (5) — `tests/03-university-matching-shortlist.spec.ts`

| # | Case |
| ---: | --- |
| 9 | My Bookings surfaces booking cards or empty-state messaging |
| 10 | University Shortlist tab is reachable from counselling student profile |
| 11 | Generate shortlist produces multi-category matching scores (Academic, Profile, Aspirations, Safety) |
| 12 | Shortlisted institutions support Safe / Target / Reach band filtering |
| 13 | weight profiles API surface is reachable for matching configuration |

---

## Appointment booking (6) — `tests/04-appointment-booking.spec.ts`

| # | Case |
| ---: | --- |
| 14 | Counselling schedule dashboard loads |
| 15 | My Bookings grouped sections (past / today / upcoming) are present |
| 16 | period agenda / calendar navigation controls render on counselling |
| 17 | booking interaction surfaces (session / journey) are available when bookings exist |
| 18 | schedule grid exposes bookable slot / pending appointment surfaces for counselors |
| 19 | View Interaction opens counselor communication trail for WhatsApp/notification audit |

---

## WhatsApp counselling (6) — `tests/05-whatsapp-counseling.spec.ts`

| # | Case |
| ---: | --- |
| 20 | AI Active queue page loads lead/contact status controls |
| 21 | Handoffs queue page loads |
| 22 | Messaging Hub is reachable for WhatsApp conversation management |
| 23 | known UAT lead exposes journey timeline (status tracking tied to outreach) |
| 24 | Exception Report (ops visibility for WhatsApp/Meta sync failures) is reachable |
| 25 | AI Active contact-status filter supports WhatsApp outreach triage |

---

## New modules (13) — `tests/06-new-modules.spec.ts`

### IntelX (3)

| # | Case |
| ---: | --- |
| 26 | IntelX Knowledge Hub loads |
| 27 | IntelX AI Assistant page loads |
| 28 | IntelX Workflows page loads |

### FlowX (4)

| # | Case |
| ---: | --- |
| 29 | FlowX Ops Dashboard loads |
| 30 | FlowX Student Journeys page loads |
| 31 | FlowX Country Workflows page loads |
| 32 | FlowX Master Workflow page loads |

### Book Appointment (1)

| # | Case |
| ---: | --- |
| 33 | Book Appointment page renders staff booking form |

### Intake Session workspace (5)

| # | Case |
| ---: | --- |
| 34 | Session workspace exposes Session / Aspirations / Future Insights / ROI tabs |
| 35 | Aspirations tab shows editable consultation aspirations surface |
| 36 | Session tab renders counselling session notes / status surface |
| 37 | Future Insights tab loads insight surface (or aspirations prerequisite) |
| 38 | ROI Calculator tab loads calculator surface (or aspirations prerequisite) |

---

## SIT screens (6) — `tests/sit/01-screen-sit.spec.ts`

| # | Case |
| ---: | --- |
| 39 | Counselling Students profile exposes mandatory profile surfaces |
| 40 | Aspirations tab accepts preference inputs used by matching |
| 41 | Category breakdown and band filters render after generation |
| 42 | Fit score UI stays within displayable bounds (0–100) |
| 43 | Counselling dashboard calendar / pending digest surfaces load |
| 44 | My Bookings supports session notes / interaction preview affordances |

---

## Last known good execution (LOCAL, 2026-08-08)

### Baseline (`npm test` before stack went down) — 32 entries (setup + 31)

| Status | Count | Notes |
| --- | ---: | --- |
| Passed | 30 | Including setup |
| Failed | 0 | After login/Personal-tab harness fixes |
| Skipped | 2 | Data: shortlist band filter; fit score bounds (no institutions) |

### New modules only — 14 entries (setup + 13)

| Status | Count | Notes |
| --- | ---: | --- |
| Passed | 14 | IntelX, FlowX, Book Appointment, Session tabs |
| Failed | 0 | |
| Skipped | 0 | |

### Product rejections / test failures

| Kind | Detail |
| --- | --- |
| **Product bug failures** | **None** on the successful LOCAL runs above |
| **Harness updates (not product rejects)** | Login heading → “Sign in to Nexus Intel”; tab “PERSONAL PROFILE” → “Personal” |
| **Data skips (not failures)** | Case 12 band filtering; case 42 fit score — empty shortlist rows for lead 27 |
| **Environment (later attempt)** | Full 45-run blocked: `ERR_CONNECTION_REFUSED` on `:5175` (frontend down) — restart stack before next run |

---

## Next run checklist

1. Frontend `:5175` and backend `:8002` responding  
2. `uat/.env` populated (`UAT_PASSWORD`, `UAT_LEAD_ID=27`, `UAT_BOOKING_ID` for session cases)  
3. `npm test` then `npm run summary`  
4. Expect **45** Playwright entries (1 setup + 44 cases)  
