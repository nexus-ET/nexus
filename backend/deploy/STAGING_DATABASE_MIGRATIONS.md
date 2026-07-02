# Staging database migrations (Alembic)

Auto-maintained by `backend/scripts/promote_to_staging.py`.

Hostinger `deploy.sh` runs `alembic upgrade head` on every deploy.

**Current head:** `q3m6n1o25p7k`  
**Previous staging head (before this release):** `j6f9g4h58i0d`  
**Doc generated:** 2026-07-03 (release prep)

---

## Migrations in this release

These **7 migrations** run when promoting from staging at `j6f9g4h58i0d` to develop head:

| Revision | Migration | Changes |
|----------|-----------|---------|
| `k7g0h5i69j1e` | k7g0h5i69j1e_add_counselling_notes_table | New table: `counselling_notes` (session notes per booking) |
| `l8h1i6j70k2f` | l8h1i6j70k2f_add_status_definitions_table | New tables: `status_definitions`, `lead_status_history`; seeds initial pipeline stages |
| `m9i2j7k81l3g` | m9i2j7k81l3g_add_lead_status_definition_id | Alter: `leads.status_definition_id`, `leads.status_entered_at` + FK to `status_definitions` |
| `n0j3k8l92m4h` | n0j3k8l92m4h_reseed_status_definitions_v2 | **Data migration:** reseeds 39 pipeline stages (v2); drops/recreates status definitions |
| `o1k4l9m03n5i` | o1k4l9m03n5i_add_status_history_table | New/renamed table: `status_history` (replaces `lead_status_history`); enum `status_changed_by_type` |
| `p2l5m0n14o6j` | p2l5m0n14o6j_add_system_logs_table | New table: `system_logs` (automation diagnostics) |
| `q3m6n1o25p7k` | q3m6n1o25p7k_unblock_session_cancelled_status | Data: `status_definitions.id=6` → `next_stage_id=4` (rebook after cancel) |

### Post-migration notes

- **`n0j3k8l92m4h`** reseeds all `status_definitions`. Existing `status_definition_id` on leads may need validation; run `python scripts/validate_status_consistency.py` after deploy if you have production-like data on staging.
- **`o1k4l9m03n5i`** migrates existing `lead_status_history` rows to `status_history` when present.
- Staging should use a **dedicated Neon database** — never run this chain against the dev database from VPS by mistake.

---

## Full migration chain (at head)

| Revision | Migration | Changes |
|----------|-----------|---------|
| `6483497fc0ee` | 6483497fc0ee_initial_migration | Initial schema |
| `2d2dd0d54afd` | 2d2dd0d54afd_add_phone_and_address_to_clients | Alter: `clients.phone_number`; `clients.address` |
| `a35af5ac8bf5` | a35af5ac8bf5_add_notes_model | Notes model |
| `02fee3037fcb` | 02fee3037fcb_add_superuser_and_role_to_user | Alter: `users.is_superuser`; `users.role` |
| `2e1d49fcdf8c` | 2e1d49fcdf8c_add_superuser_columns_to_users | User superuser columns |
| `b7d070216c32` | b7d070216c32_add_missing_lead_columns | Lead columns |
| `c8f2a1d94e6b` | c8f2a1d94e6b_rename_user_full_name_to_first_last | Alter: `users.first_name`; `users.last_name` |
| `d9a4b2c81f0e` | d9a4b2c81l0e_add_agent_config_and_lead_assignment | New table: `agent_configs`; Alter: `leads.assigned_advisor_id` |
| `e1f3a8b92c4d` | e1f3a8b92c4d_add_countries_table | New table: `countries` |
| `f2a4b9c03d5e` | f2a4b9c03d5e_add_education_degrees_table | New table: `education_degrees` |
| `g3c6d1e25f7a` | g3c6d1e25f7a_add_gpa_cgpa_scores_table | New table: `gpa_cgpa_scores` |
| `h4d7e2f36g8b` | h4d7e2f36g8b_add_target_programs_courses_tables | New tables: `target_programs`, `target_courses` |
| `i5e8f3g47h9c` | i5e8f3g47h9c_add_ai_confidence_fields | Alter: `messages.ai_confidence`; `leads.handoff_*` |
| `j6f9g4h58i0d` | j6f9g4h58i0d_add_conversation_audit_logs | New table: `conversation_audit_logs` |
| `k7g0h5i69j1e` | k7g0h5i69j1e_add_counselling_notes_table | New table: `counselling_notes` |
| `l8h1i6j70k2f` | l8h1i6j70k2f_add_status_definitions_table | New tables: `status_definitions`, `lead_status_history` |
| `m9i2j7k81l3g` | m9i2j7k81l3g_add_lead_status_definition_id | Alter: `leads.status_definition_id`; `leads.status_entered_at` |
| `n0j3k8l92m4h` | n0j3k8l92m4h_reseed_status_definitions_v2 | SQL data migration (39 stages v2) |
| `o1k4l9m03n5i` | o1k4l9m03n5i_add_status_history_table | New table: `status_history` |
| `p2l5m0n14o6j` | p2l5m0n14o6j_add_system_logs_table | New table: `system_logs` |
| `q3m6n1o25p7k` | q3m6n1o25p7k_unblock_session_cancelled_status | Data: status 6 next_stage → 4 |

---

## Manual run (VPS or local staging)

```bash
cd /var/www/nexus/backend
source .venv/bin/activate
alembic current
alembic upgrade head
```

Local staging worktree:

```powershell
cd E:\NEXUS-staging\backend
.\.venv\Scripts\activate
alembic current
alembic upgrade head
```

---

## Verify after deploy

```bash
alembic current
# Expected: q3m6n1o25p7k (head)

# Optional consistency pass
python scripts/validate_status_consistency.py
```
