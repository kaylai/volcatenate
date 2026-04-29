"""Tests for SulfurX install resolution: prepare_sulfurx_tested,
smarter _find_sulfurx, and the use_tested_version flag's effect on
the wrapper's _ensure_on_path.

Most of these need git operations against the developer's SulfurX
checkout, so they share the conftest auto-discovery logic and skip
cleanly when SulfurX isn't installed.
"""
from __future__ import annotations

import os
import subprocess
import sys
from unittest.mock import patch

import pytest

from volcatenate.config import (
    RunConfig, SulfurXConfig,
    _find_sulfurx, _git_head_sha, _sulfurx_candidates,
    _volcatenate_cache_dir, prepare_sulfurx_tested,
)
from volcatenate.versions import KNOWN_SULFURX, TESTED_SULFURX_VERSION


def _has_sulfurx() -> bool:
    src = os.environ.get("SULFURX_PATH") or _find_sulfurx()
    return bool(src) and os.path.isdir(src)


sulfurx_required = pytest.mark.skipif(
    not _has_sulfurx(),
    reason="No SulfurX install discoverable — skipping",
)


# ── Pure unit tests (no SulfurX required) ────────────────────────────


def test_use_tested_version_field_default_true():
    cfg = SulfurXConfig()
    assert cfg.use_tested_version is True


def test_use_tested_version_settable():
    cfg = SulfurXConfig(use_tested_version=False)
    assert cfg.use_tested_version is False


def test_volcatenate_cache_dir_honors_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert _volcatenate_cache_dir() == str(tmp_path / "volcatenate")


def test_volcatenate_cache_dir_default_when_xdg_unset(monkeypatch):
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    assert _volcatenate_cache_dir() == os.path.expanduser("~/.cache/volcatenate")


def test_prepare_sulfurx_tested_raises_when_no_install_found(monkeypatch):
    monkeypatch.delenv("SULFURX_PATH", raising=False)
    with patch("volcatenate.config._sulfurx_candidates", return_value=[]):
        with pytest.raises(FileNotFoundError, match="install location not found"):
            prepare_sulfurx_tested()


# ── Integration tests (need a real SulfurX checkout) ─────────────────


@sulfurx_required
def test_find_sulfurx_returns_a_real_install():
    path = _find_sulfurx()
    assert path
    assert os.path.isfile(os.path.join(path, "Iacono_Marziano_COH.py"))


@sulfurx_required
def test_prepare_sulfurx_tested_returns_path_at_tested_sha():
    path = prepare_sulfurx_tested()
    expected_sha = next(
        sha for sha, tag in KNOWN_SULFURX.items()
        if tag == TESTED_SULFURX_VERSION
    )
    assert _git_head_sha(path) == expected_sha


@sulfurx_required
def test_prepare_sulfurx_tested_fast_path_returns_source_when_already_at_sha(
    tmp_path,
):
    """When the source checkout's HEAD is already at the tested-version
    SHA, prepare_sulfurx_tested returns the source path directly — no
    worktree is created.
    """
    expected_sha = next(
        sha for sha, tag in KNOWN_SULFURX.items()
        if tag == TESTED_SULFURX_VERSION
    )

    # Pretend an arbitrary directory is the source AND that it already
    # has the right SHA. We only verify the fast-path return; the file
    # contents don't matter for this test.
    fake_source = str(tmp_path / "fake_sulfurx")
    os.makedirs(fake_source)

    with patch("volcatenate.config._git_head_sha",
               return_value=expected_sha):
        with patch("volcatenate.config._find_sulfurx",
                   return_value=fake_source):
            result = prepare_sulfurx_tested()

    assert result == fake_source, (
        "Fast path should return the source path unchanged when its "
        "HEAD already matches the tested-version SHA."
    )


def test_prepare_sulfurx_tested_raises_when_source_has_no_git(tmp_path):
    """A source directory without .git/ should fail with an actionable
    error pointing the user at git clone."""
    fake_source = str(tmp_path / "zip_extract")
    os.makedirs(fake_source)

    # Stub _find_sulfurx and _git_head_sha so we don't accidentally
    # use the developer's real install.
    with patch("volcatenate.config._find_sulfurx",
               return_value=fake_source), \
         patch("volcatenate.config._git_head_sha", return_value=None):
        with pytest.raises(RuntimeError, match=r"no \.git/ directory"):
            prepare_sulfurx_tested()


@sulfurx_required
def test_find_sulfurx_prefers_tested_version_when_multiple_candidates(
    tmp_path, monkeypatch,
):
    """When _sulfurx_candidates returns multiple paths, _find_sulfurx
    should prefer the one whose HEAD is at TESTED_SULFURX_VERSION's SHA.
    """
    expected_sha = next(
        sha for sha, tag in KNOWN_SULFURX.items()
        if tag == TESTED_SULFURX_VERSION
    )
    other = str(tmp_path / "other_checkout")
    tested = str(tmp_path / "v12_checkout")
    os.makedirs(other)
    os.makedirs(tested)

    def fake_head_sha(path):
        return expected_sha if path == tested else "deadbeef" * 5

    monkeypatch.delenv("SULFURX_PATH", raising=False)
    with patch("volcatenate.config._sulfurx_candidates",
               return_value=[other, tested]), \
         patch("volcatenate.config._git_head_sha",
               side_effect=fake_head_sha):
        result = _find_sulfurx()

    assert result == tested, (
        f"Expected _find_sulfurx to prefer the v.1.2 candidate "
        f"({tested}), got {result}"
    )


@sulfurx_required
def test_find_sulfurx_falls_back_to_first_candidate_when_no_match(
    tmp_path, monkeypatch,
):
    """If no candidate matches the tested-version SHA, _find_sulfurx
    falls back to the first candidate (legacy behavior).
    """
    other_a = str(tmp_path / "checkout_a")
    other_b = str(tmp_path / "checkout_b")
    os.makedirs(other_a)
    os.makedirs(other_b)

    monkeypatch.delenv("SULFURX_PATH", raising=False)
    with patch("volcatenate.config._sulfurx_candidates",
               return_value=[other_a, other_b]), \
         patch("volcatenate.config._git_head_sha",
               return_value="deadbeef" * 5):
        result = _find_sulfurx()

    assert result == other_a


# ── Wrapper integration: use_tested_version flag effect ───────────────


@sulfurx_required
def test_ensure_on_path_uses_tested_version_when_default(tmp_path):
    """With default use_tested_version=True, _ensure_on_path ensures the
    tested-version checkout is on sys.path — and the bogus user-set
    `path` is NOT what gets used.
    """
    from volcatenate.backends.sulfurx import Backend

    config = RunConfig()
    config.sulfurx.path = "/this/path/should/be/ignored"
    # use_tested_version defaults to True
    saved_path = list(sys.path)
    try:
        Backend()._ensure_on_path(config)
        # After the call, sys.path must contain a checkout whose HEAD
        # is the tested-version SHA. Whether it was newly added by this
        # call or already present from a prior call doesn't matter for
        # this contract.
        expected_sha = next(
            sha for sha, tag in KNOWN_SULFURX.items()
            if tag == TESTED_SULFURX_VERSION
        )
        on_path = [p for p in sys.path if _git_head_sha(p) == expected_sha]
        assert on_path, (
            f"Expected a SulfurX checkout at the tested-version SHA on "
            f"sys.path; got entries {sys.path[:5]!r}..."
        )
        # And the bogus path is NOT what got resolved to.
        assert "/this/path/should/be/ignored" not in sys.path
    finally:
        sys.path[:] = saved_path


@sulfurx_required
def test_ensure_on_path_honors_explicit_path_when_use_tested_version_false(
    tmp_path,
):
    """With use_tested_version=False, _ensure_on_path uses the explicit
    cfg.sulfurx.path (not the tested-version cache).
    """
    from volcatenate.backends.sulfurx import Backend

    src = _find_sulfurx()  # the user's main checkout
    config = RunConfig()
    config.sulfurx.path = src
    config.sulfurx.use_tested_version = False
    saved_path = list(sys.path)
    try:
        Backend()._ensure_on_path(config)
        assert src in sys.path, (
            f"Expected explicit path {src!r} to be on sys.path with "
            f"use_tested_version=False; sys.path is {sys.path[:5]!r}..."
        )
    finally:
        sys.path[:] = saved_path


def test_ensure_on_path_raises_actionable_error_when_no_install(monkeypatch):
    """When no SulfurX install can be found at all, the error message
    mentions the new wording 'install location not found' and gives
    actionable next steps.
    """
    from volcatenate.backends.sulfurx import Backend

    monkeypatch.delenv("SULFURX_PATH", raising=False)
    config = RunConfig()
    config.sulfurx.path = ""
    # Force every discovery path to come back empty.
    with patch("volcatenate.config._sulfurx_candidates", return_value=[]), \
         patch("volcatenate.config._find_sulfurx", return_value=""):
        with pytest.raises(FileNotFoundError) as exc_info:
            Backend()._ensure_on_path(config)
    msg = str(exc_info.value)
    assert "install location not found" in msg
    assert "git clone" in msg
