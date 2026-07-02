# Release snapshot: develop → staging (2026-07-03)

Generated for manual promotion. Alembic head: **`q3m6n1o25p7k`**.

---

## Migrations applied on staging (after `j6f9g4h58i0d`)

| # | Revision | Description |
|---|----------|-------------|
| 1 | `k7g0h5i69j1e` | `counselling_notes` table |
| 2 | `l8h1i6j70k2f` | `status_definitions`, `lead_status_history` |
| 3 | `m9i2j7k81l3g` | `leads.status_definition_id`, `status_entered_at` |
| 4 | `n0j3k8l92m4h` | Reseed status_definitions v2 (39 stages) |
| 5 | `o1k4l9m03n5i` | `status_history` table |
| 6 | `p2l5m0n14o6j` | `system_logs` table |
| 7 | `q3m6n1o25p7k` | Status 6 → next_stage_id = 4 |

---

## Env changes (manual — do not auto-apply)

See [../STAGING_ENV_CHANGES.md](../STAGING_ENV_CHANGES.md).

Key additions for this release:
- `NEXUS_APPOINTMENTS_ONLY=true`
- WhatsApp outreach template variables (`WHATSAPP_OUTREACH_*`)
- `PUBLIC_TUNNEL_BASE=https://nexus-dev.edutrust.in` (not dev quick tunnel)

---

## Promote command

```powershell
cd E:\NEXUS
python backend/scripts/promote_to_staging.py --message "Release 2026-07-03: status pipeline and session UI"
```

## VPS deploy

```bash
sudo bash /var/www/nexus/backend/deploy/deploy-staging.sh
sudo bash /var/www/nexus/backend/deploy/verify-staging-deploy.sh
```

---

## Feature checklist (post-deploy)

- [ ] My Bookings: Session modal shows Update Session Outcome + Data Exchange
- [ ] View Interaction / View Journey open as right panels
- [ ] Prospects: pipeline status dropdown with descriptions
- [ ] AI Active: no duplicate Start AI Conversation when messages exist
- [ ] Status 7/8/9: closure WhatsApp sent on pipeline update
- [ ] Reschedule/cancel appear in journey (repeat events)
- [ ] `GET /api/v1/leads/{id}/journey` returns status_history entries
