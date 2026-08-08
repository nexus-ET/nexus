# Staging database migrations (Alembic)

Auto-maintained by `backend/scripts/promote_to_staging.py`.

Hostinger `deploy.sh` runs `alembic upgrade head` on every deploy.

**Current head:** `kk1l2mbiztseq`
**Doc generated:** 2026-08-08 08:13 UTC

## Migrations in this release

| Revision | Migration | Changes |
|----------|-----------|---------|
| `kk1l2mbiztseq` | kk1l2mbiztseq_fix_candidate_test_scores_id_seq | SQL data migration |

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
| `s5p8q1r54s0m` | s5p8q1r54s0m_reseed_status_definitions_v3 | reseed status_definitions v3 (45 stages) |
| `t6u9v2w65x7y` | t6u9v2w65x7y_add_students_master_table | New table(s): `students_master` |
| `u7v0w3x76y8z` | u7v0w3x76y8z_add_students_master_aspirations | Alter: `students_master.aspirations_data` |
| `v8w1x4y87z9a` | v8w1x4y87z9a_add_students_master_gender_marital_status | Alter: `students_master.gender`; `students_master.marital_status` |
| `w9x2y5z98a0b` | w9x2y5z98a0b_add_candidate_test_scores | New table(s): `candidate_test_scores` |
| `x0y3z6a01b2c` | x0y3z6a01b2c_add_work_experiences | New table(s): `work_experiences`, `work_projects` |
| `y1z4a7b12c3d` | y1z4a7b12c3d_add_research_projects | New table(s): `research_projects` |
| `z2a5b8c13d4e` | z2a5b8c13d4e_add_non_academic_activities | New table(s): `non_academic_activities` |
| `a3b6c9d02e4f` | a3b6c9d02e4f_fix_countries_16_19 | fix countries ids 16-19 qatar netherlands russia hong kong |
| `b4c7d0e25f5g` | b4c7d0e25f5g_add_candidate_test_overall_score | Alter: `candidate_test_scores.overall_score` |
| `c5d8e1f36g6h` | c5d8e1f36g6h_add_candidate_educations | New table(s): `candidate_educations` |
| `d6e9f2g47h7i` | d6e9f2g47h7i_update_education_degrees_catalog | update education_degrees catalog with secondary school levels |
| `e7f0g3h58i8j` | e7f0g3h58i8j_add_education_majors_table | New table(s): `education_majors` |
| `f8g1h4i69j9k` | f8g1h4i69j9k_add_digital_presence_links | New table(s): `digital_presence_links` |
| `a9b2c5d78e0f` | a9b2c5d78e0f_add_academia_hub_tables | New table(s): `geography_states`, `geography_cities`, `institutions`, `campuses`, `colleges` |
| `b0c3d6e89f1a` | b0c3d6e89f1a_enhance_geography_metadata | Alter: `geography_cities.time_zone`; `geography_cities.postal_code_prefix` |
| `c1d4e7f90g2b` | c1d4e7f90g2b_add_program_course_metadata | Alter: `target_programs.description`; `target_courses.level` |
| `d2e5f8g01h3c` | d2e5f8g01h3c_add_academic_degrees_hierarchy | New table(s): `academic_degrees`; Alter: `target_programs.degree_id` |
| `e3f6g9h02i4d` | e3f6g9h02i4d_enhance_institutional_hierarchy | Alter: `institutions.accreditation_details`; `campuses.location_id`; `colleges.dean_name` |
| `f4g7h0i13j5e` | f4g7h0i13j5e_add_institution_wizard_and_audit | New table(s): `institution_wizard_drafts`, `institution_intakes`, `institution_pictures`, `institution_course_offerings`, `academia_audit_logs` |
| `g5h8i1j24k6f` | g5h8i1j24k6f_add_institution_profile_fields | Alter: `institutions.state_id`; `institutions.city_id`; `institutions.zipcode`; `institutions.company_affiliated`; `institutions.ranking_tier_global`; `institutions.ad_promotion_flag`; `institutions.institution_web_url`; `institutions.currency_type`; `institutions.students_count`; `institutions.short_description`; `institutions.long_description` |
| `h6i9j2k35l7g` | h6i9j2k35l7g_add_campus_classification_fields | Alter: `campuses.campus_type`; `campuses.type_description`; `campuses.is_residential` |
| `i7j0k3l46m8h` | i7j0k3l46m8h_campus_types_lookup_table | New table(s): `campus_types`; Alter: `campuses.campus_type_id`; drop `campuses.type_description`; drop `campuses.campus_type` |
| `j8k1l4m57n9i` | j8k1l4m57n9i_course_levels_and_degree_links | New table(s): `course_levels`; Alter: `education_degrees.course_level_id`; `academic_degrees.course_level_id` |
| `k9l2m5n68o0j` | k9l2m5n68o0j_campus_profile_fields | Alter: `campuses.description`; `campuses.address`; `campuses.country_id`; `campuses.state_id`; `campuses.zipcode`; `campuses.phone_numbers`; `campuses.fax_number`; `campuses.email_addresses` |
| `l0m3n6o79p1k` | l0m3n6o79p1k_seed_academic_programs | Seed framework qualification programs (BEng, BSc, MBA, etc.) |
| `m1n4o7p80q2l` | m1n4o7p80q2l_add_college_web_url | Alter: `colleges.web_url` |
| `n2o5p8q91r3m` | n2o5p8q91r3m_replace_academic_degrees_with_programs | New table(s): `programs`, `academic_degree_program_map`; Alter: `target_programs.program_id`; drop `target_programs.degree_id` |
| `o3p6q9r02s4n` | o3p6q9r02s4n_rename_course_levels_to_levels | SQL data migration |
| `p4q7r03s5t6u` | p4q7r03s5t6u_ensure_hierarchy_fk_indexes | SQL data migration |
| `q5r8s14t6u7v` | q5r8s14t6u7v_add_course_education_major_links | Alter: `target_courses.education_major_id`; `target_courses.qualification_program_id` |
| `r6s9t15u7v8w` | r6s9t15u7v8w_add_education_major_levels | New table(s): `education_major_levels` |
| `s7t0u16v8w9x` | s7t0u16v8w9x_recreate_programs_with_major_mapping | New table(s): `programs` |
| `t8u1v17w9x0y` | t8u1v17w9x0y_clear_programs_table | Clear programs table for manual UI entry. |
| `u9v2w18x9y0z` | u9v2w18x9y0z_add_education_courses_table | New table(s): `education_courses` |
| `v0w3x19y0z1a` | v0w3x19y0z1a_clear_education_courses_table | Clear education_courses for manual UI entry. |
| `w1x4y20z1a2b` | w1x4y20z1a2b_add_levels_is_active | Alter: `levels.is_active` |
| `x2y5z21a2b3c` | x2y5z21a2b3c_restructure_lmpc_hierarchy | Alter: `education_majors.program_id`; drop `programs.education_major_id` |
| `y3z6a22b3c4d` | y3z6a22b3c4d_nullable_major_course_codes | Make education_majors.code and education_courses.code nullable. |
| `z4a7b23c4d5e` | z4a7b23c4d5e_academic_calendar_intake_system | New table(s): `global_academic_templates`, `program_intake_assignments`; Alter: `institution_intakes.template_id`; `institution_intakes.parent_intake_id`; `institution_intakes.term_name`; `institution_intakes.year`; `institution_intakes.intake_type`; `institution_intakes.status` |
| `a5b8c34d5e6f` | a5b8c34d5e6f_simplify_levels_id_value | New table(s): `levels` |
| `b6c9d45e6f7a` | b6c9d45e6f7a_extend_levels_code_name_description | Alter: `levels.code`; `levels.name`; `levels.description`; drop `levels.value` |
| `c7d0e56f7g8h` | c7d0e56f7g8h_recreate_education_majors_no_defaults | New table(s): `education_majors`, `education_major_levels` |
| `d8e1f67g8h9i` | d8e1f67g8h9i_hierarchical_intake_system | New table(s): `calendar_intake_alert_logs`; Alter: `institution_intakes.entity_type`; `institution_intakes.entity_id`; `institution_intakes.is_overridden`; `institution_intakes.check_in_date`; `institution_intakes.orientation_date`; `institution_intakes.class_start_date` |
| `e9f2g8h0i1j2` | e9f2g8h0i1j2_institution_summary_timestamps_indexes | Alter: `institutions.created_at`; `institutions.updated_at` |
| `f1g4h0i3j4k5` | f1g4h0i3j4k5_labeled_contact_fields | Alter: `colleges.phone_numbers`; `colleges.email_addresses` |
| `g2h5i1j4k5l6` | g2h5i1j4k5l6_allow_colleges_without_campus | Allow colleges to remain unlinked from a campus. |
| `h3i6j2k5l7m8` | h3i6j2k5l7m8_clear_education_majors_mappings | Clear education majors and their program/level mappings. |
| `i4j7k3l6m8n9` | i4j7k3l6m8n9_add_education_major_color | Alter: `education_majors.color` |
| `j5k8l4m7n9o0` | j5k8l4m7n9o0_add_program_major_mappings | New table(s): `program_education_major_mappings` |
| `k6l9m5n8o1p2` | k6l9m5n8o1p2_reset_education_majors_table | Reset education_majors and related mapping data. |
| `l7m0n6o9p1q3` | l7m0n6o9p1q3_allow_multiple_majors_per_program | Allow multiple majors per program mapping. |
| `m8n1o7p0q2r4` | m8n1o7p0q2r4_make_course_major_optional | Make course major optional for direct program ownership. |
| `n9o2p8q1r3s5` | n9o2p8q1r3s5_add_course_major_mappings | New table(s): `course_education_major_mappings` |
| `o0p3q9r2s4t6` | o0p3q9r2s4t6_add_academic_entity_descriptions | Alter: `education_majors.description`; `education_courses.description` |
| `p1q4r0s3t5u7` | p1q4r0s3t5u7_clear_institution_intakes | Clear institution_intakes for a fresh start. |
| `q2r5s1t4u6v8` | q2r5s1t4u6v8_add_intake_level_ids | Alter: `institution_intakes.level_ids` |
| `r3s6t2u5v7w9` | r3s6t2u5v7w9_add_intake_cascade_to_children | Alter: `institution_intakes.cascade_to_children` |
| `s4t7u3v6w8x0` | s4t7u3v6w8x0_expand_institution_description_limits | Expand institution accreditation and short description limits. |
| `t5u8v4w7x9y1` | t5u8v4w7x9y1_add_institution_publish_status | Alter: `institutions.publish_status`; `institutions.last_publish_attempt_at`; `institutions.last_publish_error` |
| `u6v9w2x76y8z` | u6v9w2x76y8z_institution_picture_college_storage | Alter: `institution_pictures.college_id`; `institution_pictures.storage_key` |
| `v7w0x3y87z9a` | v7w0x3y87z9a_add_institution_contact_fields | Alter: `institutions.address`; `institutions.phone_numbers`; `institutions.fax_number`; `institutions.email_addresses` |
| `w8x1y4z98a0b` | w8x1y4z98a0b_add_institution_dean_name | Alter: `institutions.dean_name` |
| `x9y2z5a09b1c` | x9y2z5a09b1c_replace_fax_number_with_fax_numbers | Replace single fax_number with typed fax_numbers lists. |
| `y0z3a6b10c2d` | y0z3a6b10c2d_add_college_code_and_category | Alter: `colleges.code`; `colleges.category` |
| `z1a4b7c20d3e` | z1a4b7c20d3e_pending_institution_publish_status | SQL data migration |
| `a2b5c8d31e4f` | a2b5c8d31e4f_add_institution_college_web_links | Alter: `institutions.web_links`; `colleges.web_links` |
| `b3c6d9e42f5g` | b3c6d9e42f5g_heal_never_attempted_publish_pending | SQL data migration |
| `c4d7e0f53g6h` | c4d7e0f53g6h_add_campus_web_links | Alter: `campuses.web_links` |
| `d5e8f1a64h7i` | d5e8f1a64h7i_add_phase1_university_matching | New table(s): `matching_weight_profiles`, `matching_shortlist_runs`, `matching_shortlist_items` |
| `e6x9c2eption01` | e6x9c2eption01_add_exception_logs_table | New table(s): `exception_logs` |
| `f7y0d3esolution` | f7y0d3esolution_add_exception_resolution_comment | Alter: `exception_logs.resolution_comment` |
| `g8z1a4timestamptz` | g8z1a4timestamptz_event_timestamps_timestamptz | SQL data migration |
| `h9a2b5studyyears` | h9a2b5studyyears_full_time_study_years | New table(s): `full_time_study_years`; Alter: `candidate_educations.full_time_study_years` |
| `i0b3c6ftlevels` | i0b3c6ftlevels_link_study_years_to_levels | Alter: `full_time_study_years.level_id` |
| `j1c4d7ftdocint` | j1c4d7ftdocint_map_integrated_doctoral_study_years | Map Integrated Degree and Doctoral to full_time_study_years. |
| `k2d5e8ftcode10` | k2d5e8ftcode10_add_study_year_10 | Add full_time_study_years code 10 (High School). |
| `l3e6f9ftint1213` | l3e6f9ftint1213_integrated_study_years_12_13 | Allow same FT study year codes per level; add Integrated 12/13. |
| `m4f7g0ft16int` | m4f7g0ft16int_ensure_16_integrated | Ensure study year 16 maps to Integrated Degree. |
| `n5g8h1ftint1718` | n5g8h1ftint1718_fix_integrated_study_years_17_18 | Fix Integrated Degree FT study years to 17+ and 18+. |
| `o6h9i2nexusintel` | o6h9i2nexusintel_add_nexus_intel_tables | New table(s): `intel_glossary`, `intel_trivia`, `intel_trivia_answers`, `intel_user_preferences`, `intel_scraper_config`, `intel_academy_modules`, `intel_scrape_reviews` |
| `p7j0k3usjpintel` | p7j0k3usjpintel_seed_us_jp_nexus_intel | Seed US and JP Nexus Intel glossary, scrapers, and academy content. |
| `q8k1l4eurowintel` | q8k1l4eurowintel_seed_fr_ae_nz_sg_se_ch | Seed FR, AE, NZ, SG, SE, CH Nexus Intel glossary and scrapers. |
| `r9m2n5scrapefetch` | r9m2n5scrapefetch_add_scraper_content_snapshot | Alter: `intel_scraper_config.last_content_hash`; `intel_scraper_config.last_content_text`; `intel_scraper_config.last_fetched_at`; `intel_scraper_config.last_http_status` |
| `s0n3p6scrapehard` | s0n3p6scrapehard_retarget_us_state_scraper | SQL data migration |
| `t1o4q7scrapefix` | t1o4q7scrapefix_harden_scraper_fetch | SQL data migration |
| `u2p5r8isafinal` | u2p5r8isafinal_retarget_isa_japan_url | SQL data migration |
| `v3w6x9glossaryexp` | v3w6x9glossaryexp_expand_glossary_terms | Expand Nexus Intel glossary across all subscribed countries (~100 terms). |
| `w4x7z0intaichat` | w4x7z0intaichat_add_intel_ai_chat_logs | New table(s): `intel_ai_chat_logs` |
| `x5y8z1aithread` | x5y8z1aithread_add_intel_ai_chat_thread_id | Alter: `intel_ai_chat_logs.thread_id` |
| `y6z9a2bithreadsx` | y6z9a2bithreadsx_add_intel_ai_user_created_index | SQL data migration |
| `a1b2c3flowxcore` | a1b2c3flowxcore_add_flowx_operational_tables | New table(s): `flowx_workflow_rules`, `flowx_pipelines`, `flowx_tracks`, `flowx_tasks`, `flowx_audit_logs`, `flowx_workflow_rules` |
| `b2c3d4flowxcntry` | b2c3d4flowxcntry_rebuild_country_workflows | New table(s): `flowx_country_workflows`, `flowx_stages`, `flowx_tracks`, `flowx_task_templates`, `flowx_enrollments`, `flowx_enrollment_tracks`, `flowx_tasks`, `flowx_audit_logs` |
| `c3d4e5flowxbrick` | c3d4e5flowxbrick_subprocess_links_overrides | New table(s): `flowx_subprocess_links` |
| `u2p5r8frvisas` | u2p5r8frvisas_retarget_france_visas_scraper | SQL data migration |
| `z9a2b5flowxapps` | z9a2b5flowxapps_multi_country_college_enrollments | Alter: `flowx_enrollments.institution_id`; `flowx_enrollments.college_id` |
| `aa1b2cflowxappform` | aa1b2cflowxappform_pathway_registry_application_fields | New table(s): `flowx_pathway_registry` |
| `bb2c3denrolltrackpos` | bb2c3denrolltrackpos_enrollment_track_position | Alter: `flowx_enrollment_tracks.position_index` |
| `cc3d4etaskoptional` | cc3d4etaskoptional_flowx_task_is_optional | Alter: `flowx_tasks.is_optional` |
| `dd4e5fbricksteps` | dd4e5fbricksteps_add_template_action_steps | Alter: `flowx_task_templates.action_steps` |
| `ee5f6gnestca` | ee5f6gnestca_nest_tests_under_scores_canada | Alter: `flowx_stages.is_hidden`; `flowx_task_templates.parent_template_id` |
| `ff6g7hmaster` | ff6g7hmaster_add_master_template_id | Alter: `flowx_task_templates.master_template_id` |
| `gg7h8iparentcasc` | gg7h8iparentcasc_cascade_delete_nested_bricks | Cascade-delete nested FlowX bricks when their parent is deleted. |
| `hh8i9jchecklist` | hh8i9jchecklist_flowx_task_checklist_state | Alter: `flowx_tasks.checklist_state` |
| `ii9j0kintakeass` | ii9j0kintakeass_counselling_intake_assessment | Alter: `counselling_bookings.intake_assessment` |
| `jj0k1lbizlogo` | jj0k1lbizlogo_add_business_logo_path | Alter: `businesses.logo_path` |
| `kk1l2mbiztseq` | kk1l2mbiztseq_fix_candidate_test_scores_id_seq | SQL data migration |

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
# Expected: kk1l2mbiztseq (head)
```
