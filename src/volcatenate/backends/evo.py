"""EVo backend — C-O-H-S volcanic degassing model.

Wraps the EVo library (https://github.com/pipliggins/EVo).
EVo is run via YAML config files → ``evo.run_evo()`` → CSV output.
"""

from __future__ import annotations

import contextlib
import glob
import io
import os
import shutil
import warnings
from typing import Optional

import numpy as np
import pandas as pd
import yaml

from volcatenate.log import logger

from volcatenate.backends._base import ModelBackend
from volcatenate.composition import MeltComposition
from volcatenate.config import RunConfig, resolve_sample_config
from volcatenate.converters.evo_converter import convert
from volcatenate.convert import compute_cs_v_mf, normalize_volatiles, ensure_standard_columns


# ── Patch EVo's interactive prompts ──────────────────────────────
# EVo sometimes asks y/N questions (e.g. SiO2-composition mismatch,
# temperature outside solubility model range).  When run inside
# volcatenate there is no terminal, so we monkey-patch query_yes_no
# to always answer "yes" and emit a Python warning instead.

def _auto_yes(question, default="yes"):
    """Non-interactive replacement for ``evo.messages.query_yes_no``."""
    warnings.warn(
        f"EVo asked: \"{question}\" — automatically continuing. "
        "Check your composition and settings if this is unexpected.",
        stacklevel=2,
    )
    return True


def _patch_evo_prompts():
    """Replace interactive prompts in the evo.messages module."""
    try:
        import evo.messages
        evo.messages.query_yes_no = _auto_yes
    except (ImportError, AttributeError):
        pass


@contextlib.contextmanager
def _quiet_evo():
    """Capture EVo's prolific stdout/stderr and route to the volcatenate logger.

    EVo prints config dumps, chemistry summaries, pressure-step progress,
    and class repr to stdout.  It also uses tqdm for progress bars, which
    writes to stderr and floods Jupyter notebooks with hundreds of
    ``0%| | 0/N`` lines.

    This redirects both stdout and stderr to ``logger.debug``, and sets
    ``TQDM_DISABLE=1`` to prevent tqdm output entirely.
    """
    buf_out = io.StringIO()
    buf_err = io.StringIO()
    old_tqdm = os.environ.get("TQDM_DISABLE")
    os.environ["TQDM_DISABLE"] = "1"
    try:
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            yield
    finally:
        if old_tqdm is None:
            os.environ.pop("TQDM_DISABLE", None)
        else:
            os.environ["TQDM_DISABLE"] = old_tqdm
        for buf in (buf_out, buf_err):
            captured = buf.getvalue()
            if captured.strip():
                for line in captured.strip().splitlines():
                    logger.debug("[EVo] %s", line)


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
    ) -> pd.Series | None:
        import evo
        _patch_evo_prompts()

        cfg = resolve_sample_config(config.evo, comp.sample)
        work_dir = os.path.join(config.output_dir, config.raw_output_dir, f"{comp.sample}_evo_satp")
        os.makedirs(work_dir, exist_ok=True)

        chem_path, env_path, out_yaml = _write_yaml_configs(
            comp, cfg, work_dir, run_type="closed",
            output_dir=config.output_dir,
        )

        evo_output_folder = os.path.join(work_dir, "output")
        try:
            with _quiet_evo():
                evo.run_evo(chem_path, env_path, out_yaml, folder=evo_output_folder)
        except Exception as exc:
            # EVo may write valid output before raising — check for it
            logger.warning("EVo raised during satP: %s — checking for partial output", exc)

        # EVo prefixes crashed-but-valid output with "_CRASHED_"
        csv_files = glob.glob(os.path.join(evo_output_folder, "*dgs_output_*.csv"))
        if not csv_files:
            return None

        df = pd.read_csv(csv_files[0])
        if "P" not in df.columns or len(df) == 0:
            return None

        # Run through the same converter pipeline as degassing
        comp_dict = comp.oxide_dict
        T_K = comp.T_C + 273.15
        df = convert(df, composition=comp_dict, T_K=T_K)
        df = compute_cs_v_mf(df)
        # Skip normalize_volatiles — meaningless for a single point
        df = ensure_standard_columns(df)

        result = df.iloc[0].copy()

        # Clean up raw tool output if requested
        if not config.keep_raw_output:
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
        _patch_evo_prompts()

        cfg = resolve_sample_config(config.evo, comp.sample)
        work_dir = os.path.join(config.output_dir, config.raw_output_dir, f"{comp.sample}_evo_degas")
        os.makedirs(work_dir, exist_ok=True)

        chem_path, env_path, out_yaml = _write_yaml_configs(
            comp, cfg, work_dir, run_type=cfg.run_type,
            output_dir=config.output_dir,
        )

        evo_output_folder = os.path.join(work_dir, "output")
        try:
            with _quiet_evo():
                evo.run_evo(chem_path, env_path, out_yaml, folder=evo_output_folder)
        except (Exception, SystemExit) as exc:
            # EVo sometimes writes valid output *before* raising
            # (e.g. "Model failed to converge at lowest pressure step.
            #  Data has been written out.").  It also calls exit() on
            # mass-conservation failure in open-system runs, which raises
            # SystemExit — catch both so we can salvage partial output.
            logger.warning("EVo raised during degassing: %s — checking for partial output", exc)

        # EVo prefixes crashed-but-valid output with "_CRASHED_", so match both
        # normal ("dgs_output_*.csv") and crashed ("_CRASHED_dgs_output_*.csv").
        csv_files = glob.glob(os.path.join(evo_output_folder, "*dgs_output_*.csv"))
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

        # Clean up raw tool output if requested
        if not config.keep_raw_output:
            shutil.rmtree(work_dir, ignore_errors=True)

        return df


# ── Helpers ─────────────────────────────────────────────────────────


def _pick_evo_buffer(comp: MeltComposition, cfg) -> dict:
    """Choose the fO2 buffer and offset that match the composition data.

    EVo accepts ``"FMQ"``, ``"NNO"``, or ``"IW"`` as the buffer name.
    The offset (``FO2_buffer_START``) must be relative to *that* buffer.

    Priority: ``comp.dNNO`` → ``"NNO"`` buffer; ``comp.dFMQ`` → ``"FMQ"``
    buffer; otherwise fall back to ``cfg.fo2_buffer`` with offset 0.
    """
    if comp.dNNO is not None:
        return {
            "FO2_buffer": "NNO",
            "FO2_buffer_START": float(comp.dNNO),
        }
    if comp.dFMQ is not None:
        return {
            "FO2_buffer": "FMQ",
            "FO2_buffer_START": float(comp.dFMQ),
        }
    # No explicit buffer offset — use config default
    logger.warning(
        "[EVo] No dNNO or dFMQ for %s; using %s buffer with offset 0",
        comp.sample, cfg.fo2_buffer,
    )
    return {
        "FO2_buffer": cfg.fo2_buffer,
        "FO2_buffer_START": 0.0,
    }


def _resolve_fo2_source(comp: MeltComposition, cfg) -> dict:
    """Resolve ``cfg.fo2_source`` into the env.yaml fO2 fields.

    Returns a dict of env.yaml keys to merge into the run config.
    Raises ``ValueError`` when the requested source has no matching
    data on the composition (only ``"auto"`` is silently permissive).

    See :class:`~volcatenate.config.EVoConfig.fo2_source` for the
    semantics of each option.
    """
    src = cfg.fo2_source
    has_fe3fet = not np.isnan(comp.fe3fet_computed) and comp.fe3fet_computed > 0

    if src == "absolute":
        if not cfg.fo2_set or cfg.fo2_start <= 0:
            raise ValueError(
                f"[EVo] fo2_source='absolute' requires fo2_set=True and "
                f"fo2_start>0; got fo2_set={cfg.fo2_set}, fo2_start={cfg.fo2_start}"
            )
        logger.info(
            "[EVo] %s: fO2 set absolutely (FO2_START=%g bar)",
            comp.sample, cfg.fo2_start,
        )
        return {
            "FO2_buffer_SET": False,
            "FO2_buffer": cfg.fo2_buffer,   # ignored but must be valid
            "FO2_buffer_START": 0.0,
            "FO2_SET": True,
            "FO2_START": float(cfg.fo2_start),
        }

    if src == "fe3fet":
        if not has_fe3fet:
            raise ValueError(
                f"[EVo] fo2_source='fe3fet' requires Fe3+/FeT on sample "
                f"{comp.sample!r}, but none was provided "
                f"(no Fe3FeT and no speciated FeO/Fe2O3)."
            )
        logger.info(
            "[EVo] %s: fO2 driven by Fe3+/FeT=%.4f via FO2_MODEL=%s",
            comp.sample, comp.fe3fet_computed, cfg.fo2_model,
        )
        return {
            "FO2_buffer_SET": False,
            "FO2_buffer": cfg.fo2_buffer,   # ignored
            "FO2_buffer_START": 0.0,
            "FO2_SET": False,
            "FO2_START": 0.0,
        }

    if src == "buffer":
        # Required offset must match cfg.fo2_buffer.
        wanted = cfg.fo2_buffer.upper()
        if wanted == "NNO" and comp.dNNO is None:
            raise ValueError(
                f"[EVo] fo2_source='buffer' with fo2_buffer='NNO' requires "
                f"comp.dNNO on sample {comp.sample!r}, but it is missing."
            )
        if wanted == "FMQ" and comp.dFMQ is None:
            raise ValueError(
                f"[EVo] fo2_source='buffer' with fo2_buffer='FMQ' requires "
                f"comp.dFMQ on sample {comp.sample!r}, but it is missing."
            )
        if wanted not in {"NNO", "FMQ", "IW"}:
            raise ValueError(
                f"[EVo] fo2_buffer must be one of NNO/FMQ/IW for "
                f"fo2_source='buffer'; got {cfg.fo2_buffer!r}"
            )
        # IW: no comp field exists — the user is responsible for using a
        # composition that actually buffers at IW. Use offset 0.
        offset = (
            float(comp.dNNO) if wanted == "NNO" and comp.dNNO is not None
            else float(comp.dFMQ) if wanted == "FMQ" and comp.dFMQ is not None
            else 0.0
        )
        logger.info(
            "[EVo] %s: fO2 set via %s buffer offset %+.3f",
            comp.sample, wanted, offset,
        )
        return {
            "FO2_buffer_SET": True,
            "FO2_buffer": wanted,
            "FO2_buffer_START": offset,
            "FO2_SET": False,
            "FO2_START": 0.0,
        }

    # ── "auto" (default) ─────────────────────────────────────────────
    # Prefer Fe3+/FeT when available; otherwise fall back to dNNO/dFMQ
    # via _pick_evo_buffer. Always logs the choice at INFO.
    if has_fe3fet:
        logger.info(
            "[EVo] %s: fo2_source=auto → Fe3+/FeT=%.4f available, "
            "driving fO2 via FO2_MODEL=%s",
            comp.sample, comp.fe3fet_computed, cfg.fo2_model,
        )
        return {
            "FO2_buffer_SET": False,
            "FO2_buffer": cfg.fo2_buffer,
            "FO2_buffer_START": 0.0,
            "FO2_SET": False,
            "FO2_START": 0.0,
        }

    picked = _pick_evo_buffer(comp, cfg)
    logger.info(
        "[EVo] %s: fo2_source=auto → no Fe3+/FeT, using %s buffer offset %+.3f",
        comp.sample, picked["FO2_buffer"], picked["FO2_buffer_START"],
    )
    return {
        "FO2_buffer_SET": True,
        **picked,
        "FO2_SET": False,
        "FO2_START": 0.0,
    }


def _write_yaml_configs(
    comp: MeltComposition,
    cfg,
    work_dir: str,
    run_type: str = "closed",
    output_dir: Optional[str] = None,
) -> tuple[str, str, str]:
    """Write chem.yaml, env.yaml, and output.yaml for an EVo run.

    Returns (chem_path, env_path, output_yaml_path). When ``output_dir`` is provided, also captures the resolved env / chem / output dicts via :mod:`volcatenate.resolved_inputs` so a sidecar yaml is written and the run-bundle picks them up.
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
        # Always include every oxide — even when 0.  EVo's single_cat()
        # silently drops keys with value 0, which makes downstream
        # functions (oneill2020, eguchi2018) crash with KeyError on
        # missing species like "mno".  Writing a tiny epsilon instead of
        # true zero keeps the key alive without affecting chemistry.
        chem_data[evo_key] = float(val) if val > 0 else 1e-10

    # Iron handling: split FeOT into FeO + Fe2O3 using Fe3FeT, except
    # when ``fo2_source="absolute"`` — EVo raises if both FO2_SET=True
    # and the iron split are present (readin.py:164).
    fe3fet = comp.fe3fet_computed
    split_iron = (
        cfg.fo2_source != "absolute"
        and not np.isnan(fe3fet)
        and fe3fet > 0
    )
    if split_iron:
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

    # fO2 / redox initialization: dispatched via cfg.fo2_source.
    # Returns the FO2_buffer_SET / FO2_buffer / FO2_buffer_START /
    # FO2_SET / FO2_START block ready to merge into env_data.
    fo2_block = _resolve_fo2_source(comp, cfg)

    env_data = {
        "COMPOSITION": cfg.composition,
        "RUN_TYPE": run_type,
        "SINGLE_STEP": cfg.single_step,
        "FIND_SATURATION": cfg.find_saturation,
        "ATOMIC_MASS_SET": cfg.atomic_mass_set,

        "GAS_SYS": cfg.gas_system,
        "FE_SYSTEM": cfg.fe_system,
        "OCS": cfg.ocs,
        "S_SAT_WARN": cfg.s_sat_warn,

        "T_START": t_kelvin,
        "P_START": cfg.p_start,
        "P_STOP": cfg.p_stop,
        "DP_MIN": cfg.dp_min,
        "DP_MAX": cfg.dp_max,
        "MASS": cfg.mass,
        "WgT": cfg.wgt,
        "LOSS_FRAC": cfg.loss_frac,

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

        # fO2 / fugacity initialization (dispatched above).
        **fo2_block,

        "ATOMIC_H": cfg.atomic_h,
        "ATOMIC_C": cfg.atomic_c,
        "ATOMIC_S": cfg.atomic_s,
        "ATOMIC_N": cfg.atomic_n,

        "FH2_SET": cfg.fh2_set,
        "FH2_START": cfg.fh2_start,
        "FH2O_SET": cfg.fh2o_set,
        "FH2O_START": cfg.fh2o_start,
        "FCO2_SET": cfg.fco2_set,
        "FCO2_START": cfg.fco2_start,

        "WTH2O_SET": True,
        "WTH2O_START": comp.H2O / 100.0,     # wt% → weight fraction

        "WTCO2_SET": True,
        "WTCO2_START": comp.CO2 / 100.0,

        "SULFUR_SET": True,
        "SULFUR_START": comp.S / 100.0,

        "NITROGEN_SET": cfg.nitrogen_set,
        # When the user has enabled nitrogen, prefer the sample's N
        # (ppm → mass fraction); fall back to ``cfg.nitrogen_start``
        # if the sample doesn't carry it.
        "NITROGEN_START": (
            float(comp.N_ppm) * 1e-6
            if cfg.nitrogen_set and getattr(comp, "N_ppm", 0.0) > 0
            else cfg.nitrogen_start
        ),

        "GRAPHITE_SATURATED": cfg.graphite_saturated,
        "GRAPHITE_START": cfg.graphite_start,
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

    # Capture the resolved input for the run-bundle and the per-run
    # resolved-inputs sidecar yaml.
    from volcatenate.resolved_inputs import capture as _capture_resolved
    _capture_resolved(
        sample=comp.sample,
        backend="EVo",
        data={"env": env_data, "chem": chem_data, "output": output_data},
        output_dir=output_dir,
    )

    return chem_path, env_path, output_yaml_path
