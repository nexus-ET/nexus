#!/usr/bin/env python3
"""
Start the full NEXUS dev stack (backend, frontend, Cloudflare tunnel).

Ports and bind host are read from backend/.env (NEXUS_PORT, NEXUS_FRONTEND_PORT,
NEXUS_BIND_HOST, NEXUS_TUNNEL_ENABLED). CLI flags override .env values.

Usage (from backend root):
  .venv\\Scripts\\python.exe scripts/run_dev.py
  .venv\\Scripts\\python.exe scripts/run_dev.py --reload
  .venv\\Scripts\\python.exe scripts/run_dev.py --backend-only
  .venv\\Scripts\\python.exe scripts/run_dev.py --no-tunnel
  .venv\\Scripts\\python.exe scripts/run_dev.py --port 8003

On Windows, prefer this over raw uvicorn when you see WinError 10013 (port in use).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = BACKEND_ROOT.parent / "frontend"
ENV_FILE = BACKEND_ROOT / ".env"
DEV_LOCK_FILE = BACKEND_ROOT / ".dev-stack.lock"
_ENV_WRITE_LOCK = threading.Lock()

DEFAULT_HOST = "127.0.0.1"
DEFAULT_BACKEND_PORT = 8002
DEFAULT_FRONTEND_PORT = 5175

TUNNEL_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.IGNORECASE)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True,
            text=True,
            check=False,
        )
        return str(pid) in result.stdout
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _acquire_dev_lock() -> bool:
    if DEV_LOCK_FILE.is_file():
        try:
            existing_pid = int(DEV_LOCK_FILE.read_text(encoding="utf-8").strip())
        except ValueError:
            existing_pid = 0
        if existing_pid and existing_pid != os.getpid() and _pid_alive(existing_pid):
            print(
                f"ERROR: dev stack already running (pid {existing_pid}). "
                "Stop it first or delete .dev-stack.lock if stale.",
                file=sys.stderr,
            )
            return False
    DEV_LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
    return True


def _release_dev_lock() -> None:
    if not DEV_LOCK_FILE.is_file():
        return
    try:
        if int(DEV_LOCK_FILE.read_text(encoding="utf-8").strip()) == os.getpid():
            DEV_LOCK_FILE.unlink(missing_ok=True)
    except ValueError:
        DEV_LOCK_FILE.unlink(missing_ok=True)


@dataclass(frozen=True)
class DevConfig:
    host: str
    backend_port: int
    frontend_port: int
    tunnel_enabled: bool
    tunnel_mode: str  # "quick" | "named"
    tunnel_name: str
    tunnel_config_path: Path | None
    public_tunnel_base: str | None
    tunnel_edge_ip_version: str | None


def _parse_env_bool(value: str | None, default: bool) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _whatsapp_auto_sync_enabled(env: dict[str, str]) -> bool:
    raw = os.getenv("NEXUS_WHATSAPP_AUTO_SYNC") or env.get("NEXUS_WHATSAPP_AUTO_SYNC")
    return _parse_env_bool(raw, default=True)


def _sync_whatsapp_webhook_for_dev(tunnel_url: str | None = None) -> None:
    python = sys.executable
    script = BACKEND_ROOT / "scripts" / "sync_whatsapp_webhook.py"
    if not script.is_file():
        return
    base = (tunnel_url or "").strip().rstrip("/")
    cmd = [python, str(script)]
    if base:
        cmd.extend(["--callback-url", f"{base}/api/webhook"])
    print("[whatsapp] Registering inbound webhook for this development environment...")
    result = subprocess.run(
        cmd,
        cwd=str(BACKEND_ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print("[whatsapp] Webhook registered for local development.")
        if result.stdout.strip():
            print(result.stdout.strip())
    else:
        print("[whatsapp] WARNING: webhook sync failed.", file=sys.stderr)
        if result.stderr.strip():
            print(result.stderr.strip(), file=sys.stderr)
        if result.stdout.strip():
            print(result.stdout.strip(), file=sys.stderr)


def _schedule_whatsapp_webhook_sync(tunnel_url: str) -> None:
    """Wait for the quick tunnel to become reachable, then register with Meta."""

    def _worker() -> None:
        time.sleep(3)
        _sync_whatsapp_webhook_for_dev(tunnel_url)

    threading.Thread(target=_worker, daemon=True).start()


def _release_whatsapp_webhook_handoff(env: dict[str, str]) -> None:
    handoff = (os.getenv("NEXUS_WHATSAPP_HANDOFF_URL") or env.get("NEXUS_WHATSAPP_HANDOFF_URL") or "").strip()
    if not handoff:
        return
    python = sys.executable
    script = BACKEND_ROOT / "scripts" / "sync_whatsapp_webhook.py"
    if not script.is_file():
        return
    print(f"[whatsapp] Handing webhook back to {handoff.rstrip('/')}/api/webhook ...")
    result = subprocess.run(
        [python, str(script), "--release"],
        cwd=str(BACKEND_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        if result.stdout.strip():
            print(result.stdout.strip())
        return
    print(
        "[whatsapp] WARNING: webhook handoff failed — nexus-dev may still be unreachable to Meta. "
        "Ensure the handoff server is running or set NEXUS_WHATSAPP_AUTO_SYNC=false for local-only work.",
        file=sys.stderr,
    )
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    if result.stdout.strip():
        print(result.stdout.strip(), file=sys.stderr)


def _read_env_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "mbcs"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _normalize_env_newlines(text: str) -> str:
    """Collapse CRLF / bare CR to LF before any rewrite.

    Windows ``Path.write_text`` (newline=None) translates ``\\n`` → ``\\r\\n``.
    If we read via bytes and keep ``\\r\\n``, that becomes ``\\r\\r\\n`` on write;
    the next ``splitlines(keepends=True)`` then inserts blank lines between every
    key — exponential .env bloat on each tunnel URL update.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _compact_env_lines(lines: list[str]) -> list[str]:
    """Keep at most one consecutive blank line; drop trailing blanks."""
    out: list[str] = []
    blank_run = 0
    for line in lines:
        if line.strip() == "":
            blank_run += 1
            if blank_run <= 1:
                out.append("")
            continue
        blank_run = 0
        out.append(line.rstrip())
    while out and out[-1] == "":
        out.pop()
    return out


def _write_env_text(path: Path, text: str) -> None:
    """Write .env with LF endings only (no Windows CRLF translation)."""
    payload = _normalize_env_newlines(text)
    if not payload.endswith("\n"):
        payload += "\n"
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    # newline="\n" disables universal-newline translation on Windows.
    tmp_path.write_text(payload, encoding="utf-8", newline="\n")
    tmp_path.replace(path)


def _load_env_file() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_FILE.is_file():
        return values
    for line in _normalize_env_newlines(_read_env_text(ENV_FILE)).split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _env_int(values: dict[str, str], key: str, default: int) -> int:
    raw = os.getenv(key) or values.get(key)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _env_str(values: dict[str, str], key: str, default: str) -> str:
    return (os.getenv(key) or values.get(key) or default).strip()


def load_dev_config(args: argparse.Namespace) -> DevConfig:
    env = _load_env_file()
    host = args.host or _env_str(env, "NEXUS_BIND_HOST", DEFAULT_HOST)
    backend_port = args.port if args.port is not None else _env_int(env, "NEXUS_PORT", DEFAULT_BACKEND_PORT)
    frontend_port = (
        args.frontend_port
        if args.frontend_port is not None
        else _env_int(env, "NEXUS_FRONTEND_PORT", DEFAULT_FRONTEND_PORT)
    )
    tunnel_enabled = not args.no_tunnel and _parse_env_bool(
        os.getenv("NEXUS_TUNNEL_ENABLED") or env.get("NEXUS_TUNNEL_ENABLED"),
        default=True,
    )
    tunnel_mode = _env_str(env, "NEXUS_TUNNEL_MODE", "quick").lower()
    if tunnel_mode not in {"quick", "named"}:
        tunnel_mode = "quick"
    tunnel_name = _env_str(env, "NEXUS_TUNNEL_NAME", "nexus-dev")
    config_raw = _env_str(env, "NEXUS_CLOUDFLARE_CONFIG", "")
    tunnel_config_path = Path(config_raw) if config_raw else BACKEND_ROOT / "cloudflared" / "config.yml"
    public_base = (os.getenv("PUBLIC_TUNNEL_BASE") or env.get("PUBLIC_TUNNEL_BASE") or "").strip() or None
    edge_raw = (
        os.getenv("NEXUS_TUNNEL_EDGE_IP_VERSION")
        or env.get("NEXUS_TUNNEL_EDGE_IP_VERSION")
        or ""
    ).strip().lower()
    if edge_raw in {"4", "6", "auto"}:
        tunnel_edge_ip_version: str | None = edge_raw
    elif tunnel_mode == "quick" and sys.platform == "win32":
        # Quick tunnels often fail over IPv6 on Windows ("control stream encountered a failure").
        tunnel_edge_ip_version = "4"
    else:
        tunnel_edge_ip_version = None
    return DevConfig(
        host=host,
        backend_port=backend_port,
        frontend_port=frontend_port,
        tunnel_enabled=tunnel_enabled and not args.backend_only and not args.no_tunnel,
        tunnel_mode=tunnel_mode,
        tunnel_name=tunnel_name,
        tunnel_config_path=tunnel_config_path,
        public_tunnel_base=public_base,
        tunnel_edge_ip_version=tunnel_edge_ip_version,
    )


def _update_env_key(key: str, value: str, *, env_path: Path | None = None) -> bool:
    """Update a single KEY=value in backend/.env (best-effort; never raises).

    Returns True when the file was rewritten. Normalizes newlines and collapses
    runaway blank lines so Windows tunnel restarts cannot bloat the file.
    """
    path = env_path or ENV_FILE
    if not path.is_file():
        return False
    with _ENV_WRITE_LOCK:
        try:
            normalized = _normalize_env_newlines(_read_env_text(path))
            raw_lines = normalized.split("\n")
            # split("\n") leaves a trailing empty string when the file ends with \n
            if raw_lines and raw_lines[-1] == "":
                raw_lines = raw_lines[:-1]

            found = False
            current_value: str | None = None
            updated: list[str] = []
            for line in raw_lines:
                stripped = line.strip()
                if stripped.startswith(f"{key}=") and not stripped.startswith("#"):
                    current_value = stripped.split("=", 1)[1]
                    updated.append(f"{key}={value}")
                    found = True
                else:
                    updated.append(line)
            if not found:
                updated.append(f"{key}={value}")

            compacted = _compact_env_lines(updated)
            payload = "\n".join(compacted) + "\n"
            prior = normalized if normalized.endswith("\n") else normalized + "\n"
            # Skip rewrite when value and formatting are already clean.
            if found and current_value == value and prior == payload:
                return False

            _write_env_text(path, payload)
            return True
        except OSError as exc:
            print(
                f"[tunnel] WARNING: could not update {key} in .env ({exc}). "
                f"Set {key}={value} manually if needed.",
                file=sys.stderr,
            )
            return False


def compact_env_file(env_path: Path | None = None) -> bool:
    """Rewrite .env with normalized newlines and collapsed blank lines."""
    path = env_path or ENV_FILE
    if not path.is_file():
        return False
    with _ENV_WRITE_LOCK:
        normalized = _normalize_env_newlines(_read_env_text(path))
        raw_lines = normalized.split("\n")
        if raw_lines and raw_lines[-1] == "":
            raw_lines = raw_lines[:-1]
        compacted = _compact_env_lines(raw_lines)
        payload = "\n".join(compacted) + "\n"
        prior = normalized if normalized.endswith("\n") else normalized + "\n"
        if prior == payload:
            return False
        _write_env_text(path, payload)
        return True


def _venv_uvicorn() -> Path:
    if sys.platform == "win32":
        candidate = BACKEND_ROOT / ".venv" / "Scripts" / "uvicorn.exe"
        if candidate.exists():
            return candidate
        candidate = BACKEND_ROOT / ".venv" / "Scripts" / "python.exe"
        if candidate.exists():
            return candidate
    else:
        candidate = BACKEND_ROOT / ".venv" / "bin" / "uvicorn"
        if candidate.exists():
            return candidate
    return Path("uvicorn")


def _find_npm() -> str:
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        raise RuntimeError("npm not found in PATH — install Node.js to run the frontend.")
    return npm


def _find_cloudflared() -> str | None:
    return shutil.which("cloudflared") or shutil.which("cloudflared.exe")


def _pids_listening_on_port(port: int) -> set[int]:
    pids: set[int] = set()
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    (
                        f"Get-NetTCPConnection -LocalPort {port} -State Listen "
                        "-ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess"
                    ),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.isdigit():
                    pids.add(int(line))
        except OSError:
            pass

        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            check=False,
        )
        pattern = re.compile(
            rf"TCP\s+127\.0\.0\.1:{port}\s+0\.0\.0\.0:0\s+LISTENING\s+(\d+)"
        )
        for line in result.stdout.splitlines():
            match = pattern.search(line)
            if match:
                pids.add(int(match.group(1)))
        return pids

    result = subprocess.run(
        ["lsof", "-ti", f"tcp:{port}"],
        capture_output=True,
        text=True,
        check=False,
    )
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            pids.add(int(line))
    return pids


def _nexus_backend_pids(port: int) -> set[int]:
    pids: set[int] = set()
    backend_marker = str(BACKEND_ROOT).lower().replace("/", "\\")
    port_token = f"*{port}*"

    if sys.platform == "win32":
        script = (
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.CommandLine -like '*app.main*' -or "
            f"($_.Name -eq 'uvicorn.exe' -and $_.CommandLine -like '{port_token}') }} | "
            "Select-Object -ExpandProperty ProcessId"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.isdigit():
                pids.add(int(line))
    else:
        result = subprocess.run(
            ["pgrep", "-f", "uvicorn app.main:app"],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.isdigit():
                pids.add(int(line))

    filtered: set[int] = set()
    for pid in pids:
        if sys.platform != "win32":
            filtered.add(pid)
            continue
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f'(Get-CimInstance Win32_Process -Filter "ProcessId={pid}").CommandLine',
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        cmd = (proc.stdout or "").lower()
        if backend_marker in cmd or "app.main:app" in cmd:
            filtered.add(pid)
    return filtered or pids


def _stop_pid(pid: int) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
        else:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.3)
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        return True
    except OSError:
        return False


def free_port(port: int, *, kill_backends: bool = False) -> list[int]:
    targets: set[int] = set(_pids_listening_on_port(port))
    if kill_backends:
        targets.update(_nexus_backend_pids(port))
    targets.discard(os.getpid())

    stopped: list[int] = []
    for pid in sorted(targets):
        if _stop_pid(pid):
            stopped.append(pid)

    if stopped:
        time.sleep(1.5)

    remaining = _pids_listening_on_port(port)
    if remaining:
        for pid in sorted(remaining):
            if pid != os.getpid() and _stop_pid(pid):
                stopped.append(pid)
        time.sleep(0.5)

    return stopped


def _wait_for_backend_ready(
    host: str,
    port: int,
    *,
    timeout: float = 300.0,
    proc: subprocess.Popen[str] | None = None,
) -> bool:
    """Poll until uvicorn accepts connections (avoids Vite ECONNREFUSED on startup).

    Cold Neon + SQLAlchemy create_all routinely takes 90–180s; keep the budget
    generous and surface progress so the wait does not look hung.
    """
    import urllib.error
    import urllib.request

    url = f"http://{host}:{port}/docs"
    deadline = time.time() + timeout
    started = time.time()
    last_progress = 0.0
    print(
        f"[backend] waiting for readiness at {url} "
        f"(up to {int(timeout)}s; cold DB sync can take a few minutes) ..."
    )
    while time.time() < deadline:
        if proc is not None and proc.poll() is not None:
            print(
                f"ERROR: backend process exited early (code {proc.returncode}). "
                "Check [backend] logs above for import or database errors.",
                file=sys.stderr,
            )
            return False
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    elapsed = time.time() - started
                    print(f"[backend] ready on http://{host}:{port} ({elapsed:.0f}s)")
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        elapsed = time.time() - started
        if elapsed - last_progress >= 15.0:
            print(f"[backend] still starting... {elapsed:.0f}s elapsed (DB sync / bootstrap)")
            last_progress = elapsed
        time.sleep(0.5)
    return False


def build_uvicorn_cmd(config: DevConfig, *, reload: bool) -> list[str]:
    uvicorn_bin = _venv_uvicorn()
    if uvicorn_bin.name == "python.exe":
        cmd = [
            str(uvicorn_bin),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            config.host,
            "--port",
            str(config.backend_port),
        ]
    else:
        cmd = [
            str(uvicorn_bin),
            "app.main:app",
            "--host",
            config.host,
            "--port",
            str(config.backend_port),
        ]
    if reload:
        cmd.append("--reload")
    return cmd


def build_frontend_cmd(config: DevConfig) -> list[str]:
    npm = _find_npm()
    return [
        npm,
        "run",
        "dev",
        "--",
        "--port",
        str(config.frontend_port),
        "--host",
        config.host,
    ]


def _print_meta_webhook_hint(base_url: str) -> None:
    base = base_url.rstrip("/")
    print("[tunnel] Meta WhatsApp webhook callback URL (paste in Meta Developer Console):")
    print(f"[tunnel]   {base}/api/webhook")
    print("[tunnel] Verify token must match WEBHOOK_VERIFY_TOKEN in backend/.env")
    print("[tunnel] Subscribe to the 'messages' field on your WhatsApp Business Account.")


def _validate_named_tunnel(config: DevConfig) -> None:
    cfg = config.tunnel_config_path
    if not cfg or not cfg.is_file():
        raise RuntimeError(
            f"Named tunnel config not found at {cfg}. "
            "Run: .\\scripts\\setup_cloudflare_tunnel.ps1 (one-time setup)"
        )
    if not config.public_tunnel_base:
        raise RuntimeError(
            "PUBLIC_TUNNEL_BASE is required for NEXUS_TUNNEL_MODE=named. "
            "Run setup_cloudflare_tunnel.ps1 or set it in backend/.env"
        )


def build_tunnel_cmd(config: DevConfig) -> list[str]:
    cloudflared = _find_cloudflared()
    if not cloudflared:
        raise RuntimeError("cloudflared not found in PATH — install it or use --no-tunnel.")
    if config.tunnel_mode == "named":
        _validate_named_tunnel(config)
        cmd = [
            cloudflared,
            "tunnel",
            "--config",
            str(config.tunnel_config_path),
            "run",
        ]
    else:
        cmd = [
            cloudflared,
            "tunnel",
            "--url",
            f"http://{config.host}:{config.backend_port}",
        ]
    if config.tunnel_edge_ip_version:
        cmd.extend(["--edge-ip-version", config.tunnel_edge_ip_version])
    return cmd


def _popen(cmd: list[str], *, cwd: Path, name: str) -> subprocess.Popen[str]:
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    print(f"[{name}] starting: {' '.join(cmd)}")
    return subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        creationflags=creationflags,
    )


def _stream_process(
    proc: subprocess.Popen[str],
    prefix: str,
    *,
    on_line: Callable[[str], None] | None = None,
) -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        text = line.rstrip()
        print(f"[{prefix}] {text}")
        if on_line:
            try:
                on_line(text)
            except Exception as exc:  # noqa: BLE001 — keep stream alive
                print(
                    f"[{prefix}] WARNING: line handler failed: {exc}",
                    file=sys.stderr,
                )


def parse_args() -> argparse.Namespace:
    env = _load_env_file()
    default_backend = _env_int(env, "NEXUS_PORT", DEFAULT_BACKEND_PORT)
    default_frontend = _env_int(env, "NEXUS_FRONTEND_PORT", DEFAULT_FRONTEND_PORT)
    default_host = _env_str(env, "NEXUS_BIND_HOST", DEFAULT_HOST)

    parser = argparse.ArgumentParser(
        description=(
            "Run the NEXUS dev stack. Config is read from backend/.env "
            f"(defaults: backend {default_backend}, frontend {default_frontend})."
        )
    )
    parser.add_argument("--host", default=None, help=f"Bind host (default: {default_host})")
    parser.add_argument("--port", type=int, default=None, help=f"Backend port (default: {default_backend})")
    parser.add_argument(
        "--frontend-port",
        type=int,
        default=None,
        help=f"Frontend port (default: {default_frontend})",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable uvicorn auto-reload (can leave zombie workers on Windows).",
    )
    parser.add_argument(
        "--no-kill",
        action="store_true",
        help="Do not stop existing listeners before starting.",
    )
    parser.add_argument(
        "--backend-only",
        action="store_true",
        help="Start only the backend (legacy mode).",
    )
    parser.add_argument(
        "--no-frontend",
        action="store_true",
        help="Skip the Vite frontend dev server.",
    )
    parser.add_argument(
        "--no-tunnel",
        action="store_true",
        help="Skip the Cloudflare quick tunnel.",
    )
    return parser.parse_args()


def _ensure_ports_free(config: DevConfig, *, no_kill: bool, backend_only: bool, no_frontend: bool) -> int:
    if no_kill:
        return 0

    ports: list[tuple[int, bool]] = [(config.backend_port, True)]
    if not backend_only and not no_frontend:
        ports.append((config.frontend_port, False))

    for port, kill_backends in ports:
        stopped = free_port(port, kill_backends=kill_backends)
        if stopped:
            label = "backend" if port == config.backend_port else "frontend"
            print(f"Stopped stale {label} process(es) on port {port}: {', '.join(map(str, stopped))}")
        remaining = _pids_listening_on_port(port)
        if remaining:
            print(
                f"ERROR: port {port} is still in use by PID(s): {', '.join(map(str, sorted(remaining)))}",
                file=sys.stderr,
            )
            print(f"Run: netstat -ano | findstr :{port}", file=sys.stderr)
            return 1
    return 0


def run_stack(args: argparse.Namespace) -> int:
    if not _acquire_dev_lock():
        return 1

    try:
        return _run_stack_inner(args)
    finally:
        _release_dev_lock()


def _run_stack_inner(args: argparse.Namespace) -> int:
    # Heal CRLF/blank-line inflation from older tunnel writers (Windows-only bug).
    try:
        if compact_env_file():
            print("[env] Compacted backend/.env (removed runaway blank lines)")
    except OSError as exc:
        print(f"[env] WARNING: could not compact .env ({exc})", file=sys.stderr)

    config = load_dev_config(args)
    env = _load_env_file()
    backend_only = args.backend_only
    start_frontend = not backend_only and not args.no_frontend
    start_tunnel = config.tunnel_enabled

    if start_frontend and not FRONTEND_ROOT.is_dir():
        print(f"ERROR: frontend not found at {FRONTEND_ROOT}", file=sys.stderr)
        return 1

    if start_tunnel and not _find_cloudflared():
        print("WARNING: cloudflared not in PATH — starting without tunnel.", file=sys.stderr)
        start_tunnel = False

    rc = _ensure_ports_free(
        config,
        no_kill=args.no_kill,
        backend_only=backend_only,
        no_frontend=not start_frontend,
    )
    if rc != 0:
        return rc

    tunnel_label = ""
    if start_tunnel:
        tunnel_label = (
            f", named tunnel ({config.tunnel_name})"
            if config.tunnel_mode == "named"
            else ", quick tunnel"
        )
        if config.tunnel_edge_ip_version:
            tunnel_label += f", edge IPv{config.tunnel_edge_ip_version}"
    print(
        "NEXUS dev stack:"
        f" backend http://{config.host}:{config.backend_port}"
        + (f", frontend http://{config.host}:{config.frontend_port}" if start_frontend else "")
        + (tunnel_label if start_tunnel else "")
    )

    procs: list[tuple[str, subprocess.Popen[str]]] = []
    tunnel_url: str | None = None
    webhook_synced_locally = False

    def on_tunnel_line(line: str) -> None:
        nonlocal tunnel_url, webhook_synced_locally
        match = TUNNEL_URL_RE.search(line)
        if match and tunnel_url != match.group(0):
            tunnel_url = match.group(0)
            _update_env_key("PUBLIC_TUNNEL_BASE", tunnel_url)
            print(f"[tunnel] PUBLIC_TUNNEL_BASE updated in .env -> {tunnel_url}")
            if _whatsapp_auto_sync_enabled(env):
                _schedule_whatsapp_webhook_sync(tunnel_url)
                webhook_synced_locally = True
            else:
                _print_meta_webhook_hint(tunnel_url)

    try:
        backend_proc = _popen(
            build_uvicorn_cmd(config, reload=args.reload),
            cwd=BACKEND_ROOT,
            name="backend",
        )
        procs.append(("backend", backend_proc))
        threading.Thread(
            target=_stream_process,
            args=(backend_proc, "backend"),
            daemon=True,
        ).start()

        if not _wait_for_backend_ready(
            config.host, config.backend_port, proc=backend_proc
        ):
            print(
                "ERROR: backend did not become ready in time. "
                "Check [backend] logs above for import or database errors "
                "(cold Neon create_all often exceeds 2 minutes).",
                file=sys.stderr,
            )
            return 1

        if start_frontend:
            frontend_proc = _popen(
                build_frontend_cmd(config),
                cwd=FRONTEND_ROOT,
                name="frontend",
            )
            procs.append(("frontend", frontend_proc))
            threading.Thread(
                target=_stream_process,
                args=(frontend_proc, "frontend"),
                daemon=True,
            ).start()

        if start_tunnel:
            if config.tunnel_mode == "named":
                try:
                    _validate_named_tunnel(config)
                except RuntimeError as exc:
                    print(f"ERROR: {exc}", file=sys.stderr)
                    return 1
                assert config.public_tunnel_base
                print(f"[tunnel] Stable URL: {config.public_tunnel_base.rstrip('/')}")
                if _whatsapp_auto_sync_enabled(env):
                    _sync_whatsapp_webhook_for_dev(config.public_tunnel_base.rstrip("/"))
                    webhook_synced_locally = True
                else:
                    _print_meta_webhook_hint(config.public_tunnel_base)
            tunnel_proc = _popen(
                build_tunnel_cmd(config),
                cwd=BACKEND_ROOT,
                name="tunnel",
            )
            procs.append(("tunnel", tunnel_proc))
            threading.Thread(
                target=_stream_process,
                args=(tunnel_proc, "tunnel"),
                kwargs={"on_line": on_tunnel_line},
                daemon=True,
            ).start()

        while True:
            tunnel_exited = False
            for name, proc in procs:
                code = proc.poll()
                if code is None:
                    continue
                if name == "tunnel":
                    print(
                        f"[tunnel] WARNING: tunnel exited with code {code}. "
                        "Backend and frontend will keep running without a public URL.",
                        file=sys.stderr,
                    )
                    print(
                        "[tunnel] Tip: retry dev.ps1, use .\\dev.ps1 -NoTunnel for local UI work, "
                        "or set NEXUS_TUNNEL_MODE=named after setup_cloudflare_tunnel.ps1.",
                        file=sys.stderr,
                    )
                    procs.remove((name, proc))
                    tunnel_exited = True
                    break
                print(f"[{name}] exited with code {code}", file=sys.stderr)
                return code
            if tunnel_exited:
                continue
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\nShutting down NEXUS dev stack...")
        return 0
    finally:
        for name, proc in procs:
            if proc.poll() is None:
                print(f"[{name}] stopping...")
                _stop_pid(proc.pid)
        if start_tunnel and _whatsapp_auto_sync_enabled(env) and webhook_synced_locally:
            _release_whatsapp_webhook_handoff(env)


def main() -> int:
    args = parse_args()
    os.chdir(BACKEND_ROOT)
    return run_stack(args)


if __name__ == "__main__":
    raise SystemExit(main())
