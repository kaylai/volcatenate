"""Post-processing utilities for standardized model output.

Includes C/S ratio computation, volatile normalization, and
column completeness checks.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from volcatenate import columns as col


def compute_cs_v_mf(df: pd.DataFrame) -> pd.DataFrame:
    """Compute elemental C/S ratio in the vapor phase.

    Uses stoichiometric coefficients from :data:`columns.C_SPECIES` and :data:`columns.S_SPECIES` to count carbon and sulfur atoms:

    .. code-block:: text

        C/S = (1*X_CO2 + 1*X_CO + 1*X_CH4 + 1*X_OCS)
            / (1*X_SO2 + 1*X_H2S + 2*X_S2 + 1*X_OCS)

    Species columns missing from ``df`` or containing NaN are treated as zero. Sets ``CS_v_mf = NaN`` where the sulfur denominator is zero.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain at least some of the vapor species columns
        (gas-phase mole fractions).

    Returns
    -------
    pd.DataFrame
        Same DataFrame with ``CS_v_mf`` column added or overwritten.
    """
    c_cols = {c: coeff for c, coeff in col.C_SPECIES.items() if c in df.columns}
    s_cols = {s: coeff for s, coeff in col.S_SPECIES.items() if s in df.columns}

    if c_cols and s_cols:
        c_sum = sum(df[c].fillna(0.0) * coeff for c, coeff in c_cols.items())
        s_sum = sum(df[s].fillna(0.0) * coeff for s, coeff in s_cols.items())
        df[col.CS_V_MF] = np.where(s_sum > 0, c_sum / s_sum, np.nan)
    elif col.CS_V_MF not in df.columns:
        df[col.CS_V_MF] = np.nan

    return df


def normalize_volatiles(df: pd.DataFrame) -> pd.DataFrame:
    """Add ``_norm`` columns for H2O, CO2, S relative to initial (row 0) values.

    Modifies *df* in place and returns it for chaining.

    Parameters
    ----------
    df : pd.DataFrame
        Degassing path DataFrame with at least one row.

    Returns
    -------
    pd.DataFrame
        Same DataFrame (mutated) with ``_norm`` columns added.
    """
    pairs = [
        (col.H2OT_M_WTPC, col.H2OT_M_WTPC_NORM),
        (col.CO2T_M_PPMW, col.CO2T_M_PPMW_NORM),
        (col.ST_M_PPMW, col.ST_M_PPMW_NORM),
    ]
    for src, dst in pairs:
        if src in df.columns and len(df) > 0:
            init_val = df[src].iloc[0]
            if init_val != 0 and not np.isnan(init_val):
                df[dst] = (df[src] / init_val).values
            else:
                df[dst] = np.nan

    return df


def compute_o2_mass_balance(df: pd.DataFrame) -> pd.DataFrame:
    """Add ``SUM_v_mf`` and ``XO2_BYDIFF_v_mf`` columns.

    ``SUM_v_mf`` is the sum of every present vapor mole-fraction column
    in :data:`columns.VAPOR_MF_COLUMNS`; on rows where the vapor mass
    fraction is zero (no vapor yet) the sum is left as 0.  Treat NaN
    species as 0 so partial backends still produce a number.

    ``XO2_BYDIFF_v_mf`` is ``1 − Σ X_i`` over the *non-O2* vapor
    species.  Useful when a backend doesn't compute ``O2_v_mf``
    directly but other species close to 1.

    Both columns are NaN on rows where no vapor species column is
    present at all (defensive — should not happen after
    :func:`ensure_standard_columns`).
    """
    species_present = [c for c in col.VAPOR_MF_COLUMNS if c in df.columns]
    if not species_present:
        df[col.SUM_V_MF] = np.nan
        df[col.XO2_BYDIFF_V_MF] = np.nan
        return df

    non_o2 = [c for c in species_present if c != col.O2_V_MF]
    sum_all = df[species_present].fillna(0.0).sum(axis=1)
    if non_o2:
        sum_non_o2 = df[non_o2].fillna(0.0).sum(axis=1)
    else:
        sum_non_o2 = pd.Series(0.0, index=df.index)

    df[col.SUM_V_MF] = sum_all
    df[col.XO2_BYDIFF_V_MF] = 1.0 - sum_non_o2
    return df


def ensure_standard_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure all standard columns exist, filling missing ones with NaN.

    Modifies *df* in place and returns it for chaining.

    Parameters
    ----------
    df : pd.DataFrame
        Model output DataFrame (may be missing some columns).

    Returns
    -------
    pd.DataFrame
        Same DataFrame (mutated) with all ``STANDARD_COLUMNS`` present.
    """
    for c in col.STANDARD_COLUMNS:
        if c not in df.columns:
            df[c] = np.nan
    return df


def to_standard_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Return *df* containing exactly the standard schema columns.

    Adds any missing :data:`columns.STANDARD_COLUMNS` (filled with NaN),
    keeps :data:`columns.OPTIONAL_COLUMNS` if present, and drops every
    other column.  Use this immediately before writing degassing CSVs so
    backend-specific intermediate columns (e.g. MAGEC's ``Run_ID``,
    ``_sample``) never leak into the user-facing output.

    Parameters
    ----------
    df : pd.DataFrame
        Model output DataFrame, possibly with extra columns.

    Returns
    -------
    pd.DataFrame
        New DataFrame restricted to the canonical schema, with column
        order matching ``STANDARD_COLUMNS`` followed by any optional
        columns that were present.
    """
    df = ensure_standard_columns(df)
    # Idempotently populate derived columns so every written CSV carries
    # the full schema that downstream figure code expects.
    df = compute_cs_v_mf(df)
    if len(df) > 0:
        df = normalize_volatiles(df)
    df = compute_o2_mass_balance(df)
    keep = list(col.STANDARD_COLUMNS) + [c for c in col.OPTIONAL_COLUMNS if c in df.columns]
    return df[keep].copy()
