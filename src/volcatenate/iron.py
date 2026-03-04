"""Iron speciation utilities.

Molecular weights:
    Fe2O3 = 159.69 g/mol
    FeO   = 71.844 g/mol
"""

from __future__ import annotations

import numpy as np

MW_FE2O3 = 159.69
MW_FEO = 71.844


def fe3fet_from_speciated(feo: float, fe2o3: float) -> float:
    """Compute Fe3+/FeT from speciated FeO and Fe2O3.

    Parameters
    ----------
    feo : float
        FeO wt% (ferrous iron oxide).
    fe2o3 : float
        Fe2O3 wt% (ferric iron oxide).

    Returns
    -------
    float
        Fe3+/FeT molar ratio, or NaN if inputs are non-positive.
    """
    if fe2o3 > 0 and feo > 0:
        fe3_mol = 2.0 * fe2o3 / MW_FE2O3
        fe2_mol = feo / MW_FEO
        return fe3_mol / (fe3_mol + fe2_mol)
    return np.nan


def split_feot(feot: float, fe3fet: float) -> tuple[float, float]:
    """Split FeOT into FeO and Fe2O3 given Fe3+/FeT ratio.

    Parameters
    ----------
    feot : float
        Total iron as FeO (wt%).
    fe3fet : float
        Fe3+/FeT molar ratio.

    Returns
    -------
    tuple[float, float]
        (FeO wt%, Fe2O3 wt%)
    """
    feo = feot * (1.0 - fe3fet)
    fe2o3 = feot * fe3fet * (MW_FE2O3 / (2.0 * MW_FEO))
    return feo, fe2o3


def feot_from_speciated(feo: float, fe2o3: float) -> float:
    """Compute total iron as FeO from speciated FeO and Fe2O3.

    Parameters
    ----------
    feo : float
        FeO wt%.
    fe2o3 : float
        Fe2O3 wt%.

    Returns
    -------
    float
        Total iron as FeO (wt%).
    """
    return feo + fe2o3 * (2.0 * MW_FEO / MW_FE2O3)


# ---------------------------------------------------------------------------
# Kress & Carmichael (1991) — Fe3+/FeT from fO2, T, and composition
# ---------------------------------------------------------------------------
#
# Molecular weights for single-cation mole fractions:
_MW_SINGLE_CATION = {
    "SiO2": 60.08,    # SiO₂
    "TiO2": 79.87,    # TiO₂
    "Al2O3": 50.98,   # AlO₁.₅ (= Al₂O₃/2)
    "FeOT": 71.844,   # FeO
    "MnO": 70.94,     # MnO
    "MgO": 40.30,     # MgO
    "CaO": 56.08,     # CaO
    "Na2O": 30.99,    # NaO₀.₅ (= Na₂O/2)
    "K2O": 47.10,     # KO₀.₅ (= K₂O/2)
    "P2O5": 70.97,    # PO₂.₅ (= P₂O₅/2)
}
# Number of single-cation formula units per formula unit:
_N_CATION = {
    "SiO2": 1, "TiO2": 1, "Al2O3": 2, "FeOT": 1, "MnO": 1,
    "MgO": 1, "CaO": 1, "Na2O": 2, "K2O": 2, "P2O5": 2,
}


def _oxide_mole_fractions(composition: dict[str, float]) -> dict[str, float]:
    """Convert wt% oxide composition to single-cation mole fractions.

    Parameters
    ----------
    composition : dict
        Oxide wt% with keys like ``SiO2``, ``TiO2``, ..., ``FeOT``.

    Returns
    -------
    dict
        Single-cation mole fractions (sum to 1).
    """
    moles = {}
    for ox, wt in composition.items():
        if ox in _MW_SINGLE_CATION and wt > 0:
            n = _N_CATION[ox]
            moles[ox] = n * wt / _MW_SINGLE_CATION[ox]
    total = sum(moles.values())
    if total == 0:
        return {ox: 0.0 for ox in moles}
    return {ox: m / total for ox, m in moles.items()}


def fe3fet_kc91(
    log_fo2: float,
    T_K: float,
    composition: dict[str, float],
    P_bar: float = 1.0,
) -> float:
    """Compute Fe3+/FeT using Kress & Carmichael (1991).

    Parameters
    ----------
    log_fo2 : float
        log₁₀(fO₂) in bar.
    T_K : float
        Temperature in Kelvin.
    composition : dict
        Anhydrous oxide wt% (``SiO2``, ``TiO2``, ``Al2O3``, ``FeOT``,
        ``MnO``, ``MgO``, ``CaO``, ``Na2O``, ``K2O``, ``P2O5``).
    P_bar : float
        Pressure in bar (default 1 bar; KC91 pressure term is small).

    Returns
    -------
    float
        Fe³⁺/FeT (molar ratio), or NaN on failure.

    Notes
    -----
    Equation (7) of Kress & Carmichael (1991) *Contributions to Mineralogy
    and Petrology*, 108, 82-92.  Constants from their Table 7.
    """
    # KC91 Table 7 constants
    a = 0.196
    b = 11_492.0
    c = -6.675
    d = {
        "Al2O3": -2.243,
        "FeOT":  -1.828,
        "CaO":    3.201,
        "Na2O":   5.854,
        "K2O":    6.215,
    }
    e = -3.36
    f = -7.01e-7   # Pa⁻¹ — note: KC91 uses P in Pascal
    g = -1.114
    T0 = 1673.0    # reference T (K)

    xmf = _oxide_mole_fractions(composition)

    # ln(XFe2O3/XFeO) term
    ln_ratio = (
        a * np.log(10.0) * log_fo2   # a * ln(fO₂)
        + b / T_K
        + c
        + sum(coeff * xmf.get(ox, 0.0) for ox, coeff in d.items())
        + e * (
            xmf.get("Al2O3", 0.0) * xmf.get("FeOT", 0.0)
            / max(
                xmf.get("Al2O3", 0.0) + xmf.get("FeOT", 0.0)
                + xmf.get("CaO", 0.0) + xmf.get("Na2O", 0.0)
                + xmf.get("K2O", 0.0),
                1e-20,
            )
        )
        + f * (P_bar * 1e5) / T_K     # convert bar → Pa
        + g * (T0 / T_K * np.log(T_K / T0) + 1.0 - T0 / T_K)
    )

    # XFe2O3/XFeO = exp(ln_ratio)
    ratio = np.exp(ln_ratio)
    # Fe3+/FeT = 2*XFe2O3 / (2*XFe2O3 + XFeO)
    #          = 2*ratio / (2*ratio + 1)
    fe3fet = 2.0 * ratio / (2.0 * ratio + 1.0)

    if np.isnan(fe3fet) or fe3fet < 0 or fe3fet > 1:
        return np.nan
    return fe3fet
