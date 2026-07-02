# Git deploy to Hostinger VPS

Deploy NEXUS with **Git + pull** (recommended) or **Git push** (optional).

## Architecture

```
GitHub (main)  →  git pull on VPS  →  deploy.sh  →  nginx + systemd
https://nexus.YOUR_DOMAIN.com
https://nexus.YOUR_DOMAIN.com/api/webhook   ← permanent Meta callback URL
```

---

## Part 1 — Push code to GitHub (your PC)

From `E:\NEXUS` in PowerShell:

```powershell
cd E:\NEXUS
git init
git add .
git commit -m "Initial NEXUS commit"
```

Create a **private** repo on GitHub (e.g. `your-user/nexus`), then:

```powershell
git branch -M main
git remote add origin https://github.com/YOUR_USER/nexus.git
git push -u origin main
```

`.env` is gitignored — secrets stay on the server only.

---

## Part 2 — One-time VPS setup (Hostinger terminal)

SSH into the VPS, then:

```bash
sudo apt update && sudo apt install -y git

# Clone (public repo) — use your GitHub URL
sudo mkdir -p /var/www
cd /var/www
sudo git clone --branch main https://github.com/YOUR_USER/nexus.git nexus
cd nexus

# One-time install (nginx, systemd, build)
sudo bash backend/deploy/install.sh --domain nexus.YOUR_DOMAIN.com
```

**If the repo is private**, clone manually with a token or SSH key:

```bash
sudo mkdir -p /var/www && cd /var/www
sudo git clone --branch main https://github.com/YOUR_USER/nexus.git nexus
cd nexus
sudo bash backend/deploy/install.sh --domain nexus.YOUR_DOMAIN.com
```

### DNS (Hostinger hPanel)

| Type | Name  | Points to   |
|------|-------|-------------|
| A    | nexus | VPS IP      |

### Production secrets

```bash
sudo nano /var/www/nexus/backend/.env
```

Copy values from your local `backend/.env` (database, WhatsApp, `SECRET_KEY`, etc.), then:

```bash
sudo systemctl restart nexus-backend
```

### HTTPS

```bash
sudo certbot --nginx -d nexus.YOUR_DOMAIN.com
```

### Meta webhook (set once)

```
https://nexus.YOUR_DOMAIN.com/api/webhook
```

Verify token = `WEBHOOK_VERIFY_TOKEN` in `/var/www/nexus/backend/.env`.

---

## Promote develop → staging (NEXUS → NEXUS-Staging)

Two local folders share one GitHub repo via **worktrees**:

| Folder | Branch | Purpose |
|--------|--------|---------|
| `E:\NEXUS` | `develop` | Daily dev + WhatsApp test number |
| `E:\NEXUS-staging` | `staging` | Staging-local + Hostinger deploy |

**One command (recommended on Windows):**

```powershell
cd E:\NEXUS
python backend/scripts/promote_to_staging.py --message "Describe your release"
```

Or use the launcher:

```powershell
.\backend\deploy\promote-to-staging.py.ps1 -Message "Describe your release"
```

Legacy PowerShell script (no auto migration docs):

```powershell
.\backend\deploy\promote-to-staging.ps1 -Message "Describe your release"
```

The Python script will:

1. Detect new Alembic migrations since `origin/staging` and refresh `STAGING_DATABASE_MIGRATIONS.md`
2. Write a timestamped file under `backend/deploy/releases/` when migrations are included
3. Commit any uncommitted changes on `develop` (if present)
4. Push `develop` to GitHub
5. Merge `develop` into `staging` in `E:\NEXUS-staging`
6. Push `staging` to GitHub

**Push and deploy to Hostinger in one step:**

```powershell
python backend/scripts/promote_to_staging.py --message "Release notes" --vps root@YOUR_VPS_IP
```

**Options (`python backend/scripts/promote_to_staging.py --help`):**

| Flag | Effect |
|------|--------|
| `--dry-run` | Show steps without git push/merge/write |
| `--skip-develop-push` | Only merge/push staging (develop already on GitHub) |
| `--skip-deploy` | Do not SSH to VPS even if `--vps` is set |
| `--skip-migration-doc` | Do not refresh migration markdown |
| `--staging-root PATH` | Override `E:\NEXUS-staging` worktree path |

**From GitHub (no local PC):**

1. Push `develop` first: `git push origin develop`
2. GitHub → **Actions** → **Promote develop to staging** → **Run workflow**
3. On VPS: `sudo bash /var/www/nexus/backend/deploy/deploy.sh`

**Git Bash / Linux:**

```bash
bash backend/deploy/promote-to-staging.sh --message "Release" --vps root@YOUR_VPS_IP
```

`.env` is gitignored — after promote, verify staging secrets on the server (`/var/www/nexus/backend/.env`).

**Database:** `deploy.sh` runs `alembic upgrade head` automatically. See [STAGING_DATABASE_MIGRATIONS.md](./STAGING_DATABASE_MIGRATIONS.md) for new tables and column changes.

**Current release (2026-07-03):** [STAGING_RELEASE_2026-07-03.md](./STAGING_RELEASE_2026-07-03.md) — env changes in [STAGING_ENV_CHANGES.md](./STAGING_ENV_CHANGES.md) (apply manually on VPS).

**On VPS after deploy:**

```bash
sudo bash /var/www/nexus/backend/deploy/deploy-staging.sh
sudo bash /var/www/nexus/backend/deploy/verify-staging-deploy.sh
```

---

## Part 3 — Deploy updates (every time you change code)

**On your PC:**

```powershell
cd E:\NEXUS
git add .
git commit -m "Describe your change"
git push origin main
```

**On the VPS:**

```bash
sudo bash /var/www/nexus/backend/deploy/deploy.sh
```

Or SSH one-liner from PC:

```powershell
ssh root@YOUR_VPS_IP "sudo bash /var/www/nexus/backend/deploy/deploy.sh"
```

---

## Optional — Push directly to VPS (no GitHub pull)

On VPS once:

```bash
cd /var/www/nexus
sudo bash backend/deploy/setup-bare-repo.sh
```

On PC:

```powershell
git remote add production ssh://root@YOUR_VPS_IP/var/repo/nexus.git
git push production main
```

The `post-receive` hook runs `deploy.sh` automatically.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `502 Bad Gateway` | `sudo systemctl status nexus-backend` and `journalctl -u nexus-backend -f` |
| Meta verify fails | URL must end with `/api/webhook`; token must match `.env` |
| Frontend blank | `cd /var/www/nexus/frontend && npm run build` |
| DB errors | Check `DATABASE_URL` in `.env`; Neon must allow VPS IP if restricted |

```bash
sudo systemctl status nexus-backend
sudo journalctl -u nexus-backend -n 50
curl http://127.0.0.1:8002/
curl https://nexus.YOUR_DOMAIN.com/api/webhook/info
```
