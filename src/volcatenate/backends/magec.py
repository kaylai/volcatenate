"""MAGEC backend — Magma And Gas Equilibrium Calculator (Sun & Yao, 2024).

Runs MAGEC's compiled MATLAB solver (.p) via subprocess, using a bundled
CSV wrapper for fast I/O.  Requires:
  1. MATLAB installed (with the bundled fsolve/lsqnonlin shims if the
     Optimization Toolbox is not available)
  2. MAGEC_Solver_v1b.p in the configured solver directory

The backend generates CSV input files, writes a MATLAB batch script that
passes settings as a struct, and calls MAGEC_CSV_Wrapper.m which handles
CSV↔xlsx conversion inside MATLAB before calling the .p solver.  Python-
side I/O is pure CSV, eliminating the slow openpyxl dependency for MAGEC.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import warnings

import numpy as np
import pandas as pd

from volcatenate.backends._base import ModelBackend
from volcatenate import columns as col
from volcatenate.composition import MeltComposition
from volcatenate.config import RunConfig
from volcatenate.converters.magec_converter import convert
from volcatenate.convert import compute_cs_v_mf, normalize_volatiles, ensure_standard_columns
from volcatenate.log import logger


# ── Resolve bundled data directories (computed once at import) ──────
_DATA_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, "data")
)
_SOLVER_DIR = os.path.join(_DATA_DIR, "magec_solver")
_SHIMS_DIR = os.path.join(_DATA_DIR, "magec_shims")


class Backend(ModelBackend):

    supports_batch_satp: bool = True

    @property
    def name(self) -> str:
        return "MAGEC"

    def is_available(self) -> bool:
        """Check that MATLAB and the MAGEC solver directory exist."""
        # We can't fully test at import time, but we can check for
        # a sensible default.  The real check happens at run time.
        return True  # Always register; will fail clearly at run time

    def _check_matlab(self, config: RunConfig) -> None:
        """Raise a clear error if MATLAB is not found."""
        matlab_bin = config.magec.matlab_bin
        if not matlab_bin or not os.path.isfile(matlab_bin):
            raise FileNotFoundError(
                f"MATLAB not found at '{matlab_bin}'.\n"
                f"MAGEC requires a MATLAB installation to run.\n"
                f"Set config.magec.matlab_bin to the full path of your "
                f"MATLAB binary (e.g. /Applications/MATLAB_R2025b.app/bin/matlab)."
            )

    def _check_solver(self, config: RunConfig) -> None:
        """Raise a clear error if the MAGEC solver is missing."""
        # Check bundled CSV wrapper
        wrapper_m = os.path.join(_SOLVER_DIR, "MAGEC_CSV_Wrapper.m")
        if not os.path.isfile(wrapper_m):
            raise FileNotFoundError(
                f"Bundled MAGEC CSV wrapper not found at '{wrapper_m}'.\n"
                f"This file should have been installed with volcatenate.\n"
                f"Try reinstalling: pip install -e ."
            )
        # Check that the compiled .p solver exists in the configured dir
        solver_dir = config.magec.solver_dir
        if not solver_dir or not os.path.isdir(solver_dir):
            raise FileNotFoundError(
                f"MAGEC solver directory not found at '{solver_dir}'.\n"
                f"Set config.magec.solver_dir to the directory containing "
                f"MAGEC_Solver_v1b.p (typically the 'Supplement' folder)."
            )
        solver_p = os.path.join(solver_dir, "MAGEC_Solver_v1b.p")
        if not os.path.isfile(solver_p):
            raise FileNotFoundError(
                f"MAGEC_Solver_v1b.p not found in '{solver_dir}'.\n"
                f"Ensure the MAGEC solver .p file is in the configured directory."
            )

    # ----------------------------------------------------------------
    # Saturation pressure
    # ----------------------------------------------------------------
    def calculate_saturation_pressure(
        self,
        comp: MeltComposition,
        config: RunConfig,
    ) -> pd.Series | None:
        self._check_matlab(config)
        self._check_solver(config)

        cfg = config.magec
        work_dir = os.path.join(config.output_dir, config.raw_output_dir, "magec", comp.sample)
        os.makedirs(work_dir, exist_ok=True)

        safe_name = comp.sample.replace("/", "_").replace(" ", "_")
        in_csv = os.path.abspath(os.path.join(work_dir, f"{safe_name}_input.csv"))
        out_csv = os.path.abspath(os.path.join(work_dir, f"{safe_name}_output.csv"))

        _create_magec_input_csv(comp, cfg, in_csv)
        _run_magec_matlab(in_csv, out_csv, cfg)

        if not os.path.isfile(out_csv):
            warnings.warn(
                f"MAGEC produced no output for {comp.sample}. "
                f"This may indicate a MATLAB timeout or solver failure. "
                f"Check timeout={cfg.timeout}s and p_start_kbar={cfg.p_start_kbar}."
            )
            return None

        try:
            df = pd.read_csv(out_csv)

            # Run through the same converter pipeline as degassing
            df = convert(df)
            df = compute_cs_v_mf(df)
            # Skip normalize_volatiles — meaningless for a single point
            df = ensure_standard_columns(df)

            # Find saturation row: first where vapor > 0
            if col.VAPOR_WT not in df.columns:
                warnings.warn(f"MAGEC output has no vapor_wt column for {comp.sample}")
                return None

            saturated = df[df[col.VAPOR_WT] > 0]
            if saturated.empty:
                logger.warning(
                    "MAGEC: no saturation found for %s in "
                    "%.1f–%.3f kbar range (%d steps, timeout=%ds). "
                    "Try increasing magec.p_start_kbar.",
                    comp.sample, cfg.p_start_kbar, cfg.p_final_kbar,
                    cfg.n_steps, cfg.timeout,
                )
                return None

            result = saturated.iloc[0].copy()
        except Exception as exc:
            warnings.warn(f"MAGEC output parse failed for {comp.sample}: {exc}")
            return None

        # Clean up raw tool output if requested
        if not config.keep_raw_output:
            shutil.rmtree(work_dir, ignore_errors=True)

        return result

    # ----------------------------------------------------------------
    # Saturation pressure — batch (single MATLAB launch)
    # ----------------------------------------------------------------
    def calculate_saturation_pressure_batch(
        self,
        comps: list[MeltComposition],
        config: RunConfig,
    ) -> list[pd.Series | None]:
        """Run satP for all samples in a single MATLAB launch.

        Stacks all samples into one input CSV, runs MAGEC once, then
        splits the output back per sample.  This avoids the ~5–15 s
        MATLAB startup cost per sample.
        """
        self._check_matlab(config)
        self._check_solver(config)

        cfg = config.magec
        work_dir = os.path.join(
            config.output_dir, config.raw_output_dir, "magec", "_batch_satp",
        )
        os.makedirs(work_dir, exist_ok=True)

        in_csv = os.path.abspath(os.path.join(work_dir, "batch_input.csv"))
        out_csv = os.path.abspath(os.path.join(work_dir, "batch_output.csv"))

        # Build input rows for each sample; skip comps that fail
        # (e.g. no usable redox indicator).
        results: list[pd.Series | None] = [None] * len(comps)
        all_rows: list[dict] = []
        comp_index: dict[str, int] = {}  # sample name → index in comps

        for i, comp in enumerate(comps):
            try:
                rows = _build_sample_input_rows(comp, cfg)
                all_rows.extend(rows)
                comp_index[comp.sample] = i
            except Exception as exc:
                logger.warning(
                    "[MAGEC] Skipping %s in batch: %s", comp.sample, exc,
                )

        if not all_rows:
            return results

        # Write combined CSV and run MATLAB once
        _write_magec_csv(all_rows, cfg, in_csv)

        # Scale timeout: base timeout (covers MATLAB startup) plus
        # ~10 s per sample for the solver.
        batch_timeout = cfg.timeout + len(comp_index) * 10
        logger.info(
            "  MAGEC batch: %d samples, %d total rows, timeout=%ds",
            len(comp_index), len(all_rows), batch_timeout,
        )
        _run_magec_matlab(in_csv, out_csv, cfg, timeout=batch_timeout)

        if not os.path.isfile(out_csv):
            warnings.warn(
                "MAGEC batch produced no output. "
                f"Check MATLAB logs in {work_dir}."
            )
            return results

        # Read and convert output
        try:
            df = pd.read_csv(out_csv)
        except Exception as exc:
            warnings.warn(f"MAGEC batch output parse failed: {exc}")
            return results

        df = convert(df)
        df = compute_cs_v_mf(df)
        df = ensure_standard_columns(df)

        # Split output by sample using Run_ID column
        if "Run_ID" in df.columns:
            df["_sample"] = (
                df["Run_ID"].astype(str).apply(lambda x: x.rsplit("_", 1)[0])
            )
        else:
            # Fallback: assign by row count (n_steps per sample, in order)
            sample_labels: list[str] = []
            for comp in comps:
                if comp.sample in comp_index:
                    sample_labels.extend([comp.sample] * cfg.n_steps)
            if len(sample_labels) == len(df):
                df["_sample"] = sample_labels
            else:
                warnings.warn(
                    f"MAGEC batch: {len(df)} output rows vs "
                    f"{len(sample_labels)} expected; cannot split by sample."
                )
                return results

        # Extract saturation row per sample
        for sample_name, group in df.groupby("_sample", sort=False):
            if sample_name not in comp_index:
                continue
            idx = comp_index[sample_name]

            if col.VAPOR_WT not in group.columns:
                continue

            saturated = group[group[col.VAPOR_WT] > 0]
            if saturated.empty:
                logger.warning(
                    "MAGEC: no saturation found for %s in batch run. "
                    "Try increasing magec.p_start_kbar.",
                    sample_name,
                )
                continue

            state = saturated.iloc[0].drop(
                ["_sample", "Run_ID"], errors="ignore",
            ).copy()
            results[idx] = state

        # Cleanup
        if not config.keep_raw_output:
            shutil.rmtree(work_dir, ignore_errors=True)

        return results

    # ----------------------------------------------------------------
    # Degassing path
    # ----------------------------------------------------------------
    def calculate_degassing(
        self,
        comp: MeltComposition,
        config: RunConfig,
    ) -> pd.DataFrame:
        self._check_matlab(config)
        self._check_solver(config)

        cfg = config.magec
        work_dir = os.path.join(config.output_dir, config.raw_output_dir, "magec", comp.sample)
        os.makedirs(work_dir, exist_ok=True)

        safe_name = comp.sample.replace("/", "_").replace(" ", "_")
        in_csv = os.path.abspath(os.path.join(work_dir, f"{safe_name}_input.csv"))
        out_csv = os.path.abspath(os.path.join(work_dir, f"{safe_name}_output.csv"))

        _create_magec_input_csv(comp, cfg, in_csv)
        _run_magec_matlab(in_csv, out_csv, cfg)

        if not os.path.isfile(out_csv):
            raise FileNotFoundError(
                f"MAGEC produced no output for {comp.sample}. "
                f"Check MATLAB logs in {work_dir}."
            )

        df = pd.read_csv(out_csv)

        # Standardize
        df = convert(df)
        df = compute_cs_v_mf(df)
        df = normalize_volatiles(df)
        df = ensure_standard_columns(df)

        # Clean up raw tool output if requested
        if not config.keep_raw_output:
            shutil.rmtree(work_dir, ignore_errors=True)

        return df


# ── Helpers ─────────────────────────────────────────────────────────

def _build_sample_input_rows(
    comp: MeltComposition,
    cfg,
) -> list[dict]:
    """Build MAGEC input rows for a single sample (one row per pressure step).

    Returns a list of row dicts ready for ``pd.DataFrame(rows)``.
    Raises ``ValueError`` if no usable redox indicator is available.
    """

    fe3fet = comp.fe3fet_computed

    # Determine redox option string and value.
    # The config specifies the preferred input (e.g. "Fe3+/FeT"), but
    # not all compositions provide that indicator.  Use a fallback chain
    # so we never send NaN to MATLAB.
    redox_option = cfg.redox_option   # e.g. "Fe3+/FeT"
    redox_value = np.nan

    if redox_option == "Fe3+/FeT" and not np.isnan(fe3fet):
        redox_value = fe3fet
    elif redox_option == "dFMQ" and comp.dFMQ is not None:
        redox_value = comp.dFMQ
    elif redox_option == "logfO2":
        pass  # no generic source — leave NaN, will warn below

    # Fallback chain: try every available indicator.
    # MAGEC's internal dFMQ→logfO2 conversion can fail for certain
    # compositions, so we prefer computing Fe3+/FeT via KC91 when
    # only a buffer offset (dNNO or dFMQ) is available.
    if np.isnan(redox_value):
        if not np.isnan(fe3fet):
            redox_option = "Fe3+/FeT"
            redox_value = fe3fet
        elif comp.dNNO is not None or comp.dFMQ is not None:
            # Compute logfO2 from the available buffer offset, then
            # use Kress & Carmichael (1991) to get Fe3+/FeT.  This is
            # the most reliable pathway because MAGEC uses KC91
            # internally (fe_redox=2) and handles Fe3+/FeT natively.
            from volcatenate.iron import fe3fet_kc91

            T_K = comp.T_C + 273.15
            if comp.dNNO is not None:
                # NNO buffer (Frost 1991, at 1 bar):
                nno_1bar = -24930.0 / T_K + 9.36
                log_fo2 = nno_1bar + comp.dNNO
                src = f"dNNO={comp.dNNO}"
            else:
                # FMQ buffer (Frost 1991, at 1 bar):
                fmq_1bar = -25096.3 / T_K + 8.735
                log_fo2 = fmq_1bar + comp.dFMQ
                src = f"dFMQ={comp.dFMQ}"

            computed = fe3fet_kc91(
                log_fo2, T_K, comp.oxide_dict, P_bar=1.0,
            )
            if not np.isnan(computed):
                redox_option = "Fe3+/FeT"
                redox_value = computed
                logger.warning(
                    "[MAGEC] No Fe3+/FeT for %s; computed %.4f via KC91 "
                    "from %s (logfO2=%.3f at %s K)",
                    comp.sample, computed, src, log_fo2, T_K,
                )
            else:
                logger.warning(
                    "[MAGEC] KC91 failed for %s (logfO2=%.3f); "
                    "cannot determine Fe3+/FeT",
                    comp.sample, log_fo2,
                )

    if np.isnan(redox_value):
        raise ValueError(
            f"No usable redox indicator for {comp.sample}. "
            f"MAGEC needs Fe3+/FeT, dFMQ, or dNNO."
        )

    # ── Normalize oxides to 100% anhydrous for MAGEC ──
    # MAGEC expects oxide columns on a volatile-free basis summing to
    # 100 wt% (confirmed by MAGEC supplement example1.xlsx).  Typical
    # petrological input data includes volatiles in the ~100% total, so
    # oxides sum to ~96%.  We normalize here.
    anhydrous_sum = (comp.SiO2 + comp.TiO2 + comp.Al2O3 + comp.FeOT
                     + comp.MnO + comp.MgO + comp.CaO + comp.Na2O
                     + comp.K2O + comp.P2O5)
    norm = 100.0 / anhydrous_sum

    sio2  = comp.SiO2  * norm
    tio2  = comp.TiO2  * norm
    al2o3 = comp.Al2O3 * norm
    feot  = comp.FeOT  * norm
    mno   = comp.MnO   * norm
    mgo   = comp.MgO   * norm
    cao   = comp.CaO   * norm
    na2o  = comp.Na2O  * norm
    k2o   = comp.K2O   * norm
    p2o5  = comp.P2O5  * norm

    # ── Convert volatile wt% → elemental wt% for MAGEC ──
    # MAGEC expects Bulk_H, Bulk_C, Bulk_S as ELEMENTAL weight percent
    # per 100 g of anhydrous melt.  Volatile wt% in the input CSV is
    # on a hydrous basis (part of the ~100% total), so we first
    # re-express it per 100 g anhydrous (multiply by `norm`), then
    # convert molecular → elemental using rounded molecular weights
    # (matching the MAGEC author convention: 2/18 for H2O→H, 12/44
    # for CO2→C).
    #   H2O → H:  multiply by 2*M_H / M_H2O = 2.0 / 18 = 1/9
    #   CO2 → C:  multiply by M_C / M_CO2    = 12 / 44  = 3/11
    #   S:         already elemental, just renormalize
    _H2O_TO_H = 2.0 / 18   # ≈ 0.1111
    _CO2_TO_C = 12. / 44    # ≈ 0.2727

    bulk_h = comp.H2O * norm * _H2O_TO_H
    bulk_c = comp.CO2 * norm * _CO2_TO_C
    bulk_s = comp.S   * norm

    # Pressure grid (log-spaced, high -> low)
    # Allow per-sample override of the starting pressure.
    p_start = cfg.p_start_overrides.get(comp.sample, cfg.p_start_kbar)
    p_grid = np.logspace(
        np.log10(p_start),
        np.log10(cfg.p_final_kbar),
        cfg.n_steps,
    )

    # Build one row per pressure step — column names must match
    # MAGEC solver expectations exactly.
    input_rows = []
    for i, p_kbar in enumerate(p_grid):
        input_rows.append({
            "Run_ID":                   f"{comp.sample}_{i+1}",
            "T_degas (C)":              comp.T_C,
            "P_final (kbar)":           cfg.p_final_kbar,
            "P_degas (kbar)":           float(p_kbar),
            "Initial redox options":    redox_option,
            "Initial redox values":     redox_value,
            "Reference P (kbar)":       np.nan,
            "melt_SiO2 (wt%)":         sio2,
            "melt_TiO2 (wt%)":         tio2,
            "melt_Al2O3 (wt%)":        al2o3,
            "melt_Cr2O3 (wt%)":        0.0,
            "melt_FeOT (wt%)":         feot,
            "melt_MgO (wt%)":          mgo,
            "melt_MnO (wt%)":          mno,
            "melt_CaO (wt%)":          cao,
            "melt_Na2O (wt%)":         na2o,
            "melt_K2O (wt%)":          k2o,
            "melt_P2O5 (wt%)":         p2o5,
            "Bulk_H (wt%)":            bulk_h,
            "Bulk_C (wt%)":            bulk_c,
            "Bulk_S (wt%)":            bulk_s,
            "Reference":               "auto_satP",
        })

    return input_rows


def _build_settings_matlab_struct(cfg) -> str:
    """Build a MATLAB struct literal string from the MAGEC config.

    This is passed as the 3rd argument to MAGEC_Solver_volcatenate(),
    which uses it directly instead of reading a 'settings' sheet.
    The field names must match MAGEC's internal field_keystr mapping.
    """
    fields = [
        f"'solver_opt', {float(cfg.solver)}",
        f"'sat_sulfide', {float(cfg.sulfide_sat)}",
        f"'sat_sulfate', {float(cfg.sulfate_sat)}",
        f"'sat_graphite', {float(cfg.graphite_sat)}",
        f"'Fe32_opt', {float(cfg.fe_redox)}",
        f"'S62_opt', {float(cfg.s_redox)}",
        f"'SCSS_opt', {float(cfg.scss)}",
        f"'S2max_opt', {float(cfg.sulfide_cap)}",
        f"'CO2_opt', {float(cfg.co2_sol)}",
        f"'H2O_opt', {float(cfg.h2o_sol)}",
        f"'CO_opt', {float(cfg.co_sol)}",
        f"'adiabat_r', {float(cfg.adiabatic)}",
        f"'ideal', {float(cfg.gas_behavior)}",
        f"'buffer', {float(cfg.o2_balance)}",
    ]
    return "struct(" + ", ".join(fields) + ")"


def _write_magec_csv(
    input_rows: list[dict],
    cfg,
    csv_path: str,
) -> None:
    """Write a MAGEC input CSV from row dicts."""
    df_input = pd.DataFrame(input_rows)
    df_input.to_csv(csv_path, index=False)


def _create_magec_input_csv(
    comp: MeltComposition,
    cfg,
    csv_path: str,
) -> None:
    """Generate the MAGEC input CSV file.

    Column names and structure must match exactly what the MAGEC
    solver expects — see the original example files distributed
    with the MAGEC supplement.
    """
    _write_magec_csv(_build_sample_input_rows(comp, cfg), cfg, csv_path)


def _run_magec_matlab(
    in_csv: str,
    out_csv: str,
    cfg,
    timeout: int | None = None,
) -> None:
    """Run MAGEC via the CSV wrapper + compiled .p solver.

    Writes a .m script file and executes it with
    ``matlab -batch "eval(fileread('/path/to/script.m'))"``.

    The script:
      1. ``cd``'s to the input file's directory (working directory)
      2. Adds the bundled wrapper, original solver dir, and shims to
         the MATLAB path
      3. Builds a settings struct from the Python config
      4. Calls ``MAGEC_CSV_Wrapper(input.csv, output.csv, settings)``
         which internally converts CSV→xlsx, runs the .p solver,
         then converts output xlsx→CSV

    Python-side I/O is pure CSV (fast).  The xlsx conversion happens
    inside MATLAB where it is much faster than Python's openpyxl.

    Parameters
    ----------
    timeout : int, optional
        Subprocess timeout in seconds.  Defaults to ``cfg.timeout``.
    """
    effective_timeout = timeout if timeout is not None else cfg.timeout

    in_basename = os.path.basename(in_csv)
    out_basename = os.path.basename(out_csv)
    work_dir = os.path.abspath(os.path.dirname(in_csv))
    solver_dir = os.path.abspath(cfg.solver_dir)

    # Build settings struct from Python config
    settings_struct = _build_settings_matlab_struct(cfg)

    # Write .m script in the working directory
    script_dir = os.path.join(work_dir, "_matlab_scripts")
    os.makedirs(script_dir, exist_ok=True)
    safe_name = os.path.splitext(in_basename)[0]
    script_name = f"_volcatenate_run_{safe_name}.m"
    script_path = os.path.abspath(os.path.join(script_dir, script_name))

    lines = [
        f"cd('{work_dir}');",
        # Add bundled CSV wrapper to MATLAB path
        f"addpath('{_SOLVER_DIR}');",
        # Add original solver directory so MATLAB finds MAGEC_Solver_v1b.p
        f"addpath('{solver_dir}');",
        # Add bundled Optimization Toolbox shims to the END of the path
        # so they serve as fallbacks for fsolve/lsqnonlin/optimoptions.
        # If the Optimization Toolbox IS installed, its functions stay
        # earlier on the path and take priority.
        f"addpath('{_SHIMS_DIR}', '-end');",
        f"try",
        f"    settings = {settings_struct};",
        f"    MAGEC_CSV_Wrapper('{in_basename}', '{out_basename}', settings);",
        f"    fprintf('MAGEC: OK\\n');",
        f"catch ME",
        f"    fprintf('MAGEC: FAILED - %s\\n', ME.message);",
        f"end",
        f"exit;",
    ]

    with open(script_path, "w", encoding="ascii") as f:
        f.write("\n".join(lines))

    # Use eval(fileread(...)) instead of run() to avoid MATLAB's
    # directory scanning behaviour that causes "Invalid text character".
    try:
        result = subprocess.run(
            [cfg.matlab_bin, "-batch", f"eval(fileread('{script_path}'))"],
            capture_output=True,
            text=True,
            timeout=effective_timeout,
        )
    except subprocess.TimeoutExpired:
        warnings.warn(
            f"MAGEC timed out after {effective_timeout}s. This usually means the "
            f"saturation pressure is outside the search range "
            f"({cfg.p_start_kbar}–{cfg.p_final_kbar} kbar). "
            f"Try increasing magec.p_start_kbar in your config."
        )
        return

    if result.stdout:
        for line in result.stdout.strip().split("\n"):
            logger.debug("    [MATLAB] %s", line)
    if result.returncode != 0:
        stderr_msg = result.stderr[:500] if result.stderr else "no stderr"
        stdout_msg = result.stdout[:500] if result.stdout else "no stdout"
        warnings.warn(
            f"MATLAB returned exit code {result.returncode}.\n"
            f"  stdout: {stdout_msg}\n"
            f"  stderr: {stderr_msg}"
        )

    # Clean up script file
    try:
        os.remove(script_path)
    except OSError:
        pass
