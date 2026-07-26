# Nexus pre-staging QA pipeline (5 phases)

## Run all phases

```powershell
powershell -File qa/run_pre_staging.ps1
```

## Cursor agent prompt (paste before staging deploy)

See **[PRE_STAGING_AGENT_PROMPT.md](./PRE_STAGING_AGENT_PROMPT.md)**.

## Layout

| Phase | Location |
|-------|----------|
| 1 SIT | `uat/tests/sit/` (+ profile/shortlist specs) |
| 2 API / scoring | `backend/tests/qa/test_matching_contracts.py` |
| 3 WhatsApp resilience | `backend/tests/qa/test_whatsapp_resilience.py` |
| 4 Security / RBAC | `backend/tests/qa/test_rbac_security.py` |
| 5 E2E + load | `uat/tests/01`–`05` + `qa/load/shortlist_load.py` |
