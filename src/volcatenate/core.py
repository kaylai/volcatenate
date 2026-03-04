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
from volcatenate.log import logger, setup_logging
from volcatenate.progress import VolcProgress


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


def _init_progress(config, _progress, total, description):
    """Create or reuse a VolcProgress bar and configure logging.

    Returns ``(progress, owns_progress)`` where *owns_progress* is
    True when this call created the bar (and must close it later).
    """
    owns = _progress is None
    if owns:
        _progress = VolcProgress(
            total=total,
            description=description,
            enabled=config.show_progress,
        )
        _progress.__enter__()
    if config.verbose and _progress.console:
        setup_logging(config.verbose, config.log_file, console=_progress.console)
    return _progress, owns


# ------------------------------------------------------------------
# Saturation Pressure
# ------------------------------------------------------------------

def calculate_saturation_pressure(
    compositions: Union[str, dict, list, MeltComposition],
    models: Optional[list[str]] = None,
    config: Optional[RunConfig] = None,
    _progress: Optional[VolcProgress] = None,
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

    setup_logging(config.verbose, config.log_file)
    os.makedirs(config.output_dir, exist_ok=True)

    comps = _resolve_compositions(compositions)
    model_names = _resolve_models(models)

    total_iters = len(model_names) * len(comps)
    _progress, owns_progress = _init_progress(
        config, _progress, total_iters,
        "\U0001f30b Saturation pressures",
    )

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
            _progress.advance(len(comps))
            continue

        if not backend.is_available():
            logger.info("  %s: SKIPPED (not available)", model_name)
            for row in rows:
                row[f"{model_name}_SatP_bars"] = np.nan
            _progress.advance(len(comps))
            continue

        _progress.update_model(model_name)
        logger.info("  Running %s...", model_name)
        for i, comp in enumerate(comps):
            try:
                p = backend.calculate_saturation_pressure(comp, config)
                rows[i][f"{model_name}_SatP_bars"] = p
                logger.info("    %s: %.1f bar", comp.sample, p)
            except Exception as exc:
                rows[i][f"{model_name}_SatP_bars"] = np.nan
                logger.warning("    %s: FAILED — %s", comp.sample, exc)
            _progress.advance()

    if owns_progress:
        _progress.__exit__(None, None, None)

    return pd.DataFrame(rows)


# ------------------------------------------------------------------
# Degassing Path
# ------------------------------------------------------------------

def calculate_degassing(
    composition: Union[str, dict, MeltComposition],
    models: Optional[list[str]] = None,
    config: Optional[RunConfig] = None,
    _progress: Optional[VolcProgress] = None,
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

    setup_logging(config.verbose, config.log_file)
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

    _progress, owns_progress = _init_progress(
        config, _progress, len(model_names),
        f"\U0001f30b Degassing \u2022 {comp.sample}",
    )

    for model_name in model_names:
        try:
            backend = get_backend(model_name)
        except KeyError:
            warnings.warn(f"Unknown model: {model_name}")
            _progress.advance()
            continue

        if not backend.is_available():
            logger.info("  %s: SKIPPED (not available)", model_name)
            _progress.advance()
            continue

        _progress.update_model(model_name)
        logger.info("  Running %s...", model_name)
        try:
            df = backend.calculate_degassing(comp, config)
            results[model_name] = df
            logger.info("    %s: OK (%d steps)", model_name, len(df))
        except Exception as exc:
            logger.warning("    %s: FAILED — %s", model_name, exc)
        _progress.advance()

    if owns_progress:
        _progress.__exit__(None, None, None)

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
    logger.info("  Saturation pressures saved to %s", path)
    return path


def export_degassing_paths(
    results: dict[str, pd.DataFrame],
    output_dir: str = "degassing_paths",
    sample_name: Optional[str] = None,
) -> list[str]:
    """Save degassing-path DataFrames to individual CSVs.

    The directory layout matches what :func:`~volcatenate.compat.loadData`
    expects, so you can read the files back with::

        loadData(model_names, topdirectory_name=output_dir)

    Parameters
    ----------
    results : dict[str, pd.DataFrame]
        Output from :func:`calculate_degassing`.  Keys are model names.
    output_dir : str
        Top-level directory.  A subfolder per model is created
        (``output_dir/MODEL/sample.csv``).  VESIcal models get the
        extra nesting that ``loadData`` expects
        (``output_dir/VESIcal/MODEL/sample.csv``).
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
        # Match loadData's VESIcal nesting: topdirectory/VESIcal/MODEL/
        if "VESIcal" in model:
            model_dir = os.path.join(output_dir, "VESIcal", model)
        else:
            model_dir = os.path.join(output_dir, model)
        os.makedirs(model_dir, exist_ok=True)
        csv_path = os.path.join(model_dir, f"{name}.csv")
        df.to_csv(csv_path, index=False)
        written.append(csv_path)
        logger.info("  %s: saved to %s", model, csv_path)
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
    degassing_output_dir: Optional[str] = None,
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
    degassing_output_dir : str, optional
        Directory for degassing-path CSVs.  Defaults to
        ``config.output_dir`` so that files land at
        ``output_dir/MODEL/sample.csv`` — the layout that
        :func:`~volcatenate.compat.loadData` expects.

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
            satp_output="saturation_pressures.csv",
        )

        # results["satp_df"] is the saturation pressure DataFrame
        # results["degassing"]["Kilauea"]["EVo"] is a degassing DataFrame

        # Load the saved CSVs back for plotting:
        data = volcatenate.load_results("volcatenate_output", model_names)
    """
    if config is None:
        config = RunConfig()

    if degassing_output_dir is None:
        degassing_output_dir = config.output_dir

    setup_logging(config.verbose, config.log_file)
    output = {"satp_df": None, "degassing": None}

    # Pre-compute total work for the unified progress bar
    model_names = _resolve_models(models)
    n_models = len(model_names)

    satp_comps = (
        _resolve_compositions(satp_compositions)
        if satp_compositions is not None else []
    )
    degas_comps = (
        _resolve_compositions(degassing_compositions)
        if degassing_compositions is not None else []
    )
    total_work = n_models * len(satp_comps) + n_models * len(degas_comps)

    with VolcProgress(
        total=total_work,
        description="\U0001f30b Model comparison",
        enabled=config.show_progress,
    ) as vp:
        if config.verbose and vp.console:
            setup_logging(config.verbose, config.log_file, console=vp.console)

        # --- Saturation pressure ---
        if satp_compositions is not None:
            vp.update_description("\U0001f30b Saturation pressures")
            logger.info("=== Calculating saturation pressures ===")
            satp_df = calculate_saturation_pressure(
                satp_compositions, models=models, config=config,
                _progress=vp,
            )
            export_saturation_pressure(satp_df, satp_output)
            output["satp_df"] = satp_df

        # --- Degassing paths ---
        if degassing_compositions is not None:
            logger.info("=== Calculating degassing paths ===")
            comps = _resolve_compositions(degassing_compositions)
            all_degassing = {}
            for comp in comps:
                vp.update_description(
                    f"\U0001f30b Degassing \u2022 [yellow]{comp.sample}[/yellow]"
                )
                logger.info("--- %s ---", comp.sample)
                results = calculate_degassing(
                    comp, models=models, config=config,
                    _progress=vp,
                )
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

    logger.info("=== Comparison complete ===")
    return output
