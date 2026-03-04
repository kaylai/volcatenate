"""Orchestrator — dispatches composition(s) to model backends.

This is the main engine behind the public API functions:
  - ``calculate_saturation_pressure()``
  - ``calculate_degassing()``
  - ``export_saturation_pressure()``
  - ``export_degassing_paths()``
  - ``run_comparison()`` (end-to-end workflow)
"""

from __future__ import annotations

import os
import shutil
import warnings
from typing import Optional, Union

import numpy as np
import pandas as pd

from volcatenate.backends import get_backend, list_backends
from volcatenate.composition import MeltComposition, read_compositions, composition_from_dict
from volcatenate.config import RunConfig
from volcatenate.convert import compute_cs_v_mf, normalize_volatiles, ensure_standard_columns


def _resolve_models(models: Optional[list[str]]) -> list[str]:
    """Resolve model list, expanding 'all' and validating names."""
    if models is None or models == ["all"] or models == "all":
        return list_backends()
    if isinstance(models, str):
        models = [m.strip() for m in models.split(",")]
    return models


def _resolve_compositions(
    source: Union[str, dict, list, MeltComposition],
) -> list[MeltComposition]:
    """Normalise the input to a list of MeltComposition objects.

    Dicts are routed through the same alias table as the CSV reader,
    so ``"Sample"`` and ``"sample"`` both work, ``"FeO"`` maps to
    speciated iron while ``"FeOT"`` maps to total iron, etc.
    """
    if isinstance(source, str):
        # CSV file path
        return read_compositions(source)
    if isinstance(source, MeltComposition):
        return [source]
    if isinstance(source, dict):
        # Single composition as a dict (flexible keys)
        return [composition_from_dict(source)]
    if isinstance(source, list):
        if all(isinstance(c, MeltComposition) for c in source):
            return source
        # List of dicts (flexible keys)
        return [composition_from_dict(c) for c in source]
    raise TypeError(f"Cannot interpret {type(source)} as composition(s)")


# ------------------------------------------------------------------
# Saturation Pressure
# ------------------------------------------------------------------

def calculate_saturation_pressure(
    compositions: Union[str, dict, list, MeltComposition],
    models: Optional[list[str]] = None,
    config: Optional[RunConfig] = None,
) -> pd.DataFrame:
    """Calculate volatile saturation pressure for a batch of compositions.

    Parameters
    ----------
    compositions : str | dict | list | MeltComposition
        * Path to a CSV file of melt compositions.
        * A single ``MeltComposition`` object.
        * A dict with composition fields.
        * A list of any of the above.
    models : list[str] or None
        Which model backends to use.  Pass ``["all"]`` or *None* to
        use every available model.  E.g. ``["EVo", "VolFe"]``.
    config : RunConfig or None
        Configuration.  Defaults to ``RunConfig()`` (paper defaults).

    Returns
    -------
    pd.DataFrame
        One row per sample, columns ``Sample``, ``Reservoir``,
        plus ``<Model>_SatP_bars`` for each requested model.
    """
    if config is None:
        config = RunConfig()

    os.makedirs(config.output_dir, exist_ok=True)

    comps = _resolve_compositions(compositions)
    model_names = _resolve_models(models)

    # Build results table
    rows = []
    for comp in comps:
        row = {"Sample": comp.sample, "Reservoir": comp.reservoir}
        rows.append(row)

    for model_name in model_names:
        try:
            backend = get_backend(model_name)
        except KeyError:
            warnings.warn(f"Unknown model: {model_name}")
            continue

        if not backend.is_available():
            print(f"  {model_name}: SKIPPED (not available)")
            for row in rows:
                row[f"{model_name}_SatP_bars"] = np.nan
            continue

        print(f"  Running {model_name}...")
        for i, comp in enumerate(comps):
            try:
                p = backend.calculate_saturation_pressure(comp, config)
                rows[i][f"{model_name}_SatP_bars"] = p
                print(f"    {comp.sample}: {p:.1f} bar")
            except Exception as exc:
                rows[i][f"{model_name}_SatP_bars"] = np.nan
                print(f"    {comp.sample}: FAILED — {exc}")

    return pd.DataFrame(rows)


# ------------------------------------------------------------------
# Degassing Path
# ------------------------------------------------------------------

def calculate_degassing(
    composition: Union[str, dict, MeltComposition],
    models: Optional[list[str]] = None,
    config: Optional[RunConfig] = None,
) -> dict[str, pd.DataFrame]:
    """Run degassing path calculations for a single composition.

    Parameters
    ----------
    composition : str | dict | MeltComposition
        A single melt composition (CSV path reads the first row).
    models : list[str] or None
        Which model backends to use.
    config : RunConfig or None
        Configuration.

    Returns
    -------
    dict[str, pd.DataFrame]
        Keys are model names, values are standardized DataFrames
        with degassing path data (high P → low P).
    """
    if config is None:
        config = RunConfig()

    os.makedirs(config.output_dir, exist_ok=True)

    comps = _resolve_compositions(composition)
    if len(comps) > 1:
        warnings.warn(
            "calculate_degassing expects a single composition; "
            f"using the first of {len(comps)} provided."
        )
    comp = comps[0]

    model_names = _resolve_models(models)
    results: dict[str, pd.DataFrame] = {}

    for model_name in model_names:
        try:
            backend = get_backend(model_name)
        except KeyError:
            warnings.warn(f"Unknown model: {model_name}")
            continue

        if not backend.is_available():
            print(f"  {model_name}: SKIPPED (not available)")
            continue

        print(f"  Running {model_name}...")
        try:
            df = backend.calculate_degassing(comp, config)
            results[model_name] = df
            print(f"    {model_name}: OK ({len(df)} steps)")
        except Exception as exc:
            print(f"    {model_name}: FAILED — {exc}")

    return results


# ------------------------------------------------------------------
# Export Helpers
# ------------------------------------------------------------------

def export_saturation_pressure(
    df: pd.DataFrame,
    path: str = "saturation_pressures.csv",
) -> str:
    """Save a saturation-pressure DataFrame to CSV.

    Parameters
    ----------
    df : pd.DataFrame
        Output from :func:`calculate_saturation_pressure`.
    path : str
        Output file path.

    Returns
    -------
    str
        The path that was written to.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    df.to_csv(path, index=False)
    print(f"  Saturation pressures saved to {path}")
    return path


def export_degassing_paths(
    results: dict[str, pd.DataFrame],
    output_dir: str = "degassing_paths",
    sample_name: Optional[str] = None,
) -> list[str]:
    """Save degassing-path DataFrames to individual CSVs.

    Parameters
    ----------
    results : dict[str, pd.DataFrame]
        Output from :func:`calculate_degassing`.  Keys are model names.
    output_dir : str
        Directory for the CSVs.  A subfolder per model is created.
    sample_name : str, optional
        Name used in the CSV filename (e.g. ``"kilauea"``).
        If *None*, a generic name is used.

    Returns
    -------
    list[str]
        Paths of the CSV files written.
    """
    os.makedirs(output_dir, exist_ok=True)
    name = sample_name or "degassing"
    written = []
    for model, df in results.items():
        model_dir = os.path.join(output_dir, model)
        os.makedirs(model_dir, exist_ok=True)
        csv_path = os.path.join(model_dir, f"{name}.csv")
        df.to_csv(csv_path, index=False)
        written.append(csv_path)
        print(f"  {model}: saved to {csv_path}")
    return written


# ------------------------------------------------------------------
# End-to-end workflow
# ------------------------------------------------------------------

def run_comparison(
    satp_compositions: Optional[Union[str, dict, list, MeltComposition]] = None,
    degassing_compositions: Optional[Union[str, dict, list, MeltComposition]] = None,
    models: Optional[list[str]] = None,
    config: Optional[RunConfig] = None,
    satp_output: str = "saturation_pressures.csv",
    degassing_output_dir: str = "degassing_paths",
) -> dict:
    """Run a complete model comparison: satP + degassing + CSV export.

    This is a convenience wrapper that chains the individual steps.
    It does *not* generate plots — call the :mod:`volcatenate.plotting`
    functions separately with the returned data.

    Parameters
    ----------
    satp_compositions : str | dict | list | MeltComposition, optional
        Compositions for saturation-pressure calculation.  If *None*,
        the satP step is skipped.
    degassing_compositions : str | dict | list | MeltComposition, optional
        Composition(s) for degassing-path calculations.  Accepts a
        single composition or a list; if a list, each is run
        independently.  If *None*, degassing is skipped.
    models : list[str] or None
        Model names (``None`` or ``["all"]`` for all available).
    config : RunConfig or None
        Configuration (defaults to paper settings).
    satp_output : str
        CSV path for saturation-pressure export.
    degassing_output_dir : str
        Directory for degassing-path CSVs.

    Returns
    -------
    dict
        ``{"satp_df": DataFrame or None,
           "degassing": {sample_name: {model: DataFrame}} or None}``

    Example
    -------
    ::

        import volcatenate

        results = volcatenate.run_comparison(
            satp_compositions="melt_inclusions.csv",
            degassing_compositions=[kilauea_dict, morb_dict],
            models=["EVo", "VolFe", "MAGEC"],
            satp_output="results/satp.csv",
            degassing_output_dir="results/degassing",
        )

        # results["satp_df"] is the saturation pressure DataFrame
        # results["degassing"]["Kilauea"]["EVo"] is a degassing DataFrame
    """
    if config is None:
        config = RunConfig()

    output = {"satp_df": None, "degassing": None}

    # --- Saturation pressure ---
    if satp_compositions is not None:
        print("\n=== Calculating saturation pressures ===")
        satp_df = calculate_saturation_pressure(
            satp_compositions, models=models, config=config,
        )
        export_saturation_pressure(satp_df, satp_output)
        output["satp_df"] = satp_df

    # --- Degassing paths ---
    if degassing_compositions is not None:
        print("\n=== Calculating degassing paths ===")
        # Normalise to list
        comps = _resolve_compositions(degassing_compositions)
        all_degassing = {}
        for comp in comps:
            print(f"\n--- {comp.sample} ---")
            results = calculate_degassing(comp, models=models, config=config)
            export_degassing_paths(
                results,
                output_dir=degassing_output_dir,
                sample_name=comp.sample.lower(),
            )
            all_degassing[comp.sample] = results
        output["degassing"] = all_degassing

    # --- Cleanup empty output directory ---
    if not config.keep_intermediates:
        out_dir = config.output_dir
        if os.path.isdir(out_dir) and not os.listdir(out_dir):
            shutil.rmtree(out_dir, ignore_errors=True)

    print("\n=== Comparison complete ===")
    return output
