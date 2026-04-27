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
from volcatenate import columns as col
from volcatenate.composition import MeltComposition, read_compositions, composition_from_dict
from volcatenate.config import RunConfig
from volcatenate.convert import compute_cs_v_mf, normalize_volatiles, ensure_standard_columns
from volcatenate.log import logger, setup_logging
from volcatenate.progress import VolcProgress
from volcatenate.result import SaturationResult


def _validate_override_sample_names(config, sample_names):
    """Raise ValueError if any backend overrides reference a sample
    name not in ``sample_names``.
    """
    known = set(sample_names)
    bad = []
    for backend_name in ("evo", "magec"):
        backend_cfg = getattr(config, backend_name)
        for sample in backend_cfg.overrides.keys():
            if sample not in known:
                bad.append((backend_name, sample))
    if bad:
        msg = "; ".join(
            f"{b}.overrides references unknown sample '{s}'"
            for b, s in bad
        )
        raise ValueError(
            f"{msg}. Known samples: {sorted(known)}"
        )


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
) -> SaturationResult:
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
    SaturationResult
        Result object with two views:

        * ``.pressure`` — flat DataFrame with columns ``Sample``,
          ``Reservoir``, and ``<Model>_SatP_bars`` for each model
          (backward-compatible with the old return type).
        * ``.equilibrium_state`` — ``dict[str, pd.DataFrame]`` keyed by
          model name, each containing one row per sample with the full
          equilibrium state at saturation (standard column names from
          :mod:`volcatenate.columns`).
    """
    if config is None:
        config = RunConfig()

    setup_logging(config.verbose, config.log_file)
    os.makedirs(config.output_dir or ".", exist_ok=True)

    comps = _resolve_compositions(compositions)
    model_names = _resolve_models(models)

    # Save reproducible bundle if requested (only when called directly,
    # not when called from run_comparison which saves its own bundle)
    if config.save_bundle and _progress is None:
        from volcatenate.reproducible import create_bundle, save_bundle
        bundle = create_bundle(
            run_type="saturation_pressure",
            compositions=comps,
            models=model_names,
            config=config,
        )
        save_bundle(bundle, config.save_bundle)

    total_iters = len(model_names) * len(comps)
    _progress, owns_progress = _init_progress(
        config, _progress, total_iters,
        "\U0001f30b Saturation pressures",
    )

    # Per-model detail storage
    detail_data: dict[str, list[dict]] = {}

    try:
        for model_name in model_names:
            try:
                backend = get_backend(model_name)
            except KeyError:
                _progress.add_warning(f"Unknown model: {model_name}")
                _progress.advance(len(comps))
                continue

            if not backend.is_available():
                _progress.add_warning(f"{model_name}: skipped (not available)")
                detail_data[model_name] = [
                    {"Sample": c.sample, "Reservoir": c.reservoir}
                    for c in comps
                ]
                _progress.advance(len(comps))
                continue

            _progress.update_model(model_name)
            logger.info("  Running %s...", model_name)
            model_rows: list[dict] = []

            # Use batch processing for backends that support it (e.g. MAGEC
            # avoids repeated MATLAB startup); otherwise loop per sample.
            if getattr(backend, "supports_batch_satp", False):
                try:
                    states = backend.calculate_saturation_pressure_batch(
                        comps, config,
                    )
                except Exception as exc:
                    _progress.add_warning(
                        f"{model_name} batch satP failed: {exc}"
                    )
                    states = [None] * len(comps)
                # Advance progress for all samples at once
                _progress.advance(len(comps))
            else:
                states = []
                for comp in comps:
                    try:
                        state = backend.calculate_saturation_pressure(
                            comp, config,
                        )
                    except Exception as exc:
                        _progress.add_warning(
                            f"{model_name} satP failed for {comp.sample}: {exc}"
                        )
                        state = None
                    states.append(state)
                    _progress.advance()

            # Process results (unified for both paths)
            for comp, state in zip(comps, states):
                row: dict = {"Sample": comp.sample, "Reservoir": comp.reservoir}
                if state is not None:
                    state_dict = state.to_dict()
                    state_dict.pop("Sample", None)
                    state_dict.pop("Reservoir", None)
                    row.update(state_dict)
                    p = state.get(col.P_BARS, np.nan)
                    logger.info("    %s: %.1f bar", comp.sample, p)
                else:
                    logger.info("    %s: failed (None)", comp.sample)
                model_rows.append(row)

            detail_data[model_name] = model_rows
    finally:
        if owns_progress:
            _progress.__exit__(None, None, None)

    # Build per-model DataFrames
    equilibrium_state = {
        name: pd.DataFrame(rows) for name, rows in detail_data.items()
    }

    return SaturationResult(
        equilibrium_state=equilibrium_state,
        samples=[c.sample for c in comps],
        reservoirs=[c.reservoir for c in comps],
    )


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
    os.makedirs(config.output_dir or ".", exist_ok=True)

    comps = _resolve_compositions(composition)
    if len(comps) > 1:
        warnings.warn(
            "calculate_degassing expects a single composition; "
            f"using the first of {len(comps)} provided."
        )
    comp = comps[0]

    model_names = _resolve_models(models)

    # Save reproducible bundle if requested (only when called directly)
    if config.save_bundle and _progress is None:
        from volcatenate.reproducible import create_bundle, save_bundle
        bundle = create_bundle(
            run_type="degassing",
            compositions=[comp],
            models=model_names,
            config=config,
        )
        save_bundle(bundle, config.save_bundle)

    results: dict[str, pd.DataFrame] = {}

    _progress, owns_progress = _init_progress(
        config, _progress, len(model_names),
        f"\U0001f30b Degassing \u2022 {comp.sample}",
    )

    try:
        for model_name in model_names:
            try:
                backend = get_backend(model_name)
            except KeyError:
                _progress.add_warning(f"Unknown model: {model_name}")
                _progress.advance()
                continue

            if not backend.is_available():
                _progress.add_warning(f"{model_name}: skipped (not available)")
                _progress.advance()
                continue

            _progress.update_model(model_name)
            logger.info("  Running %s...", model_name)
            try:
                df = backend.calculate_degassing(comp, config)
                results[model_name] = df
                logger.info("    %s: OK (%d steps)", model_name, len(df))
            except Exception as exc:
                _progress.add_warning(f"{model_name} degassing failed: {exc}")
            _progress.advance()
    finally:
        if owns_progress:
            _progress.__exit__(None, None, None)

    return results


# ------------------------------------------------------------------
# Export Helpers
# ------------------------------------------------------------------

def export_saturation_pressure(
    df: Union[SaturationResult, pd.DataFrame],
    path: str = "saturation_pressures.csv",
) -> str:
    """Save saturation-pressure results to CSV.

    Parameters
    ----------
    df : SaturationResult or pd.DataFrame
        Output from :func:`calculate_saturation_pressure`.
    path : str
        Output file path for the pressure-summary CSV.  If *df* is a
        ``SaturationResult``, per-model equilibrium-state CSVs are also
        written to a ``_details/`` subdirectory alongside the summary.

    Returns
    -------
    str
        The path that was written to.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    if isinstance(df, SaturationResult):
        # Write backward-compatible summary CSV
        df.pressure.to_csv(path, index=False)

        # Write per-model equilibrium-state CSVs
        detail_dir = path.replace(".csv", "_details")
        os.makedirs(detail_dir, exist_ok=True)
        for model, detail_df in df.equilibrium_state.items():
            detail_path = os.path.join(detail_dir, f"{model}_satp.csv")
            detail_df.to_csv(detail_path, index=False)
        logger.info(
            "  Saturation pressures saved to %s (details in %s/)",
            path, detail_dir,
        )
    else:
        # Plain DataFrame (backward compat)
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
    os.makedirs(output_dir or ".", exist_ok=True)
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
        degassing_output_dir = config.output_dir or "."

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

    all_sample_names = [c.sample for c in satp_comps] + [c.sample for c in degas_comps]
    _validate_override_sample_names(config, all_sample_names)

    # Save reproducible bundle if requested
    if config.save_bundle:
        from volcatenate.reproducible import create_bundle, save_bundle
        # Use the union of all compositions for the bundle
        all_comps = satp_comps if satp_comps else degas_comps
        bundle = create_bundle(
            run_type="comparison",
            compositions=all_comps,
            models=model_names,
            config=config,
            satp_output=satp_output,
            degassing_output_dir=degassing_output_dir,
        )
        save_bundle(bundle, config.save_bundle)

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
    if not config.keep_raw_output:
        raw_dir = os.path.join(config.output_dir, config.raw_output_dir)
        if os.path.isdir(raw_dir) and not os.listdir(raw_dir):
            shutil.rmtree(raw_dir, ignore_errors=True)

    logger.info("=== Comparison complete ===")
    return output
