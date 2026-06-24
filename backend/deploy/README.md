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
