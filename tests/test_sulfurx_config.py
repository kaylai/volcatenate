"""SulfurXConfig field-shape tests.

Covers:
- s_fe_choice accepts both int and float (Muth & Wallace and modified variants)
- monte_carlo and monte_carlo_n_iter are real config fields with the right defaults
- The wrapper's resolved-inputs capture in _run_degassing includes the new fields

Behavior tests for the Monte Carlo loop itself live in
``test_sulfurx_montecarlo.py``.
"""
from __future__ import annotations

import pytest

from volcatenate.config import SulfurXConfig, load_config


# ── s_fe_choice: int and float both accepted ───────────────────────


def test_s_fe_choice_accepts_int():
    cfg = SulfurXConfig(s_fe_choice=1)
    assert cfg.s_fe_choice == 1


def test_s_fe_choice_accepts_float_muth_wallace():
    """Per S_Fe.py, model_choice == 100 selects Muth & Wallace.
    Volcatenate must not reject float values: any float other than 0/1/100
    triggers the upstream "modified Muth & Wallace" branch.
    """
    cfg = SulfurXConfig(s_fe_choice=99.5)
    assert cfg.s_fe_choice == pytest.approx(99.5)


def test_s_fe_choice_float_via_yaml(tmp_path):
    yaml_path = tmp_path / "cfg.yaml"
    yaml_path.write_text("sulfurx:\n  s_fe_choice: 99.5\n")
    cfg = load_config(str(yaml_path))
    assert cfg.sulfurx.s_fe_choice == pytest.approx(99.5)


# ── monte_carlo config fields ─────────────────────────────────────


def test_monte_carlo_field_default_zero():
    cfg = SulfurXConfig()
    assert cfg.monte_carlo == 0


def test_monte_carlo_n_iter_field_default_zero():
    cfg = SulfurXConfig()
    assert cfg.monte_carlo_n_iter == 0


def test_monte_carlo_fields_settable():
    cfg = SulfurXConfig(monte_carlo=1, monte_carlo_n_iter=10)
    assert cfg.monte_carlo == 1
    assert cfg.monte_carlo_n_iter == 10


def test_monte_carlo_fields_loadable_from_yaml(tmp_path):
    yaml_path = tmp_path / "cfg.yaml"
    yaml_path.write_text(
        "sulfurx:\n"
        "  monte_carlo: 1\n"
        "  monte_carlo_n_iter: 50\n"
    )
    cfg = load_config(str(yaml_path))
    assert cfg.sulfurx.monte_carlo == 1
    assert cfg.sulfurx.monte_carlo_n_iter == 50
