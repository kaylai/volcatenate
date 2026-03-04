"""Example: End-to-end volcanic degassing model comparison with volcatenate.

This script demonstrates the complete workflow:
  1. Calculate saturation pressures from a CSV → export as CSV
  2. Calculate degassing paths for individual compositions → export as CSVs
  3. Generate manuscript figures using volcatenate.plotting

Usage:
    python run_full_comparison.py

To suppress intermediate file clutter (EVo YAML dirs, MAGEC scripts, etc.):
    Set keep_intermediates=False in the RunConfig below.
"""

import os
import numpy as np
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for saving figures
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import re

import volcatenate
from volcatenate.config import RunConfig
import volcatenate.compat as mh
import volcatenate.plotting as vp


# ──────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────

config = RunConfig(
    output_dir="volcatenate_output",
    keep_intermediates=False,   # Set True to keep EVo YAML dirs, MAGEC scripts, etc.
)

RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)


# ──────────────────────────────────────────────────────────────────
# Step 1: Saturation Pressures from CSV
# ──────────────────────────────────────────────────────────────────

# Calculate saturation pressures for all compositions in a CSV file.
# Uncomment and provide your CSV path:
#
# satp_df = volcatenate.calculate_saturation_pressure(
#     "melt_inclusions.csv",
#     models=["EVo", "VolFe", "MAGEC", "SulfurX", "DCompress"],
#     config=config,
# )
# volcatenate.export_saturation_pressure(
#     satp_df, os.path.join(RESULTS_DIR, "saturation_pressures.csv")
# )

# Or use the one-shot workflow:
# results = volcatenate.run_comparison(
#     satp_compositions="melt_inclusions.csv",
#     models=["EVo", "VolFe", "MAGEC", "SulfurX", "DCompress"],
#     config=config,
#     satp_output=os.path.join(RESULTS_DIR, "saturation_pressures.csv"),
# )


# ──────────────────────────────────────────────────────────────────
# Step 2: Degassing Paths for individual compositions
# ──────────────────────────────────────────────────────────────────

# Define compositions inline (or read from CSV):
kilauea = {
    "Sample": "Kilauea", "T_C": 1200.0,
    "SiO2": 50.19, "TiO2": 2.34, "Al2O3": 12.79,
    "FeO": 11.34, "MnO": 0.18, "MgO": 9.23, "CaO": 10.44,
    "Na2O": 2.39, "K2O": 0.43, "P2O5": 0.27,
    "H2O": 0.30, "CO2": 0.0800, "S": 0.1500,
    "Fe3FeT": 0.18, "dNNO": -0.23,
}

# Uncomment to run degassing:
# paths = volcatenate.calculate_degassing(
#     kilauea,
#     models=["EVo", "VolFe", "MAGEC", "SulfurX", "DCompress"],
#     config=config,
# )
# volcatenate.export_degassing_paths(
#     paths,
#     output_dir=os.path.join(RESULTS_DIR, "degassing"),
#     sample_name="kilauea",
# )


# ──────────────────────────────────────────────────────────────────
# Step 3: Generate Figures from pre-existing model data
# ──────────────────────────────────────────────────────────────────

# Load data from existing model output directories.
# Adjust the path to where your model runs live:
TOP_DIR = "../Model_Runs_28Feb2026/"

model_names_all = ["DCompress", "EVo", "MAGEC", "VolFe", "SulfurX", "VESIcal_MS"]
model_names_w_S = ["DCompress", "EVo", "MAGEC", "VolFe", "SulfurX"]

data_morb, data_kil, data_fuego, data_fogo = mh.loadData(
    model_names_all,
    topdirectory_name=TOP_DIR,
    O2_mass_bal=True,
)
all_basalts = [data_morb, data_kil, data_fuego, data_fogo]

systems = {
    "MORB": data_morb,
    "Kilauea": data_kil,
    "Fuego": data_fuego,
    "Fogo": data_fogo,
}

line_colors = vp.get_line_properties()
rgb_list = list(line_colors.values())
mpl_colors = [
    tuple(int(x) / 255 for x in re.findall(r"\d+", rgb))
    for rgb in rgb_list
]

# System colours for envelopes
sys_colors = ["#4477AA", "#EE6677", "#ABABAB", "#93CC44"]
legend_order = ["MORB", "Kilauea", "Fuego", "Fogo"]


# --- Figure 4: P-normalized H2O, CO2, S degassing paths ---
print("\nFigure 4: P-normalized melt volatiles")
fig4 = vp.plot_results(
    model_names_all, all_basalts, ["H2Om", "CO2m", "Sm"],
    line_colors, p_norm=True, scale=4,
)
fig4 = vp.unify_legend(fig4)
fig4.update_layout(
    legend=dict(x=0.995, y=0.02, xanchor="right", yanchor="bottom",
                orientation="v", bgcolor="rgba(255,255,255,0.8)",
                bordercolor="black", borderwidth=1),
    margin=dict(r=50, b=50, t=50, l=50),
)
vp.save_plotly_fig(fig4, os.path.join(RESULTS_DIR, "Fig_P_norm_H2Om_CO2m_Sm"),
                   overwrite_if_exists=True, scale=4)


# --- Figure 5: Melt volatile model-spread envelopes ---
print("\nFigure 5: Melt volatile model-spread envelopes")
all_data, fig5, axes5 = vp.plot_all_melt_volatiles(
    systems, colors=sys_colors, alpha=0.35,
    legend_order=legend_order, exclude_models=["VESIcal_MS"],
)
for ax in axes5:
    ax.set_ylim(-100, 350)
fig5.savefig(os.path.join(RESULTS_DIR, "melt_volatiles_model_spread.png"), dpi=300)
print(f"  Saved {RESULTS_DIR}/melt_volatiles_model_spread.png")


# --- Figure 6: P-normalized redox variables ---
print("\nFigure 6: P-normalized redox variables")
fig6 = vp.plot_results(
    model_names_w_S, all_basalts, ["fO2_FMQ", "Fe_speciation", "S_speciation"],
    line_colors, p_norm=True,
)
for sbplt in [[2, 4, 0, None], [3, 1, 0, 1], [3, 2, 0, 1], [3, 3, 0, 1], [3, 4, 0, 1]]:
    vp.update_axis_limits(fig6, "y", sbplt[0], sbplt[1], [sbplt[2], sbplt[3]])
fig6 = vp.unify_legend(fig6)
fig6.update_layout(
    legend=dict(x=0.995, y=0.02, xanchor="right", yanchor="bottom",
                orientation="v", bgcolor="rgba(255,255,255,0.8)",
                bordercolor="black", borderwidth=1),
    margin=dict(r=50, b=50, t=50, l=50),
)
vp.save_plotly_fig(fig6, os.path.join(RESULTS_DIR, "Fig_P_norm_redox"),
                   overwrite_if_exists=True, scale=4)


# --- Figure 7: Redox model-spread envelopes ---
print("\nFigure 7: Redox model-spread envelopes")
all_data, fig7, axes7 = vp.plot_all_redox_variables(
    systems, colors=["#4477AA", "#EE6677", "#6F6F6F", "#93CC44"],
    alpha=0.35, legend_order=legend_order,
)
for ax in axes7:
    ax.set_ylim(-200, 350)
fig7.savefig(os.path.join(RESULTS_DIR, "redox_all.png"), dpi=300)
print(f"  Saved {RESULTS_DIR}/redox_all.png")


# --- Figure 8A: C/S vapor line plots ---
print("\nFigure 8A: C/S vapor line plots")
fig8a = vp.plot_results(
    model_names_w_S, all_basalts, ["C_S_vapor"], line_colors,
)
fig8a.update_yaxes(range=[0, None])
fig8a = vp.unify_legend(fig8a)
for col in range(1, 5):
    vp.update_axis_limits(fig8a, "y", 1, col, [0, 150])
vp.save_plotly_fig(fig8a, os.path.join(RESULTS_DIR, "Fig_CS_vapor"),
                   overwrite_if_exists=True, scale=4)


# --- Figure 8B: C/S vapor deviation envelopes ---
print("\nFigure 8B: C/S vapor deviation envelopes")
exclude_cs = {"MORB": ["DCompress", "EVo"], "Kilauea": ["DCompress"]}
env_data, fig8b, ax8b = vp.plot_deviation_envelopes(
    systems, param="CS_v_mf", colors=sys_colors,
    exclude_models=exclude_cs, legend_order=legend_order,
)
ax8b.legend(loc="upper right", framealpha=1)
ax8b.text(0.025, 250, "*Excluding outlier tools")
fig8b.savefig(os.path.join(RESULTS_DIR, "CS_vapor_envelopes.png"), dpi=600)
print(f"  Saved {RESULTS_DIR}/CS_vapor_envelopes.png")


print("\n=== All figures generated! ===")
