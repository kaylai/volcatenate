"""Tests for reproducible run bundles — provenance fields."""

from __future__ import annotations

import json
import os
import subprocess
from unittest import mock

import pytest

from volcatenate.composition import MeltComposition
from volcatenate.config import RunConfig
from volcatenate.reproducible import (
    RunBundle,
    create_bundle,
    save_bundle,
    load_bundle,
)


def _minimal_comp() -> MeltComposition:
    return MeltComposition(
        sample="Test",
        T_C=1200.0,
        SiO2=50.0,
        TiO2=1.0,
        Al2O3=15.0,
        FeOT=10.0,
        MgO=8.0,
        CaO=11.0,
        Na2O=2.5,
        K2O=0.5,
        P2O5=0.2,
        MnO=0.2,
        H2O=2.0,
        CO2=0.1,
        S=0.05,
    )


def test_bundle_has_new_provenance_fields():
    bundle = create_bundle(
        run_type="saturation_pressure",
        compositions=[_minimal_comp()],
        models=["VESIcal_Iacono"],
        config=RunConfig(),
    )
    assert hasattr(bundle, "caller_git_state")
    assert hasattr(bundle, "pip_freeze")
    assert hasattr(bundle, "comments")
    assert hasattr(bundle, "platform_info")


def test_platform_info_populated():
    bundle = create_bundle(
        run_type="saturation_pressure",
        compositions=[_minimal_comp()],
        models=["VESIcal_Iacono"],
        config=RunConfig(),
    )
    assert isinstance(bundle.platform_info, dict)
    for k in ("system", "release", "machine", "python_implementation"):
        assert k in bundle.platform_info
        assert bundle.platform_info[k]  # non-empty


def test_pip_freeze_is_string_or_none():
    bundle = create_bundle(
        run_type="saturation_pressure",
        compositions=[_minimal_comp()],
        models=["VESIcal_Iacono"],
        config=RunConfig(),
    )
    assert bundle.pip_freeze is None or isinstance(bundle.pip_freeze, str)
    if isinstance(bundle.pip_freeze, str):
        assert len(bundle.pip_freeze) > 0


def test_pip_freeze_failure_yields_none():
    with mock.patch(
        "volcatenate.reproducible._capture_pip_freeze",
        return_value=None,
    ):
        bundle = create_bundle(
            run_type="saturation_pressure",
            compositions=[_minimal_comp()],
            models=["VESIcal_Iacono"],
            config=RunConfig(),
        )
    assert bundle.pip_freeze is None


def test_pip_freeze_helper_handles_subprocess_error():
    """The helper itself should swallow OSError / CalledProcessError."""
    from volcatenate.reproducible import _capture_pip_freeze

    with mock.patch(
        "volcatenate.reproducible.subprocess.check_output",
        side_effect=OSError("boom"),
    ):
        assert _capture_pip_freeze() is None

    with mock.patch(
        "volcatenate.reproducible.subprocess.check_output",
        side_effect=subprocess.CalledProcessError(1, "pip"),
    ):
        assert _capture_pip_freeze() is None


def test_comments_default_empty_string():
    bundle = create_bundle(
        run_type="saturation_pressure",
        compositions=[_minimal_comp()],
        models=["VESIcal_Iacono"],
        config=RunConfig(),
    )
    assert bundle.comments == ""


def test_comments_passed_via_kwarg():
    bundle = create_bundle(
        run_type="saturation_pressure",
        compositions=[_minimal_comp()],
        models=["VESIcal_Iacono"],
        config=RunConfig(),
        comments="hello world",
    )
    assert bundle.comments == "hello world"


def test_comments_picked_up_from_config_when_kwarg_absent():
    cfg = RunConfig(bundle_comments="from-config")
    bundle = create_bundle(
        run_type="saturation_pressure",
        compositions=[_minimal_comp()],
        models=["VESIcal_Iacono"],
        config=cfg,
    )
    assert bundle.comments == "from-config"


def test_caller_git_state_in_repo(tmp_path, monkeypatch):
    # Run inside the volcatenate repo's working tree — there IS a .git
    bundle = create_bundle(
        run_type="saturation_pressure",
        compositions=[_minimal_comp()],
        models=["VESIcal_Iacono"],
        config=RunConfig(),
    )
    gs = bundle.caller_git_state
    assert isinstance(gs, dict)
    assert "repo_path" in gs
    assert "sha" in gs and isinstance(gs["sha"], str) and len(gs["sha"]) >= 7
    assert "dirty" in gs and isinstance(gs["dirty"], bool)
    assert "branch" in gs  # may be None for detached HEAD


def test_caller_git_state_outside_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # tmp_path is not inside any git repo
    bundle = create_bundle(
        run_type="saturation_pressure",
        compositions=[_minimal_comp()],
        models=["VESIcal_Iacono"],
        config=RunConfig(),
    )
    assert bundle.caller_git_state is None


def test_round_trip_preserves_new_fields(tmp_path):
    cfg = RunConfig(bundle_comments="round-trip")
    bundle = create_bundle(
        run_type="saturation_pressure",
        compositions=[_minimal_comp()],
        models=["VESIcal_Iacono"],
        config=cfg,
    )
    path = tmp_path / "bundle.json"
    save_bundle(bundle, str(path))
    loaded = load_bundle(str(path))
    assert loaded.comments == "round-trip"
    assert loaded.platform_info == bundle.platform_info
    assert loaded.pip_freeze == bundle.pip_freeze
    assert loaded.caller_git_state == bundle.caller_git_state


def test_load_old_bundle_without_new_fields(tmp_path):
    """Old bundles missing new fields must still load."""
    legacy = {
        "volcatenate_version": "0.0.1",
        "timestamp": "2025-01-01T00:00:00",
        "python_version": "3.11.0",
        "run_type": "saturation_pressure",
        "models": ["VESIcal_Iacono"],
        "compositions": [],
        "config": {},
        "satp_output": None,
        "degassing_output_dir": None,
        "backend_versions": {},
    }
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(legacy))
    loaded = load_bundle(str(path))
    assert loaded.comments == ""
    assert loaded.pip_freeze is None
    assert loaded.caller_git_state is None
    assert loaded.platform_info == {} or loaded.platform_info is None


def test_runconfig_has_bundle_comments_field():
    cfg = RunConfig()
    assert hasattr(cfg, "bundle_comments")
    assert cfg.bundle_comments == ""

    cfg2 = RunConfig(bundle_comments="hi")
    assert cfg2.bundle_comments == "hi"
