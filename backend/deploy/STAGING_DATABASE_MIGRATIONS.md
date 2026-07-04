# Staging database migrations (Alembic)

Auto-maintained by `backend/scripts/promote_to_staging.py`.

Hostinger `deploy.sh` runs `alembic upgrade head` on every deploy.

**Current head:** `r4n7o2p36q8l`
**Doc generated:** 2026-07-04 08:11 UTC

## Migrations in this release

| Revision | Migration | Changes |
|----------|-----------|---------|
| `r4n7o2p36q8l` | r4n7o2p36q8l_add_status_transitions_table | New table(s): `status_transitions` |

## Full migration chain (at head)

| Revision | Migration | Changes |
|----------|-----------|---------|
| `6483497fc0ee` | 6483497fc0ee_initial_migration | Alter: `clients.owner_id` |
| `2d2dd0d54afd` | 2d2dd0d54afd_add_phone_and_address_to_clients | add phone and address to clients |
| `a35af5ac8bf5` | a35af5ac8bf5_add_notes_model | Alter: `clients.phone_number`; `clients.address` |
| `02fee3037fcb` | 02fee3037fcb_add_superuser_and_role_to_user | Alter: `users.is_superuser`; `users.role` |
| `2e1d49fcdf8c` | 2e1d49fcdf8c_add_superuser_columns_to_users | Alter: `users.is_superuser`; `users.role` |
| `b7d070216c32` | b7d070216c32_add_missing_lead_columns | drop table `messages`; drop table `leads` |
| `c8f2a1d94e6b` | c8f2a1d94e6b_rename_user_full_name_to_first_last | Alter: `users.first_name`; `users.last_name`; drop `users.full_name` |
| `d9a4b2c81f0e` | d9a4b2c81f0e_add_agent_config_and_lead_assignment | New table(s): `agent_configs`; Alter: `leads.assigned_advisor_id` |
| `e1f3a8b92c4d` | e1f3a8b92c4d_add_countries_table | New table(s): `countries` |
| `f2a4b9c03d5e` | f2a4b9c03d5e_add_education_degrees_table | New table(s): `education_degrees` |
| `g3c6d1e25f7a` | g3c6d1e25f7a_add_gpa_cgpa_scores_table | New table(s): `gpa_cgpa_scores` |
| `h4d7e2f36g8b` | h4d7e2f36g8b_add_target_programs_courses_tables | New table(s): `target_programs`, `target_courses` |
| `i5e8f3g47h9c` | i5e8f3g47h9c_add_ai_confidence_fields | Alter: `messages.ai_confidence`; `leads.handoff_ai_confidence`; `leads.handoff_reason` |
| `j6f9g4h58i0d` | j6f9g4h58i0d_add_conversation_audit_logs | New table(s): `conversation_audit_logs` |
| `k7g0h5i69j1e` | k7g0h5i69j1e_add_counselling_notes_table | New table(s): `counselling_notes` |
| `l8h1i6j70k2f` | l8h1i6j70k2f_add_status_definitions_table | New table(s): `status_definitions`, `lead_status_history`; Alter: `leads.status_definition_id`; `leads.status_entered_at` |
| `m9i2j7k81l3g` | m9i2j7k81l3g_add_lead_status_definition_id | Alter: `leads.status_definition_id`; `leads.status_entered_at` |
| `n0j3k8l92m4h` | n0j3k8l92m4h_reseed_status_definitions_v2 | SQL data migration |
| `o1k4l9m03n5i` | o1k4l9m03n5i_add_status_history_table | New table(s): `status_history`; Alter: `status_history.changed_by_type` |
| `p2l5m0n14o6j` | p2l5m0n14o6j_add_system_logs_table | New table(s): `system_logs` |
| `q3m6n1o25p7k` | q3m6n1o25p7k_unblock_session_cancelled_status | SQL data migration |
| `r4n7o2p36q8l` | r4n7o2p36q8l_add_status_transitions_table | New table(s): `status_transitions` |

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
# Expected: r4n7o2p36q8l (head)
```
