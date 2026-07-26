# Staging config requirements (2026-07-26 release)

**Do not copy this into `.env` automatically.** Apply keys manually on the Staging server (`nexus-dev` / Hostinger) after review.

This release does **not** introduce new mandatory secrets beyond what Staging already needs for mail and Meta. It **expands how existing settings are used**.

---

## 1. Required / confirm on Staging `.env`

| Key | Required? | Notes |
|-----|-----------|--------|
| `DATABASE_URL` | Yes | Staging Neon URL (psycopg3-compatible; strip `channel_binding` if needed) |
| `ENVIRONMENT` | Yes | Should be staging-like (not develop tunnel settings) |
| `FRONTEND_URL` | Yes | `https://nexus-dev.edutrust.in` (or current Staging front URL) |
| `SMTP_HOST` | Yes for Exception emails | Hostinger / SMTP provider |
| `SMTP_PORT` | Yes for Exception emails | Usually `465` or `587` |
| `SMTP_USE_TLS` | Yes for Exception emails | Match provider (`true`/`false`) |
| `SMTP_USER` | Yes for Exception emails | |
| `SMTP_PASSWORD` | Yes for Exception emails | Never commit |
| `SMTP_FROM_EMAIL` | Yes for Exception emails | From address |
| `META_GRAPH_ACCESS_TOKEN` | Yes for Meta sync | Page/user token with Lead Ads access |
| `META_PAGE_ID` | Yes for Meta sync | |
| `META_LEAD_SYNC_ENABLED` | Recommended | `true` on Staging if sync should run |
| `R2_BUCKET_NAME` | Yes if uploads used | Must be **`nexus-edutrust-staging`** (not develop bucket) |
| Other `R2_*` | As today | Account, keys, public URL for Staging |

**Do not** overwrite Staging `.env` with develop ngrok / tunnel values.

---

## 2. App Settings / DB dynamic keys (no `.env` change required)

These live in application settings (UI: **Admin → Settings** / App Settings). Defaults are seeded by code if missing.

| Key | Default | Purpose for this release |
|-----|---------|---------------------------|
| `ALERT_EMAIL` | _(empty)_ | **Expanded:** now receives Exception Report emails (new OPEN/ERROR/WARNING) and auto-resolve confirmations, in addition to uptime alerts. Set one or more valid emails. |
| `MONITORING_STATUS` | — | Keep `Active` for uptime monitoring |
| `UPTIME_TARGET_URL` | — | Prefer `https://nexus-dev.edutrust.in/` |
| `EXCEPTION_LOG_RETENTION_DAYS` | `90` | Days to keep Exception Report rows before scheduler purge |
| `ADMIN_SESSION_DIGEST_ENABLED` | off/default | Counsellor morning WhatsApp digest (optional) |
| `ADMIN_SESSION_DIGEST_TIME` | — | Local time for digest if enabled |
| `ADMIN_SESSION_NUDGE_ENABLED` | — | Pre-session WhatsApp nudge (optional) |
| `ADMIN_SESSION_NUDGE_MINUTES` | — | Minutes before session |
| `ADMIN_BOOKING_ALERTS_ENABLED` | — | Cancel/reschedule WhatsApp alerts (optional) |

### Manual Staging checklist for alerts

1. Set `ALERT_EMAIL` to ops recipients (comma-separated if supported by UI).
2. Confirm SMTP env keys are present and restart `nexus-backend`.
3. Confirm logs do **not** say SMTP is skipped / not configured.
4. Optionally set Exception retention days in the Exception Report UI.

---

## 3. Optional ops-only env (scripts, not runtime)

Only needed when running copy/seed scripts against Staging:

| Key | Purpose |
|-----|---------|
| `STAGING_DATABASE_URL` | Target DB for copy scripts |
| `STAGING_ADMIN_PASSWORD` | `seed_staging_users.py` |
| `STAGING_USERS_SOURCE_URL` | Optional source for user seed |
| `ACADEMIA_COPY_*` | Academia copy script credentials/URLs |

---

## 4. Not required as new `.env` keys

- Exception Report capture / auto-resolve — uses DB + SMTP + `ALERT_EMAIL`
- Queue `contact_status` / pagination — API query params only
- University matching — DB tables + weight profile seeds from migration
- Period agenda filters — API date range query params

---

## 5. After editing Staging env

```bash
# Restart backend so SMTP / Meta / R2 changes load
sudo systemctl restart nexus-backend   # or your Hostinger process name
# Confirm health
curl -sS -o /dev/null -w "%{http_code}\n" https://nexus-dev.edutrust.in/docs
```
