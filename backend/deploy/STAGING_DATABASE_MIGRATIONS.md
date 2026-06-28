# Staging database migrations (Alembic)

Run automatically on Hostinger when `deploy.sh` executes `alembic upgrade head`.

**Current head:** `j6f9g4h58i0d`

**Chain (new since agent_config):**

| Revision | Migration | Changes |
|----------|-----------|---------|
| `e1f3a8b92c4d` | add_countries_table | New table `countries` (iso2, name, dial_code, is_active, sort_order) |
| `f2a4b9c03d5e` | add_education_degrees_table | New table `education_degrees` |
| `g3c6d1e25f7a` | add_gpa_cgpa_scores_table | New table `gpa_cgpa_scores` |
| `h4d7e2f36g8b` | add_target_programs_courses_tables | New tables `target_programs`, `target_courses` |
| `i5e8f3g47h9c` | add_ai_confidence_fields | **Alter** `messages.ai_confidence`; **alter** `leads.handoff_ai_confidence`, `leads.handoff_reason`; prefix `agent_configs.ai_model` with provider |
| `j6f9g4h58i0d` | add_conversation_audit_logs | New table `conversation_audit_logs` (AI audit dashboard) |

## Manual run (VPS or local)

```bash
cd /var/www/nexus/backend
source .venv/bin/activate
alembic current
alembic upgrade head
```

## Verify after deploy

```bash
alembic current
# Expected: j6f9g4h58i0d (head)
```

## Rollback (emergency only)

```bash
alembic downgrade i5e8f3g47h9c   # removes conversation_audit_logs only
# or
alembic downgrade h4d7e2f36g8b   # also removes ai_confidence columns
```

Seed data for countries, education degrees, GPA scales, and target programs is applied by application startup/services after tables exist — no separate seed migration required.
