"""EVo backend — C-O-H-S volcanic degassing model.

Wraps the EVo library (https://github.com/pipliggins/EVo).
EVo is run via YAML config files → ``evo.run_evo()`` → CSV output.
"""

from __future__ import annotations

import glob
import os
import shutil

import numpy as np
import pandas as pd
import yaml

from volcatenate.backends._base import ModelBackend
from volcatenate.composition import MeltComposition
from volcatenate.config import RunConfig
from volcatenate.converters.evo_converter import convert
from volcatenate.convert import compute_cs_v_mf, normalize_volatiles, ensure_standard_columns


# ── Custom YAML dumper (EVo expects True/False not true/false) ──────

class _EvoDumper(yaml.SafeDumper):
    pass

_EvoDumper.add_representer(
    bool,
    lambda dumper, data: dumper.represent_scalar(
        "tag:yaml.org,2002:bool", "True" if data else "False"),
)
_EvoDumper.add_representer(
    type(None),
    lambda dumper, data: dumper.represent_scalar(
        "tag:yaml.org,2002:null", ""),
)


class Backend(ModelBackend):

    @property
    def name(self) -> str:
        return "EVo"

    def is_available(self) -> bool:
        try:
            import evo  # noqa: F401
            return True
        except ImportError:
            return False

    # ----------------------------------------------------------------
    # Saturation pressure
    # ----------------------------------------------------------------
    def calculate_saturation_pressure(
        self,
        comp: MeltComposition,
        config: RunConfig,
    ) -> float:
        import evo

        cfg = config.evo
        work_dir = os.path.join(config.output_dir, f"{comp.sample}_evo_satp")
        os.makedirs(work_dir, exist_ok=True)

        chem_path, env_path, out_yaml = _write_yaml_configs(
            comp, cfg, work_dir, run_type="closed",
        )

        evo_output_folder = os.path.join(work_dir, "output")
        try:
            evo.run_evo(chem_path, env_path, out_yaml, folder=evo_output_folder)
        except Exception:
            return np.nan

        csv_files = glob.glob(os.path.join(evo_output_folder, "dgs_output_*.csv"))
        if not csv_files:
            return np.nan

        df = pd.read_csv(csv_files[0])
        result = np.nan
        if "P" in df.columns and len(df) > 0:
            result = float(df["P"].iloc[0])

        # Clean up intermediate files if requested
        if not config.keep_intermediates:
            shutil.rmtree(work_dir, ignore_errors=True)

        return result

    # ----------------------------------------------------------------
    # Degassing path
    # ----------------------------------------------------------------
    def calculate_degassing(
        self,
        comp: MeltComposition,
        config: RunConfig,
    ) -> pd.DataFrame:
        import evo

        cfg = config.evo
        work_dir = os.path.join(config.output_dir, f"{comp.sample}_evo_degas")
        os.makedirs(work_dir, exist_ok=True)

        chem_path, env_path, out_yaml = _write_yaml_configs(
            comp, cfg, work_dir, run_type="closed",
        )

        evo_output_folder = os.path.join(work_dir, "output")
        evo.run_evo(chem_path, env_path, out_yaml, folder=evo_output_folder)

        csv_files = glob.glob(os.path.join(evo_output_folder, "dgs_output_*.csv"))
        if not csv_files:
            raise FileNotFoundError(
                f"EVo did not produce output CSV in {evo_output_folder}"
            )

        df = pd.read_csv(csv_files[0])

        # Build composition dict for Fe3+/FeT calculation
        comp_dict = comp.oxide_dict
        T_K = comp.T_C + 273.15

        # Standardize output
        df = convert(df, composition=comp_dict, T_K=T_K)
        df = compute_cs_v_mf(df)
        df = normalize_volatiles(df)
        df = ensure_standard_columns(df)

        # Clean up intermediate files if requested
        if not config.keep_intermediates:
            shutil.rmtree(work_dir, ignore_errors=True)

        return df


# ── Helpers ─────────────────────────────────────────────────────────

def _write_yaml_configs(
    comp: MeltComposition,
    cfg,
    work_dir: str,
    run_type: str = "closed",
) -> tuple[str, str, str]:
    """Write chem.yaml, env.yaml, and output.yaml for an EVo run.

    Returns (chem_path, env_path, output_yaml_path).
    """
    # --- chem.yaml ---
    oxide_map = {
        "SiO2": "SIO2", "TiO2": "TIO2", "Al2O3": "AL2O3",
        "MnO": "MNO", "MgO": "MGO",
        "CaO": "CAO", "Na2O": "NA2O", "K2O": "K2O", "P2O5": "P2O5",
    }
    chem_data = {}
    for src_key, evo_key in oxide_map.items():
        val = getattr(comp, src_key, 0.0)
        if val > 0:
            chem_data[evo_key] = float(val)

    # Iron handling: split FeOT into FeO + Fe2O3 using Fe3FeT
    fe3fet = comp.fe3fet_computed
    if not np.isnan(fe3fet) and fe3fet > 0:
        feot = comp.FeOT
        # MW ratio: Fe2O3 / (2 * FeO) = 159.69 / (2 * 71.844) ≈ 1.11134
        chem_data["FEO"] = float(feot * (1.0 - fe3fet))
        chem_data["FE2O3"] = float(feot * fe3fet * (159.69 / (2.0 * 71.844)))
    else:
        chem_data["FEO"] = float(comp.FeOT)

    chem_path = os.path.join(work_dir, "chem.yaml")
    with open(chem_path, "w") as f:
        yaml.dump(chem_data, f, Dumper=_EvoDumper, default_flow_style=False)

    # --- env.yaml ---
    t_kelvin = comp.T_C + 273.15
    has_fe3fet = not np.isnan(fe3fet) and fe3fet > 0

    env_data = {
        "COMPOSITION": "basalt",
        "RUN_TYPE": run_type,
        "SINGLE_STEP": False,
        "FIND_SATURATION": cfg.find_saturation,
        "ATOMIC_MASS_SET": cfg.atomic_mass_set,

        "GAS_SYS": cfg.gas_system,
        "FE_SYSTEM": cfg.fe_system,
        "OCS": False,
        "S_SAT_WARN": False,

        "T_START": t_kelvin,
        "P_START": cfg.p_start,
        "P_STOP": cfg.p_stop,
        "DP_MIN": cfg.dp_min,
        "DP_MAX": cfg.dp_max,
        "MASS": cfg.mass,
        "WgT": 0.00001,
        "LOSS_FRAC": 0.9999,

        "DENSITY_MODEL": cfg.density_model,
        "FO2_MODEL": cfg.fo2_model,
        "FMQ_MODEL": cfg.fmq_model,
        "H2O_MODEL": cfg.h2o_model,
        "H2_MODEL": cfg.h2_model,
        "C_MODEL": cfg.c_model,
        "CO_MODEL": cfg.co_model,
        "CH4_MODEL": cfg.ch4_model,
        "SULFIDE_CAPACITY": cfg.sulfide_capacity,
        "SULFATE_CAPACITY": cfg.sulfate_capacity,
        "SCSS": cfg.scss,
        "N_MODEL": cfg.n_model,

        # fO2 buffer: use buffer if no Fe3FeT split
        "FO2_buffer_SET": not has_fe3fet,
        "FO2_buffer": cfg.fo2_buffer,
        "FO2_buffer_START": float(comp.dNNO) if comp.dNNO is not None else 0.0,

        "FO2_SET": False,
        "FO2_START": 0.0,

        "ATOMIC_H": 500,
        "ATOMIC_C": 200,
        "ATOMIC_S": 4000,
        "ATOMIC_N": 10,

        "FH2_SET": False,
        "FH2_START": 0.24,
        "FH2O_SET": False,
        "FH2O_START": 1000,
        "FCO2_SET": False,
        "FCO2_START": 1,

        "WTH2O_SET": True,
        "WTH2O_START": comp.H2O / 100.0,     # wt% → weight fraction

        "WTCO2_SET": True,
        "WTCO2_START": comp.CO2 / 100.0,

        "SULFUR_SET": True,
        "SULFUR_START": comp.S / 100.0,

        "NITROGEN_SET": False,
        "NITROGEN_START": 0.0001,

        "GRAPHITE_SATURATED": False,
        "GRAPHITE_START": 0.0001,
    }

    env_path = os.path.join(work_dir, "env.yaml")
    with open(env_path, "w") as f:
        yaml.dump(env_data, f, Dumper=_EvoDumper, default_flow_style=False)

    # --- output.yaml ---
    output_data = {
        "plot_melt_species": False,
        "plot_gas_species_wt": False,
        "plot_gas_species_mol": False,
        "plot_gas_fraction": False,
        "plot_fo2_dFMQ": False,
    }

    output_yaml_path = os.path.join(work_dir, "output.yaml")
    with open(output_yaml_path, "w") as f:
        yaml.dump(output_data, f, Dumper=_EvoDumper, default_flow_style=False)

    return chem_path, env_path, output_yaml_path
