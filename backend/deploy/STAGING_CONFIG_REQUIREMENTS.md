# Staging config requirements (Hostinger)

**Do not overwrite** local `backend/.env` or commit secrets.  
Apply these changes **manually** on the Hostinger VPS file:

```text
/var/www/nexus/backend/.env
```

Optional local staging worktree: `E:\NEXUS-staging\backend\.env`

Template (no secrets): `backend/deploy/env.staging.example`

---

## Critical — new Neon database: Nexus-Dev-1

Your previous Neon DB hit its limit. Staging must use the **new** Neon project/database:

| Item | Value |
|------|--------|
| Neon DB name | **Nexus-Dev-1** (Staging account only) |
| Used by | Hostinger staging (`nexus-dev.edutrust.in`) only |
| Not for | Local development (`E:\NEXUS\backend\.env`) |

### What to put in staging `.env`

1. Open Neon console → **Nexus-Dev-1** → **Connection details**
2. Choose **Pooled connection**
3. Copy the URI and change the scheme:

| Neon shows | Staging `.env` needs |
|------------|----------------------|
| `postgresql://...` or `postgres://...` | `postgresql+psycopg://...` |

4. Ensure `?sslmode=require` is present (append if missing).

```env
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@ep-XXXX-pooler.REGION.aws.neon.tech/neondb?sslmode=require
```

5. In Neon, allow the Hostinger VPS IP if IP allowlisting is enabled.

### Empty DB bootstrap

Nexus-Dev-1 starts empty. After `DATABASE_URL` is set on the VPS:

```bash
cd /var/www/nexus/backend
source .venv/bin/activate
python scripts/bootstrap_alembic.py
# Fresh DB → alembic upgrade head
alembic current
# Expected head: c4d7e0f53g6h (or whatever `alembic heads` prints after deploy)
```

Or run the full staging deploy (migrations included):

```bash
sudo bash /var/www/nexus/backend/deploy/hostinger-staging.sh
```

---

## Required identity / routing

| Variable | Staging value |
|----------|---------------|
| `NEXUS_INSTANCE` | `nexus-dev` or `staging` (never `development`) |
| `ENVIRONMENT` | `staging` |
| `PUBLIC_TUNNEL_BASE` | `https://nexus-dev.edutrust.in` |
| `FRONTEND_URL` | `https://nexus-dev.edutrust.in` |
| `NEXUS_TUNNEL_ENABLED` | `false` |
| `NEXUS_PORT` | `8002` |
| `NEXUS_BIND_HOST` | `127.0.0.1` |
| `NEXUS_WHATSAPP_AUTO_SYNC` | `true` |

Meta webhook callback:

```text
https://nexus-dev.edutrust.in/api/webhook
```

---

## Required WhatsApp / intake (current product behavior)

| Variable | Staging value | Why |
|----------|---------------|-----|
| `PROVIDER` | `WHATSAPP` | |
| `NEXUS_APPOINTMENTS_ONLY` | `true` | Deterministic intake (degree → major → country → booking) |
| `WHATSAPP_OUTREACH_TEMPLATE` | `et_student_welcome` | Welcome only |
| `WHATSAPP_OUTREACH_SKIP_INTAKE_FOLLOWUP` | `true` | **No** hi/hello continue nudge message |
| `WHATSAPP_OUTREACH_TEMPLATE_LANGUAGE` | `en` | |
| `WHATSAPP_OUTREACH_TEMPLATE_PARAMETERS` | `student,company` | |
| `WHATSAPP_OUTREACH_TEMPLATE_PARAMETER_FORMAT` | `positional` | |
| `WHATSAPP_OUTREACH_COMPANY_NAME` | `Edutrust` | |

Business line (used when `NEXUS_INSTANCE` is staging / nexus-dev):

```env
WHATSAPP_BUSINESS_PHONE_NUMBER=+917411952525
WHATSAPP_BUSINESS_PHONE_NUMBER_ID=1097416893464116
WHATSAPP_BUSINESS_WABA_ID=1312656237246811
```

Also keep valid:

```env
WEBHOOK_VERIFY_TOKEN=<Meta verify token>
WHATSAPP_VERIFY_TOKEN=<same as WEBHOOK_VERIFY_TOKEN>
WHATSAPP_ACCESS_TOKEN=<long-lived token>
SECRET_KEY=<existing staging secret — do not copy from local dev>
```

Meta welcome template body should be **greeting only** (no full-name / continue prompt), for example:

```text
Hi {{1}}! Thanks for reaching {{2}}. We're excited to help you get started with your study abroad plans.
```

Student replies `hi` / `hello` → intake advances to **degree** questions.

---

## Recommended on staging

| Variable | Value | Why |
|----------|-------|-----|
| `SECURITY_AUDIT_ALERT_WHATSAPP_ENABLED` | `false` | Avoid nightly WhatsApp noise |
| `SECURITY_AUDIT_ALERT_MANUAL_ONLY` | `true` | Alerts only on manual Run audit |

---

## Optional — Academia Hub assets (R2)

If institution logos/banners are used on staging:

```env
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=
R2_PUBLIC_BASE_URL=
R2_ENDPOINT_URL=
```

---

## Do NOT copy from local development `.env`

| Variable | Dev (wrong on staging) |
|----------|-------------------------|
| `DATABASE_URL` | Old Neon / local DB (limit reached) |
| `PUBLIC_TUNNEL_BASE` | `*.trycloudflare.com` or `*.ngrok-free.dev` |
| `NEXUS_INSTANCE` | `development` |
| `NEXUS_TUNNEL_ENABLED` | `true` |
| `SECRET_KEY` | Dev secret |

---

## Quick paste block (fill secrets on VPS)

```env
NEXUS_INSTANCE=nexus-dev
ENVIRONMENT=staging
PUBLIC_TUNNEL_BASE=https://nexus-dev.edutrust.in
FRONTEND_URL=https://nexus-dev.edutrust.in
NEXUS_TUNNEL_ENABLED=false
NEXUS_PORT=8002
NEXUS_BIND_HOST=127.0.0.1
NEXUS_APPOINTMENTS_ONLY=true
WHATSAPP_OUTREACH_SKIP_INTAKE_FOLLOWUP=true
WHATSAPP_OUTREACH_TEMPLATE=et_student_welcome
NEXUS_WHATSAPP_AUTO_SYNC=true
SECURITY_AUDIT_ALERT_WHATSAPP_ENABLED=false
SECURITY_AUDIT_ALERT_MANUAL_ONLY=true

# PASTE Nexus-Dev-1 pooled URL (psycopg scheme):
# DATABASE_URL=postgresql+psycopg://...@ep-XXXX-pooler....neon.tech/neondb?sslmode=require
```

After editing:

```bash
sudo systemctl restart nexus-backend
cd /var/www/nexus/backend && source .venv/bin/activate
python scripts/sync_whatsapp_webhook.py --status
```

Expected: `owned_by_this_environment: true`, callback `https://nexus-dev.edutrust.in/api/webhook`.
