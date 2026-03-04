"""MAGEC backend — Magma And Gas Equilibrium Calculator (Sun & Yao, 2024).

Runs MAGEC's compiled MATLAB solver via subprocess.  Requires:
  1. MATLAB installed (with the fsolve shim if Optimization Toolbox
     is not available)
  2. MAGEC_Solver_v1b.p in the configured solver directory

The backend generates Excel input files, writes a MATLAB batch script,
runs MATLAB once via subprocess, and parses the output xlsx.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import warnings

import numpy as np
import pandas as pd

from volcatenate.backends._base import ModelBackend
from volcatenate.composition import MeltComposition
from volcatenate.config import RunConfig
from volcatenate.converters.magec_converter import convert, parse_saturation_pressure
from volcatenate.convert import compute_cs_v_mf, normalize_volatiles, ensure_standard_columns


class Backend(ModelBackend):

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
        """Raise a clear error if the MAGEC solver directory is missing."""
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
    ) -> float:
        self._check_matlab(config)
        self._check_solver(config)

        cfg = config.magec
        work_dir = os.path.join(config.output_dir, "magec", comp.sample)
        inp_dir = os.path.join(work_dir, "inputs")
        out_dir = os.path.join(work_dir, "outputs")
        os.makedirs(inp_dir, exist_ok=True)
        os.makedirs(out_dir, exist_ok=True)

        safe_name = comp.sample.replace("/", "_").replace(" ", "_")
        in_xlsx = os.path.abspath(os.path.join(inp_dir, f"{safe_name}_input.xlsx"))
        out_xlsx = os.path.abspath(os.path.join(out_dir, f"{safe_name}_output.xlsx"))

        _create_magec_input_xlsx(comp, cfg, in_xlsx)
        _run_magec_matlab(in_xlsx, out_xlsx, cfg)

        if not os.path.isfile(out_xlsx):
            warnings.warn(f"MAGEC produced no output for {comp.sample}")
            return np.nan

        try:
            result = parse_saturation_pressure(out_xlsx)
        except Exception as exc:
            warnings.warn(f"MAGEC output parse failed for {comp.sample}: {exc}")
            result = np.nan

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
        self._check_matlab(config)
        self._check_solver(config)

        cfg = config.magec
        work_dir = os.path.join(config.output_dir, "magec", comp.sample)
        inp_dir = os.path.join(work_dir, "inputs")
        out_dir = os.path.join(work_dir, "outputs")
        os.makedirs(inp_dir, exist_ok=True)
        os.makedirs(out_dir, exist_ok=True)

        safe_name = comp.sample.replace("/", "_").replace(" ", "_")
        in_xlsx = os.path.abspath(os.path.join(inp_dir, f"{safe_name}_input.xlsx"))
        out_xlsx = os.path.abspath(os.path.join(out_dir, f"{safe_name}_output.xlsx"))

        _create_magec_input_xlsx(comp, cfg, in_xlsx)
        _run_magec_matlab(in_xlsx, out_xlsx, cfg)

        if not os.path.isfile(out_xlsx):
            raise FileNotFoundError(
                f"MAGEC produced no output for {comp.sample}. "
                f"Check MATLAB logs in {work_dir}."
            )

        try:
            df = pd.read_excel(out_xlsx)
        except Exception:
            csv_path = out_xlsx.replace(".xlsx", ".csv")
            df = pd.read_csv(csv_path)

        # Standardize
        df = convert(df)
        df = compute_cs_v_mf(df)
        df = normalize_volatiles(df)
        df = ensure_standard_columns(df)

        # Clean up intermediate files if requested
        if not config.keep_intermediates:
            shutil.rmtree(work_dir, ignore_errors=True)

        return df


# ── Helpers ─────────────────────────────────────────────────────────

def _create_magec_input_xlsx(
    comp: MeltComposition,
    cfg,
    xlsx_path: str,
) -> None:
    """Generate the MAGEC input Excel file (input + settings sheets).

    Column names and structure must match exactly what
    MAGEC_Solver_v1b.p expects — see the original example files
    distributed with the MAGEC supplement.
    """

    fe3fet = comp.fe3fet_computed

    # Determine redox option string and value
    redox_option = cfg.redox_option   # e.g. "Fe3+/FeT"
    redox_value = np.nan
    if redox_option == "Fe3+/FeT" and not np.isnan(fe3fet):
        redox_value = fe3fet
    elif redox_option == "dFMQ" and comp.dFMQ is not None:
        redox_value = comp.dFMQ
    elif redox_option == "Fe3+/FeT":
        # Fallback: use Fe3FeT if available regardless of config
        if not np.isnan(fe3fet):
            redox_value = fe3fet

    # ── Convert volatile wt% → elemental wt% for MAGEC ──
    # MAGEC expects Bulk_H, Bulk_C, Bulk_S as ELEMENTAL weight percent,
    # not as H2O, CO2, S.  See MAGEC example files (example1.xlsx) and
    # the output column "melt-gas_H (wt%)" which tracks elemental H.
    #   H2O → H:  multiply by 2*M_H / M_H2O = 2*1.008 / 18.015
    #   CO2 → C:  multiply by M_C / M_CO2    = 12.011 / 44.01
    #   S:         already elemental, no conversion
    _H2O_TO_H = 2 * 1.008 / 18.015   # ≈ 0.1119
    _CO2_TO_C = 12.011 / 44.01       # ≈ 0.2729

    bulk_h = comp.H2O * _H2O_TO_H
    bulk_c = comp.CO2 * _CO2_TO_C
    bulk_s = comp.S  # already elemental

    # Pressure grid (log-spaced, high -> low)
    p_grid = np.logspace(
        np.log10(cfg.p_start_kbar),
        np.log10(cfg.p_final_kbar),
        cfg.n_steps,
    )

    # Build one row per pressure step — column names must match
    # MAGEC_Solver_v1b.p expectations exactly.
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
            "melt_SiO2 (wt%)":         comp.SiO2,
            "melt_TiO2 (wt%)":         comp.TiO2,
            "melt_Al2O3 (wt%)":        comp.Al2O3,
            "melt_Cr2O3 (wt%)":        0.0,
            "melt_FeOT (wt%)":         comp.FeOT,
            "melt_MgO (wt%)":          comp.MgO,
            "melt_MnO (wt%)":          comp.MnO,
            "melt_CaO (wt%)":          comp.CaO,
            "melt_Na2O (wt%)":         comp.Na2O,
            "melt_K2O (wt%)":          comp.K2O,
            "melt_P2O5 (wt%)":         comp.P2O5,
            "Bulk_H (wt%)":            bulk_h,    # elemental H (converted from H2O)
            "Bulk_C (wt%)":            bulk_c,    # elemental C (converted from CO2)
            "Bulk_S (wt%)":            bulk_s,    # elemental S (no conversion needed)
            "Reference":               "auto_satP",
        })

    df_input = pd.DataFrame(input_rows)

    # Settings sheet — option names must match MAGEC_Solver_v1b.p exactly
    settings_rows = [
        {"Option name": "Adjust for sulfide saturation:",
         "Value": float(cfg.sulfide_sat),
         "Instruction": "(1) Yes; (0) No"},
        {"Option name": "Adjust for sulfate saturation:",
         "Value": float(cfg.sulfate_sat),
         "Instruction": "(1) Yes; (0) No"},
        {"Option name": "Adjust for graphite saturation:",
         "Value": float(cfg.graphite_sat),
         "Instruction": "(1) Yes; (0) No"},
        {"Option name": "Choose the Fe redox model:",
         "Value": float(cfg.fe_redox),
         "Instruction": "(1) New model from Sun & Yao (2024); "
                        "(2) Kress & Carmicheal (1991) CMP; "
                        "(3) Hirschmann (2022) GCA-Deng's EOS"},
        {"Option name": "Choose the S redox model:",
         "Value": float(cfg.s_redox),
         "Instruction": "(1) New model from Sun & Yao (2024); "
                        "(2) Nash et al. (2019) EPSL; "
                        "(3) Jugo et al. (2010) GCA; "
                        "(4) O'Neill & Mavrogenes (2022) GCA; "
                        "(5) Boulliung & Wood (2023) CMP"},
        {"Option name": "Choose the SCSS model:",
         "Value": float(cfg.scss),
         "Instruction": "(1) Blanchard et al. (2021) AM; "
                        "(2) Fortin et al. (2015) GCA; "
                        "(3) Smythe et al. (2017) AM; "
                        "(4) O'Neill (2021) AGU Geophysical Monograph"},
        {"Option name": "Choose the sulfide capacity model:",
         "Value": float(cfg.sulfide_cap),
         "Instruction": "(1) Nzotta et al. (1999) used in Sun & Lee (2022) GCA; "
                        "(2) O'Neill (2021) AGU Geophysical Monograph; "
                        "(3) Boulliung & Wood (2023) CMP"},
        {"Option name": "Choose the CO2 solubility model:",
         "Value": float(cfg.co2_sol),
         "Instruction": "(1) Iacono-Marziano et al. (2012) GCA; "
                        "(2) rhyolite - Liu et al. (2005); "
                        "(3.1/3.2/3.3) rhyolite/basalt/phonolite - Burgisser et al. (2015)"},
        {"Option name": "Choose the H2O solubility model:",
         "Value": float(cfg.h2o_sol),
         "Instruction": "(1) Iacono-Marziano et al. (2012) GCA; "
                        "(2) rhyolite - Liu et al. (2005); "
                        "(3.1/3.2/3.3) rhyolite/basalt/phonolite - Burgisser et al. (2015)"},
        {"Option name": "Choose the CO solubility model:",
         "Value": float(cfg.co_sol),
         "Instruction": "(1) Armstrong et al. (2015) GCA; "
                        "(2.1/2.2) rhyolite/basalt - Yoshioka et al. (2019) GCA"},
        {"Option name": "Set eruption adiabatic factor (r):",
         "Value": float(cfg.adiabatic),
         "Instruction": "r = 0 (default): Isothermal; r = alpha*V/Cp: adiabatic; "
                        "r in T = Tp*exp[r(P_GPa-0.0001)]"},
        {"Option name": "Choose the numerical solver:",
         "Value": float(cfg.solver),
         "Instruction": "(1) lsqnonlin; (2) fsolve (default)"},
        {"Option name": "Choose the vapor behavior:",
         "Value": float(cfg.gas_behavior),
         "Instruction": "(1) real gas behavior of individual species in an ideal mixture; "
                        "(2) ideal gas behavior of individual species in an ideal mixture"},
        {"Option name": "Set the oxygen mass balance:",
         "Value": float(cfg.o2_balance),
         "Instruction": "(0) Total oxygen mass balanced; (1) fixed fO2 buffer"},
    ]
    df_settings = pd.DataFrame(settings_rows)

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df_input.to_excel(writer, sheet_name="input", index=False)
        df_settings.to_excel(writer, sheet_name="settings", index=False)


def _run_magec_matlab(
    in_xlsx: str,
    out_xlsx: str,
    cfg,
) -> None:
    """Run MAGEC_Solver_v1b via a MATLAB subprocess.

    Writes a .m script file and executes it with
    ``matlab -batch "eval(fileread('/path/to/script.m'))"``.

    We use ``eval(fileread(...))`` instead of ``run()`` because
    MATLAB's ``run()`` first ``cd``'s to the script's parent directory
    and scans every file there — which can trigger "Invalid text
    character" errors if the directory contains .p files, quarantined
    downloads, or any other non-ASCII content.  ``eval(fileread(...))``
    reads the file as a plain string and evaluates it in place, with
    no directory scanning.
    """
    solver_dir = os.path.abspath(cfg.solver_dir)
    safe_name = os.path.splitext(os.path.basename(in_xlsx))[0]
    local_in = f"_volcatenate_{safe_name}.xlsx"
    local_out = f"_volcatenate_{safe_name}_out.xlsx"

    # Write .m script next to the output file
    script_dir = os.path.join(os.path.dirname(out_xlsx), "_matlab_scripts")
    os.makedirs(script_dir, exist_ok=True)
    script_name = f"_volcatenate_run_{safe_name}.m"
    script_path = os.path.abspath(os.path.join(script_dir, script_name))

    lines = [
        f"cd('{solver_dir}');",
        f"try",
        f"    copyfile('{in_xlsx}', '{local_in}');",
        f"    MAGEC_Solver_v1b('{local_in}', '{local_out}');",
        f"    movefile('{local_out}', '{out_xlsx}');",
        f"    delete('{local_in}');",
        f"    fprintf('MAGEC: OK\\n');",
        f"catch ME",
        f"    fprintf('MAGEC: FAILED - %s\\n', ME.message);",
        f"    if exist('{local_in}','file'); delete('{local_in}'); end",
        f"    if exist('{local_out}','file'); delete('{local_out}'); end",
        f"end",
        f"exit;",
    ]

    with open(script_path, "w", encoding="ascii") as f:
        f.write("\n".join(lines))

    # Use eval(fileread(...)) instead of run() to avoid MATLAB's
    # directory scanning behaviour that causes "Invalid text character".
    result = subprocess.run(
        [cfg.matlab_bin, "-batch", f"eval(fileread('{script_path}'))"],
        capture_output=True,
        text=True,
        timeout=cfg.timeout,
    )

    if result.stdout:
        for line in result.stdout.strip().split("\n"):
            print(f"    [MATLAB] {line}")
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
