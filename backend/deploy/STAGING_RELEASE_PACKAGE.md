# Staging release package — 2026-07-26

Lead-engineer packaging for GitHub PR → Staging.  
**No `.env` files were modified.** Config for Staging is listed in `STAGING_CONFIG_REQUIREMENTS.md`.

---

## Artifacts (this folder)

| File | Purpose |
|------|---------|
| `STAGING_RELEASE_PACKAGE.md` | This summary (PR body source) |
| `STAGING_CONFIG_REQUIREMENTS.md` | Manual Staging env / App Settings checklist |
| `DEPLOYMENT_INSTRUCTIONS.md` | Step-by-step deploy + verification |
| `staging_release_2026-07-26_migration.sql` | Consolidated SQL (prefer Alembic) |
| `STAGING_DEPLOYMENT_AGENT_PROMPT.md` | Hostinger standing checklist (SMTP, seeds, R2) |

---

## Suggested PR title

`Staging release 2026-07-26: Exception Report, queue pagination, university matching, Meta sync hardening`

## Suggested PR body

### Summary
- Exception Report (capture, retention, resolve comments, auto-resolve, email alerts)
- AI Active / Handoffs / All Prospects: pagination, Contact status filter, contact-first sort
- Phase 1 university matching tables + shortlist UI
- Meta lead sync page-token / rate-limit / lock fixes
- Period agenda on My Bookings + Counselling; remove UI preview sample tooling
- Nav: Exception Report → Audit; Leads featured order (All Prospects, Archive)

### Migrations
- `d5e8f1a64h7i` university matching
- `e6x9c2eption01` `exception_logs`
- `f7y0d3esolution` `resolution_comment`
- Head: **`f7y0d3esolution`**

### Test plan
Use Verification Section in `DEPLOYMENT_INSTRUCTIONS.md`.

---

## Feature inventory (this package)

### Exception Report / ops
- Middleware + service + reports APIs
- Frontend Exception Report page, retention UI, global capture
- Auto-resolve (Cursor agent, sync recovery, page refresh patterns)
- Email via SMTP → `ALERT_EMAIL`

### Lead experience
- Queue `limit`/`offset`/`contact_status`
- Viewing range labels; pagination top/bottom
- Prospects Recently replied = inbound replies only

### University matching
- Profiles + runs + items; counselling shortlist endpoints; profile tab

### Meta sync
- Prefer `/{page_id}?fields=access_token`; cache; avoid burning app quota on `/me/accounts`
- Advisory lock recovery

### Appointments / journey
- Period agenda shell
- Student Journey panel UX refresh (existing status_history / journey APIs)

### Status tracking note
- No new status_definitions migration in this package
- Journey/status verification remains critical after intake reset and counselling flows

---

## Conflicts & risks (scan results)

| Issue | Severity | Resolution |
|-------|----------|------------|
| Large uncommitted surface (~80+ files) vs `origin/develop` | High process | One focused PR; exclude secrets/dist/cache |
| `ui_preview_samples` leftover after UI banner removal | Medium | Removed (routes/schema/service) in QA cleanup |
| `LOGIN DEBUG` print in `login.py` | Low/Med | Removed in QA cleanup |
| Twilio “radar” prints dumping message bodies in `api/v1/leads.py` | Medium (PII in logs) | Replaced with `logger` (no message body) |
| Residual `print` in Meta webhook / messaging paths | Low | Operational diagnostics; optional follow-up to standardize on `logger` |
| Hand SQL vs Alembic double-apply | High if both | Prefer Alembic only; stamp if SQL used |
| Staging `.env` overwritten by develop tunnel values | High | Never copy develop `.env`; use requirements doc |
| R2 bucket mix-up (`nexus-edutrust` vs staging) | High | Staging must use `nexus-edutrust-staging` |
| Exception emails silent without SMTP | Medium | Confirm SMTP + `ALERT_EMAIL` after restart |
| Nav Exception Report missing until RBAC seed | Medium | Run `ensure_navigation_rbac.py` |
| Matching FKs require existing `institutions` / offerings | Medium | Academia seed/copy if Staging empty |
| Cursor exception-resolution rule assumes Staging has auto-resolve API | Low | Deploy backend before relying on agent auto-resolve |

### Do not ship
- `backend/.env`, `frontend/.env`
- `backend/.dev-stack.lock`
- `__pycache__`, `.pytest_cache`, `frontend/dist` (unless your Hostinger pipeline builds on server)

---

## QA cleanup performed for this package

1. Removed UI preview sample banner (frontend) and backend leftover routes / `UiPreviewSamplesResponse` / `ui_preview_samples.py`.
2. Removed `LOGIN DEBUG` stdout from login failure path.
3. Quieted Twilio outbound/inbound debug in `app/api/v1/leads.py` (no message-body dumps to stdout).
4. Confirmed Exception Log + university matching models registered; reports router mounted; frontend Exception Report + Student Journey panel wired.

Re-scan after your final commit before merge.
