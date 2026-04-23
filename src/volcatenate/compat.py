"""Compatibility layer — bridges volcatenate output to existing plotting code.

The existing plotting scripts (``generate_paper_plots.py``,
``plot_CS_with_gas_data.py``) expect data in the ``loadData()`` dict
format::

    {"Name": "Kilauea", "EVo": DataFrame, "VolFe": DataFrame, ...}

This module provides helpers to convert volcatenate's output into
that format, and to load pre-existing model CSV files into
standardized DataFrames.

Drop-in replacement for ``model_handling.py``
---------------------------------------------
The :func:`loadData` function is a drop-in replacement for the old
``model_handling.loadData()``.  In your plotting scripts, change::

    import model_handling as mh
    data_morb, data_kil, data_fuego, data_fogo = mh.loadData(...)

to::

    import volcatenate.compat as mh
    data_morb, data_kil, data_fuego, data_fogo = mh.loadData(...)
"""

from __future__ import annotations

import os
from typing import Optional

from volcatenate.log import logger

import numpy as np
import pandas as pd

from volcatenate import columns as col
from volcatenate.converters import (
    convert_evo, is_raw_evo,
    convert_volfe, is_raw_volfe,
    convert_magec, is_raw_magec,
    convert_vesical, is_raw_vesical,
    convert_sulfurx, is_raw_sulfurx,
    convert_dcompress, is_raw_dcompress,
)
from volcatenate.convert import compute_cs_v_mf, normalize_volatiles


# Model name → (is_raw_func, convert_func)
_AUTO_CONVERTERS = {
    "EVo":       (is_raw_evo, convert_evo),
    "VolFe":     (is_raw_volfe, convert_volfe),
    "MAGEC":     (is_raw_magec, convert_magec),
    "SulfurX":   (is_raw_sulfurx, convert_sulfurx),
    "DCompress": (is_raw_dcompress, convert_dcompress),
}

# VESIcal variants that need the VESIcal converter
_VESICAL_VARIANTS = {
    "VESIcal_MS", "VESIcal_Dixon", "VESIcal_Iacono",
    "VESIcal_Liu", "VESIcal_ShishkinaIdealMixing",
}


def load_model_csv(
    csv_path: str,
    model_name: str,
    composition: Optional[dict] = None,
    T_K: Optional[float] = None,
) -> pd.DataFrame:
    """Load a single model output CSV and standardize it.

    Automatically detects whether the file is in raw or already-
    converted format and applies the appropriate converter.

    Parameters
    ----------
    csv_path : str
        Path to the model output CSV file.
    model_name : str
        Model name (e.g. ``"EVo"``, ``"VolFe"``, ``"VESIcal_Iacono"``).
    composition : dict, optional
        Starting composition (needed for EVo Fe3+/FeT calculation).
    T_K : float, optional
        Temperature in Kelvin (needed for EVo Fe3+/FeT).

    Returns
    -------
    pd.DataFrame
        Standardized DataFrame.
    """
    df = pd.read_csv(csv_path)

    # Auto-detect and convert
    if model_name in _AUTO_CONVERTERS:
        is_raw_fn, convert_fn = _AUTO_CONVERTERS[model_name]
        if is_raw_fn(df):
            if model_name == "EVo":
                df = convert_fn(df, composition=composition, T_K=T_K)
            else:
                df = convert_fn(df)
    elif model_name in _VESICAL_VARIANTS or model_name.startswith("VESIcal"):
        if is_raw_vesical(df):
            df = convert_vesical(df, model_variant=model_name)

    # Post-processing: CS_v_mf fallback + normalization
    df = compute_cs_v_mf(df)
    df = normalize_volatiles(df)

    return df


def load_data(
    model_names: list[str],
    top_directory: str,
    volcano_names: Optional[list[str]] = None,
    compositions: Optional[dict[str, dict]] = None,
) -> dict[str, dict]:
    """Load all model run data, mirroring the old ``loadData()`` interface.

    Parameters
    ----------
    model_names : list[str]
        Model names to load, e.g. ``["EVo", "VolFe", "VESIcal_Iacono"]``.
    top_directory : str
        Top-level directory containing model subdirectories.
    volcano_names : list[str], optional
        Volcano names to look for (default: morb, kilauea, fuego, fogo).
    compositions : dict, optional
        Dict mapping volcano name → composition dict (for EVo Fe3+/FeT).

    Returns
    -------
    dict[str, dict]
        Keyed by volcano name.  Each value is a dict with
        ``{"Name": str, "ModelName": DataFrame, ...}``.
    """
    if volcano_names is None:
        volcano_names = ["morb", "kilauea", "fuego", "fogo"]

    # Display names
    display_names = {
        "morb": "MORB", "kilauea": "Kilauea",
        "fuego": "Fuego", "fogo": "Fogo",
    }

    results = {}
    for vname in volcano_names:
        results[vname] = {"Name": display_names.get(vname, vname)}

    for model in model_names:
        # Determine directory
        if "VESIcal" in model:
            model_dir = os.path.join(top_directory, "VESIcal", model)
        else:
            model_dir = os.path.join(top_directory, model)

        if not os.path.isdir(model_dir):
            continue

        for filename in os.listdir(model_dir):
            if not filename.endswith(".csv"):
                continue
            filepath = os.path.join(model_dir, filename)
            if not os.path.isfile(filepath):
                continue

            name_lower = os.path.splitext(filename)[0].lower()

            for vname in volcano_names:
                if vname in name_lower:
                    # Get composition for EVo converter if available
                    comp = None
                    t_k = None
                    if compositions and vname in compositions:
                        comp = compositions[vname]
                        t_k = comp.get("T_C", 0) + 273.15 if comp else None

                    try:
                        df = load_model_csv(
                            filepath, model,
                            composition=comp, T_K=t_k,
                        )
                        results[vname][model] = df
                    except Exception as exc:
                        logger.warning("Failed to load %s: %s", filepath, exc)

    return results


def degassing_results_to_compat(
    results: dict[str, pd.DataFrame],
    volcano_name: str,
) -> dict:
    """Convert ``calculate_degassing()`` output to ``loadData()`` format.

    Parameters
    ----------
    results : dict[str, pd.DataFrame]
        Output from :func:`volcatenate.calculate_degassing`.
    volcano_name : str
        Name to set in the ``"Name"`` key.

    Returns
    -------
    dict
        ``{"Name": "Kilauea", "EVo": DataFrame, ...}``
    """
    d = {"Name": volcano_name}
    d.update(results)
    return d


# ------------------------------------------------------------------
# Drop-in replacement for model_handling.loadData()
# ------------------------------------------------------------------

# Starting compositions (for EVo Fe3+/FeT via KC91).
# Matches starting_compositions.py in the paper repo.
_STARTING_COMPOSITIONS = {
    "kilauea": {
        "Sample": "Kilauea", "T_C": 1200.0,
        "SiO2": 50.19, "TiO2": 2.34, "Al2O3": 12.79,
        "FeO": 11.34, "MnO": 0.18, "MgO": 9.23, "CaO": 10.44,
        "Na2O": 2.39, "K2O": 0.43, "P2O5": 0.27,
        "H2O": 0.30, "CO2": 0.0800, "S": 0.1500,
        "Fe3FeT": 0.18, "dNNO": -0.23,
    },
    "fogo": {
        "Sample": "Fogo", "T_C": 1200.0,
        "SiO2": 42.40, "TiO2": 3.26, "Al2O3": 11.17,
        "FeO": 12.00, "MnO": 0.14, "MgO": 9.55, "CaO": 13.31,
        "Na2O": 3.36, "K2O": 1.57, "P2O5": 0.75,
        "H2O": 2.11, "CO2": 1.1520, "S": 0.4690,
        "dNNO": 0.7,
    },
    "fuego": {
        "Sample": "Fuego", "T_C": 1030.0,
        "SiO2": 51.46, "TiO2": 1.06, "Al2O3": 17.43,
        "FeO": 9.42, "MnO": 0.19, "MgO": 3.78, "CaO": 7.99,
        "Na2O": 3.47, "K2O": 0.78, "P2O5": 0.24,
        "H2O": 4.5, "CO2": 0.3300, "S": 0.2650,
        "Fe3FeT": 0.235, "dNNO": 0.25,
    },
    "morb": {
        "Sample": "MORB", "T_C": 1100.0,
        "SiO2": 47.40, "TiO2": 1.01, "Al2O3": 17.64,
        "FeO": 7.98, "MnO": 0.00, "MgO": 7.63, "CaO": 12.44,
        "Na2O": 2.65, "K2O": 0.03, "P2O5": 0.08,
        "H2O": 0.20, "CO2": 0.1100, "S": 0.1420,
        "Fe3FeT": 0.10, "dNNO": -2.07,
    },
}

_VAPOR_MF_COLS = [
    "O2_v_mf", "CO2_v_mf", "CO_v_mf", "H2O_v_mf", "H2_v_mf",
    "S2_v_mf", "SO2_v_mf", "H2S_v_mf", "CH4_v_mf", "OCS_v_mf",
]

_VAPOR_MF_DERIVED = {"SUM_v_mf", "XO2_BYDIFF_v_mf", "CS_v_mf"}

_SUM_VMF_TOL = 1e-3


def _warn(msg: str) -> None:
    """Emit a warning to both the volcatenate logger and the terminal.

    ``loadData`` does not take a :class:`~volcatenate.config.RunConfig`,
    so the logger may be silent.  We also ``print`` to stderr so
    data-quality warnings are visible regardless of logger setup.
    """
    import sys
    logger.warning(msg)
    print(f"WARNING: {msg}", file=sys.stderr)


def _resolve_vapor_species(
    df: pd.DataFrame,
    vapor_species: "str | list[str]",
) -> tuple[list[str], list[str]]:
    """Resolve ``vapor_species`` against ``df.columns``.

    Returns ``(present, missing)``: ``present`` are species columns that
    exist in ``df`` (derived aggregates excluded); ``missing`` are names
    requested via an explicit list that are absent from ``df``.  When
    ``vapor_species`` is a glob pattern, ``missing`` is always empty.
    """
    import fnmatch
    if isinstance(vapor_species, str):
        matches = [c for c in df.columns
                   if fnmatch.fnmatchcase(c, vapor_species)]
        present = [c for c in matches if c not in _VAPOR_MF_DERIVED]
        return present, []
    requested = list(vapor_species)
    present = [c for c in requested
               if c in df.columns and c not in _VAPOR_MF_DERIVED]
    missing = [c for c in requested if c not in df.columns]
    return present, missing


def loadData(
    model_names: list[str],
    topdirectory_name: str = "",
    subdirectory_name: str = "",
    models_w_special_subdirectory: str | list[str] = "",
    O2_mass_bal: bool = False,
    vapor_species: "str | list[str]" = "*_v_mf",
    o2_column: str = "O2_v_mf",
    simplify: bool = False,
    save_simplified: bool = False,
) -> tuple[dict, dict, dict, dict]:
    """Drop-in replacement for ``model_handling.loadData()``.

    Returns ``(data_morb, data_kil, data_fuego, data_fogo)`` — four
    dicts, each ``{"Name": str, "ModelName": DataFrame, ...}``.

    Uses volcatenate's converters for auto-detection and standardization
    instead of the ad-hoc ``convert_evo.py`` / ``convert_volfe.py``.

    Parameters
    ----------
    model_names : list[str]
        Model names to load.
    topdirectory_name : str
        Top-level directory containing model subdirectories. Degassing CSVs are
        expected at ``data_dir/MODEL/sample.csv``.
    subdirectory_name : str
        Optional sub-path appended for models in
        *models_w_special_subdirectory*.
    models_w_special_subdirectory : str or list[str]
        Model(s) that live in ``topdirectory_name/model/subdirectory_name``.
    O2_mass_bal : bool
        If True, compute ``SUM_v_mf`` and ``XO2_BYDIFF_v_mf`` columns.
    vapor_species : str or list[str]
        Defines which DataFrame columns represent vapor species mole
        fractions for the O\\ :sub:`2` mass balance.  Accepts either a
        glob pattern (default ``"*_v_mf"``, matched via ``fnmatch``) or
        an explicit list of column names (e.g.
        ``["SO2_vapor", "H2S_vapor", ...]``).  Derived aggregates
        (``SUM_v_mf``, ``XO2_BYDIFF_v_mf``, ``CS_v_mf``) are always
        excluded from the species set.
    o2_column : str
        Name of the column representing O\\ :sub:`2` mole fraction under
        the user's convention.  Default ``"O2_v_mf"``.  Used to split
        species into "O\\ :sub:`2`" and "non-O\\ :sub:`2`" for the
        by-difference calculation.
    simplify : bool
        If True, keep only the standard column set.
    save_simplified : bool
        If True (and simplify is True), save simplified CSVs.
    """
    if isinstance(models_w_special_subdirectory, str):
        models_w_special_subdirectory = [models_w_special_subdirectory]

    data_morb = {"Name": "MORB"}
    data_kil = {"Name": "Kilauea"}
    data_fuego = {"Name": "Fuego"}
    data_fogo = {"Name": "Fogo"}

    _volcano_map = {
        "morb": data_morb, "kilauea": data_kil,
        "fuego": data_fuego, "fogo": data_fogo,
    }

    # ---- Load CSV files ----
    for model in model_names:
        subdir = (subdirectory_name
                  if model in models_w_special_subdirectory else "")
        if "VESIcal" in model:
            directory = os.path.join(topdirectory_name, "VESIcal", model + subdir)
        else:
            directory = os.path.join(topdirectory_name, model + subdir)

        if not os.path.isdir(directory):
            continue

        for filename in os.listdir(directory):
            if not filename.endswith(".csv"):
                continue
            filepath = os.path.join(directory, filename)
            if not os.path.isfile(filepath):
                continue

            name_lower = os.path.splitext(filename)[0].lower()
            for vkey, data_dict in _volcano_map.items():
                if vkey in name_lower:
                    comp = _STARTING_COMPOSITIONS.get(vkey)
                    t_k = (comp["T_C"] + 273.15) if comp and "T_C" in comp else None
                    try:
                        df = load_model_csv(
                            filepath, model,
                            composition=comp, T_K=t_k,
                        )
                        data_dict[model] = df
                    except Exception as exc:
                        logger.warning("Failed to load %s: %s", filepath, exc)

    datasets = [data_morb, data_kil, data_fuego, data_fogo]

    # ---- VESIcal: map XCO2_fl/XH2O_fl if still present ----
    for data in datasets:
        for key in list(data.keys()):
            if not isinstance(data.get(key), pd.DataFrame):
                continue
            if "VESIcal" in key:
                df = data[key]
                if "XCO2_fl" in df.columns:
                    df["CO2_v_mf"] = df["XCO2_fl"]
                    df["H2O_v_mf"] = df["XH2O_fl"]
                df["ST_m_ppmw"] = np.nan

    # ---- Normalized volatile columns ----
    for data in datasets:
        for vol in ["H2OT_m_wtpc", "CO2T_m_ppmw", "ST_m_ppmw"]:
            for model in model_names:
                if model not in data or not isinstance(data[model], pd.DataFrame):
                    continue
                if model == "VESIcal_MS":
                    continue
                if vol not in data[model].columns:
                    continue
                if len(data[model]) == 0:
                    continue
                vol_init = data[model][vol].iloc[0]
                if vol_init != 0 and not np.isnan(vol_init):
                    data[model][vol + "_norm"] = data[model][vol] / vol_init
                else:
                    data[model][vol + "_norm"] = np.nan

    # ---- O2 mass balance ----
    if O2_mass_bal:
        for data in datasets:
            volcano = data["Name"]
            for model in model_names:
                if model not in data or not isinstance(data[model], pd.DataFrame):
                    continue
                df = data[model]

                species_cols, missing_requested = _resolve_vapor_species(
                    df, vapor_species)

                # Warn about expected species absent from the DataFrame.
                # For an explicit list, "expected" = the user's list.
                # For the default glob, also warn about any of the
                # standard `_VAPOR_MF_COLS` that didn't show up — default
                # users benefit from being told which species are missing.
                absent_expected = list(missing_requested)
                if isinstance(vapor_species, str) and vapor_species == "*_v_mf":
                    absent_expected = [c for c in _VAPOR_MF_COLS
                                       if c not in species_cols]

                # Warn about species that are present but all-NaN or
                # all-zero — most likely not calculated by this backend.
                uncalculated = []
                for c in species_cols:
                    s = df[c]
                    if s.isna().all() or (s.fillna(0) == 0).all():
                        uncalculated.append(c)

                if absent_expected:
                    _warn(
                        f"{model} ({volcano}): expected vapor columns not "
                        f"present: {absent_expected}. Treating as 0 in "
                        f"O2 mass balance."
                    )
                if uncalculated:
                    _warn(
                        f"{model} ({volcano}): vapor columns present but "
                        f"all NaN or zero (likely not calculated by this "
                        f"backend): {uncalculated}. Treating as 0 in O2 "
                        f"mass balance."
                    )

                if not species_cols:
                    _warn(
                        f"{model} ({volcano}): no vapor species columns "
                        f"resolved from vapor_species={vapor_species!r}. "
                        f"SUM_v_mf and XO2_BYDIFF_v_mf set to NaN."
                    )
                    df["SUM_v_mf"] = np.nan
                    df["XO2_BYDIFF_v_mf"] = np.nan
                    continue

                if o2_column not in species_cols:
                    _warn(
                        f"{model} ({volcano}): o2_column={o2_column!r} not "
                        f"in resolved species set; XO2_BYDIFF_v_mf will be "
                        f"computed from all resolved species (none treated "
                        f"as O2)."
                    )

                non_o2_cols = [c for c in species_cols if c != o2_column]

                # Treat NaN as 0 so partial results still produce a calc.
                sum_all = df[species_cols].fillna(0.0).sum(axis=1)
                if non_o2_cols:
                    sum_non_o2 = df[non_o2_cols].fillna(0.0).sum(axis=1)
                else:
                    sum_non_o2 = pd.Series(0.0, index=df.index)

                df["SUM_v_mf"] = sum_all
                df["XO2_BYDIFF_v_mf"] = 1.0 - sum_non_o2

                # Sanity check: SUM_v_mf should be ≈1 on rows with vapor.
                has_vapor = sum_all > 0
                if has_vapor.any():
                    dev = (sum_all[has_vapor] - 1.0).abs()
                    worst = float(dev.max())
                    n_bad = int((dev > _SUM_VMF_TOL).sum())
                    if n_bad:
                        _warn(
                            f"{model} ({volcano}): {n_bad} row(s) have "
                            f"|SUM_v_mf - 1| > {_SUM_VMF_TOL} (max "
                            f"deviation {worst:.3g}). Vapor mole "
                            f"fractions do not close to 1 — O2 by "
                            f"difference may be unreliable."
                        )

        # ---- Simplify ----
        if simplify:
            other_cols = [
                "P_bars", "H2OT_m_wtpc", "CO2T_m_ppmw", "ST_m_ppmw",
                "Fe3Fet_m", "S6St_m", "logfO2", "dFMQ", "vapor_wt",
                "CS_v_mf", "SUM_v_mf", "XO2_BYDIFF_v_mf",
            ]
            for data in datasets:
                volcano = data["Name"]
                for model in model_names:
                    if model not in data or not isinstance(data[model], pd.DataFrame):
                        continue
                    df = data[model]
                    species_cols, _ = _resolve_vapor_species(df, vapor_species)
                    desired = [*species_cols, *other_cols]
                    present = [c for c in desired if c in df.columns]
                    absent = [c for c in desired if c not in df.columns]
                    if absent:
                        _warn(
                            f"{model} ({volcano}): simplify dropping absent "
                            f"columns: {absent}."
                        )
                    data[model] = df[present]

            if save_simplified:
                for data in datasets:
                    vname = data["Name"].lower()
                    for model in model_names:
                        if model not in data or not isinstance(data[model], pd.DataFrame):
                            continue
                        subdir = (subdirectory_name
                                  if model in models_w_special_subdirectory else "")
                        save_dir = os.path.join(
                            topdirectory_name, model + subdir, "simplified")
                        os.makedirs(save_dir, exist_ok=True)
                        data[model].to_csv(
                            os.path.join(save_dir, f"{vname}.csv"), index=False)

    return data_morb, data_kil, data_fuego, data_fogo


# ------------------------------------------------------------------
# Convenience wrapper
# ------------------------------------------------------------------

def load_results(
    data_dir: str,
    model_names: Optional[list[str]] = None,
    O2_mass_bal: bool = True,
    vapor_species: "str | list[str]" = "*_v_mf",
    o2_column: str = "O2_v_mf",
) -> tuple[dict, dict, dict, dict]:
    """Load degassing results written by :func:`~volcatenate.core.run_comparison`.

    This is a thin convenience wrapper around :func:`loadData` that
    points at the right directory and fills in model names automatically.

    Parameters
    ----------
    data_dir : str
        Degassing CSVs are expected at ``data_dir/MODEL/sample.csv``.
    model_names : list[str], optional
        Model names to load.  If *None*, uses all registered backends.
    O2_mass_bal : bool
        Compute O\\ :sub:`2` by difference in the vapor phase.
    vapor_species : str or list[str]
        Glob pattern or explicit list of vapor species columns used for
        the O\\ :sub:`2` mass balance.  See :func:`loadData` for details.
    o2_column : str
        Name of the O\\ :sub:`2` mole-fraction column.  See
        :func:`loadData` for details.

    Returns
    -------
    tuple[dict, dict, dict, dict]
        ``(data_morb, data_kil, data_fuego, data_fogo)`` — same
        format as :func:`loadData`.

    Example
    -------
    ::

        import volcatenate

        results = volcatenate.run_comparison(
            degassing_compositions="compositions.csv",
            models=["EVo", "VolFe", "MAGEC"],
        )

        # Later, or in a separate cell / script:
        data_morb, data_kil, data_fuego, data_fogo = volcatenate.load_results(
            "volcatenate_output", ["EVo", "VolFe", "MAGEC"],
        )
    """
    if model_names is None:
        from volcatenate.backends import list_backends
        model_names = list_backends()

    return loadData(
        model_names,
        topdirectory_name=data_dir,
        O2_mass_bal=O2_mass_bal,
        vapor_species=vapor_species,
        o2_column=o2_column,
    )
