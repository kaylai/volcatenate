"""SulfurX backend — sulfur-bearing COH degassing model.

Wraps the SulfurX code (Iacono-Marziano / VolatileCalc COH models
with sulfur speciation).  SulfurX is not pip-installable, so its
path must be provided via ``config.sulfurx.path``.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys

import numpy as np
import pandas as pd

from volcatenate.log import logger
from volcatenate.backends._base import ModelBackend
from volcatenate.composition import MeltComposition
from volcatenate.config import RunConfig
from volcatenate.converters.sulfurx_converter import convert
from volcatenate.convert import compute_cs_v_mf, normalize_volatiles, ensure_standard_columns


@contextlib.contextmanager
def _quiet_sulfurx():
    """Suppress SulfurX's stdout/stderr and tqdm progress bars.

    Routes captured output to the volcatenate logger at DEBUG level.

    Note: scipy's MINPACK Fortran code prints directly to C-level stdout
    (bypassing Python's ``sys.stdout``).  We do NOT attempt OS-level FD
    redirection here because it breaks Jupyter's I/O.  The Fortran
    "improvement from the last ten iterations" messages will still appear
    in terminals; this is a known cosmetic issue.
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
                logger.debug("[SulfurX] %s", line)


def _build_composition(comp: MeltComposition) -> dict:
    """Build the oxide composition dict expected by SulfurX modules."""
    return {
        "SiO2": comp.SiO2,
        "TiO2": comp.TiO2,
        "Al2O3": comp.Al2O3,
        "FeOT": comp.FeOT,
        "MnO": comp.MnO,
        "MgO": comp.MgO,
        "CaO": comp.CaO,
        "Na2O": comp.Na2O,
        "K2O": comp.K2O,
        "P2O5": comp.P2O5,
    }


def _find_saturation_pressure_im(composition, tk, co2_ppm, h2o_wt, slope_h2o, constant_h2o):
    """Find Iacono-Marziano saturation pressure using multiple initial guesses.

    SulfurX's ``IaconoMarziano.saturation_pressure()`` uses
    ``scipy.optimize.root`` with a single initial guess derived from the
    constructor's ``pressure`` parameter (``self.Pb = pressure * 10``).
    If the guess is far from the true solution, the solver silently
    returns the guess unchanged — a false convergence.

    This helper tries a spread of starting pressures, clusters the
    converged results, and picks the most-agreed-upon solution.  True
    solutions are stable attractors: many different initial guesses
    converge to the same value, while local minima attract only guesses
    that happen to start nearby.

    Returns
    -------
    tuple[float, float]
        ``(P_sat_bar, XH2O_f)``
    """
    from Iacono_Marziano_COH import IaconoMarziano

    # Wide range of initial guesses (MPa).
    guesses_mpa = [10, 20, 30, 50, 75, 100, 150, 200, 250, 300, 400]

    candidates: list[tuple[float, float, int]] = []
    for g_mpa in guesses_mpa:
        guess_bar = g_mpa * 10
        coh = IaconoMarziano(
            pressure=g_mpa, temperature_k=tk,
            composition=composition,
            a=slope_h2o, b=constant_h2o,
        )
        try:
            P_sat, XH2O_f = coh.saturation_pressure(co2_ppm, h2o_wt)
        except Exception:
            logger.debug("[SulfurX] guess %g MPa → FAIL", g_mpa)
            continue

        # Non-convergence: result ≈ initial guess (solver didn't move)
        if abs(P_sat - guess_bar) < 5.0:
            logger.debug("[SulfurX] guess %g MPa → %.0f bar (≈ init, SKIP)", g_mpa, P_sat)
            continue

        # Physical bounds
        if P_sat <= 0 or XH2O_f <= 0 or XH2O_f >= 1:
            logger.debug("[SulfurX] guess %g MPa → %.0f bar XH2O=%.4f (unphysical, SKIP)",
                         g_mpa, P_sat, XH2O_f)
            continue

        logger.debug("[SulfurX] guess %g MPa → %.0f bar XH2O=%.4f ✓", g_mpa, P_sat, XH2O_f)
        candidates.append((P_sat, XH2O_f, g_mpa))

    if not candidates:
        logger.warning("[SulfurX] 0/%d guesses converged — no satP solution", len(guesses_mpa))
        return np.nan, np.nan

    # --- Cluster candidates by proximity (200-bar window) ---
    # True solutions attract many initial guesses; local minima attract
    # only nearby guesses.  Pick the biggest cluster.
    candidates.sort(key=lambda c: c[0])
    clusters: list[list[tuple[float, float, int]]] = [[candidates[0]]]
    for cand in candidates[1:]:
        if cand[0] - clusters[-1][-1][0] < 200:  # within 200 bar
            clusters[-1].append(cand)
        else:
            clusters.append([cand])

    # For saturation pressure the physically meaningful answer is the
    # *lowest* pressure at which the melt first saturates.  Higher-P
    # clusters are typically numerical artifacts of the IM solver.
    # Strategy: pick the lowest-pressure cluster that has ≥ 2 members
    # (i.e. not a one-off fluke).  Fall back to the largest cluster if
    # no low-P cluster meets the threshold.
    viable = [cl for cl in clusters if len(cl) >= 2]
    if viable:
        best_cluster = viable[0]  # lowest-P cluster (already sorted)
    else:
        best_cluster = max(clusters, key=lambda cl: len(cl))

    cluster_summary = ", ".join(
        f"~{cl[len(cl)//2][0]:.0f} bar ({len(cl)}x)" for cl in clusters
    )
    logger.debug(
        "[SulfurX] %d cluster(s) from %d/%d converged guesses: %s",
        len(clusters), len(candidates), len(guesses_mpa), cluster_summary,
    )

    # Within the winning cluster, take the median
    mid = len(best_cluster) // 2
    P_sat, XH2O_f, g_mpa = best_cluster[mid]
    logger.debug(
        "[SulfurX] Final satP: %.1f bar (from %d/%d converged guesses, "
        "best initial guess %d MPa)",
        P_sat, len(candidates), len(guesses_mpa), g_mpa,
    )
    return P_sat, XH2O_f


@contextlib.contextmanager
def _patch_composition(composition: dict):
    """Monkey-patch SulfurX's MeltComposition so degassing uses *our* composition.

    SulfurX's ``degassingrun.py`` hard-codes a specific volcanic composition
    inside its ``MeltComposition`` class (Hawaiian basalt for ``choice=0``).
    Every pressure step in the degassing loop creates a new
    ``MeltComposition`` and feeds it to IaconoMarziano, OxygenFugacity, etc.

    If the real sample composition differs from the hardcoded one, the
    initial conditions (computed with the real composition) and the
    per-step calculations (using the hardcoded one) are inconsistent,
    causing the inner convergence loop (100 000 iterations) to never
    converge → the run "hangs".

    This context manager replaces ``degassingrun.MeltComposition`` with a
    thin wrapper that always returns the *volcatenate* composition,
    normalised to 100 wt%.  The original class is restored on exit.
    """
    import degassingrun as _dr

    _original = _dr.MeltComposition

    # Pre-normalise once
    total = sum(composition.values())
    normed = {k: v / total * 100.0 for k, v in composition.items()}

    class _Patched:
        """Drop-in replacement that returns the volcatenate composition."""
        def __init__(self, melt_fraction, choice):
            self.composition = dict(normed)  # fresh copy each time

    _dr.MeltComposition = _Patched
    try:
        yield
    finally:
        _dr.MeltComposition = _original


def _run_degassing(comp: MeltComposition, cfg) -> pd.DataFrame:
    """Run the full SulfurX degassing path.

    Translates the workflow from SulfurX's ``main_Fuego.py`` into a
    callable function, bypassing interactive prompts and hardcoded
    compositions.
    """
    from oxygen_fugacity import OxygenFugacity
    from fugacity import Fugacity
    from sulfur_partition_coefficients import PartitionCoefficient
    from newvariables import NewVariables
    from degassingrun import COHS_degassing
    from S_Fe import Sulfur_Iron
    from SCSS_model import Sulfur_Saturation

    composition = _build_composition(comp)
    tk = comp.T_C + 273.15
    temperature = comp.T_C
    h2o_wt = comp.H2O
    co2_ppm = comp.CO2 * 10_000
    s_ppm = comp.S * 10_000

    # Determine delta_FMQ from composition
    if comp.dFMQ is not None:
        delta_FMQ = comp.dFMQ
    elif comp.dNNO is not None:
        # Approximate conversion: dFMQ ≈ dNNO - 0.7
        delta_FMQ = comp.dNNO - 0.7
    else:
        raise ValueError("SulfurX requires dFMQ or dNNO to set initial fO2.")

    coh_model = cfg.coh_model
    choice = 0  # No crystallization
    fo2_tracker = cfg.fo2_tracker
    s_fe_choice = cfg.s_fe_choice
    sigma = cfg.sigma
    sulfide_pre = cfg.sulfide_pre
    slope_h2o = cfg.slope_h2o
    constant_h2o = cfg.constant_h2o
    n_steps = cfg.n_steps
    open_degassing = 0  # closed degassing
    d34s_initial = 0  # not tracking isotopes

    # Sulfide composition (default from main_Fuego.py)
    sulfide = {"Fe": 65.43, "Ni": 0, "Cu": 0, "O": 0, "S": 36.47}

    # ── Step 1: Calculate saturation pressure ──────────────────────
    # The IM satP solver is very sensitive to the initial guess.  We
    # use a multi-guess strategy that tries several starting pressures
    # and picks the converged result.
    if coh_model == 0:
        P_initial, XH2Of_initial = _find_saturation_pressure_im(
            composition, tk, co2_ppm, h2o_wt, slope_h2o, constant_h2o,
        )
        # Reinitialize at saturation pressure (as main_Fuego.py does)
        from Iacono_Marziano_COH import IaconoMarziano

        coh = IaconoMarziano(
            pressure=P_initial / 10, temperature_k=tk,
            composition=composition,
            a=slope_h2o, b=constant_h2o,
        )
    else:
        from VC_COH import VolatileCalc

        vc = VolatileCalc(
            TK=tk, sio2=composition["SiO2"],
            a=slope_h2o, b=constant_h2o,
        )
        result = vc.SatPress(WtH2O=h2o_wt, PPMCO2=co2_ppm)
        P_initial = result[0]
        XH2Of_initial = result[5]  # index 5 per main_Fuego.py

    logger.debug("[SulfurX] Saturation pressure: %.1f bar", P_initial)

    # Guard: abort if the internal satP solver did not converge.
    # A NaN or non-positive P_initial means the degassing loop will
    # produce garbage or hang (each step's inner solver may run 100k
    # iterations trying to converge from bad initial conditions).
    if np.isnan(P_initial) or P_initial <= 0:
        raise RuntimeError(
            f"SulfurX internal satP solver did not converge "
            f"(P_initial={P_initial!r}).  Cannot compute degassing path."
        )

    # ── Step 2: Set up pressure grid and results DataFrame ─────────
    def_variables = NewVariables(P_initial, n_steps)
    my_data = def_variables.results_dic()
    df_results = pd.DataFrame(data=my_data)

    # ── Step 3: Calculate initial conditions ───────────────────────
    fo2_0 = OxygenFugacity(P_initial / 10, tk, composition)
    ferric_ratio_0 = fo2_0.fe_ratio(fo2_0.fmq() + delta_FMQ)

    phi = Fugacity(P_initial / 10, temperature)
    re = PartitionCoefficient(
        P_initial / 10, tk, composition, h2o_wt,
        phi.phiH2O, phi.phiH2S, phi.phiSO2, monte=0,
    )
    solubility = Sulfur_Saturation(
        P=P_initial / 10, T=temperature,
        sulfide_composition=sulfide,
        composition=composition, h2o=h2o_wt,
        ferric_fe=ferric_ratio_0,
    )

    fH2O_initial = XH2Of_initial * P_initial * phi.phiH2O
    fH2_initial = re.hydrogen_equilibrium(
        fh2o=fH2O_initial,
        fo2=10 ** fo2_0.fo2(ferric_ratio_0),
    )
    rs_melt = Sulfur_Iron(
        ferric_iron=ferric_ratio_0, temperature=temperature,
        model_choice=s_fe_choice, composition=composition,
        o2=fo2_0.fmq() + delta_FMQ,
    )
    rs_melt_initial = rs_melt.sulfate

    e_balance_initial = (
        (s_ppm / 10000) * (1 - rs_melt_initial) * 8 / 32.065
        + (1 - ferric_ratio_0) * composition["FeOT"] / (55.845 + 15.999)
    )

    logger.debug(
        "[SulfurX] Initial Fe3+/FeT: %.4f, S6+/ST: %.4f",
        ferric_ratio_0, rs_melt_initial,
    )

    # ── Step 4: Populate initial row ───────────────────────────────
    i0 = df_results.columns.get_loc

    df_results.iloc[0, i0("SCSS")] = solubility.SCSS_smythe()
    df_results.iloc[0, i0("SCAS")] = solubility.SCAS_Zajacz_Tsay()
    df_results.iloc[0, i0("SCSS_S6+")] = solubility.SCSStotal(
        sulfate=rs_melt_initial,
        scss=solubility.SCSS_smythe(),
        scas=solubility.SCAS_Zajacz_Tsay(),
    )

    if sulfide_pre == 0:
        XS_initial = (s_ppm / (10000 * 32.065)) / (
            re.ntot + s_ppm / (10000 * 32.065)
            + re.nh + co2_ppm / (10000 * 44.01)
        )
        df_results.iloc[0, i0("wS_melt")] = s_ppm
        df_results.iloc[0, i0("sulfide_frac")] = 0
    else:
        scss_val = df_results["SCSS_S6+"][0]
        if s_ppm < scss_val:
            df_results.iloc[0, i0("wS_melt")] = s_ppm
            df_results.iloc[0, i0("sulfide_frac")] = 0
            XS_initial = (s_ppm / (10000 * 32.065)) / (
                re.ntot + s_ppm / (10000 * 32.065)
                + re.nh + co2_ppm / (10000 * 44.01)
            )
        else:
            df_results.iloc[0, i0("wS_melt")] = scss_val
            df_results.iloc[0, i0("sulfide_frac")] = (
                (s_ppm - scss_val) / (sulfide["S"] * 10000)
            )
            XS_initial = (scss_val / (10000 * 32.065)) / (
                re.ntot + scss_val / (10000 * 32.065)
                + re.nh + co2_ppm / (10000 * 44.01)
            )

    df_results.iloc[0, i0("wH2O_melt")] = h2o_wt
    df_results.iloc[0, i0("wCO2_melt")] = co2_ppm
    df_results.iloc[0, i0("XS_melt")] = XS_initial
    df_results.iloc[0, i0("fO2")] = fo2_0.fo2(ferric_ratio_0)
    df_results.iloc[0, i0("XCO2_fluid")] = 1 - XH2Of_initial
    df_results.iloc[0, i0("XH2O_fluid")] = XH2Of_initial
    df_results.iloc[0, i0("XS_fluid")] = 0
    df_results.iloc[0, i0("phi_H2O")] = phi.phiH2O
    df_results.iloc[0, i0("phi_H2S")] = phi.phiH2S
    df_results.iloc[0, i0("phi_SO2")] = phi.phiSO2
    df_results.iloc[0, i0("S6+/ST")] = rs_melt_initial
    df_results.iloc[0, i0("water_fugacity")] = fH2O_initial
    df_results.iloc[0, i0("melt_fraction")] = 1
    df_results.iloc[0, i0("vapor_fraction")] = 0
    df_results.iloc[0, i0("crystal_fraction")] = 0
    df_results.iloc[0, i0("electron_balance")] = e_balance_initial
    df_results.iloc[0, i0("ferric")] = (
        ferric_ratio_0 * composition["FeOT"] / (55.845 + 15.999)
    )
    df_results.iloc[0, i0("ferrous")] = (
        (1 - ferric_ratio_0) * composition["FeOT"] / (55.845 + 15.999)
    )
    df_results.iloc[0, i0("ferric_ratio")] = ferric_ratio_0
    df_results.iloc[0, i0("FeOT")] = composition["FeOT"]
    df_results.iloc[0, i0("ferric_cr")] = 0
    df_results.iloc[0, i0("ferrous_cr")] = 0
    df_results.iloc[0, i0("FMQ")] = fo2_0.fmq()
    df_results.iloc[0, i0("fH2")] = fH2_initial
    df_results.iloc[0, i0("d34s_melt")] = d34s_initial

    # ── Step 5: Degassing loop ─────────────────────────────────────
    # Monkey-patch SulfurX's hardcoded MeltComposition so that
    # degassing_redox / degassing_noredox use *our* composition
    # instead of the built-in Hawaiian basalt.  Without this patch
    # the per-step calculations are inconsistent with the initial
    # conditions and the inner convergence loop (100k iter) hangs.
    with _patch_composition(composition):
        for i in range(1, n_steps):
            degas = COHS_degassing(
                pressure=df_results["pressure"][i],
                temperature=temperature,
                COH_model=coh_model,
                xlt_choice=choice,
                S_Fe_choice=s_fe_choice,
                H2O_initial=h2o_wt,
                CO2_initial=co2_ppm,
                S_initial=s_ppm,
                d34s_initial=d34s_initial,
                a=slope_h2o,
                b=constant_h2o,
                monte_c=0,
                op=open_degassing,
            )
            if fo2_tracker == 1:
                df_results.iloc[i] = degas.degassing_redox(
                    df_results=df_results, index=i,
                    e_balance_initial=df_results["electron_balance"][i - 1],
                    sigma=sigma, sulfide_pre=sulfide_pre,
                )
            else:
                df_results.iloc[i] = degas.degassing_noredox(
                    df_results=df_results, index=i,
                    delta_FMQ=delta_FMQ, sulfide_pre=sulfide_pre,
                )

    return df_results


class Backend(ModelBackend):

    @property
    def name(self) -> str:
        return "SulfurX"

    def is_available(self) -> bool:
        # SulfurX requires a local path — we can't test without config
        return True  # Always register; will fail with clear error if path is wrong

    def _ensure_on_path(self, config: RunConfig) -> None:
        """Add SulfurX to sys.path if not already present."""
        sx_path = config.sulfurx.path
        if not sx_path:
            raise FileNotFoundError(
                "SulfurX path not configured. "
                "Set config.sulfurx.path to the SulfurX source directory."
            )
        if not os.path.isdir(sx_path):
            raise FileNotFoundError(
                f"SulfurX directory not found at '{sx_path}'."
            )
        if sx_path not in sys.path:
            sys.path.insert(0, sx_path)

    # ----------------------------------------------------------------
    # Saturation pressure
    # ----------------------------------------------------------------
    def calculate_saturation_pressure(
        self,
        comp: MeltComposition,
        config: RunConfig,
    ) -> float:
        self._ensure_on_path(config)
        cfg = config.sulfurx

        tk = comp.T_C + 273.15
        h2o_wt = comp.H2O
        co2_ppm = comp.CO2 * 10_000
        composition = _build_composition(comp)

        try:
            if cfg.coh_model == 0:
                with _quiet_sulfurx():
                    P_sat, _ = _find_saturation_pressure_im(
                        composition, tk, co2_ppm, h2o_wt,
                        cfg.slope_h2o, cfg.constant_h2o,
                    )
                return float(P_sat)
            else:
                with _quiet_sulfurx():
                    from VC_COH import VolatileCalc

                    vc = VolatileCalc(
                        TK=tk, sio2=composition["SiO2"],
                        a=cfg.slope_h2o, b=cfg.constant_h2o,
                    )
                    result = vc.SatPress(WtH2O=h2o_wt, PPMCO2=co2_ppm)
                    return float(result[0])
        except Exception as exc:
            logger.warning("[SulfurX] satP failed for %s: %s", comp.sample, exc)
            return np.nan

    # ----------------------------------------------------------------
    # Degassing path
    # ----------------------------------------------------------------
    def calculate_degassing(
        self,
        comp: MeltComposition,
        config: RunConfig,
    ) -> pd.DataFrame:
        self._ensure_on_path(config)

        with _quiet_sulfurx():
            df = _run_degassing(comp, config.sulfurx)

        # Standardize columns
        df = convert(df)

        # ── Filter: keep only rows at or below saturation ────────
        # SulfurX's pressure grid starts at satP and decreases, but
        # row 0 represents the *initial* (pre-degassing) conditions.
        # Remove rows where no degassing has actually occurred, i.e.
        # the volatiles haven't changed from their starting values.
        # Keep at least row 0 (the saturation point itself).
        from volcatenate import columns as col

        if col.VAPOR_WT in df.columns:
            # Row 0 = saturation point (vapor_wt ≈ 0).
            # Rows where vapor has appeared (vapor_wt > 0) are
            # the actual degassing path.  Keep row 0 + all rows with
            # non-trivial vapor.
            has_vapor = df[col.VAPOR_WT] > 1e-10
            if has_vapor.any():
                # Keep the saturation point (first row with vapor > 0
                # or the very first row) plus the degassing path.
                first_vapor_idx = has_vapor.idxmax()
                # Include 1 row before first vapor as the satP anchor
                start = max(0, first_vapor_idx - 1)
                df = df.iloc[start:].reset_index(drop=True)
            else:
                # No vapor at all — keep everything (may indicate a
                # problem, but let downstream handle it).
                logger.warning(
                    "[SulfurX] No vapor produced in degassing run "
                    "(check saturation pressure convergence)."
                )

        # Also trim any trailing zero-rows that weren't populated
        # by the degassing loop (e.g. if the loop ended early).
        if col.H2OT_M_WTPC in df.columns:
            populated = df[col.H2OT_M_WTPC] > 0
            if populated.any():
                last_populated = populated[::-1].idxmax()
                df = df.iloc[: last_populated + 1]

        df = compute_cs_v_mf(df)
        df = normalize_volatiles(df)
        df = ensure_standard_columns(df)

        return df
