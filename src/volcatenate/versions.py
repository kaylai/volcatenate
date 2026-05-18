"""Backend version detection.

SulfurX and MAGEC are not pip-installable — they
live as source trees or supplementary-material distributions at user-
configured paths.  This module detects which version of each backend is in
use at run time, so it can be logged and recorded in reproducibility
manifests.

Public API
----------
``backend_version(name)`` returns a single string in the same spirit as
``importlib.metadata.version``:

    >>> import volcatenate
    >>> volcatenate.backend_version("sulfurx")
    "v.1.2 (4c36ee0)"
    >>> volcatenate.backend_version("magec")
    "v1b (45d3eee7)"

Possible return values share a common shape: ``"<tag> (<id>[, DIRTY])"``
or one of the sentinel strings ``"not installed"`` / ``"unknown ..."``.

Detection strategies
--------------------
Each backend registers a detector.  Two strategies exist today:

- **Git** (SulfurX): look up SHA in a manually maintained table of known
  releases.  Release tags come from ``gh api repos/<owner>/<repo>/tags``.
- **File hash** (MAGEC): hash a stable, version-identifying file (a
  compiled MATLAB P-file, a solver binary, etc.) and look it up in a
  manually maintained table.  Falls back to parsing a version tag from
  the filename so unknown future releases still produce a useful label.
- **Python module** (EVo, VolFe, VESIcal): locate the installed module
  with ``importlib.util.find_spec``, walk up looking for a ``.git``
  directory, and run the git detector if found (covers editable
  ``pip install -e`` installs of research forks). Falls back to
  ``importlib.metadata.version`` for regular pip installs.

All strategies return the same info-dict shape:

    {
      "name": str,                  # backend name
      "path": str,                  # resolved install path
      "status": "installed" | "no_version_info" | "not_installed",
      "id": str | None,             # short identifier (git short-SHA, file hash prefix)
      "full_id": str | None,        # full identifier
      "dirty": bool | None,         # tracked modifications (git only)
      "branch": str | None,         # current branch (git only; None on detached HEAD)
      "tag": str | None,            # matched release tag, if known
      "tested": bool,               # tag ∈ TESTED set
      "source": str,                # "git" | "file_hash" | "filename"
      # extras vary per detector (e.g. describe, file_hashed)
    }
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from typing import Callable, Optional


# ---------------------------------------------------------------------------
# Known-version tables (manually maintained)
# ---------------------------------------------------------------------------
# Update these dicts when a new backend release ships.

# SulfurX — commit SHA → release tag.
#   gh api repos/sdecho/Sulfur_X/tags
KNOWN_SULFURX: dict[str, str] = {
    "4c36ee0d1babdaaeaf915ba359bb9006f9c76741": "v.1.2",
    "0109e9a5de07d8f7cf05265742483deef583f21e": "v.1.1",
    "df38e6f550e3891c220411285a13299e7f81f09c": "v.1.0",
}
TESTED_SULFURX: set[str] = {"v.1.2"}

# MAGEC — SHA256 of MAGEC_Solver_v*.p (the compiled MATLAB solver) → label.
# MAGEC is distributed as supplementary material to Sun & Yao (2024) EPSL,
# not as a git repo, so we identify versions by hashing the compiled .p file.
# The filename itself also encodes a version suffix (e.g. "v1b"), which we
# fall back to when the hash is unknown.
#   shasum -a 256 MAGEC_Solver_v1b.p
KNOWN_MAGEC: dict[str, str] = {
    "45d3eee7c54e963678d7eeb0284415873359f63b2b982763a46ec4f1b9188735":
        "v1b (Sun & Yao 2024)",
}
TESTED_MAGEC: set[str] = {"v1b (Sun & Yao 2024)"}

# EVo, VolFe, VESIcal — commit SHA → release tag.
# These are Python packages typically installed editable from forks, so the
# git detector does the real work; populate as releases stabilize.
#   gh api repos/pipliggins/EVo/tags
KNOWN_EVO: dict[str, str] = {}
TESTED_EVO: set[str] = set()
#   gh api repos/kaylai/VolFe/tags
KNOWN_VOLFE: dict[str, str] = {}
TESTED_VOLFE: set[str] = set()
#   gh api repos/kaylai/VESIcal/tags
KNOWN_VESICAL: dict[str, str] = {}
TESTED_VESICAL: set[str] = set()


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _git(path: str, *args: str) -> Optional[str]:
    """Run ``git -C <path> <args>`` and return stripped stdout, or None on failure."""
    try:
        out = subprocess.check_output(
            ["git", "-C", path, *args],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _detect_git(path: str, known: dict[str, str], tested: set[str]) -> dict:
    """Git-strategy detector. Dirtiness counts only tracked modifications."""
    sha = _git(path, "rev-parse", "HEAD")
    if sha is None:
        return {"status": "no_version_info", "source": "git"}
    porcelain = _git(path, "status", "--porcelain") or ""
    tracked = [ln for ln in porcelain.splitlines() if not ln.startswith("??")]
    dirty = bool(tracked)
    describe = _git(path, "describe", "--tags", "--always") or sha[:7]
    tag = known.get(sha)
    # `symbolic-ref --short HEAD` returns the branch name, or fails on detached HEAD.
    branch = _git(path, "symbolic-ref", "--short", "HEAD")
    return {
        "status": "installed",
        "source": "git",
        "id": sha[:7],
        "full_id": sha,
        "dirty": dirty,
        "describe": describe,
        "branch": branch,
        "tag": tag,
        "tested": tag in tested if tag else False,
    }


# ---------------------------------------------------------------------------
# File-hash helpers
# ---------------------------------------------------------------------------

def _sha256_of(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _find_file(path: str, pattern: re.Pattern) -> Optional[str]:
    """Return the first file in ``path`` whose basename matches ``pattern``."""
    if not os.path.isdir(path):
        return None
    # Search recursively — MAGEC's .p file may be one level deep (Supplement/)
    for root, _dirs, files in os.walk(path):
        for name in files:
            if pattern.match(name):
                return os.path.join(root, name)
    return None


def _detect_file_hash(
    path: str,
    filename_pattern: re.Pattern,
    tag_from_filename: Callable[[str], Optional[str]],
    known: dict[str, str],
    tested: set[str],
) -> dict:
    """File-hash-strategy detector.

    Finds one version-identifying file (matching ``filename_pattern``),
    hashes it with SHA-256, and looks the hash up in ``known``.  If the
    hash is unknown, falls back to parsing a tag from the filename.
    """
    match = _find_file(path, filename_pattern)
    if match is None:
        return {"status": "no_version_info", "source": "file_hash"}

    full_hash = _sha256_of(match)
    short = full_hash[:8]
    tag = known.get(full_hash)

    info = {
        "status": "installed",
        "source": "file_hash" if tag else "filename",
        "id": short,
        "full_id": full_hash,
        "dirty": None,
        "tag": tag,
        "tested": tag in tested if tag else False,
        "file_hashed": os.path.relpath(match, path),
    }
    if tag is None:
        info["tag"] = tag_from_filename(os.path.basename(match))
    return info


# ---------------------------------------------------------------------------
# Python-module helpers
# ---------------------------------------------------------------------------

def _find_python_module_path(module_name: str) -> str:
    """Return the directory containing an importable module, or "" if absent.

    Uses ``importlib.util.find_spec`` so the module is not actually imported
    (avoids triggering side effects or import errors from unrelated deps).
    """
    try:
        import importlib.util
        spec = importlib.util.find_spec(module_name)
    except (ImportError, ValueError):
        return ""
    if spec is None or spec.origin is None:
        return ""
    return os.path.dirname(spec.origin)


def _walk_to_git_root(path: str, max_depth: int = 8) -> Optional[str]:
    """Walk up from ``path`` looking for a directory containing ``.git``."""
    cur = path
    for _ in range(max_depth):
        if os.path.isdir(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent
    return None


def _package_version(module_name: str) -> Optional[str]:
    """Return the installed package version via importlib.metadata, or None."""
    try:
        from importlib.metadata import version as _pkg_version
        return _pkg_version(module_name)
    except Exception:
        return None


def _detect_python_module(
    path: str,
    module_name: str,
    known: dict[str, str],
    tested: set[str],
) -> dict:
    """Python-module detector. Prefers git info; falls back to package metadata.

    Editable installs (``pip install -e``) of research forks live in a git
    working tree, so we walk up from the module directory to find ``.git`` and
    reuse the git detector. Regular pip installs land in site-packages with no
    git history; for those we fall back to ``importlib.metadata.version``.

    Either way the dict carries ``package_version`` (the
    ``importlib.metadata.version`` string, e.g. from ``__version__``) when
    available, alongside any git fields.
    """
    pkg_version = _package_version(module_name)

    git_root = _walk_to_git_root(path)
    if git_root is not None:
        info = _detect_git(git_root, known, tested)
        info["git_root"] = git_root
        info["package_version"] = pkg_version
        return info

    if pkg_version is None:
        return {"status": "no_version_info", "source": "importlib.metadata"}

    return {
        "status": "installed",
        "source": "importlib.metadata",
        "id": pkg_version,
        "full_id": pkg_version,
        "dirty": None,
        "tag": pkg_version,
        "tested": pkg_version in tested,
        "package_version": pkg_version,
    }


# ---------------------------------------------------------------------------
# Backend registry
# ---------------------------------------------------------------------------

def _sulfurx_path() -> str:
    from volcatenate.config import _find_sulfurx
    return _find_sulfurx()


def _magec_path() -> str:
    from volcatenate.config import _find_magec_solver
    return _find_magec_solver()


# MAGEC solver filename pattern: "MAGEC_Solver_<tag>.p" (e.g. v1b, v2a).
_MAGEC_SOLVER_RE = re.compile(r"^MAGEC_Solver_(?P<tag>[^.]+)\.p$", re.IGNORECASE)


def _magec_tag_from_filename(basename: str) -> Optional[str]:
    m = _MAGEC_SOLVER_RE.match(basename)
    return f"{m.group('tag')}?" if m else None


# Each entry: (path_resolver, detector_callable)
_BACKENDS: dict[str, tuple[Callable[[], str], Callable[[str], dict]]] = {
    "sulfurx": (
        _sulfurx_path,
        lambda path: _detect_git(path, KNOWN_SULFURX, TESTED_SULFURX),
    ),
    "magec": (
        _magec_path,
        lambda path: _detect_file_hash(
            path,
            _MAGEC_SOLVER_RE,
            _magec_tag_from_filename,
            KNOWN_MAGEC,
            TESTED_MAGEC,
        ),
    ),
    "evo": (
        lambda: _find_python_module_path("evo"),
        lambda path: _detect_python_module(path, "evo", KNOWN_EVO, TESTED_EVO),
    ),
    "volfe": (
        lambda: _find_python_module_path("VolFe"),
        lambda path: _detect_python_module(path, "VolFe", KNOWN_VOLFE, TESTED_VOLFE),
    ),
    "vesical": (
        lambda: _find_python_module_path("VESIcal"),
        lambda path: _detect_python_module(path, "VESIcal", KNOWN_VESICAL, TESTED_VESICAL),
    ),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def backend_version_info(name: str, path: Optional[str] = None) -> dict:
    """Return a dict describing a backend's version.

    Parameters
    ----------
    name : str
        Backend name. One of ``"sulfurx"``, ``"magec"``, ``"evo"``,
        ``"volfe"``, ``"vesical"``.
    path : str, optional
        Override the auto-detected install path.

    Returns
    -------
    dict
        See the module docstring for the field layout.
    """
    if name not in _BACKENDS:
        raise ValueError(
            f"Unknown backend {name!r}. Known backends: {sorted(_BACKENDS)}"
        )

    resolver, detect = _BACKENDS[name]
    resolved = path if path is not None else resolver()

    info: dict = {"name": name, "path": resolved}

    if not resolved or not os.path.isdir(resolved):
        info["status"] = "not_installed"
        return info

    info.update(detect(resolved))
    return info


def backend_version(name: str, path: Optional[str] = None) -> str:
    """Return a manifest-friendly version string for a backend.

    Mirrors the shape of ``importlib.metadata.version``:

        backend_version("sulfurx")  →  "v.1.2 (4c36ee0)"
        backend_version("magec")    →  "v1b (Sun & Yao 2024) (45d3eee7)"

    Use this directly in manifest writers::

        f"sulfurx=={backend_version('sulfurx')}\\n"
    """
    info = backend_version_info(name, path=path)
    status = info["status"]

    if status == "not_installed":
        return "not installed"

    if status == "no_version_info":
        src = info.get("source", "unknown")
        return f"unknown ({src} detection failed at {info['path']})"

    # status == "installed"
    tag = info.get("tag") or "unknown"
    identifier = info.get("id") or "?"
    dirty = ", DIRTY" if info.get("dirty") else ""
    return f"{tag} ({identifier}{dirty})"


def all_backend_versions() -> dict[str, dict]:
    """Return ``{name: backend_version_info(name)}`` for every registered backend."""
    return {name: backend_version_info(name) for name in _BACKENDS}


# Known volcatenate releases — populate as releases stabilize.
#   gh api repos/kaylai/volcatenate/tags
KNOWN_VOLCATENATE: dict[str, str] = {}
TESTED_VOLCATENATE: set[str] = set()


def volcatenate_version_info() -> dict:
    """Return rich version info for the installed volcatenate package.

    Same dict shape as :func:`backend_version_info`: git SHA, dirty flag,
    branch, ``git describe``, and ``package_version`` (from ``__version__``).
    Used by :func:`volcatenate.reproducible.create_bundle` to populate the
    ``volcatenate_version`` field of run bundles.
    """
    path = _find_python_module_path("volcatenate")
    info: dict = {"name": "volcatenate", "path": path}
    if not path or not os.path.isdir(path):
        info["status"] = "not_installed"
        return info
    info.update(_detect_python_module(
        path, "volcatenate", KNOWN_VOLCATENATE, TESTED_VOLCATENATE,
    ))
    return info
