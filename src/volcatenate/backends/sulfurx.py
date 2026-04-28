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

from scipy.optimize import brentq

from volcatenate.log import logger
from volcatenate.backends._base import ModelBackend
from volcatenate.composition import MeltComposition
from volcatenate.config import RunConfig, resolve_sample_config
from volcatenate.converters.sulfurx_converter import convert
from volcatenate.convert import compute_cs_v_mf, normalize_volatiles, ensure_standard_columns
from volcatenate.iron import fe3fet_kc91


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
    from scipy.optimize import root as scipy_root

    # Wide range of initial guesses (MPa) × XH2O_f starting values.
    # The IM solver is extremely sensitive to the fluid mole-fraction
    # initial guess — upstream SulfurX has oscillated between 0.01, 0.5,
    # and 0.9 across versions.  We try all three to maximise robustness.
    guesses_mpa = [10, 20, 30, 50, 75, 100, 150, 200, 250, 300, 400]
    xh2o_guesses = [0.01, 0.5, 0.9]

    candidates: list[tuple[float, float, int]] = []
    for g_mpa in guesses_mpa:
        guess_bar = g_mpa * 10

        # Build the IM object once per pressure — it computes derived
        # quantities (mole fractions, NBO) in __init__.
        coh = IaconoMarziano(
            pressure=g_mpa, temperature_k=tk,
            composition=composition,
            a=slope_h2o, b=constant_h2o,
        )

        # Pre-compute the args that saturation_pressure() normally
        # builds, so we can call scipy root() with varying XH2O_f.
        # func_initial expects: h2o_0 in wt%, co2_0 in ppm
        h2o_0 = h2o_wt
        co2_0 = co2_ppm  # ppm — NOT divided by 10000
        nh2o = h2o_0 / (15.999 + 2 * 1.0079)
        ntot_h = coh.ntot + nh2o
        xfeo = coh.nfeo / ntot_h
        xmgo = coh.nmgo / ntot_h
        xna2o = coh.nna2o / ntot_h
        xk2o = coh.nk2o / ntot_h
        xh2o = nh2o / ntot_h
        xsio2 = coh.nsio2 / ntot_h
        xtio2 = coh.ntio2 / ntot_h
        xal2o3 = coh.nal2o3 / ntot_h
        xcao = coh.ncao / ntot_h
        denom = xcao + xna2o + xk2o
        AI = xal2o3 / denom if denom > 0 else 0.0
        NBO = (2 * (xh2o + xk2o + xna2o + xcao + xmgo + xfeo - xal2o3)
               / (2 * xsio2 + 2 * xtio2 + 3 * xal2o3
                  + xmgo + xfeo + xcao + xna2o + xk2o + xh2o))
        args = (h2o_0, co2_0, AI, xfeo + xmgo, xna2o + xk2o,
                NBO, coh.ntot, coh.Tkc)

        for xh2o_g in xh2o_guesses:
            u0 = np.array([guess_bar, xh2o_g])
            try:
                result = scipy_root(coh.func_initial, u0, args=args)
                P_sat, XH2O_f = float(result.x[0]), float(result.x[1])
            except Exception:
                continue

            # Non-convergence: result ≈ initial guess (solver didn't move)
            if abs(P_sat - guess_bar) < 5.0 and abs(XH2O_f - xh2o_g) < 0.01:
                continue

            # Physical bounds
            if P_sat <= 0 or XH2O_f <= 0 or XH2O_f >= 1:
                continue

            logger.debug("[SulfurX] guess %g MPa xh2o=%.2f → %.0f bar XH2O=%.4f ✓",
                         g_mpa, xh2o_g, P_sat, XH2O_f)
            candidates.append((P_sat, XH2O_f, g_mpa))

    n_total = len(guesses_mpa) * len(xh2o_guesses)
    if not candidates:
        logger.warning("[SulfurX] 0/%d guesses converged — no satP solution", n_total)
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
        len(clusters), len(candidates), n_total, cluster_summary,
    )

    # Within the winning cluster, take the median
    mid = len(best_cluster) // 2
    P_sat, XH2O_f, g_mpa = best_cluster[mid]
    logger.debug(
        "[SulfurX] Final satP: %.1f bar (from %d/%d converged guesses, "
        "best initial guess %d MPa)",
        P_sat, len(candidates), n_total, g_mpa,
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


def _fmq_frost1991(T_K: float, P_bar: float = 1.0) -> float:
    """FMQ buffer — Frost (1991) Reviews in Mineralogy, Vol. 25.

    Same equation used internally by SulfurX's ``OxygenFugacity.fmq()``.
    """
    return -25096.3 / T_K + 8.735 + 0.110 * (P_bar - 1) / T_K


def _nno_frost1991(T_K: float, P_bar: float = 1.0) -> float:
    """NNO buffer — Frost (1991) Reviews in Mineralogy, Vol. 25."""
    return -24930.0 / T_K + 9.36 + 0.046 * (P_bar - 1) / T_K


def _logfo2_from_fe3fet(fe3fet: float, T_K: float,
                        composition: dict[str, float]) -> float:
    """Invert KC91 to get logfO2 from Fe3+/FeT at 1 bar.

    Uses Brent's method to find the logfO2 that makes
    ``fe3fet_kc91(logfO2, T_K, composition) == fe3fet``.
    """
    def residual(logfo2):
        return fe3fet_kc91(logfo2, T_K, composition, P_bar=1.0) - fe3fet

    # Search over a generous logfO2 range (IW-5 to HM+5 ≈ -25 to 0)
    return brentq(residual, -25.0, 0.0, xtol=1e-8)


def _compute_delta_fmq(comp: MeltComposition) -> float:
    """Determine delta_FMQ for SulfurX from the available redox input.

    Priority:
      1. ``dFMQ`` — direct, no conversion needed.
      2. ``Fe3FeT`` — invert Kress & Carmichael (1991) at 1 bar to get
         logfO2, then subtract Frost (1991) FMQ.  This mirrors what
         SulfurX does internally (KC91 for Fe redox, Frost FMQ buffer).
      3. ``dNNO`` — convert via Frost (1991) NNO and FMQ at 1 bar:
         ``dFMQ = dNNO + [NNO(T) - FMQ(T)]``.

    The offset ``NNO(T) - FMQ(T)`` is temperature-dependent (~0.74 at
    1200 °C, ~0.75 at 1030 °C), so the old constant ``dNNO - 0.7``
    approximation was systematically wrong by ~0.04–0.05 and also did
    not match how SulfurX's author computed dFMQ from Fe3FeT.
    """
    T_K = comp.T_C + 273.15
    fmq_1bar = _fmq_frost1991(T_K)

    # --- Path 1: dFMQ given directly ---
    if comp.dFMQ is not None:
        logger.debug("[SulfurX] Using supplied dFMQ = %.4f", comp.dFMQ)
        return comp.dFMQ

    # --- Path 2: Fe3FeT → KC91 inverse → logfO2 → dFMQ ---
    fe3fet = comp.fe3fet_computed
    if not np.isnan(fe3fet):
        oxides = comp.oxide_dict
        try:
            logfo2 = _logfo2_from_fe3fet(fe3fet, T_K, oxides)
            delta = logfo2 - fmq_1bar
            logger.info(
                "[SulfurX] Fe3FeT=%.3f → logfO2=%.3f → dFMQ=%.4f "
                "(Frost 1991 FMQ at %.0f °C = %.3f)",
                fe3fet, logfo2, delta, comp.T_C, fmq_1bar,
            )
            return delta
        except ValueError as exc:
            logger.warning(
                "[SulfurX] KC91 inversion failed for Fe3FeT=%.3f: %s. "
                "Falling back to dNNO.",
                fe3fet, exc,
            )

    # --- Path 3: dNNO → Frost NNO → logfO2 → dFMQ ---
    if comp.dNNO is not None:
        nno_1bar = _nno_frost1991(T_K)
        delta = comp.dNNO + (nno_1bar - fmq_1bar)
        logger.info(
            "[SulfurX] dNNO=%.3f → dFMQ=%.4f "
            "(Frost 1991: NNO=%.3f, FMQ=%.3f at %.0f °C)",
            comp.dNNO, delta, nno_1bar, fmq_1bar, comp.T_C,
        )
        return delta

    raise ValueError(
        "SulfurX requires a redox constraint: dFMQ, Fe3FeT, or dNNO."
    )


def _run_degassing(comp: MeltComposition, cfg, output_dir: str | None = None) -> pd.DataFrame:
    """Run the full SulfurX degassing path.

    Translates the workflow from SulfurX's ``main_Fuego.py`` into a callable function, bypassing interactive prompts and hardcoded compositions.

    When ``output_dir`` is provided, captures the resolved input via :mod:`volcatenate.resolved_inputs` so a sidecar yaml is written and the run-bundle picks it up.
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

    delta_FMQ = _compute_delta_fmq(comp)

    coh_model = cfg.coh_model
    choice = cfg.crystallization
    fo2_tracker = cfg.fo2_tracker
    s_fe_choice = cfg.s_fe_choice
    sigma = cfg.sigma
    sulfide_pre = cfg.sulfide_pre
    slope_h2o = cfg.slope_h2o
    constant_h2o = cfg.constant_h2o
    n_steps = cfg.n_steps
    open_degassing = cfg.open_degassing
    d34s_initial = cfg.d34s_initial

    # Sulfide phase composition — exposed via SulfurXSulfideConfig.
    sulfide = {
        "Fe": cfg.sulfide.fe,
        "Ni": cfg.sulfide.ni,
        "Cu": cfg.sulfide.cu,
        "O":  cfg.sulfide.o,
        "S":  cfg.sulfide.s,
    }

    # Capture resolved input for the bundle / sidecar yaml.
    if output_dir is not None:
        from volcatenate.resolved_inputs import capture as _capture_resolved
        _capture_resolved(
            sample=comp.sample,
            backend="SulfurX",
            data={
                "composition_oxides": dict(composition),
                "T_K": float(tk),
                "H2O_wt": float(h2o_wt),
                "CO2_ppm": float(co2_ppm),
                "S_ppm": float(s_ppm),
                "delta_FMQ": float(delta_FMQ),
                "params": {
                    "coh_model": int(coh_model),
                    "crystallization": int(choice),
                    "fo2_tracker": int(fo2_tracker),
                    "s_fe_choice": int(s_fe_choice),
                    "sigma": float(sigma),
                    "sulfide_pre": int(sulfide_pre),
                    "slope_h2o": float(slope_h2o),
                    "constant_h2o": float(constant_h2o),
                    "n_steps": int(n_steps),
                    "open_degassing": int(open_degassing),
                    "d34s_initial": float(d34s_initial),
                },
                "sulfide": sulfide,
            },
            output_dir=output_dir,
        )

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


def _compute_saturation_state(
    comp: MeltComposition,
    cfg,
    P_sat: float,
    XH2O_f: float,
) -> pd.Series:
    """Compute full equilibrium state at the saturation pressure.

    Reuses the initialization logic from ``_run_degassing`` (steps 1-4)
    to compute redox state, sulfur speciation, and vapor composition at
    the found saturation pressure.

    Parameters
    ----------
    comp : MeltComposition
        Starting melt composition.
    cfg : SulfurXConfig
        SulfurX sub-configuration.
    P_sat : float
        Saturation pressure in bars.
    XH2O_f : float
        H₂O mole fraction in the fluid phase at saturation.
    """
    from volcatenate import columns as col
    from oxygen_fugacity import OxygenFugacity
    from fugacity import Fugacity
    from sulfur_partition_coefficients import PartitionCoefficient
    from S_Fe import Sulfur_Iron

    composition = _build_composition(comp)
    tk = comp.T_C + 273.15
    temperature = comp.T_C
    h2o_wt = comp.H2O
    co2_ppm = comp.CO2 * 10_000
    s_ppm = comp.S * 10_000

    delta_FMQ = _compute_delta_fmq(comp)

    # Compute fO2 and Fe3+/FeT at saturation P
    fo2_calc = OxygenFugacity(P_sat / 10, tk, composition)
    ferric_ratio = fo2_calc.fe_ratio(fo2_calc.fmq() + delta_FMQ)
    logfo2 = fo2_calc.fo2(ferric_ratio)
    fmq_val = fo2_calc.fmq()

    # Compute S6+/ST via Sulfur_Iron
    rs = Sulfur_Iron(
        ferric_iron=ferric_ratio,
        temperature=temperature,
        model_choice=cfg.s_fe_choice,
        composition=composition,
        o2=fmq_val + delta_FMQ,
    )

    # Compute fugacity coefficients for vapor composition
    phi = Fugacity(P_sat / 10, temperature)

    # Compute partition coefficients for sulfur vapor species
    re = PartitionCoefficient(
        P_sat / 10, tk, composition, h2o_wt,
        phi.phiH2O, phi.phiH2S, phi.phiSO2, monte=0,
    )

    # --- Sulfur vapor species at saturation ---
    # Sulfur mole fraction in melt (same formula as degassing init)
    s_moles = s_ppm / (10_000 * 32.065)
    co2_moles = co2_ppm / (10_000 * 44.01)
    XS_melt = s_moles / (re.ntot + s_moles + re.nh + co2_moles)

    # Partition coefficients for H2S (RxnI) and SO2 (RxnII)
    kd1 = re.kd_rxn1(XH2O_f)               # H2S Kd
    fO2_linear = 10.0 ** logfo2             # linear fO2 in bars
    kd2 = re.kd_rxn2(fO2_linear)            # SO2 Kd

    # SO2 / (SO2 + H2S) ratio in vapor from gas equilibrium
    fH2O = XH2O_f * P_sat * phi.phiH2O     # H2O fugacity in bars
    SO2_ST_vapor = re.gas_quilibrium(
        fo2=fO2_linear, fh2o=fH2O,
        phiso2=phi.phiSO2, phih2s=phi.phiH2S,
    )

    # Combined molar Kd weighted by S6+/ST in melt
    S6ST = rs.sulfate
    kd_combined = kd1 * (1.0 - S6ST) + kd2 * S6ST

    # Total sulfur mole fraction in vapor, split into SO2 and H2S
    XS_fluid = XS_melt * kd_combined
    XSO2_fluid = XS_fluid * SO2_ST_vapor
    XH2S_fluid = XS_fluid * (1.0 - SO2_ST_vapor)

    # Adjust CO2 vapor fraction to account for sulfur
    XCO2_f = max(0.0, 1.0 - XH2O_f - XS_fluid)

    # Build the equilibrium state Series
    # Include all vapor species so compute_cs_v_mf can calculate C/S ratio
    return pd.Series({
        col.P_BARS: P_sat,
        col.H2OT_M_WTPC: h2o_wt,
        col.CO2T_M_PPMW: co2_ppm,
        col.ST_M_PPMW: s_ppm,
        col.FE3FET_M: ferric_ratio,
        col.S6ST_M: S6ST,
        col.LOGFO2: logfo2,
        col.DFMQ: delta_FMQ,
        col.VAPOR_WT: 0.0,          # at saturation onset
        col.H2O_V_MF: XH2O_f,
        col.CO2_V_MF: XCO2_f,
        col.SO2_V_MF: XSO2_fluid,
        col.H2S_V_MF: XH2S_fluid,
        col.S2_V_MF: np.nan,        # not modeled by SulfurX
        col.CO_V_MF: np.nan,        # not modeled by SulfurX
        col.CH4_V_MF: np.nan,       # not modeled by SulfurX
    })


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
            self._log_version(sx_path)

    @staticmethod
    def _log_version(sx_path: str) -> None:
        """Log the detected SulfurX version; advisory warnings for dirty/unknown/untested."""
        from volcatenate.versions import backend_version_info

        info = backend_version_info("sulfurx", path=sx_path)
        if info["status"] == "no_version_info":
            logger.warning(
                "[SulfurX] Source at %s is not a git checkout — "
                "version cannot be identified.", sx_path,
            )
            return

        tag = info.get("tag") or "unknown"
        suffix = " (uncommitted changes)" if info["dirty"] else ""
        logger.info(
            "[SulfurX] Using %s (%s)%s at %s",
            tag, info["id"], suffix, sx_path,
        )
        if info["dirty"]:
            logger.warning(
                "[SulfurX] Working tree at %s has uncommitted changes — "
                "results may not be reproducible.", sx_path,
            )
        if info["tag"] is None:
            logger.warning(
                "[SulfurX] Commit %s does not match any known release tag. "
                "Results produced with this version have not been validated "
                "against volcatenate's SulfurX wrapper.", info["id"],
            )
        elif not info["tested"]:
            logger.warning(
                "[SulfurX] %s has not been validated against volcatenate's "
                "SulfurX wrapper. Proceeding anyway.", tag,
            )

    # ----------------------------------------------------------------
    # Saturation pressure
    # ----------------------------------------------------------------
    def calculate_saturation_pressure(
        self,
        comp: MeltComposition,
        config: RunConfig,
    ) -> pd.Series | None:
        self._ensure_on_path(config)
        cfg = resolve_sample_config(config.sulfurx, comp.sample)

        tk = comp.T_C + 273.15
        h2o_wt = comp.H2O
        co2_ppm = comp.CO2 * 10_000
        composition = _build_composition(comp)

        # Capture resolved input for the bundle / sidecar yaml.
        # The ``params`` block here is a strict subset of the degassing
        # capture's ``params``: ``crystallization``, ``n_steps``,
        # ``open_degassing``, and ``d34s_initial`` are degassing-path
        # settings that have no effect on a single-point satP call,
        # so we deliberately omit them rather than record values that
        # didn't influence the answer.
        from volcatenate.resolved_inputs import capture as _capture_resolved
        s_ppm = comp.S * 10_000
        _capture_resolved(
            sample=comp.sample,
            backend="SulfurX",
            data={
                "composition_oxides": dict(composition),
                "T_K": float(tk),
                "H2O_wt": float(h2o_wt),
                "CO2_ppm": float(co2_ppm),
                "S_ppm": float(s_ppm),
                "delta_FMQ": float(_compute_delta_fmq(comp)),
                "params": {
                    "coh_model": int(cfg.coh_model),
                    "slope_h2o": float(cfg.slope_h2o),
                    "constant_h2o": float(cfg.constant_h2o),
                    "fo2_tracker": int(cfg.fo2_tracker),
                    "s_fe_choice": int(cfg.s_fe_choice),
                    "sigma": float(cfg.sigma),
                    "sulfide_pre": int(cfg.sulfide_pre),
                },
                "sulfide": {
                    "Fe": cfg.sulfide.fe, "Ni": cfg.sulfide.ni,
                    "Cu": cfg.sulfide.cu, "O": cfg.sulfide.o,
                    "S": cfg.sulfide.s,
                },
                "run_type": "satp",
            },
            output_dir=config.output_dir,
        )

        try:
            if cfg.coh_model == 0:
                with _quiet_sulfurx():
                    P_sat, XH2O_f = _find_saturation_pressure_im(
                        composition, tk, co2_ppm, h2o_wt,
                        cfg.slope_h2o, cfg.constant_h2o,
                    )
            else:
                with _quiet_sulfurx():
                    from VC_COH import VolatileCalc

                    vc = VolatileCalc(
                        TK=tk, sio2=composition["SiO2"],
                        a=cfg.slope_h2o, b=cfg.constant_h2o,
                    )
                    result = vc.SatPress(WtH2O=h2o_wt, PPMCO2=co2_ppm)
                    P_sat = float(result[0])
                    XH2O_f = float(result[5])

            if np.isnan(P_sat) or P_sat <= 0:
                return None

            # Compute full equilibrium state at saturation
            with _quiet_sulfurx():
                state = _compute_saturation_state(comp, cfg, P_sat, XH2O_f)

            # Ensure all standard columns present
            state_df = pd.DataFrame([state])
            state_df = compute_cs_v_mf(state_df)
            state_df = ensure_standard_columns(state_df)
            return state_df.iloc[0].copy()

        except Exception as exc:
            logger.warning("[SulfurX] satP failed for %s: %s", comp.sample, exc)
            return None

    # ----------------------------------------------------------------
    # Degassing path
    # ----------------------------------------------------------------
    def calculate_degassing(
        self,
        comp: MeltComposition,
        config: RunConfig,
    ) -> pd.DataFrame:
        self._ensure_on_path(config)

        cfg = resolve_sample_config(config.sulfurx, comp.sample)
        with _quiet_sulfurx():
            df = _run_degassing(comp, cfg, output_dir=config.output_dir)

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
