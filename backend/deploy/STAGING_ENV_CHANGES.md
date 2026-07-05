# Staging environment changes (apply manually)

**Do not commit live `.env` files.** Apply these changes yourself on:

- **Hostinger VPS:** `/var/www/nexus/backend/.env`
- **Local staging worktree (optional):** `E:\NEXUS-staging\backend\.env`

Development values (Cloudflare quick tunnel, test WhatsApp line, dev Neon URL) must **not** be copied to staging.

---

## Required — identity & routing

Staging must use the **business WhatsApp line** and **nexus-dev** public URL.

| Variable | Staging value | Notes |
|----------|---------------|--------|
| `NEXUS_INSTANCE` | `nexus-dev` or `staging` | Must **not** be `development` |
| `ENVIRONMENT` | `staging` | |
| `PUBLIC_TUNNEL_BASE` | `https://nexus-dev.edutrust.in` | Permanent Meta webhook base; **not** a trycloudflare URL |
| `NEXUS_TUNNEL_ENABLED` | `false` | No Cloudflare quick tunnel on VPS |
| `FRONTEND_URL` | `https://nexus-dev.edutrust.in` | Match your nginx public URL |

Remove or leave empty on staging (dev-only):

| Variable | Action on staging |
|----------|-------------------|
| `NEXUS_TUNNEL_MODE` | Remove or ignore |
| `NEXUS_TUNNEL_EDGE_IP_VERSION` | Remove or ignore |
| `NEXUS_WHATSAPP_HANDOFF_URL` | Optional on VPS; used when **dev stops** to hand webhook back |

---

## Required — database

| Variable | Action |
|----------|--------|
| `DATABASE_URL` | Must point to the **Nexus-Staging Neon** database (not the dev Neon project). Verify pooled connection string with `sslmode=require`. |

After deploy, confirm:

```bash
alembic current
# Expected: s5p8q1r54s0m (head)
```

---

## Required — WhatsApp / Meta

Ensure these exist on staging (add if missing). Values should match your Meta app / approved templates.

```env
PROVIDER=WHATSAPP
WEBHOOK_VERIFY_TOKEN=<same token registered in Meta Developer Console>
WHATSAPP_VERIFY_TOKEN=<same as WEBHOOK_VERIFY_TOKEN>
WHATSAPP_ACCESS_TOKEN=<long-lived token with whatsapp_business_messaging>

# Business line (active when NEXUS_INSTANCE is staging / nexus-dev)
WHATSAPP_BUSINESS_PHONE_NUMBER=+917411952525
WHATSAPP_BUSINESS_PHONE_NUMBER_ID=1097416893464116
WHATSAPP_BUSINESS_WABA_ID=1312656237246811

# Outreach template (Utility: et_student_welcome — body includes welcome + intake prompt)
WHATSAPP_OUTREACH_TEMPLATE=et_student_welcome
WHATSAPP_OUTREACH_TEMPLATE_LANGUAGE=en
WHATSAPP_OUTREACH_TEMPLATE_PARAMETERS=student,company
WHATSAPP_OUTREACH_TEMPLATE_PARAMETER_FORMAT=positional
WHATSAPP_OUTREACH_TEMPLATE_PARAMETER_NAMES=student_name,company_name
WHATSAPP_OUTREACH_COMPANY_NAME=Edutrust
WHATSAPP_OUTREACH_DELIVERY_WAIT_SECONDS=15
# Single combined template — do not send a second WhatsApp message.
WHATSAPP_OUTREACH_SKIP_INTAKE_FOLLOWUP=true

NEXUS_WHATSAPP_AUTO_SYNC=true
```

Meta webhook callback URL (set once in Meta, re-synced on each deploy):

```text
https://nexus-dev.edutrust.in/api/webhook
```

Test line vars (`WHATSAPP_TEST_*`) may remain for reference but are **not used** when `NEXUS_INSTANCE` is staging.

---

## WhatsApp outreach — combined welcome template (recommended)

The welcome template (`et_student_welcome`) should include **both** the greeting and the intake line in Meta, for example:

```text
Hi {{1}}! Thanks for reaching {{2}}. We're excited to help you get started with your study abroad plans.

To book your free study abroad consultation, simply reply with your full name.
```

Staging `.env`:

```env
WHATSAPP_OUTREACH_SKIP_INTAKE_FOLLOWUP=true
```

Nexus sends **one** WhatsApp template only (no second message). AI Active chat history shows the welcome + intake lines together.

### Deploy and verify

```bash
sudo bash /var/www/nexus/backend/deploy/deploy-staging.sh
journalctl -u nexus-backend -n 50 --no-pager | grep -i "Combined outreach template"
```

### Optional — separate second template

Only if you keep a short welcome template without the intake line, use `WHATSAPP_OUTREACH_FOLLOWUP_TEMPLATE=et_intake_fullname` instead of `WHATSAPP_OUTREACH_SKIP_INTAKE_FOLLOWUP=true`.

---

## Release 2026-07-05 — flash before deploy (manual edit only)

**Files to update yourself (never commit):**

| File | Environment |
|------|-------------|
| `/var/www/nexus/backend/.env` | Hostinger VPS (staging) |
| `E:\NEXUS-staging\backend\.env` | Local staging worktree (optional) |

**Do not copy** `E:\NEXUS\backend\.env` to staging.

### Required for this release

| Variable | Staging value | Why |
|----------|---------------|-----|
| `NEXUS_APPOINTMENTS_ONLY` | `true` | WhatsApp intake uses degree → major → country → booking; rule-based study extraction (no Ollama/OpenAI needed) |
| `NEXUS_INSTANCE` | `nexus-dev` or `staging` | Routes to business WhatsApp line |
| `ENVIRONMENT` | `staging` | |
| `PUBLIC_TUNNEL_BASE` | `https://nexus-dev.edutrust.in` | Permanent webhook base |
| `FRONTEND_URL` | `https://nexus-dev.edutrust.in` | |
| `DATABASE_URL` | Staging Neon URL | Separate from dev DB |
| `WHATSAPP_OUTREACH_SKIP_INTAKE_FOLLOWUP` | `true` | Single combined welcome template |

### Recommended for staging (reduce noise)

| Variable | Suggested value | Purpose |
|----------|-----------------|--------|
| `SECURITY_AUDIT_ALERT_WHATSAPP_ENABLED` | `false` | Stop nightly audit failures from WhatsApp-blasting super admins |
| `SECURITY_AUDIT_ALERT_MANUAL_ONLY` | `true` | Optional: red-flag alerts only on manual Run audit |

To silence all outbound red-flag alerts on staging (audit still runs and logs):

```env
SECURITY_AUDIT_RED_ALERTS_ENABLED=false
```

### Not required on staging for this release

| Variable | Notes |
|----------|--------|
| `OLLAMA_*` / `OPENAI_*` / `GROQ_*` | Not used when `NEXUS_APPOINTMENTS_ONLY=true` |
| `NEXUS_TUNNEL_*` | Dev-only; keep `NEXUS_TUNNEL_ENABLED=false` on VPS |

### Quick copy block (adjust secrets locally on VPS)

```env
NEXUS_INSTANCE=nexus-dev
ENVIRONMENT=staging
PUBLIC_TUNNEL_BASE=https://nexus-dev.edutrust.in
NEXUS_TUNNEL_ENABLED=false
FRONTEND_URL=https://nexus-dev.edutrust.in
NEXUS_APPOINTMENTS_ONLY=true
WHATSAPP_OUTREACH_SKIP_INTAKE_FOLLOWUP=true
SECURITY_AUDIT_ALERT_WHATSAPP_ENABLED=false
SECURITY_AUDIT_ALERT_MANUAL_ONLY=true
# DATABASE_URL, WHATSAPP_*, SECRET_KEY — keep existing staging values
```

---

## Prior release — still verify on staging

| Variable | Suggested value | Purpose |
|----------|-----------------|--------|
| `NEXUS_APPOINTMENTS_ONLY` | `true` | Fixed intake + booking flow on WhatsApp (no open-ended LLM Q&A on webhook) |
| `SECURITY_AUDIT_ALERT_WHATSAPP_ENABLED` | `false` | Stop nightly audit failures from WhatsApp-blasting super admins on staging |
| `SECURITY_AUDIT_ALERT_MANUAL_ONLY` | `true` | Optional: only send red-flag alerts when someone clicks Run audit in the UI |

---

## Optional — unchanged but verify

| Variable | Notes |
|----------|--------|
| `SECRET_KEY` | Keep existing staging secret; do not copy from dev |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Typically `60` |
| `NEXUS_PORT` | `8002` on VPS (systemd) |
| `MAX_COUNSELLING_BOOKINGS_PER_SLOT` | If used, keep staging value |
| `OLLAMA_*` / `OPENAI_*` | Only if AI summarize features enabled on staging |

---

## Local staging worktree only (E:\NEXUS-staging)

If you run staging locally against the staging Neon DB:

```env
NEXUS_PORT=8003
NEXUS_FRONTEND_PORT=5176
NEXUS_BIND_HOST=127.0.0.1
FRONTEND_URL=http://127.0.0.1:5176
NEXUS_TUNNEL_ENABLED=false
PUBLIC_TUNNEL_BASE=https://nexus-dev.edutrust.in
```

---

## After editing `.env`

```bash
sudo systemctl restart nexus-backend
cd /var/www/nexus/backend && source .venv/bin/activate
python scripts/sync_whatsapp_webhook.py --status
```

Expected: `owned_by_this_environment: true`, callback `https://nexus-dev.edutrust.in/api/webhook`.

---

## Dev-only values — do NOT copy to staging

These are fine on `E:\NEXUS\backend\.env` for development but wrong for staging:

| Variable | Dev example | Why not on staging |
|----------|-------------|-------------------|
| `PUBLIC_TUNNEL_BASE` | `https://*.trycloudflare.com` | Ephemeral; breaks inbound WhatsApp |
| `NEXUS_INSTANCE` | `development` | Routes to test WhatsApp number |
| `NEXUS_TUNNEL_ENABLED` | `true` | VPS uses fixed domain |
| `DATABASE_URL` | Dev Neon endpoint | Separate database per environment |
