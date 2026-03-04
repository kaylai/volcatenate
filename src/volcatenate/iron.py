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
