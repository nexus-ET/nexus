# Staging config requirements

**Do not copy this into `.env` automatically.** Apply keys manually on the Staging server (`nexus-dev` / Hostinger) after review.  
**Never overwrite** staging `/var/www/nexus/backend/.env` with develop tunnel/ngrok values, and never overwrite local develop `.env` with staging Neon URLs.

---

## 2026-08-08 additions (IntelX / FlowX / Book Appointment / Session)

New runtime code ships with **safe defaults** in `app/config.py`. Staging `.env` only needs these if you want to override defaults or enable Meta booking templates.

| Key | Required? | Notes |
|-----|-----------|--------|
| `SMTP_FROM_NAME` | Optional | Display name for outbound mail (code default: `Nexus Counselling`) |
| `WHATSAPP_BOOKING_TEMPLATE` | Recommended for WA confirms outside 24h | Default `et_booking_confirmation` — must be **APPROVED** in Meta |
| `WHATSAPP_BOOKING_TEMPLATE_LANGUAGE` | With template | Prefer `en` (registration default). App now resolves Meta's exact code if `en_US` is set but only `en` exists. |
| `WHATSAPP_ADMIN_BOOKING_TEMPLATE` | Recommended | Default `et_booking_assigned` — Meta **APPROVED** |
| `WHATSAPP_ADMIN_BOOKING_TEMPLATE_LANGUAGE` | With template | Prefer `en`. Same auto-resolve as candidate template. |
| `INTEL_SCRAPER_BROWSER_FALLBACK` | Optional | Default `true` for Cloudflare/JS scraper sites |

**Post-deploy seeds (not `.env`):**

```bash
cd /var/www/nexus/backend && source .venv/bin/activate
python scripts/ensure_navigation_rbac.py
# Nav routes: /book-appointment, /nexus-intel, /flowx
# hostinger-staging.sh now runs this automatically after migrations.
```

**Booking notification smoke (after deploy):** Book Appointment should return per-channel status. If WhatsApp is `failed` with template language errors, fix `*_TEMPLATE_LANGUAGE` on the server `.env` and restart — do not overwrite the whole `.env` from develop.

**Hard post-deploy gate (2026-08-08):** `hostinger-staging.sh` must exit 0. It runs `ensure_id_sequences.py`, then `verify-staging-deploy.sh` → `staging_post_deploy_smoke.py` (Meta booking templates on business WABA, id sequences, optional API TOEFL/booking notify). Set `STAGING_SMOKE_EMAIL` / `STAGING_SMOKE_PASSWORD` on the VPS `.env` for full API gates.
Register WA templates once (from a machine with Meta token configured — usually develop, then reuse names on staging):

```bash
python scripts/register_whatsapp_booking_templates.py
```

---

## Baseline (2026-07-26 and earlier)

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

**IntelX Scraper Admin (Playwright):** Deploy scripts install Chromium / `chrome-headless-shell` via `python -m playwright install chromium`. Staging is **Linux** — there is no Windows Firewall dialog. Backend already binds `127.0.0.1` only. Optional env: `INTEL_SCRAPER_BROWSER_FALLBACK=true` (default).

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
