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
# Expected: q3m6n1o25p7k (head)
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

# Outreach template (Utility: et_student_welcome)
WHATSAPP_OUTREACH_TEMPLATE=et_student_welcome
WHATSAPP_OUTREACH_TEMPLATE_LANGUAGE=en
WHATSAPP_OUTREACH_TEMPLATE_PARAMETERS=student,company
WHATSAPP_OUTREACH_TEMPLATE_PARAMETER_FORMAT=positional
WHATSAPP_OUTREACH_TEMPLATE_PARAMETER_NAMES=student_name,company_name
WHATSAPP_OUTREACH_COMPANY_NAME=Edutrust
WHATSAPP_OUTREACH_DELIVERY_WAIT_SECONDS=15
WHATSAPP_OUTREACH_FOLLOWUP_DELAY_SECONDS=12
WHATSAPP_OUTREACH_POST_TEMPLATE_DELAY_SECONDS=5
WHATSAPP_OUTREACH_UNCONFIRMED_TEMPLATE_DELAY_SECONDS=18
WHATSAPP_OUTREACH_FOLLOWUP_DELIVERY_WAIT_SECONDS=20

# REQUIRED for reliable 2nd WhatsApp message — create in Meta Business Manager first (see below).
WHATSAPP_OUTREACH_FOLLOWUP_TEMPLATE=et_intake_fullname
WHATSAPP_OUTREACH_FOLLOWUP_TEMPLATE_LANGUAGE=en
WHATSAPP_OUTREACH_REQUIRE_FOLLOWUP_TEMPLATE=true

NEXUS_WHATSAPP_AUTO_SYNC=true
```

Meta webhook callback URL (set once in Meta, re-synced on each deploy):

```text
https://nexus-dev.edutrust.in/api/webhook
```

Test line vars (`WHATSAPP_TEST_*`) may remain for reference but are **not used** when `NEXUS_INSTANCE` is staging.

---

## WhatsApp second message (intake prompt) — Meta template required

After `et_student_welcome`, Meta often **accepts session text** but **does not deliver it** to the phone (common in India). Nexus now sends a **second Utility template** instead.

### 1. Create template in Meta Business Manager

1. Open [Meta Business Manager](https://business.facebook.com/) → WhatsApp Manager → **Message templates**.
2. **Create template**:
   - **Name:** `et_intake_fullname` (must match `WHATSAPP_OUTREACH_FOLLOWUP_TEMPLATE`)
   - **Category:** Utility
   - **Language:** English
   - **Body** (no variables):

     ```text
     To book your free study abroad consultation, simply reply with your full name.
     ```

3. Submit and wait for **Approved** status.

Or register via API on the VPS (uses credentials from `.env`):

```bash
cd /var/www/nexus/backend && source .venv/bin/activate
python scripts/register_whatsapp_followup_template.py
```

### 2. Staging `.env` (required)

```env
WHATSAPP_OUTREACH_FOLLOWUP_TEMPLATE=et_intake_fullname
WHATSAPP_OUTREACH_FOLLOWUP_TEMPLATE_LANGUAGE=en
WHATSAPP_OUTREACH_REQUIRE_FOLLOWUP_TEMPLATE=true
```

### 3. Deploy and restart

```bash
sudo bash /var/www/nexus/backend/deploy/deploy-staging.sh
```

### 4. Verify logs after “Start AI Conversation”

```bash
journalctl -u nexus-backend -n 100 --no-pager | grep -i "follow-up template\|et_intake"
```

Expect: `Sent WhatsApp outreach follow-up template 'et_intake_fullname'`.

### Alternative (single message, no second template)

Append the intake line to `et_student_welcome` in Meta and set:

```env
WHATSAPP_OUTREACH_SKIP_INTAKE_FOLLOWUP=true
```

---

## New in this release — add to staging

| Variable | Suggested value | Purpose |
|----------|-----------------|--------|
| `NEXUS_APPOINTMENTS_ONLY` | `true` | Fixed intake + booking flow on WhatsApp (no open-ended LLM Q&A on webhook) |

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
