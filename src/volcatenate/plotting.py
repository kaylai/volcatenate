"""Plotting utilities for volcanic degassing model comparison.

This module consolidates all reusable plotting functions:

* **Plotly-based** degassing path subplots (``plot_results``)
* **Matplotlib-based** deviation envelopes (``plot_deviation_envelopes``,
  ``plot_all_melt_volatiles``, ``plot_all_redox_variables``)
* Style helpers (model colors, figure saving, legend management)
* Grid layout utilities

Typical usage::

    import volcatenate.plotting as vp
    import volcatenate.compat as mh

    data_morb, data_kil, data_fuego, data_fogo = mh.loadData(...)

    # Plotly degassing path figure
    colors = vp.get_line_properties()
    fig = vp.plot_results(model_list, basalt_list, ["H2Om", "CO2m", "Sm"],
                          colors, p_norm=True)
    vp.save_plotly_fig(fig, "my_figure", extension="png", scale=4)

    # Matplotlib deviation envelopes
    systems = {"MORB": data_morb, "Kilauea": data_kil, ...}
    env_data, fig, ax = vp.plot_deviation_envelopes(systems, param="ST_m_ppmw")
"""

from __future__ import annotations

import math
import os
import warnings
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

from volcatenate.log import logger

# ---------------------------------------------------------------------------
# Grid layout utilities (ported from plot_grid.py)
# ---------------------------------------------------------------------------


def optimal_grid_aspect(n_objects: int) -> tuple[int, int]:
    """Return *(rows, cols)* for an approximately-square grid layout."""
    best_r, best_c = None, None
    best_error = float("inf")
    best_area = float("inf")

    for c in range(1, n_objects + 1):
        r = math.ceil(n_objects / c)
        aspect_error = abs(r / c - 1)
        area = r * c
        if (
            aspect_error < best_error
            or (aspect_error == best_error and area < best_area)
            or (aspect_error == best_error and area == best_area and c > best_c)
        ):
            best_r, best_c = r, c
            best_error = aspect_error
            best_area = area

    return best_r, best_c


def get_grid_position(object_index: int, total_objects: int) -> tuple[int, int]:
    """Return 1-based ``(row, col)`` for a given object index (0-based)."""
    _, c = optimal_grid_aspect(total_objects)
    row = object_index // c + 1
    col = object_index % c + 1
    return row, col


def get_column_heights(n_objects: int) -> list[int]:
    """Return per-column row counts for an optimally-square grid layout."""
    r, c = optimal_grid_aspect(n_objects)
    full_rows = n_objects // c
    remainder = n_objects % c
    return [full_rows + 1 if i < remainder else full_rows for i in range(c)]


# ---------------------------------------------------------------------------
# Model colour / style definitions (ported from plot_handling.py)
# ---------------------------------------------------------------------------

# Hex colours for matplotlib / general use
MODEL_COLORS_HEX = {
    "DCompress": "#01B0F0",
    "EVo":       "#E46C0A",
    "MAGEC":     "#DD94BB",
    "SulfurX":   "#009E73",
    "VolFe":     "#FFC00D",
    "VESIcal":                      "#000000",
    "VESIcal_MS":                   "#000000",
    "VESIcal_Dixon":                "#D9D9D9",
    "VESIcal_IaconoMarziano":      "#545454",
    "VESIcal_Iacono":              "#545454",
    "VESIcal_Liu":                  "#532E5C",
    "VESIcal_ShishkinaIdealMixing": "#5E6480",
}

# Marker styles for matplotlib scatter plots
# Format: (legend_label, marker, size, facecolor, edgecolor, linewidth)
MODEL_MARKER_STYLE = {
    "DCompress":      ("D-Compress (IM)", "s",  150, "#01B0F0", "k", 0.5),
    "EVo":            ("EVo (D-C)",       "o",  150, "#E46C0A", "k", 0.5),
    "MAGEC":          ("MAGEC (IM)",      "s",  150, "#DD94BB", "k", 0.5),
    "SulfurX":        ("Sulfur_X (IM)",   "s",  150, "#009E73", "k", 0.5),
    "VolFe":          ("VolFe (Allison)", "^",  150, "#FFC00D", "k", 0.5),
    "VESIcal_Iacono": ("VESIcal (IM)",   "s",  120, "none",    "k", 1.0),
    "VESIcal_Dixon":  ("VESIcal (VC)",   "x",  100, "k",       "k", 1.5),
    "VESIcal_MS":     ("VESIcal (MS)",   "*",  140, "k",       "k", 0.5),
}


def get_line_properties() -> dict[str, str]:
    """Return a dict of model names to Plotly ``rgb(...)`` colour strings."""
    return {
        "DCompress":                    "rgb(1, 176, 240)",
        "EVo":                          "rgb(228, 108, 10)",
        "MAGEC":                        "rgb(221, 148, 187)",
        "SulfurX":                      "rgb(0, 158, 115)",
        "VolFe":                        "rgb(255, 192, 13)",
        "VESIcal":                      "rgb(0, 0, 0)",
        "VESIcal_MS":                   "rgb(0, 0, 0)",
        "VESIcal_Dixon":                "rgb(217, 217, 217)",
        "VESIcal_IaconoMarziano":       "rgb(84, 84, 84)",
        "VESIcal_Iacono":               "rgb(84, 84, 84)",
        "VESIcal_Liu":                  "rgb(83, 46, 92)",
        "VESIcal_ShishkinaIdealMixing": "rgb(94, 100, 128)",
    }


# ---------------------------------------------------------------------------
# Plotly figure utilities (ported from plot_handling.py)
# ---------------------------------------------------------------------------


def save_plotly_fig(
    fig,
    base_filename: str,
    directory: str = ".",
    extension: str = "png",
    overwrite_if_exists: bool = False,
    scale: int = 1,
) -> str:
    """Save a Plotly figure with date-stamped naming to avoid overwrites.

    Parameters
    ----------
    fig : plotly.graph_objs.Figure
    base_filename : str
    directory : str
    extension : str
    overwrite_if_exists : bool
    scale : int

    Returns
    -------
    str
        Path to the saved file.
    """
    os.makedirs(directory, exist_ok=True)

    if base_filename.endswith(f".{extension}"):
        base_filename = base_filename[: -len(f".{extension}")]

    filepath = os.path.join(directory, f"{base_filename}.{extension}")

    if overwrite_if_exists:
        fig.write_image(filepath, scale=scale)
        logger.info("Saved %s", filepath)
        return filepath

    if not os.path.exists(filepath):
        fig.write_image(filepath, scale=scale)
        logger.info("Saved %s", filepath)
        return filepath

    date_str = datetime.now().strftime("%m%d%y")
    dated_filepath = os.path.join(directory, f"{base_filename}_{date_str}.{extension}")
    if not os.path.exists(dated_filepath):
        fig.write_image(dated_filepath, scale=scale)
        logger.info("Saved %s", dated_filepath)
        return dated_filepath

    counter = 1
    while True:
        counted_filepath = os.path.join(
            directory, f"{base_filename}_{date_str}_{counter}.{extension}"
        )
        if not os.path.exists(counted_filepath):
            fig.write_image(counted_filepath, scale=scale)
            logger.info("Saved %s", counted_filepath)
            return counted_filepath
        counter += 1


def add_trace_to_subplot(fig, data, model, y_variable, l_c, l_w, l_d, row, col, p_norm):
    """Add a single model trace to a Plotly subplot.

    Parameters
    ----------
    fig : plotly Figure (from ``make_subplots``)
    data : pd.DataFrame with at least ``P_bars`` and the y-column
    model : str — model name (used as legend label)
    y_variable : str — friendly name (``H2Om``, ``CO2m``, ``Sm``, etc.)
    l_c, l_w, l_d : line colour, width, dash
    row, col : subplot position (1-based)
    p_norm : bool — if True, x-axis is P/Pi
    """
    import plotly.graph_objects as go

    if data is None or not isinstance(data, pd.DataFrame) or len(data) == 0:
        logger.warning("%s: empty DataFrame — skipping %s trace", model, y_variable)
        return
    if "P_bars" not in data.columns:
        logger.warning("%s: missing P_bars column — skipping %s trace", model, y_variable)
        return

    if p_norm:
        x_pressure = data["P_bars"] / data["P_bars"].iloc[0]
    else:
        x_pressure = data["P_bars"]

    y_map = {
        "H2Om":          "H2OT_m_wtpc",
        "CO2m":          "CO2T_m_ppmw",
        "Sm":            "ST_m_ppmw",
        "fO2_FMQ":       "dFMQ",
        "Fe_speciation":  "Fe3Fet_m",
        "S_speciation":   "S6St_m",
        "C_S_vapor":      "CS_v_mf",
        "Sm_norm":        "ST_m_ppmw_norm",
    }
    col_name = y_map.get(y_variable)
    if col_name is None:
        logger.warning("Unknown y_variable %r for %s — skipping trace", y_variable, model)
        return
    if col_name not in data.columns:
        logger.warning("%s: column %r missing — skipping %s trace", model, col_name, y_variable)
        return
    try:
        fig.add_trace(
            go.Scatter(
                mode="lines",
                y=data[col_name],
                x=x_pressure,
                name=model,
                line_color=l_c,
                line_width=l_w,
                line_dash=l_d,
                showlegend=True,
            ),
            row=row,
            col=col,
        )
    except Exception as exc:
        logger.warning("%s: failed to add %s trace — %s", model, y_variable, exc)


def plot_results(
    model_list: list[str],
    basalt_list: list[dict],
    y_variable_list: list[str],
    lc_list: dict[str, str],
    lw: int = 2,
    ld: str = "solid",
    p_norm: bool = True,
    save_fig: bool = False,
    **kwargs,
):
    """Plot degassing paths as a Plotly subplot grid.

    Parameters
    ----------
    model_list : list[str]
        Model names (keys in each basalt dict).
    basalt_list : list[dict]
        Each dict is ``{"Name": str, "ModelName": DataFrame, ...}``.
    y_variable_list : list[str]
        Variables to plot: ``H2Om``, ``CO2m``, ``Sm``, ``fO2_FMQ``,
        ``Fe_speciation``, ``S_speciation``, ``C_S_vapor``.
    lc_list : dict
        Model-name → Plotly ``rgb(...)`` colour string (from
        :func:`get_line_properties`).
    lw, ld : line width and dash style
    p_norm : bool
        If True x-axis is P/Pi, else pressure in bar.
    save_fig : bool
        If True, auto-save to ``outputs/figures/``.

    Returns
    -------
    plotly.graph_objs.Figure
    """
    from plotly.subplots import make_subplots

    scale = kwargs.get("scale", 1)

    x_axis_name = "P/P<sub>i</sub> (bar)" if p_norm else "Pressure (bar)"

    top_row_titles = [basalt["Name"] for basalt in basalt_list]
    subplot_titles = top_row_titles + [""] * (
        (len(y_variable_list) - 1) * len(basalt_list)
    )

    fig = make_subplots(
        rows=len(y_variable_list),
        cols=len(basalt_list),
        shared_yaxes=False,
        shared_xaxes=True,
        vertical_spacing=0.03,
        horizontal_spacing=0.05,
        subplot_titles=subplot_titles,
    )

    y_axis_labels = {
        "H2Om":          "H<sub>2</sub>O<sup>melt</sup> total (wt%)",
        "CO2m":          "CO<sub>2</sub><sup>melt</sup> total (ppm)",
        "Sm":            "S<sup>melt</sup> total (ppm)",
        "fO2_FMQ":       "log<sub>10</sub><i>f</i>\u2009O<sub>2</sub> (\u0394FMQ)",
        "Fe_speciation":  "Fe<sup>3+</sup>/Fe<sup>T</sup>",
        "S_speciation":   "S<sup>6+</sup>/S<sup>T</sup>",
        "C_S_vapor":      "C/S<sup>vapor</sup> (mol fraction)",
        "Sm_norm":        "S ppm norm",
    }

    for yv, y_variable in enumerate(y_variable_list, start=1):
        for b, basalt in enumerate(basalt_list, start=1):
            for model in model_list:
                if model not in basalt:
                    continue
                if model not in lc_list:
                    logger.warning("No color defined for %s — skipping trace", model)
                    continue
                add_trace_to_subplot(
                    fig, basalt[model], model, y_variable,
                    lc_list[model], lw, ld,
                    row=yv, col=b, p_norm=p_norm,
                )
                fig.update_yaxes(
                    title=y_axis_labels[y_variable], row=yv, col=1,
                )
                fig.update_xaxes(
                    title=x_axis_name,
                    row=len(y_variable_list),
                    col=b,
                    range=[0, None],
                )

    # allow fO2 y-axes to go below zero
    number_of_rows, number_of_cols = fig._get_subplot_rows_columns()

    if "fO2_FMQ" in y_variable_list:
        rownum = y_variable_list.index("fO2_FMQ") + 1
        for colnum in number_of_cols:
            fig.update_yaxes(range=[None, None], row=rownum, col=colnum)

    n_cols = len(basalt_list)
    n_rows = len(y_variable_list)
    fig_width = int(1000 * (n_cols / 4))
    fig_height = int(800 * (n_rows / 3))

    fig.update_layout(
        height=fig_height,
        width=fig_width,
        plot_bgcolor="rgb(255,255,255)",
        margin=dict(t=40, r=30, l=60, b=50),
    )
    fig.update_xaxes(
        showline=True, linewidth=1, linecolor="black", mirror=True,
        ticks="inside", ticklen=5, title_standoff=0, tickcolor="black",
        title_font=dict(size=15, family="Helvetica", color="black"),
        tickfont=dict(family="Helvetica", color="black", size=12),
    )
    fig.update_yaxes(
        showline=True, linewidth=1, linecolor="black", mirror=True,
        ticks="inside", ticklen=5, title_standoff=0, tickcolor="black",
        title_font=dict(size=15, family="Helvetica", color="black"),
        tickfont=dict(family="Helvetica", color="black", size=12),
    )
    fig.update_layout(font_family="Helvetica", font_color="black")

    if save_fig:
        var_string = "_".join(y_variable_list)
        fig_filename = "P_norm_" + var_string
        fig_directory = "figures/P_norm_figs"
        save_plotly_fig(fig, fig_filename, directory=fig_directory, scale=scale)

    return fig


def update_axis_limits(fig, axis: str, rownum: int, colnum: int, range: list):
    """Update subplot axis limits.

    Parameters
    ----------
    fig : Plotly figure
    axis : ``'x'`` or ``'y'``
    rownum, colnum : 1-based subplot indices
    range : ``[min, max]`` — use ``None`` for auto
    """
    if axis == "x":
        return fig.update_xaxes(range=range, row=rownum, col=colnum)
    if axis == "y":
        return fig.update_yaxes(range=range, row=rownum, col=colnum)


def unify_legend(fig, axis_ID: int = 1):
    """Show legend entries from only one subplot, hiding duplicates.

    Parameters
    ----------
    fig : Plotly figure (from ``make_subplots``)
    axis_ID : int
        Which axis pair to keep legends for (1 = first subplot).
    """
    if axis_ID == 1:
        axes_ID = ["x", "y"]
    else:
        axes_ID = [f"x{axis_ID}", f"y{axis_ID}"]

    for trace in fig.data:
        if not (trace.xaxis == axes_ID[0] and trace.yaxis == axes_ID[1]):
            trace.showlegend = False

    fig.update_layout(legend=dict(font=dict(size=10)))
    return fig


# ---------------------------------------------------------------------------
# Deviation envelopes (ported from plot_deviation_envelopes.py)
# ---------------------------------------------------------------------------

# Lazy-import matplotlib so the module can be imported without it
_plt = None
_interp1d = None


def _ensure_mpl():
    global _plt, _interp1d
    if _plt is None:
        import matplotlib.pyplot as plt
        from scipy.interpolate import interp1d

        _plt = plt
        _interp1d = interp1d


def _default_variable_names(param: str) -> str:
    """Return a formatted LaTeX label for a column name."""
    _labels = {
        "H2OT_m_wtpc": r"H$_2$O$^{melt}$ total",
        "CO2T_m_ppmw": r"CO$_2^{melt}$ total",
        "ST_m_ppmw":   r"S$^{melt}$ total",
        "dFMQ":        r"$\Delta$FMQ",
        "Fe3Fet_m":    r"Fe$^{3+}$/Fe$^{T}$",
        "S6St_m":      r"S$^{6+}$/S$^{T}$",
        "CS_v_mf":     r"C/S$^{vapor}$",
    }
    return _labels.get(param, param)


def _compute_deviation_envelope(
    data_dict: dict,
    param: str,
    x_col: str = "P_bars",
    n_points: int = 200,
    exclude_models: Optional[list[str]] = None,
) -> Optional[dict]:
    """Compute min/max percent deviation from ensemble mean across models.

    Returns *None* if no valid models are found.
    """
    _ensure_mpl()
    if exclude_models is None:
        exclude_models = []

    x_common = np.linspace(0, 1, n_points)
    interp_data = {}
    model_names = []

    for model_name, df in data_dict.items():
        if model_name in exclude_models:
            continue
        if not isinstance(df, pd.DataFrame):
            continue
        if x_col not in df.columns or param not in df.columns:
            continue

        sub = df[[x_col, param]].dropna()
        if sub.empty:
            continue

        sub = sub.sort_values(by=x_col, ascending=False).reset_index(drop=True)
        Pi = sub[x_col].iloc[0]
        sub["P_norm"] = sub[x_col] / Pi

        try:
            f = _interp1d(
                sub["P_norm"], sub[param],
                kind="linear", bounds_error=False, fill_value=np.nan,
            )
            interp_data[model_name] = f(x_common)
            model_names.append(model_name)
        except Exception as exc:
            logger.debug("Interpolation failed for %s: %s", model_name, exc)
            continue

    if not model_names:
        return None

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)

        model_array = np.column_stack([interp_data[m] for m in model_names])
        ensemble_mean = np.nanmean(model_array, axis=1)

        deviations_abs = model_array - ensemble_mean[:, np.newaxis]
        deviations_pct = 100 * deviations_abs / ensemble_mean[:, np.newaxis]

        dev_pct_min = np.nanmin(deviations_pct, axis=1)
        dev_pct_max = np.nanmax(deviations_pct, axis=1)
        dev_abs_min = np.nanmin(deviations_abs, axis=1)
        dev_abs_max = np.nanmax(deviations_abs, axis=1)

    return {
        "P_norm":      x_common,
        "dev_pct_min": dev_pct_min,
        "dev_pct_max": dev_pct_max,
        "dev_abs_min": dev_abs_min,
        "dev_abs_max": dev_abs_max,
        "mean":        ensemble_mean,
        "n_models":    len(model_names),
        "model_names": model_names,
    }


def plot_deviation_envelopes(
    systems_dict: dict,
    param: str = "ST_m_ppmw",
    x_col: str = "P_bars",
    n_points: int = 200,
    colors=None,
    alpha: float = 0.3,
    show_edges: bool = True,
    edge_alpha: float = 0.8,
    figsize: tuple = (7, 4),
    sort_by_spread: bool = True,
    legend_order: Optional[list[str]] = None,
    exclude_models=None,
    ax=None,
):
    """Plot model-spread deviation envelopes for multiple volcanic systems.

    Parameters
    ----------
    systems_dict : dict
        ``{"MORB": data_morb, "Kilauea": data_kil, ...}`` where each
        value is a dict of ``{model_name: DataFrame, "Name": str}``.
    param : str
        Column name to analyze (e.g. ``"ST_m_ppmw"``, ``"CS_v_mf"``).
    colors : dict or list, optional
        Per-system colours.
    exclude_models : dict or list, optional
        Models to exclude — a list (global) or dict (per-system).
    ax : matplotlib Axes, optional
        Plot on an existing axis.

    Returns
    -------
    envelope_data : dict
    fig : matplotlib Figure
    ax : matplotlib Axes
    """
    _ensure_mpl()

    if legend_order is None:
        legend_order = ["MORB", "Kilauea", "Fogo", "Fuego"]

    if exclude_models is None:
        exclude_dict = {}
    elif isinstance(exclude_models, list):
        exclude_dict = {s: exclude_models for s in systems_dict}
    else:
        exclude_dict = exclude_models

    default_colors = [
        "#0072B2", "#E69F00", "#009E73", "#CC79A7",
        "#F0E442", "#56B4E9", "#D55E00", "#000000",
    ]
    system_names = list(systems_dict.keys())

    if colors is None:
        color_dict = {
            name: default_colors[i % len(default_colors)]
            for i, name in enumerate(system_names)
        }
    elif isinstance(colors, dict):
        color_dict = colors
    else:
        color_dict = {
            name: colors[i % len(colors)]
            for i, name in enumerate(system_names)
        }

    if ax is None:
        fig, ax = _plt.subplots(figsize=figsize)
    else:
        fig = ax.get_figure()

    # Compute envelopes
    envelope_data = {}
    for system_name, data_dict in systems_dict.items():
        system_excludes = exclude_dict.get(system_name, [])
        env = _compute_deviation_envelope(
            data_dict, param, x_col, n_points,
            exclude_models=system_excludes,
        )
        if env is None:
            logger.info("  Skipping %s: no valid models for %s", system_name, param)
            continue
        if system_excludes:
            logger.info("  %s: excluded %s, using %s", system_name, system_excludes, env['model_names'])
        envelope_width = env["dev_pct_max"] - env["dev_pct_min"]
        env["mean_spread"] = np.nanmean(envelope_width)
        envelope_data[system_name] = env

    # Sort (largest in back)
    if sort_by_spread:
        sorted_systems = sorted(
            envelope_data, key=lambda s: envelope_data[s]["mean_spread"], reverse=True,
        )
    else:
        sorted_systems = [s for s in system_names if s in envelope_data]

    # Plot
    for system_name in sorted_systems:
        env = envelope_data[system_name]
        color = color_dict.get(system_name, "#333333")

        ax.fill_between(
            env["P_norm"], env["dev_pct_min"], env["dev_pct_max"],
            alpha=alpha, color=color, label=system_name, linewidth=0,
        )
        if show_edges:
            ax.plot(env["P_norm"], env["dev_pct_min"], color=color, alpha=edge_alpha, lw=1)
            ax.plot(env["P_norm"], env["dev_pct_max"], color=color, alpha=edge_alpha, lw=1)

    ax.axhline(0, color="gray", lw=0.8, ls="--", zorder=0)
    ax.set_xlim(0, 1)
    ax.set_xlabel("P / P$_i$")
    ax.set_ylabel("Deviation from mean (%)")
    ax.set_title(f"Model spread \u2014 {_default_variable_names(param)}")

    # Fixed legend order
    handles, labels = ax.get_legend_handles_labels()
    handle_dict = dict(zip(labels, handles))
    ordered_handles, ordered_labels = [], []
    for name in legend_order:
        if name in handle_dict:
            ordered_handles.append(handle_dict[name])
            ordered_labels.append(name)
    for label, handle in handle_dict.items():
        if label not in legend_order:
            ordered_handles.append(handle)
            ordered_labels.append(label)
    ax.legend(ordered_handles, ordered_labels, loc="best", fontsize=9)

    fig.set_layout_engine("constrained")
    return envelope_data, fig, ax


def plot_all_melt_volatiles(
    systems_dict: dict,
    colors=None,
    figsize: tuple = (7, 9),
    sort_by_spread: bool = True,
    legend_order: Optional[list[str]] = None,
    exclude_models=None,
    **kwargs,
):
    """Three-panel deviation envelopes for H2O, CO2, and S in melt.

    Returns ``(all_data, fig, (ax_h2o, ax_co2, ax_s))``.
    """
    _ensure_mpl()

    fig, (ax_h2o, ax_co2, ax_s) = _plt.subplots(
        3, 1, figsize=figsize, sharex=True,
        gridspec_kw={"hspace": 0.15},
    )

    all_data = {}

    env_h2o, _, _ = plot_deviation_envelopes(
        systems_dict, param="H2OT_m_wtpc", colors=colors, ax=ax_h2o,
        sort_by_spread=sort_by_spread, legend_order=legend_order,
        exclude_models=exclude_models, **kwargs,
    )
    all_data["H2O"] = env_h2o
    ax_h2o.set_xlabel("")

    env_co2, _, _ = plot_deviation_envelopes(
        systems_dict, param="CO2T_m_ppmw", colors=colors, ax=ax_co2,
        sort_by_spread=sort_by_spread, legend_order=legend_order,
        exclude_models=exclude_models, **kwargs,
    )
    all_data["CO2"] = env_co2
    ax_co2.set_xlabel("")
    ax_co2.legend().remove()

    env_s, _, _ = plot_deviation_envelopes(
        systems_dict, param="ST_m_ppmw", colors=colors, ax=ax_s,
        sort_by_spread=sort_by_spread, legend_order=legend_order,
        exclude_models=exclude_models, **kwargs,
    )
    all_data["S"] = env_s
    ax_s.legend().remove()

    fig.set_layout_engine("constrained")
    return all_data, fig, (ax_h2o, ax_co2, ax_s)


def plot_all_redox_variables(
    systems_dict: dict,
    colors=None,
    figsize: tuple = (7, 9),
    sort_by_spread: bool = True,
    legend_order: Optional[list[str]] = None,
    **kwargs,
):
    """Three-panel deviation envelopes for fO2, Fe3+/FeT, and S6+/ST.

    Returns ``(all_data, fig, (ax_fo2, ax_fe_spec, ax_s_spec))``.
    """
    _ensure_mpl()

    fig, (ax_fo2, ax_fe_spec, ax_s_spec) = _plt.subplots(
        3, 1, figsize=figsize, sharex=True,
        gridspec_kw={"hspace": 0.15},
    )

    all_data = {}

    env_fo2, _, _ = plot_deviation_envelopes(
        systems_dict, param="dFMQ", colors=colors, ax=ax_fo2,
        sort_by_spread=sort_by_spread, legend_order=legend_order, **kwargs,
    )
    all_data["fO2"] = env_fo2
    ax_fo2.set_xlabel("")

    env_fe, _, _ = plot_deviation_envelopes(
        systems_dict, param="Fe3Fet_m", colors=colors, ax=ax_fe_spec,
        sort_by_spread=sort_by_spread, legend_order=legend_order, **kwargs,
    )
    all_data["Fe_spec"] = env_fe
    ax_fe_spec.set_xlabel("")
    ax_fe_spec.legend().remove()

    env_s, _, _ = plot_deviation_envelopes(
        systems_dict, param="S6St_m", colors=colors, ax=ax_s_spec,
        sort_by_spread=sort_by_spread, legend_order=legend_order, **kwargs,
    )
    all_data["S_spec"] = env_s
    ax_s_spec.legend().remove()

    fig.set_layout_engine("constrained")
    return all_data, fig, (ax_fo2, ax_fe_spec, ax_s_spec)


# ---------------------------------------------------------------------------
# Composition overview & saturation pressure figures (Figs 1-3)
# ---------------------------------------------------------------------------

# Default volcano colours for composition/envelope plots
_VOLCANO_COLORS_DEFAULT = ["#4477AA", "#EE6677", "#ABABAB", "#93CC44"]

# Display names with special characters
_DISPLAY_NAMES = {"Kilauea": "K\u012blauea"}


def _get_comp_value(comp, key):
    """Extract a value from a MeltComposition or dict."""
    if isinstance(comp, dict):
        return comp.get(key, np.nan)
    return getattr(comp, key, np.nan)


def _get_sample_name(comp):
    """Extract sample name from a MeltComposition or dict."""
    if isinstance(comp, dict):
        return comp.get("Sample", comp.get("sample", ""))
    return getattr(comp, "sample", "")


def plot_composition_overview(
    compositions,
    volcano_order=None,
    colors=None,
    figsize=(16, 3.5),
):
    """Five-panel dot chart of starting composition variables.

    Parameters
    ----------
    compositions : list
        List of ``MeltComposition`` objects or dicts with keys
        ``H2O``, ``CO2``, ``S``, ``T_C``, ``dNNO``, and ``Sample``.
    volcano_order : list[str], optional
        Sample names in the desired display order.  If *None*, uses
        the order from *compositions*.
    colors : dict or list, optional
        Per-volcano colours.  A dict mapping sample name to colour,
        or a list of colours applied in order.  Defaults to the
        envelope palette (blue, red, grey, green).
    figsize : tuple
        Figure size in inches.

    Returns
    -------
    fig : matplotlib.figure.Figure
    axes : ndarray of Axes
    """
    _ensure_mpl()
    import matplotlib.ticker as mticker

    variables = [
        ("H2O",  r"H$_2$O (wt%)"),
        ("CO2",  r"CO$_2$ (wt%)"),
        ("S",    "S (wt%)"),
        ("T_C",  "Temperature (\u00b0C)"),
        ("dNNO", r"$\Delta$NNO"),
    ]

    # Resolve order
    if volcano_order is None:
        volcano_order = [_get_sample_name(c) for c in compositions]
    comp_by_name = {_get_sample_name(c): c for c in compositions}

    # Resolve colours
    if colors is None:
        color_dict = {
            name: _VOLCANO_COLORS_DEFAULT[i % len(_VOLCANO_COLORS_DEFAULT)]
            for i, name in enumerate(volcano_order)
        }
    elif isinstance(colors, dict):
        color_dict = colors
    else:
        color_dict = {
            name: colors[i % len(colors)]
            for i, name in enumerate(volcano_order)
        }

    fig, axes = _plt.subplots(1, len(variables), figsize=figsize)

    for i, (key, ylabel) in enumerate(variables):
        ax = axes[i]
        for j, vname in enumerate(volcano_order):
            comp = comp_by_name.get(vname)
            if comp is None:
                continue
            val = _get_comp_value(comp, key)
            ax.scatter(
                j, val,
                color=color_dict.get(vname, "#333333"),
                s=150, zorder=3,
                edgecolors="k", linewidths=0.5,
                marker="D",
            )

        ax.set_ylabel(ylabel, fontsize=13)
        ax.set_xticks(range(len(volcano_order)))
        ax.set_xticklabels(
            [_DISPLAY_NAMES.get(v, v) for v in volcano_order],
            fontsize=11,
        )
        ax.tick_params(axis="y", labelsize=11)

        # Visual padding
        ymin, ymax = ax.get_ylim()
        margin = (ymax - ymin) * 0.15 if ymax != ymin else 0.1
        ax.set_ylim(ymin - margin, ymax + margin)

    fig.set_layout_engine("constrained")
    return fig, axes


def plot_satp_grouped(
    satp_df,
    models=None,
    style=None,
    figsize=(11, 5),
):
    """Grouped scatter plot of saturation pressures by sample.

    Parameters
    ----------
    satp_df : pd.DataFrame
        Output from :func:`~volcatenate.calculate_saturation_pressure`.
        Must contain ``Sample`` column and ``<Model>_SatP_bars`` columns.
    models : list[str], optional
        Model display order.  If *None*, auto-detected from columns.
    style : dict, optional
        ``{model: (label, marker, size, facecolor, edgecolor, lw)}``.
        Defaults to :data:`MODEL_MARKER_STYLE`.
    figsize : tuple
        Figure size in inches.

    Returns
    -------
    fig : matplotlib.figure.Figure
    ax : matplotlib.axes.Axes
    """
    _ensure_mpl()
    import matplotlib.ticker as mticker

    if style is None:
        style = dict(MODEL_MARKER_STYLE)

    # Auto-detect models from column names
    if models is None:
        models = [
            c.replace("_SatP_bars", "")
            for c in satp_df.columns
            if c.endswith("_SatP_bars")
        ]

    samples = list(satp_df["Sample"])

    # Split models into core and VESIcal groups
    core_models = [m for m in models if not m.startswith("VESIcal")]
    vesical_models = [m for m in models if m.startswith("VESIcal")]

    # Build x-offsets within each panel
    offsets = {}
    x = 0
    for m in core_models:
        offsets[m] = x
        x += 2
    if vesical_models:
        x += 3  # gap between groups
        for m in vesical_models:
            offsets[m] = x
            x += 1

    panel_width = x + 2  # total width per panel (with padding)

    # Panel bases and dividers
    panel_bases = {s: i * panel_width for i, s in enumerate(samples)}
    dividers = [
        (i + 1) * panel_width - 1.5
        for i in range(len(samples) - 1)
    ]
    panel_left = -2.5
    panel_right = len(samples) * panel_width - 3.5
    panel_centres = [
        panel_bases[s] + (x - 1) / 2
        for s in samples
    ]

    fig, ax = _plt.subplots(figsize=figsize)

    for model in models:
        col_name = f"{model}_SatP_bars"
        if col_name not in satp_df.columns:
            continue

        lbl, mkr, ms, fc, ec, lw = style.get(
            model, (model, "o", 100, MODEL_COLORS_HEX.get(model, "#333"), "k", 0.5)
        )

        xs, ys = [], []
        for _, row in satp_df.iterrows():
            sample = row["Sample"]
            val = row[col_name]
            if pd.notna(val) and sample in panel_bases:
                xs.append(panel_bases[sample] + offsets[model])
                ys.append(val)

        if mkr in ("x", "+", "|", "_"):
            ax.scatter(
                xs, ys, marker=mkr, s=ms, color=ec,
                linewidths=lw, label=lbl, zorder=3,
            )
        else:
            ax.scatter(
                xs, ys, marker=mkr, s=ms,
                facecolors=fc, edgecolors=ec, linewidths=lw,
                label=lbl, zorder=3,
            )

    # Vertical panel dividers
    for xd in dividers:
        ax.axvline(xd, color="k", linewidth=0.8, zorder=1)

    ax.set_xlim(panel_left, panel_right)
    ax.set_ylim(0, None)

    # Bold sample names centred at top of each panel
    ytop = ax.get_ylim()[1]
    for cx, s in zip(panel_centres, samples):
        display = _DISPLAY_NAMES.get(s, s)
        ax.text(cx, ytop * 0.95, display, ha="center", va="top", fontsize=20)

    ax.set_ylabel("Saturation Pressure (bar)", fontsize=15)
    ax.tick_params(axis="both", labelsize=12)
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda v, p: f"{v:,.0f}")
    )
    ax.set_xticks([])

    ax.legend(
        fontsize=13, bbox_to_anchor=(0.54, 0.3),
        frameon=True, edgecolor="k", facecolor="white", framealpha=1.0,
        ncol=2,
    )

    fig.set_layout_engine("constrained")
    return fig, ax


def plot_satp_deviation(
    satp_df,
    ref_model="VESIcal_Iacono",
    compositions=None,
    x_variable="CO2",
    compare_models=None,
    style=None,
    figsize=(7, 5),
):
    """Plot saturation pressure deviation from a reference model.

    Parameters
    ----------
    satp_df : pd.DataFrame
        Output from :func:`~volcatenate.calculate_saturation_pressure`.
    ref_model : str
        Reference model name.  A horizontal line at 0 % is drawn.
    compositions : list, optional
        ``MeltComposition`` objects or dicts with composition data.
        Needed to provide x-axis values (e.g. starting CO\ :sub:`2`).
        Matched to *satp_df* rows by sample name.
    x_variable : str
        Composition key for the x-axis (e.g. ``"CO2"``).
    compare_models : list[str], optional
        Models to compare against the reference.  Defaults to all
        models in *satp_df* except *ref_model*.
    style : dict, optional
        ``{model: (label, marker, size, color)}``.
    figsize : tuple
        Figure size in inches.

    Returns
    -------
    fig : matplotlib.figure.Figure
    ax : matplotlib.axes.Axes
    """
    _ensure_mpl()
    import matplotlib.ticker as mticker

    ref_col = f"{ref_model}_SatP_bars"
    if ref_col not in satp_df.columns:
        raise KeyError(
            f"Reference model column {ref_col!r} not in DataFrame. "
            f"Available: {[c for c in satp_df.columns if c.endswith('_SatP_bars')]}"
        )

    # Build composition lookup: sample name (lower) → composition
    comp_lookup = {}
    if compositions is not None:
        for c in compositions:
            name = _get_sample_name(c).lower()
            comp_lookup[name] = c

    # Auto-detect comparison models
    if compare_models is None:
        compare_models = [
            c.replace("_SatP_bars", "")
            for c in satp_df.columns
            if c.endswith("_SatP_bars") and c != ref_col
        ]

    # Default style from MODEL_MARKER_STYLE (pick label, marker, size, color)
    if style is None:
        style = {}
        for m, (lbl, mkr, ms, fc, ec, lw) in MODEL_MARKER_STYLE.items():
            color = fc if fc != "none" else ec
            style[m] = (lbl, mkr, ms, color)

    fig, ax = _plt.subplots(figsize=figsize)

    for model in compare_models:
        col_name = f"{model}_SatP_bars"
        if col_name not in satp_df.columns:
            continue

        lbl, mkr, ms, color = style.get(
            model, (model, "o", 80, MODEL_COLORS_HEX.get(model, "#333"))
        )

        xs, ys = [], []
        for _, row in satp_df.iterrows():
            p_model = row[col_name]
            p_ref = row[ref_col]
            if pd.isna(p_model) or pd.isna(p_ref) or p_ref == 0:
                continue

            # Get x-axis value from compositions
            sample_lower = str(row["Sample"]).lower()
            if sample_lower in comp_lookup:
                x_val = _get_comp_value(comp_lookup[sample_lower], x_variable)
            else:
                continue

            xs.append(x_val)
            ys.append(100.0 * (p_model - p_ref) / p_ref)

        # Unfilled markers (x, +, |, _) ignore edgecolors — omit to
        # avoid a matplotlib UserWarning.
        if mkr in ("x", "+", "|", "_"):
            ax.scatter(
                xs, ys, marker=mkr, s=ms, color=color,
                linewidths=0.5, label=lbl, zorder=3,
            )
        else:
            ax.scatter(
                xs, ys, marker=mkr, s=ms, color=color,
                edgecolors="k", linewidths=0.5, label=lbl, zorder=3,
            )

    # Reference line
    ref_label = style.get(ref_model, (ref_model,))[0] if ref_model in style else ref_model
    ax.axhline(0, color="k", linewidth=1.2, zorder=2, label=ref_label)

    # Axis labels
    x_labels = {
        "CO2": r"Starting CO$_2^{\,\mathrm{melt}}$ total (wt%)",
        "H2O": r"Starting H$_2$O$^{\mathrm{melt}}$ total (wt%)",
        "S":   r"Starting S$^{\mathrm{melt}}$ total (wt%)",
    }
    ax.set_xlabel(x_labels.get(x_variable, f"Starting {x_variable}"), fontsize=12)
    ax.set_ylabel("Relative deviation from reference", fontsize=12)
    ax.yaxis.set_major_formatter(mticker.PercentFormatter())
    ax.legend(fontsize=9, edgecolor="k")
    ax.set_xlim(left=0)

    fig.set_layout_engine("constrained")
    return fig, ax


# ---------------------------------------------------------------------------
# C/S depth profile (Fig 10)
# ---------------------------------------------------------------------------

# Physical constants for depth conversion
RHO_BASALT = 2770      # kg/m³ (Poland et al. 2014)
_G = 9.81              # m/s²
P_PER_KM = RHO_BASALT * _G * 1000 / 1e5   # bars per km ≈ 271.6

# Vapor mass fraction threshold for numerical stability
_VAPOR_WT_MIN = 1e-4


def p_to_depth(p_bars, rho=RHO_BASALT):
    """Convert pressure (bars) to depth (km) assuming lithostatic load.

    Parameters
    ----------
    p_bars : array-like
        Pressure in bars.
    rho : float
        Crustal density in kg/m³ (default 2770).

    Returns
    -------
    numpy.ndarray
        Depth below surface in km.
    """
    ppk = rho * _G * 1000 / 1e5
    return np.asarray(p_bars) / ppk


def depth_to_p(depth_km, rho=RHO_BASALT):
    """Convert depth (km) to pressure (bars) assuming lithostatic load.

    Parameters
    ----------
    depth_km : array-like
        Depth below surface in km.
    rho : float
        Crustal density in kg/m³ (default 2770).

    Returns
    -------
    numpy.ndarray
        Pressure in bars.
    """
    ppk = rho * _G * 1000 / 1e5
    return np.asarray(depth_km) * ppk


def get_cs_vs_p(df, truncate=True, vapor_wt_min=_VAPOR_WT_MIN):
    """Extract sorted (P_bars, CS_v_mf) from a model DataFrame.

    Parameters
    ----------
    df : pandas.DataFrame
        Model output with at least ``P_bars`` and ``CS_v_mf`` columns.
    truncate : bool
        If *True*, remove rows where ``vapor_wt < vapor_wt_min``.
    vapor_wt_min : float
        Minimum vapor mass fraction for truncation.

    Returns
    -------
    p_bars : numpy.ndarray or None
    cs_values : numpy.ndarray or None
        Both sorted from high-P (deep) to low-P (shallow).
    """
    if not isinstance(df, pd.DataFrame):
        return None, None
    if "CS_v_mf" not in df.columns or "P_bars" not in df.columns:
        return None, None

    cols = ["P_bars", "CS_v_mf"]
    if truncate and "vapor_wt" in df.columns:
        cols.append("vapor_wt")

    sub = df[cols].dropna(subset=["P_bars", "CS_v_mf"])
    if sub.empty:
        return None, None

    sub = sub.sort_values("P_bars", ascending=False).reset_index(drop=True)

    if truncate and "vapor_wt" in sub.columns:
        mask = sub["vapor_wt"] >= vapor_wt_min
        if mask.any():
            first_good = mask.idxmax()
            sub = sub.iloc[first_good:]
        else:
            return None, None

    return sub["P_bars"].values, sub["CS_v_mf"].values


def find_pressure_at_cs(p_bars, cs_values, cs_target):
    """Find pressure(s) where a C/S curve crosses *cs_target*.

    Uses linear interpolation on log₁₀(C/S) for smoother results.

    Parameters
    ----------
    p_bars, cs_values : array-like
        Paired arrays of pressure and C/S (any sort order).
    cs_target : float
        The C/S molar ratio to intersect.

    Returns
    -------
    list[float]
        Pressures at which crossings occur (may be empty).
    """
    if p_bars is None or len(p_bars) < 2:
        return []

    log_cs = np.log10(np.clip(cs_values, 1e-10, None))
    log_target = np.log10(cs_target)

    crossings = []
    for i in range(len(log_cs) - 1):
        if (log_cs[i] - log_target) * (log_cs[i + 1] - log_target) <= 0:
            if abs(log_cs[i + 1] - log_cs[i]) < 1e-12:
                p_cross = (p_bars[i] + p_bars[i + 1]) / 2
            else:
                frac = (log_target - log_cs[i]) / (log_cs[i + 1] - log_cs[i])
                p_cross = p_bars[i] + frac * (p_bars[i + 1] - p_bars[i])
            crossings.append(p_cross)

    return crossings


def find_cs_at_pressure(p_curve, cs_curve, p_target):
    """Interpolate a model's C/S curve at a given pressure.

    Parameters
    ----------
    p_curve, cs_curve : array-like
        Model C/S data (may be any sort order).
    p_target : float
        Pressure (bars) at which to evaluate.

    Returns
    -------
    float
        Interpolated C/S molar ratio.
    """
    _ensure_mpl()
    p_sorted = np.asarray(p_curve)[::-1].copy()
    cs_sorted = np.asarray(cs_curve)[::-1].copy()
    p_target = np.clip(p_target, p_sorted[0], p_sorted[-1])
    f = _interp1d(p_sorted, np.log10(np.clip(cs_sorted, 1e-10, None)))
    return 10 ** f(p_target)


def plot_cs_depth_profile(
    system_data,
    gas_data=None,
    depth_constraints=None,
    satp_df=None,
    models=None,
    model_style=None,
    rho=RHO_BASALT,
    truncate=True,
    figsize=(8, 7),
    title=None,
    xlim=(0.05, 2000),
    max_depth_km=20.0,
    ax=None,
):
    """C/S vapor ratio vs depth profile with gas & seismic constraints.

    Compares model-predicted C/S vapor ratios with measured volcanic-gas
    data to infer degassing depths, following the approach of
    Werner et al. (2020).

    Parameters
    ----------
    system_data : dict
        ``{model_name: DataFrame}`` for one volcanic system (e.g. Kilauea).
        Each DataFrame must contain ``P_bars`` and ``CS_v_mf`` columns.
    gas_data : dict, optional
        Measured gas C/S ratios.  Keys are labels; values are dicts with::

            {"cs": float, "cs_lo": float, "cs_hi": float,
             "source": str, "color": str}

        Vertical bands and crossing markers are drawn for each entry.
    depth_constraints : dict, optional
        Independent geophysical depth constraints.  Keys are labels;
        values are dicts with::

            {"depth_belowsummit_km": float,
             "belowsummit_lo": float, "belowsummit_hi": float,
             "source": str, "color": str}

        Horizontal shaded bands are drawn for each entry.
    satp_df : pandas.DataFrame, optional
        Saturation-pressure data with columns ``Sample``, ``Reservoir``,
        and ``<Model>_SatP_bars``.  When provided, box-and-whisker
        diagrams are drawn along each model curve.
    models : list[str], optional
        Model names to plot (default: all keys in *system_data* that are
        DataFrames with ``CS_v_mf``).
    model_style : dict, optional
        ``{model_name: {"color": str, "marker": str, "label": str}}``.
        Uses ``MODEL_COLORS_HEX`` colours by default.
    rho : float
        Crustal density in kg/m³ for pressure ↔ depth conversion.
    truncate : bool
        Truncate model curves where vapor mass fraction is negligible.
    figsize : tuple
        Figure size.
    title : str, optional
        Figure title.
    xlim : tuple
        C/S axis limits (log scale).
    max_depth_km : float
        Maximum depth (km) for y-axis.
    ax : matplotlib Axes, optional
        Plot on an existing axis.

    Returns
    -------
    fig : matplotlib.figure.Figure
    ax : matplotlib.axes.Axes
    inferred : dict
        ``{gas_label: {model: {"P_bars": float, "depth_km": float}}}``.
    """
    _ensure_mpl()

    if ax is None:
        fig, ax = _plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    if gas_data is None:
        gas_data = {}
    if depth_constraints is None:
        depth_constraints = {}

    # -- Default model list and styles --
    if models is None:
        models = [
            m for m, v in system_data.items()
            if isinstance(v, pd.DataFrame) and "CS_v_mf" in v.columns
        ]
    if model_style is None:
        model_style = {
            m: {
                "color": MODEL_COLORS_HEX.get(m, "#333"),
                "marker": "o",
                "label": m,
            }
            for m in models
        }

    # -- Depth constraint bands --
    for dc_label, dc in depth_constraints.items():
        ax.axhspan(
            dc["belowsummit_lo"], dc["belowsummit_hi"],
            color=dc["color"], alpha=0.10, zorder=0,
        )
        ax.axhline(
            dc["depth_belowsummit_km"], color=dc["color"],
            ls="--", lw=1.2, alpha=0.5, zorder=1,
        )

    # -- Gas data vertical bands --
    for gas_label, gd in gas_data.items():
        ax.axvspan(
            gd["cs_lo"], gd["cs_hi"], color=gd["color"],
            alpha=0.15, zorder=1,
        )
        ax.axvline(
            gd["cs"], color=gd["color"], ls="-", lw=1.5,
            alpha=0.6, zorder=2,
        )

    # -- Model curves --
    model_curves = {}
    for model in models:
        if model not in system_data:
            continue
        p, cs = get_cs_vs_p(system_data[model], truncate=truncate)
        if p is None:
            continue
        model_curves[model] = (p, cs)
        depth = p_to_depth(p, rho=rho)
        sty = model_style.get(model, {"color": "#333", "label": model})
        ax.plot(
            cs, depth, color=sty["color"], lw=2.5, ls="-",
            label=sty.get("label", model), zorder=3,
        )
        # Anchor marker at deepest (highest-P) point
        ax.plot(
            cs[0], depth[0], marker="o", ms=8,
            color=sty["color"], markeredgecolor="k",
            markeredgewidth=0.8, zorder=5,
        )

    # -- Mark where curves cross gas data --
    inferred = {}
    for gas_label, gd in gas_data.items():
        inferred[gas_label] = {}
        for model in models:
            if model not in model_curves:
                continue
            p, cs = model_curves[model]
            crossings = find_pressure_at_cs(p, cs, gd["cs"])
            sty = model_style.get(model, {"color": "#333"})
            for pc in crossings:
                dc_val = p_to_depth(pc, rho=rho)
                ax.plot(
                    gd["cs"], dc_val, marker="*", ms=14,
                    color=sty["color"], markeredgecolor="k",
                    markeredgewidth=0.6, zorder=6,
                )
                inferred[gas_label][model] = {
                    "P_bars": pc, "depth_km": dc_val,
                }

    # -- Box-and-whisker plots from satP data --
    if satp_df is not None and not satp_df.empty:
        _draw_satp_boxes(ax, satp_df, model_curves, model_style, rho)

    # -- Axis configuration --
    ax.set_xscale("log")
    ax.set_xlim(*xlim)
    ax.set_ylim(bottom=0)
    ax.invert_yaxis()

    # Set y-limit from data
    all_depths = []
    for p, _ in model_curves.values():
        all_depths.extend(p_to_depth(p, rho=rho).tolist())
    if all_depths:
        y_max = min(max(all_depths), max_depth_km)
        for dc in depth_constraints.values():
            y_max = max(y_max, dc["belowsummit_hi"] * 1.1)
        ax.set_ylim(y_max, 0)

    # -- Depth constraint labels --
    for dc_label, dc in depth_constraints.items():
        ax.text(
            ax.get_xlim()[1] * 0.6,
            dc["depth_belowsummit_km"] + 0.1,
            dc_label.replace("\n", " "),
            fontsize=8, color=dc["color"], fontweight="bold",
            va="top", ha="right",
            bbox=dict(
                boxstyle="round,pad=0.15", fc="white",
                ec=dc["color"], alpha=0.8, lw=0.5,
            ),
        )

    # -- Gas data labels --
    for gas_label, gd in gas_data.items():
        label_clean = gas_label.replace("\n", " ")
        ax.text(
            gd["cs_hi"] * 1.15, 0.05,
            f"{label_clean}\n{gd.get('source', '')}",
            fontsize=8, color=gd["color"], fontweight="bold",
            va="top", ha="left", rotation=90,
            bbox=dict(
                boxstyle="round,pad=0.2", fc="white",
                ec=gd["color"], alpha=0.85, lw=0.5,
            ),
        )

    # Axis labels
    ax.set_xlabel(r"C/S$^{\mathrm{vapor}}$ (molar)", fontsize=13)
    ax.set_ylabel("Depth Below Summit (km)", fontsize=13)
    if title is not None:
        ax.set_title(title, fontsize=14, fontweight="bold")

    # Secondary y-axis for pressure
    ax_p = ax.secondary_yaxis(
        "right",
        functions=(
            lambda d: depth_to_p(d, rho=rho),
            lambda p: p_to_depth(p, rho=rho),
        ),
    )
    ax_p.set_ylabel("Pressure (bars)", fontsize=12)

    # Legend
    ax.legend(
        loc="lower right", fontsize=9, edgecolor="k",
        framealpha=0.9, title="Models", title_fontsize=10,
    )

    fig.tight_layout()
    return fig, ax, inferred


def _draw_satp_boxes(ax, satp_df, model_curves, model_style, rho):
    """Draw box-and-whisker plots of MI saturation pressures along curves.

    Parameters
    ----------
    ax : matplotlib Axes
    satp_df : DataFrame
        Must have ``Sample``, ``Reservoir``, and ``*_SatP_bars`` columns.
    model_curves : dict
        ``{model: (p_bars, cs_values)}``.
    model_style : dict
    rho : float
    """
    # Auto-detect satP columns → model keys
    satp_cols = {}
    for col in satp_df.columns:
        if col.endswith("_SatP_bars"):
            key = col.replace("_SatP_bars", "")
            # Try exact match first, then case-insensitive
            for mk in model_curves:
                if mk == key or mk.upper() == key.upper():
                    satp_cols[col] = mk
                    break

    if not satp_cols:
        return

    reservoirs = [r for r in satp_df["Reservoir"].dropna().unique()]
    hatch_list = [None, "//", "\\\\", "xx"]

    for col, model_key in satp_cols.items():
        if model_key not in model_curves:
            continue
        p_curve, cs_curve = model_curves[model_key]
        sty = model_style.get(model_key, {"color": "gray"})

        for j, reservoir in enumerate(reservoirs):
            mask = satp_df["Reservoir"] == reservoir
            vals = satp_df.loc[mask, col].dropna().values
            if len(vals) == 0:
                continue
            depths = p_to_depth(vals, rho=rho)

            # Position box so median line sits on the model curve
            median_p = np.median(vals)
            try:
                x_pos = find_cs_at_pressure(p_curve, cs_curve, median_p)
            except Exception:
                continue
            box_width = x_pos * 0.20

            bp = ax.boxplot(
                [depths],
                positions=[x_pos],
                widths=[box_width],
                vert=True,
                patch_artist=True,
                manage_ticks=False,
                zorder=4,
            )

            hatch = hatch_list[j % len(hatch_list)]
            for box in bp["boxes"]:
                box.set_facecolor(sty["color"])
                box.set_alpha(0.45)
                box.set_edgecolor("k")
                box.set_linewidth(0.8)
                if hatch:
                    box.set_hatch(hatch)
            for whisker in bp["whiskers"]:
                whisker.set_color("k")
                whisker.set_linewidth(0.8)
            for cap in bp["caps"]:
                cap.set_color("k")
                cap.set_linewidth(0.8)
            for median in bp["medians"]:
                median.set_color("k")
                median.set_linewidth(1.5)
            for flier in bp["fliers"]:
                flier.set(
                    marker="o", markerfacecolor=sty["color"],
                    markeredgecolor="k", markersize=3, alpha=0.6,
                )


# Kilauea defaults (used by figure_10 convenience function)
KILAUEA_GAS_DATA = {
    "2018 LERZ Fissures": {
        "cs": 0.3, "cs_lo": 0.2, "cs_hi": 0.4,
        "source": "Kern+ 2020",
        "type": "UAS-mounted MultiGAS",
        "color": "#f36e15",
    },
    "HMM Reservoir": {
        "cs": 2.0, "cs_lo": 1.0, "cs_hi": 3.0,
        "source": "Anderson+ 2019",
        "type": "restored gas",
        "color": "#1f77b4",
    },
}

KILAUEA_DEPTH_CONSTRAINTS = {
    "Halema\u02BBuma\u02BBu reservoir": {
        "depth_bsl_km": 0.75, "bsl_lo": 0.0, "bsl_hi": 1.5,
        "depth_belowsummit_km": 2.0,
        "belowsummit_lo": 1.25, "belowsummit_hi": 2.75,
        "source": "Anderson+ 2019",
        "color": "#d62728",
    },
    "South Caldera reservoir": {
        "depth_bsl_km": 2.5, "bsl_lo": 0.75, "bsl_hi": 3.25,
        "depth_belowsummit_km": 3.75,
        "belowsummit_lo": 3.0, "belowsummit_hi": 4.5,
        "source": "Poland+ 2014, Anderson+ 2019",
        "color": "#9467bd",
    },
}

# Default C/S figure model styles (models with sulfur)
_CS_MODEL_STYLE = {
    "DCompress": {"color": "#01B0F0", "marker": "s",  "label": "D-Compress"},
    "EVo":       {"color": "#E46C0A", "marker": "o",  "label": "EVo"},
    "MAGEC":     {"color": "#DD94BB", "marker": "s",  "label": "MAGEC"},
    "VolFe":     {"color": "#FFC00D", "marker": "^",  "label": "VolFe"},
    "SulfurX":   {"color": "#009E73", "marker": "s",  "label": "Sulfur_X"},
}


# ---------------------------------------------------------------------------
# Manuscript figure convenience API (Figs 1–10)
# ---------------------------------------------------------------------------
# Each ``figure_N()`` encapsulates the paper's layout, colours, axis limits,
# and legend placement so callers only pass data.
#
# Usage::
#
#     import volcatenate.plotting as vp
#
#     fig, axes = vp.figure_1(compositions)
#     fig       = vp.figure_4(systems)
#     fig, ax, inferred = vp.figure_10(systems["Kilauea"])
#
#     vp.generate_all_figures(
#         systems, compositions=comps, satp_df=df, output_dir="figures/",
#     )
# ---------------------------------------------------------------------------

# Public mapping of system names → colours (matches paper palette)
SYSTEM_COLORS = {
    "MORB": "#4477AA",
    "Kilauea": "#EE6677",
    "Fuego": "#ABABAB",
    "Fogo": "#93CC44",
}
SYSTEM_ORDER = ["MORB", "Kilauea", "Fuego", "Fogo"]

# Redox envelopes use a darker Fuego shade for print contrast
_REDOX_COLORS = ["#4477AA", "#EE6677", "#6F6F6F", "#93CC44"]


def _models_from_systems(systems, require_col=None):
    """Extract unique model names present in a *systems* dict.

    Parameters
    ----------
    systems : dict
        ``{system_name: {model_name: DataFrame, "Name": str, ...}}``.
    require_col : str, optional
        Only include models whose DataFrame contains this column.
    """
    models = set()
    for data in systems.values():
        for key, val in data.items():
            if key == "Name" or not isinstance(val, pd.DataFrame):
                continue
            if require_col and require_col not in val.columns:
                continue
            models.add(key)
    return sorted(models)


def _save_figure(fig, path, dpi=300, scale=4):
    """Save a matplotlib or Plotly figure if *path* is not None."""
    if path is None:
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if hasattr(fig, "write_image"):  # Plotly
        fig.write_image(path, scale=scale)
    else:  # matplotlib
        fig.savefig(path, dpi=dpi, bbox_inches="tight")


def _apply_standard_legend(fig):
    """Apply unified Plotly legend placement (lower-right, vertical)."""
    fig = unify_legend(fig)
    fig.update_layout(
        legend=dict(
            x=0.995, y=0.02, xanchor="right", yanchor="bottom",
            orientation="v", bgcolor="rgba(255,255,255,0.8)",
            bordercolor="black", borderwidth=1,
        ),
        margin=dict(r=50, b=50, t=50, l=50),
    )
    return fig


# ---- Figure 1 ----

def figure_1(compositions, save_path=None, dpi=300, **kwargs):
    """Figure 1: Starting composition overview (5-panel dot chart).

    Parameters
    ----------
    compositions : list
        ``MeltComposition`` objects or dicts with H2O, CO2, S, T_C, dNNO.
    save_path : str, optional
        Save the figure to this path.

    Returns
    -------
    fig : matplotlib Figure
    axes : ndarray of Axes
    """
    order = kwargs.pop("volcano_order", None)
    if order is None:
        order = [_get_sample_name(c) for c in compositions]
    colors = kwargs.pop("colors", {
        name: SYSTEM_COLORS.get(
            name, _VOLCANO_COLORS_DEFAULT[i % len(_VOLCANO_COLORS_DEFAULT)]
        )
        for i, name in enumerate(order)
    })
    fig, axes = plot_composition_overview(
        compositions, volcano_order=order, colors=colors, **kwargs,
    )
    _save_figure(fig, save_path, dpi=dpi)
    return fig, axes


# ---- Figure 2 ----

def figure_2(satp_df, save_path=None, dpi=300, **kwargs):
    """Figure 2: Absolute saturation pressures grouped by sample.

    Parameters
    ----------
    satp_df : pd.DataFrame
        From :func:`~volcatenate.calculate_saturation_pressure`.
    save_path : str, optional

    Returns
    -------
    fig : matplotlib Figure
    ax : matplotlib Axes
    """
    fig, ax = plot_satp_grouped(satp_df, **kwargs)
    _save_figure(fig, save_path, dpi=dpi)
    return fig, ax


# ---- Figure 3 ----

def figure_3(satp_df, compositions, save_path=None, dpi=300, **kwargs):
    """Figure 3: SatP deviation from reference model vs. starting CO2.

    Parameters
    ----------
    satp_df : pd.DataFrame
    compositions : list
        Needed for x-axis values (starting CO2).
    save_path : str, optional

    Returns
    -------
    fig : matplotlib Figure
    ax : matplotlib Axes
    """
    fig, ax = plot_satp_deviation(
        satp_df, compositions=compositions, **kwargs,
    )
    _save_figure(fig, save_path, dpi=dpi)
    return fig, ax


# ---- Figure 4 ----

def figure_4(systems, save_path=None, scale=4, **kwargs):
    """Figure 4: P-normalized H2O, CO2, S degassing paths (Plotly).

    Parameters
    ----------
    systems : dict
        ``{system_name: basalt_data_dict}`` from ``load_results()``.
    save_path : str, optional

    Returns
    -------
    plotly.graph_objs.Figure
    """
    models = kwargs.pop("models", None) or _models_from_systems(systems)
    basalt_list = list(systems.values())
    colors = get_line_properties()
    fig = plot_results(
        models, basalt_list, ["H2Om", "CO2m", "Sm"],
        colors, p_norm=True, scale=scale,
    )
    fig = _apply_standard_legend(fig)
    _save_figure(fig, save_path, scale=scale)
    return fig


# ---- Figure 5 ----

def figure_5(systems, save_path=None, dpi=300, **kwargs):
    """Figure 5: Melt volatile deviation envelopes (H2O, CO2, S).

    Parameters
    ----------
    systems : dict
    save_path : str, optional

    Returns
    -------
    fig : matplotlib Figure
    axes : tuple of Axes (H2O, CO2, S)
    """
    colors = kwargs.pop("colors", list(SYSTEM_COLORS.values()))
    exclude = kwargs.pop("exclude_models", ["VESIcal_MS"])
    ylim = kwargs.pop("ylim", (-100, 350))
    legend_order = kwargs.pop("legend_order", SYSTEM_ORDER)
    _, fig, axes = plot_all_melt_volatiles(
        systems, colors=colors, alpha=0.35,
        legend_order=legend_order, exclude_models=exclude,
        **kwargs,
    )
    for ax in axes:
        ax.set_ylim(*ylim)
    _save_figure(fig, save_path, dpi=dpi)
    return fig, axes


# ---- Figure 6 ----

def figure_6(systems, save_path=None, scale=4, **kwargs):
    """Figure 6: P-normalized redox variables (Plotly).

    Auto-selects models with S speciation data (``S6St_m`` column).

    Parameters
    ----------
    systems : dict
    save_path : str, optional

    Returns
    -------
    plotly.graph_objs.Figure
    """
    models = kwargs.pop("models", None) or _models_from_systems(
        systems, require_col="S6St_m",
    )
    basalt_list = list(systems.values())
    colors = get_line_properties()
    fig = plot_results(
        models, basalt_list,
        ["fO2_FMQ", "Fe_speciation", "S_speciation"],
        colors, p_norm=True,
    )
    # S6+/ST row (row 3): clamp to [0, 1]
    n_cols = len(basalt_list)
    for col in range(1, n_cols + 1):
        update_axis_limits(fig, "y", 3, col, [0, 1])
    # Fe3+/FeT last column: start at 0
    update_axis_limits(fig, "y", 2, n_cols, [0, None])

    fig = _apply_standard_legend(fig)
    _save_figure(fig, save_path, scale=scale)
    return fig


# ---- Figure 7 ----

def figure_7(systems, save_path=None, dpi=300, **kwargs):
    """Figure 7: Redox deviation envelopes (fO2, Fe3+/FeT, S6+/ST).

    Parameters
    ----------
    systems : dict
    save_path : str, optional

    Returns
    -------
    fig : matplotlib Figure
    axes : tuple of Axes
    """
    colors = kwargs.pop("colors", _REDOX_COLORS)
    ylim = kwargs.pop("ylim", (-200, 350))
    legend_order = kwargs.pop("legend_order", SYSTEM_ORDER)
    _, fig, axes = plot_all_redox_variables(
        systems, colors=colors, alpha=0.35,
        legend_order=legend_order, **kwargs,
    )
    for ax in axes:
        ax.set_ylim(*ylim)
    _save_figure(fig, save_path, dpi=dpi)
    return fig, axes


# ---- Figure 8 ----

def figure_8(systems, save_path_lines=None, save_path_envelopes=None,
             scale=4, dpi=300, **kwargs):
    """Figure 8: C/S vapor paths (A) and deviation envelopes (B).

    Parameters
    ----------
    systems : dict
    save_path_lines : str, optional
        Save path for 8A (Plotly).
    save_path_envelopes : str, optional
        Save path for 8B (matplotlib).

    Returns
    -------
    fig_8a : plotly Figure
    fig_8b : matplotlib Figure
    ax_8b : matplotlib Axes
    """
    # 8A: C/S vapor line plots
    models = kwargs.pop("models", None) or _models_from_systems(
        systems, require_col="CS_v_mf",
    )
    basalt_list = list(systems.values())
    colors = get_line_properties()
    fig_8a = plot_results(models, basalt_list, ["C_S_vapor"], colors)
    fig_8a.update_yaxes(range=[0, None])
    fig_8a = unify_legend(fig_8a)
    for col in range(1, len(basalt_list) + 1):
        update_axis_limits(fig_8a, "y", 1, col, [0, 150])
    _save_figure(fig_8a, save_path_lines, scale=scale)

    # 8B: C/S vapor deviation envelopes
    exclude = kwargs.pop("exclude_models", {
        "MORB": ["DCompress", "EVo"],
        "Kilauea": ["DCompress"],
    })
    sys_colors = list(SYSTEM_COLORS.values())
    _, fig_8b, ax_8b = plot_deviation_envelopes(
        systems, param="CS_v_mf", colors=sys_colors,
        exclude_models=exclude, legend_order=SYSTEM_ORDER,
    )
    ax_8b.legend(loc="upper right", framealpha=1)
    ax_8b.text(0.025, 250, "*Excluding outlier tools")
    _save_figure(fig_8b, save_path_envelopes, dpi=dpi)

    return fig_8a, fig_8b, ax_8b


# ---- Figure 9 ----

def figure_9(systems, save_path=None, dpi=300, **kwargs):
    """Figure 9: O2 mass balance (reported vs. by-difference X_O2).

    Only models with ``O2_v_mf`` and ``XO2_BYDIFF_v_mf`` columns are
    plotted.

    Parameters
    ----------
    systems : dict
    save_path : str, optional

    Returns
    -------
    fig : matplotlib Figure or None
    axes : ndarray of Axes or None
    """
    _ensure_mpl()
    exclude_o2 = kwargs.pop("exclude_models", ["SulfurX"])
    o2_models = [
        m for m in _models_from_systems(systems, require_col="XO2_BYDIFF_v_mf")
        if m not in exclude_o2
    ]
    if not o2_models:
        warnings.warn("No models with O2 mass balance data for Figure 9.")
        return None, None

    abs_y_models = kwargs.pop("abs_y_models", ["MAGEC"])
    data_colors = ["blue", "red", "darkgray", "green"]
    basalt_list = list(systems.values())

    n = len(o2_models)
    ncols = min(n, 2)
    nrows = math.ceil(n / ncols)
    fig, axes = _plt.subplots(nrows, ncols, figsize=(5 * ncols, 5 * nrows))
    if n == 1:
        axes = np.array([axes])
    axes_flat = np.array(axes).flat

    panel_labels = "ABCDEFGH"
    for idx, model in enumerate(o2_models):
        ax = axes_flat[idx]
        for enum, data in enumerate(basalt_list):
            if model not in data or not isinstance(data[model], pd.DataFrame):
                continue
            df = data[model]
            if "O2_v_mf" not in df.columns or "XO2_BYDIFF_v_mf" not in df.columns:
                continue
            y_vals = df["XO2_BYDIFF_v_mf"]
            if model in abs_y_models:
                y_vals = y_vals.abs()
            ax.scatter(
                df["O2_v_mf"], y_vals,
                s=15, color=data_colors[enum % len(data_colors)],
                edgecolors="k", linewidths=0.4, marker="D", alpha=0.9,
            )

        # 1:1 reference line
        xlims, ylims = ax.get_xlim(), ax.get_ylim()
        ref_min = min(xlims[0], ylims[0])
        ref_max = max(xlims[1], ylims[1])
        ax.plot([ref_min, ref_max], [ref_min, ref_max], "k-", linewidth=1)

        ax.set_xlabel(r"Reported $X_{O_2}^{vapor}$ (molar frac)")
        ylabel = r"By Difference $X_{O_2}^{vapor}$ (molar frac)"
        if model in abs_y_models:
            ylabel = r"|By Difference $X_{O_2}^{vapor}$| (molar frac)"
            ax.text(
                0.05, 0.95,
                "y-axis: absolute value\n(raw values are negative)",
                transform=ax.transAxes, ha="left", va="top",
                fontsize=9, fontstyle="italic", color="dimgray",
            )
        ax.set_ylabel(ylabel)
        ax.text(
            0.95, 0.05, f"{panel_labels[idx]}) {model}",
            transform=ax.transAxes, ha="right", va="bottom",
            fontsize=12, fontweight="bold",
        )
        ax.set_xscale("log")
        ax.set_yscale("log")

    # Hide unused axes
    total_axes = nrows * ncols
    for idx in range(n, total_axes):
        axes_flat[idx].set_visible(False)

    _plt.tight_layout()
    _save_figure(fig, save_path, dpi=dpi)
    return fig, axes


# ---- Figure 10 ----

def figure_10(
    system_data,
    gas_data=None,
    depth_constraints=None,
    satp_df=None,
    system_name="K\u012blauea",
    save_path=None,
    dpi=300,
    **kwargs,
):
    """Figure 10: C/S vapor ratio vs depth profile with gas constraints.

    By default uses K\u012blauea gas data and seismic depth constraints
    from the manuscript.  Override *gas_data* and *depth_constraints*
    for other volcanoes.

    Parameters
    ----------
    system_data : dict
        ``{model_name: DataFrame}`` for one volcanic system.
    gas_data : dict, optional
        Default: ``KILAUEA_GAS_DATA``.
    depth_constraints : dict, optional
        Default: ``KILAUEA_DEPTH_CONSTRAINTS``.
    satp_df : pandas.DataFrame, optional
        Saturation-pressure data for box-whisker overlays.
    system_name : str
        Display name used in the title.
    save_path : str, optional
    dpi : int

    Returns
    -------
    fig : matplotlib Figure
    ax : matplotlib Axes
    inferred : dict
    """
    if gas_data is None:
        gas_data = KILAUEA_GAS_DATA
    if depth_constraints is None:
        depth_constraints = KILAUEA_DEPTH_CONSTRAINTS

    title = kwargs.pop("title", None)
    if title is None:
        title = (
            f"{system_name}: C/S vapor ratio vs depth\n"
            "Model predictions with gas & seismic constraints"
        )

    model_style = kwargs.pop("model_style", _CS_MODEL_STYLE)

    fig, ax, inferred = plot_cs_depth_profile(
        system_data,
        gas_data=gas_data,
        depth_constraints=depth_constraints,
        satp_df=satp_df,
        model_style=model_style,
        title=title,
        **kwargs,
    )

    _save_figure(fig, save_path, dpi=dpi)
    return fig, ax, inferred


# ---- Generate all ----

def generate_all_figures(
    systems,
    compositions=None,
    satp_df=None,
    output_dir=None,
    dpi=300,
    scale=4,
    figure_kwargs=None,
):
    """Generate all manuscript figures and save to *output_dir*.

    Parameters
    ----------
    systems : dict
        ``{"MORB": data_morb, ...}`` from :func:`~volcatenate.load_results`.
    compositions : list, optional
        ``MeltComposition`` objects for Figures 1 and 3.
    satp_df : pd.DataFrame, optional
        Saturation-pressure DataFrame for Figures 2, 3, and 10.
    output_dir : str, optional
        Directory for saved PNGs.  Defaults to ``"figures/"``.
    dpi : int
        Resolution for matplotlib figures.
    scale : int
        Scale factor for Plotly figure export.
    figure_kwargs : dict, optional
        Per-figure keyword arguments.  Keys are figure names
        (``"figure_1"`` through ``"figure_10"``; also ``"figure_8a"``
        and ``"figure_8b"`` for the C/S sub-figures); values are dicts
        of kwargs forwarded to the corresponding ``figure_N()`` call.

        Example::

            generate_all_figures(
                systems,
                figure_kwargs={
                    "figure_9": {"exclude_models": ["SulfurX", "DCompress"]},
                    "figure_5": {"ylim": (-50, 200)},
                },
            )

    Returns
    -------
    dict
        ``{figure_name: figure_object}`` for every generated figure.
    """
    if output_dir is None:
        from volcatenate.config import RunConfig
        output_dir = os.path.join(RunConfig().output_dir, "figures")
    if figure_kwargs is None:
        figure_kwargs = {}

    os.makedirs(output_dir, exist_ok=True)
    figs = {}

    def _path(name):
        return os.path.join(output_dir, name)

    def _kw(fig_name):
        return figure_kwargs.get(fig_name, {})

    if compositions is not None:
        logger.info("Figure 1: Composition overview")
        figs["figure_1"], _ = figure_1(
            compositions,
            save_path=_path("Fig1_composition_overview.png"), dpi=dpi,
            **_kw("figure_1"),
        )

    if satp_df is not None:
        logger.info("Figure 2: Saturation pressures")
        figs["figure_2"], _ = figure_2(
            satp_df,
            save_path=_path("Fig2_satp_grouped.png"), dpi=dpi,
            **_kw("figure_2"),
        )

    if satp_df is not None and compositions is not None:
        logger.info("Figure 3: SatP deviation")
        figs["figure_3"], _ = figure_3(
            satp_df, compositions,
            save_path=_path("Fig3_satp_deviation.png"), dpi=dpi,
            **_kw("figure_3"),
        )

    logger.info("Figure 4: Melt volatile degassing paths")
    figs["figure_4"] = figure_4(
        systems, save_path=_path("Fig4_melt_volatiles.png"), scale=scale,
        **_kw("figure_4"),
    )

    logger.info("Figure 5: Melt volatile envelopes")
    figs["figure_5"], _ = figure_5(
        systems, save_path=_path("Fig5_melt_volatile_envelopes.png"), dpi=dpi,
        **_kw("figure_5"),
    )

    logger.info("Figure 6: Redox variable degassing paths")
    figs["figure_6"] = figure_6(
        systems, save_path=_path("Fig6_redox_variables.png"), scale=scale,
        **_kw("figure_6"),
    )

    logger.info("Figure 7: Redox envelopes")
    figs["figure_7"], _ = figure_7(
        systems, save_path=_path("Fig7_redox_envelopes.png"), dpi=dpi,
        **_kw("figure_7"),
    )

    logger.info("Figure 8: C/S vapor")
    fig_8a, fig_8b, _ = figure_8(
        systems,
        save_path_lines=_path("Fig8A_CS_vapor.png"),
        save_path_envelopes=_path("Fig8B_CS_vapor_envelopes.png"),
        scale=scale, dpi=dpi,
        **_kw("figure_8"),
    )
    figs["figure_8a"] = fig_8a
    figs["figure_8b"] = fig_8b

    logger.info("Figure 9: O2 mass balance")
    fig9, _ = figure_9(
        systems, save_path=_path("Fig9_O2_mass_balance.png"), dpi=dpi,
        **_kw("figure_9"),
    )
    if fig9 is not None:
        figs["figure_9"] = fig9

    # Figure 10: C/S depth profile (Kilauea by default)
    if "Kilauea" in systems:
        logger.info("Figure 10: C/S depth profile")
        fig10, _, inferred = figure_10(
            systems["Kilauea"],
            satp_df=satp_df,
            save_path=_path("Fig10_CS_depth_profile.png"), dpi=dpi,
            **_kw("figure_10"),
        )
        figs["figure_10"] = fig10

    logger.info("All figures saved to %s/", output_dir)
    return figs
