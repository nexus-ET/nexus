"""Unit tests for bootstrap_alembic legacy-chain helpers (no DB required)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "scripts" / "bootstrap_alembic.py"


def _load_bootstrap():
    spec = importlib.util.spec_from_file_location("bootstrap_alembic", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # Avoid executing main / engine creation — only load helpers after patching?
    # The module imports sqlalchemy at top level but does not connect until main().
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def boot():
    return _load_bootstrap()


def test_revision_index_known_and_unknown(boot):
    assert boot._revision_index("d9a4b2c81f0e") == 0
    assert boot._revision_index("s5p8q1r54s0m") == len(boot.ORDERED_REVISIONS) - 1
    # Post-legacy revisions that tripped deploy.sh on 2026-07-26
    assert boot._revision_index("c4d7e0f53g6h") is None
    assert boot._revision_index("f7y0d3esolution") is None
    assert boot._revision_index("not_a_real_rev") is None


def test_next_revision_stops_at_legacy_end(boot):
    assert boot._next_revision("d9a4b2c81f0e") == "e1f3a8b92c4d"
    assert boot._next_revision("s5p8q1r54s0m") is None
    assert boot._next_revision("c4d7e0f53g6h") is None


def test_stamp_if_behind_schema_skips_post_legacy(boot, monkeypatch):
    calls: list[tuple] = []

    def fake_run(*args):
        calls.append(args)
        raise AssertionError("stamp must not run for post-legacy current")

    monkeypatch.setattr(boot, "_run_alembic", fake_run)
    monkeypatch.setattr(
        boot,
        "_detect_sequential_schema_revision",
        lambda _i: "s5p8q1r54s0m",
    )

    out = boot._stamp_if_behind_schema(inspector=None, current="c4d7e0f53g6h")
    assert out == "c4d7e0f53g6h"
    assert calls == []
