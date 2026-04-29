"""Session-level pytest fixtures shared across the test suite."""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

from volcatenate.config import _find_sulfurx
from volcatenate.versions import KNOWN_SULFURX, TESTED_SULFURX_VERSION


def _purge_sulfurx_modules(prefix: str | None = None) -> None:
    """Drop cached SulfurX modules so a re-import picks up new source.

    SulfurX is loaded via ``sys.path`` injection by the wrapper, so once a
    module like ``oxygen_fugacity`` is in ``sys.modules`` it will be reused
    even if ``sys.path`` later points at a different SulfurX checkout.
    Without this purge, swapping the configured ``cfg.sulfurx.path`` to a
    tested-version worktree would have no effect inside the same pytest session.

    If ``prefix`` is given, only modules whose ``__file__`` starts with that
    prefix are purged; otherwise every module that looks like a SulfurX
    module (by name) is purged.
    """
    sulfurx_module_names = {
        "Iacono_Marziano_COH", "VC_COH", "S_Fe", "SCSS_model",
        "degassingrun", "fugacity", "newvariables",
        "oxygen_fugacity", "sulfur_partition_coefficients",
        "melt_composition", "main_Fuego", "fuegodegassing",
        "s_isotope", "sulfur_fO2_degassing_test",
    }
    for name in list(sys.modules):
        mod = sys.modules.get(name)
        if name in sulfurx_module_names:
            if prefix is None:
                sys.modules.pop(name, None)
            else:
                file = getattr(mod, "__file__", None) or ""
                if file.startswith(prefix):
                    sys.modules.pop(name, None)


def _strip_sulfurx_paths_from_sys_path() -> list[str]:
    """Remove any ``sys.path`` entries that look like SulfurX checkouts.

    Returns the list that was removed so callers can restore it on teardown.
    """
    removed: list[str] = []
    keep: list[str] = []
    for entry in sys.path:
        if "Sulfur_X" in entry or "Sulfur" in os.path.basename(entry.rstrip("/")):
            removed.append(entry)
        else:
            keep.append(entry)
    sys.path[:] = keep
    return removed


@pytest.fixture(scope="session")
def sulfurx_tested_path(tmp_path_factory):
    """Yield a path to a clean SulfurX checkout at ``TESTED_SULFURX_VERSION``.

    Uses ``git worktree add`` from the developer's existing SulfurX repo
    (auto-discovered via :func:`volcatenate.config._find_sulfurx` or
    overridden by the ``SULFURX_PATH`` environment variable). The worktree
    is detached at the tested-version tag so SulfurX-touching tests run against
    byte-identical source regardless of what the parent checkout has
    progressed to.

    Skips cleanly if SulfurX is not installed locally or if
    ``TESTED_SULFURX_VERSION`` is not in the local checkout (run
    ``git -C $SULFURX_PATH fetch --tags`` to fix the latter).

    Asserts that the SHA the local tag points to matches the SHA recorded
    in :data:`volcatenate.versions.KNOWN_SULFURX` — this catches the rare
    but real case where upstream force-pushes a tag and silently changes
    what ``v.1.2`` (or whichever tag is currently set as ``TESTED_SULFURX_VERSION``) means.

    Also purges any cached SulfurX modules from ``sys.modules`` and any
    SulfurX-shaped entries from ``sys.path`` at setup and teardown, so
    re-imports inside the tested-version worktree are not shadowed by an earlier
    bare-checkout import in the same session.
    """
    src = os.environ.get("SULFURX_PATH") or _find_sulfurx()
    if not src or not os.path.isdir(src):
        pytest.skip(
            "SulfurX not found via SULFURX_PATH or auto-discovery — "
            "skipping tested-version SulfurX tests"
        )

    if not os.path.isdir(os.path.join(src, ".git")):
        pytest.skip(
            f"SulfurX install at {src} has no .git/ directory (probably "
            f"a zip download). The test fixture needs git history to "
            f"materialize a worktree at {TESTED_SULFURX_VERSION!r}. "
            f"Re-install via `git clone https://github.com/sdecho/Sulfur_X` "
            f"to enable SulfurX-touching tests."
        )

    tag_check = subprocess.run(
        ["git", "-C", src, "rev-parse", "--verify", TESTED_SULFURX_VERSION],
        capture_output=True, text=True,
    )
    if tag_check.returncode != 0:
        pytest.skip(
            f"SulfurX checkout at {src} is missing tag "
            f"{TESTED_SULFURX_VERSION!r}; run `git -C {src} fetch --tags`"
            f" and re-run."
        )
    actual_sha = tag_check.stdout.strip()

    expected_sha = next(
        (sha for sha, tag in KNOWN_SULFURX.items()
         if tag == TESTED_SULFURX_VERSION),
        None,
    )
    if expected_sha is None:
        pytest.fail(
            f"TESTED_SULFURX_VERSION={TESTED_SULFURX_VERSION!r} has no "
            f"matching SHA in KNOWN_SULFURX — versions.py is internally "
            f"inconsistent."
        )
    assert actual_sha == expected_sha, (
        f"Tag {TESTED_SULFURX_VERSION!r} in your SulfurX checkout points "
        f"to {actual_sha}, but KNOWN_SULFURX expects {expected_sha}. "
        f"Did upstream force-push the tag?"
    )

    target = tmp_path_factory.mktemp(f"sulfurx_{TESTED_SULFURX_VERSION}")
    add = subprocess.run(
        ["git", "-C", src, "worktree", "add", "--detach",
         str(target), TESTED_SULFURX_VERSION],
        capture_output=True, text=True,
    )
    if add.returncode != 0:
        pytest.fail(
            f"`git worktree add` failed for {TESTED_SULFURX_VERSION!r}: "
            f"{add.stderr.strip()}"
        )

    saved_sys_path = list(sys.path)
    _strip_sulfurx_paths_from_sys_path()
    _purge_sulfurx_modules()
    sys.path.insert(0, str(target))

    try:
        yield str(target)
    finally:
        sys.path[:] = saved_sys_path
        _purge_sulfurx_modules()
        subprocess.run(
            ["git", "-C", src, "worktree", "remove", "--force", str(target)],
            check=False, capture_output=True,
        )
