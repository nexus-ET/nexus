# Staging release package — current

**Active package date:** **2026-08-08**  
See **`STAGING_RELEASE_2026-08-08.md`** for this promote’s feature list, Alembic head, and Hostinger steps.

**No `.env` files are modified by the promote script.** Config for Staging is listed in `STAGING_CONFIG_REQUIREMENTS.md`.

---

## Artifacts (this folder)

| File | Purpose |
|------|---------|
| `STAGING_RELEASE_2026-08-08.md` | **Current** release summary + deploy steps |
| `STAGING_RELEASE_PACKAGE.md` | This index |
| `STAGING_CONFIG_REQUIREMENTS.md` | Manual Staging env / App Settings checklist |
| `STAGING_DATABASE_MIGRATIONS.md` | Alembic chain (auto-refreshed by `promote_to_staging.py`) |
| `DEPLOYMENT_INSTRUCTIONS.md` | Step-by-step deploy + verification |
| `STAGING_DEPLOYMENT_AGENT_PROMPT.md` | Hostinger standing checklist (SMTP, seeds, R2, lead 27) |
| `env.staging.example` | Example keys only — copy values manually onto server `.env` |
| `hostinger-staging.sh` | Full VPS deploy (pull, migrate, frontend build, restart) |
| `deploy.sh` | Pull + migrate + restart backend |

---

## Promote command (from develop machine)

```powershell
cd E:\NEXUS
python backend/scripts/promote_to_staging.py `
  --message "Staging release 2026-08-08: IntelX, FlowX, Book Appointment, Session insights/ROI" `
  --skip-deploy
```

Then on VPS:

```bash
sudo bash /var/www/nexus/backend/deploy/hostinger-staging.sh
```

---

## Do not ship

- `backend/.env`, `frontend/.env`, `uat/.env`
- Bloated `.env` backups, tunnel credentials
- `__pycache__`, `frontend/dist` (build on server)
