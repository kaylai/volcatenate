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
    "VESIcal_MS":                   "#000000",
    "VESIcal_Dixon":                "#D9D9D9",
    "VESIcal_IaconoMarziano":      "#545454",
    "VESIcal_Iacono":              "#545454",
    "VESIcal_Liu":                  "#532E5C",
    "VESIcal_ShishkinaIdealMixing": "#5E6480",
}


def get_line_properties() -> dict[str, str]:
    """Return a dict of model names to Plotly ``rgb(...)`` colour strings."""
    return {
        "DCompress":                    "rgb(1, 176, 240)",
        "EVo":                          "rgb(228, 108, 10)",
        "MAGEC":                        "rgb(221, 148, 187)",
        "SulfurX":                      "rgb(0, 158, 115)",
        "VolFe":                        "rgb(255, 192, 13)",
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
        print(f"Saved {filepath}")
        return filepath

    if not os.path.exists(filepath):
        fig.write_image(filepath, scale=scale)
        print(f"Saved {filepath}")
        return filepath

    date_str = datetime.now().strftime("%m%d%y")
    dated_filepath = os.path.join(directory, f"{base_filename}_{date_str}.{extension}")
    if not os.path.exists(dated_filepath):
        fig.write_image(dated_filepath, scale=scale)
        print(f"Saved {dated_filepath}")
        return dated_filepath

    counter = 1
    while True:
        counted_filepath = os.path.join(
            directory, f"{base_filename}_{date_str}_{counter}.{extension}"
        )
        if not os.path.exists(counted_filepath):
            fig.write_image(counted_filepath, scale=scale)
            print(f"Saved {counted_filepath}")
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
    try:
        fig.add_trace(
            go.Scatter(
                mode="lines",
                y=data[y_map[y_variable]],
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
    except Exception:
        pass


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
        fig_directory = "outputs/figures/P_norm_figs"
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
        except Exception:
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
            print(f"  Skipping {system_name}: no valid models for {param}")
            continue
        if system_excludes:
            print(f"  {system_name}: excluded {system_excludes}, using {env['model_names']}")
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
