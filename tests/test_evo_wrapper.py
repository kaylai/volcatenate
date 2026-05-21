from __future__ import annotations

import pytest

def test_evo_config_has_run_type():
    """EVoConfig must have a run_type field defaulting to 'closed'."""
    from volcatenate.config import EVoConfig
    cfg = EVoConfig()
    assert hasattr(cfg, "run_type"), "EVoConfig is missing run_type field"
    assert cfg.run_type == "closed", "EVoConfig.run_type default should be 'closed'"


def test_evo_config_accepts_open():
    """EVoConfig must accept run_type='open'."""
    from volcatenate.config import EVoConfig
    cfg = EVoConfig(run_type="open")
    assert cfg.run_type == "open"


def test_evo_run_type_passed_to_yaml(tmp_path):
    """_write_yaml_configs must use cfg.run_type, not hardcoded 'closed'."""
    from volcatenate.backends.evo import _write_yaml_configs
    from volcatenate.config import EVoConfig
    from volcatenate.composition import composition_from_dict
    import yaml

    comp = composition_from_dict({
        "Sample": "TestSample", "T_C": 1200,
        "SiO2": 50, "TiO2": 1, "Al2O3": 15, "FeOT": 10,
        "MnO": 0.2, "MgO": 8, "CaO": 10, "Na2O": 2.5, "K2O": 0.5,
        "P2O5": 0.2, "H2O": 0.3, "CO2": 0.05, "S": 0.1, "Fe3FeT": 0.15,
    })
    cfg = EVoConfig(run_type="open")
    _, env_path, _ = _write_yaml_configs(comp, cfg, str(tmp_path), run_type=cfg.run_type)

    with open(env_path) as f:
        env_data = yaml.safe_load(f)

    assert env_data["RUN_TYPE"] == "open", (
        f"Expected RUN_TYPE='open' in EVo env.yaml but got {env_data.get('RUN_TYPE')!r}"
    )