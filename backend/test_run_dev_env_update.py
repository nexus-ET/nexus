"""Regression: Windows CRLF must not bloat backend/.env on tunnel URL updates."""

from __future__ import annotations

import importlib.util
import sys
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
