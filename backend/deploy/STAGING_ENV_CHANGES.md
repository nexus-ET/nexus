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

## Critical — switch DATABASE_URL to Hostinger KVM 1 Postgres

Staging no longer uses Neon (Nexus-Dev-1 / sparkling-violet reached limits). Use the **Hostinger KVM 1** database:

| Item | Value |
|------|--------|
| Database | **`nexus_edutrust`** |
| User | **`nexus_et_admin`** (full privileges) |
| Host | `127.0.0.1` on VPS, or Hostinger hPanel DB host |
| Port | `5432` (default) |
| Scheme | `postgresql+psycopg://...` |

```env
DATABASE_URL=postgresql+psycopg://nexus_et_admin:YOUR_PASSWORD@127.0.0.1:5432/nexus_edutrust
```

Full bootstrap steps: [setup_staging_db.md](./setup_staging_db.md).

**Do not** point staging at develop Neon (`ep-still-paper-…` / still-paper) or old staging Neon URLs.

If scripts can talk to the DB but nginx returns **502** after `systemctl restart nexus-backend`, the unit is crashing or never binding — see [STAGING_DEPLOYMENT_AGENT_PROMPT.md](./STAGING_DEPLOYMENT_AGENT_PROMPT.md) gate **E1b**. Fix `.env`, install `deploy/nexus-backend.service` (dotenv wrapper), then:

```bash
sudo sed -i 's/\r$//' /var/www/nexus/backend/.env
sudo cp /var/www/nexus/backend/deploy/nexus-backend.service /etc/systemd/system/nexus-backend.service
sudo chmod +x /var/www/nexus/backend/deploy/run-nexus-backend.sh
sudo systemctl daemon-reload
sudo systemctl restart nexus-backend
cd /var/www/nexus/backend && source .venv/bin/activate
python scripts/verify_staging_database.py --migrate
```

Expected Alembic head: `yy5z6asupermaj`

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

# PASTE Hostinger KVM 1 Postgres URL (fill password on VPS):
# DATABASE_URL=postgresql+psycopg://nexus_et_admin:YOUR_PASSWORD@127.0.0.1:5432/nexus_edutrust
```

After edit:

```bash
sudo systemctl restart nexus-backend
cd /var/www/nexus/backend && source .venv/bin/activate
python scripts/sync_whatsapp_webhook.py --status
```

---

## Do NOT copy from local development `.env`

Develop should use Hostinger **`nexus_dev`** (see [setup_dev_db.md](./setup_dev_db.md)), not Neon still-paper.

| Variable | Wrong on staging |
|----------|------------------|
| `DATABASE_URL` | Neon (still-paper / Nexus-Dev-1 / sparkling-violet), develop **`nexus_dev`**, or local SQLite |
| `PUBLIC_TUNNEL_BASE` | `*.trycloudflare.com` / `*.ngrok-free.dev` |
| `NEXUS_INSTANCE` | `development` |
| `NEXUS_TUNNEL_ENABLED` | `true` |
| `SECRET_KEY` | Dev secret |
