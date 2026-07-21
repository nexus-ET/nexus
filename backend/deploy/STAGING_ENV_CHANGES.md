# Staging environment changes (apply manually)

**Canonical checklist:** [STAGING_CONFIG_REQUIREMENTS.md](./STAGING_CONFIG_REQUIREMENTS.md)  
**Deploy steps:** [DEPLOYMENT_INSTRUCTIONS.md](./DEPLOYMENT_INSTRUCTIONS.md)  
**Template (no secrets):** [env.staging.example](./env.staging.example)

**Do not overwrite** local `E:\NEXUS\backend\.env`.  
Edit only on the Hostinger VPS:

```text
/var/www/nexus/backend/.env
```

Optional local staging worktree: `E:\NEXUS-staging\backend\.env`

---

## Critical — switch DATABASE_URL to Nexus-Dev-1

Old Neon reached its limit. Staging must use the new DB:

| Item | Value |
|------|--------|
| Neon database | **Nexus-Dev-1** |
| Scheme in `.env` | `postgresql+psycopg://...` |
| Required query | `?sslmode=require` |
| Prefer | Neon **pooled** connection host (`-pooler`) |

```env
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@ep-XXXX-pooler.REGION.aws.neon.tech/neondb?sslmode=require
```

Then:

```bash
sudo systemctl restart nexus-backend
cd /var/www/nexus/backend && source .venv/bin/activate
python scripts/verify_staging_database.py --migrate
```

Expected Alembic head: `c4d7e0f53g6h`

---

## Required — identity & routing

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

---

## Required — WhatsApp / intake (current product)

| Variable | Staging value | Why |
|----------|---------------|-----|
| `PROVIDER` | `WHATSAPP` | |
| `NEXUS_APPOINTMENTS_ONLY` | `true` | Degree → major → country → booking |
| `WHATSAPP_OUTREACH_TEMPLATE` | `et_student_welcome` | Welcome only |
| `WHATSAPP_OUTREACH_SKIP_INTAKE_FOLLOWUP` | `true` | **No** hi/hello continue nudge |
| `WHATSAPP_OUTREACH_TEMPLATE_LANGUAGE` | `en` | |
| `WHATSAPP_OUTREACH_TEMPLATE_PARAMETERS` | `student,company` | |
| `WHATSAPP_OUTREACH_TEMPLATE_PARAMETER_FORMAT` | `positional` | |
| `WHATSAPP_OUTREACH_COMPANY_NAME` | `Edutrust` | |

Business line (when `NEXUS_INSTANCE` is staging / nexus-dev):

```env
WHATSAPP_BUSINESS_PHONE_NUMBER=+917411952525
WHATSAPP_BUSINESS_PHONE_NUMBER_ID=1097416893464116
WHATSAPP_BUSINESS_WABA_ID=1312656237246811
WEBHOOK_VERIFY_TOKEN=<Meta verify token>
WHATSAPP_VERIFY_TOKEN=<same as WEBHOOK_VERIFY_TOKEN>
WHATSAPP_ACCESS_TOKEN=<long-lived token>
```

Meta webhook:

```text
https://nexus-dev.edutrust.in/api/webhook
```

### Welcome template body (Meta) — greeting only

Do **not** include full-name booking or “reply hi/hello to continue” in the template:

```text
Hi {{1}}! Thanks for reaching {{2}}. We're excited to help you get started with your study abroad plans.
```

Student replies `hi` / `hello` → intake starts at **degree**.

---

## Recommended on staging

| Variable | Value |
|----------|--------|
| `SECURITY_AUDIT_ALERT_WHATSAPP_ENABLED` | `false` |
| `SECURITY_AUDIT_ALERT_MANUAL_ONLY` | `true` |

---

## Quick paste block (fill secrets on VPS only)

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

# PASTE Nexus-Dev-1 pooled URL:
# DATABASE_URL=postgresql+psycopg://...@ep-XXXX-pooler....neon.tech/neondb?sslmode=require
```

After edit:

```bash
sudo systemctl restart nexus-backend
cd /var/www/nexus/backend && source .venv/bin/activate
python scripts/sync_whatsapp_webhook.py --status
```

---

## Do NOT copy from local development `.env`

| Variable | Wrong on staging |
|----------|------------------|
| `DATABASE_URL` | Old Neon / local (limit reached) |
| `PUBLIC_TUNNEL_BASE` | `*.trycloudflare.com` / `*.ngrok-free.dev` |
| `NEXUS_INSTANCE` | `development` |
| `NEXUS_TUNNEL_ENABLED` | `true` |
| `SECRET_KEY` | Dev secret |
