"""Regression: Windows CRLF must not bloat backend/.env on tunnel URL updates."""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent / "scripts"
RUN_DEV_PATH = SCRIPTS_DIR / "run_dev.py"


def _load_run_dev():
    spec = importlib.util.spec_from_file_location("nexus_run_dev", RUN_DEV_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


run_dev = _load_run_dev()


def test_update_env_key_does_not_bloat_on_repeated_crlf_writes(tmp_path: Path):
    env_path = tmp_path / ".env"
    # Typical Windows-edited .env (CRLF), including a blank section separator.
    env_path.write_bytes(
        b"PROJECT_NAME=NEXUS\r\n"
        b"\r\n"
        b"PUBLIC_TUNNEL_BASE=https://old.trycloudflare.com\r\n"
        b"NEXUS_PORT=8002\r\n"
    )

    for i in range(12):
        run_dev._update_env_key(
            "PUBLIC_TUNNEL_BASE",
            f"https://pass-{i}.trycloudflare.com",
            env_path=env_path,
        )

    raw = env_path.read_bytes()
    assert b"\r\r\n" not in raw
    text = raw.decode("utf-8")
    lines = text.split("\n")
    nonempty = [ln for ln in lines if ln.strip()]
    assert len(nonempty) == 3
    assert "PUBLIC_TUNNEL_BASE=https://pass-11.trycloudflare.com" in nonempty
    assert "PROJECT_NAME=NEXUS" in nonempty
    assert "NEXUS_PORT=8002" in nonempty
    # File should stay small (orders of magnitude below the old multi-MB bloat).
    assert len(raw) < 500


def test_update_env_key_skips_rewrite_when_unchanged(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text("FOO=bar\nPUBLIC_TUNNEL_BASE=https://stable.example\n", encoding="utf-8", newline="\n")
    before = env_path.read_bytes()
    wrote = run_dev._update_env_key(
        "PUBLIC_TUNNEL_BASE",
        "https://stable.example",
        env_path=env_path,
    )
    assert wrote is False
    assert env_path.read_bytes() == before


def test_compact_env_file_removes_runaway_blank_lines(tmp_path: Path):
    env_path = tmp_path / ".env"
    # Simulate already-corrupted \\r\\r\\n inflation between keys.
    bloated = b"A=1" + (b"\r\r\n" * 64) + b"B=2\r\r\n"
    env_path.write_bytes(bloated)
    assert run_dev.compact_env_file(env_path) is True
    raw = env_path.read_bytes()
    # One blank separator may remain; runaway doubles must be gone.
    assert raw in (b"A=1\nB=2\n", b"A=1\n\nB=2\n")
    assert b"\r" not in raw
    assert raw.count(b"\n\n\n") == 0


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("A=1\r\nB=2\r\n", "A=1\nB=2\n"),
        ("A=1\r\r\nB=2\r\r\n", "A=1\n\nB=2\n\n"),
    ],
)
def test_normalize_env_newlines(raw: str, expected: str):
    assert run_dev._normalize_env_newlines(raw) == expected


def test_reload_excludes_env_file():
    cmd = run_dev.build_uvicorn_cmd(
        run_dev.DevConfig(
            host="127.0.0.1",
            backend_port=8002,
            frontend_port=5175,
            tunnel_enabled=True,
            tunnel_mode="quick",
            tunnel_name="nexus-dev",
            tunnel_config_path=None,
            public_tunnel_base=None,
            tunnel_edge_ip_version="4",
            tunnel_protocol="http2",
        ),
        reload=True,
    )
    assert "--reload" in cmd
    # Pair form: --reload-exclude <pattern>
    excludes = [cmd[i + 1] for i, part in enumerate(cmd) if part == "--reload-exclude"]
    assert "**/.env" in excludes
    assert "**/.env.*" in excludes


def test_build_tunnel_cmd_puts_protocol_before_url(monkeypatch):
    monkeypatch.setattr(run_dev, "_find_cloudflared", lambda: "cloudflared")
    cmd = run_dev.build_tunnel_cmd(
        run_dev.DevConfig(
            host="127.0.0.1",
            backend_port=8002,
            frontend_port=5175,
            tunnel_enabled=True,
            tunnel_mode="quick",
            tunnel_name="nexus-dev",
            tunnel_config_path=None,
            public_tunnel_base=None,
            tunnel_edge_ip_version="4",
            tunnel_protocol="http2",
        )
    )
    assert cmd[:6] == [
        "cloudflared",
        "tunnel",
        "--protocol",
        "http2",
        "--edge-ip-version",
        "4",
    ]
    assert "--retries" in cmd
    assert "--url" in cmd
    assert cmd[cmd.index("--url") + 1] == "http://127.0.0.1:8002"


def test_tunnel_supervisor_detects_edge_failure_unhealthy():
    supervisor = run_dev.TunnelSupervisor(
        run_dev.DevConfig(
            host="127.0.0.1",
            backend_port=8002,
            frontend_port=5175,
            tunnel_enabled=True,
            tunnel_mode="quick",
            tunnel_name="nexus-dev",
            tunnel_config_path=None,
            public_tunnel_base=None,
            tunnel_edge_ip_version="4",
            tunnel_protocol="http2",
        ),
        unhealthy_after_sec=1.0,
    )
    supervisor._started_at = time.monotonic() - 5.0
    supervisor._last_edge_fail_at = time.monotonic()

    class _Alive:
        def poll(self):
            return None

    assert supervisor._should_force_restart(_Alive()) is True


def test_tunnel_supervisor_healthy_after_register():
    supervisor = run_dev.TunnelSupervisor(
        run_dev.DevConfig(
            host="127.0.0.1",
            backend_port=8002,
            frontend_port=5175,
            tunnel_enabled=True,
            tunnel_mode="quick",
            tunnel_name="nexus-dev",
            tunnel_config_path=None,
            public_tunnel_base=None,
            tunnel_edge_ip_version="4",
            tunnel_protocol="http2",
        ),
        unhealthy_after_sec=1.0,
    )
    now = time.monotonic()
    supervisor._started_at = now - 10.0
    supervisor._saw_registered = True
    supervisor._last_registered_at = now
    supervisor._last_edge_fail_at = now - 0.5  # fail before last register

    class _Alive:
        def poll(self):
            return None

    assert supervisor._should_force_restart(_Alive()) is False


def test_handoff_preflight_ok_skips_when_no_handoff(monkeypatch):
    monkeypatch.delenv("NEXUS_WHATSAPP_HANDOFF_URL", raising=False)
    assert run_dev._handoff_preflight_ok({}) is True


def test_handoff_preflight_detects_403(monkeypatch):
    class _Resp:
        status_code = 403
        text = "Forbidden"

    def _fake_get(*args, **kwargs):
        return _Resp()

    import httpx as httpx_mod

    monkeypatch.setattr(httpx_mod, "get", _fake_get)
    assert (
        run_dev._handoff_preflight_ok(
            {
                "NEXUS_WHATSAPP_HANDOFF_URL": "https://nexus-dev.edutrust.in",
                "WEBHOOK_VERIFY_TOKEN": "local-token",
            }
        )
        is False
    )
