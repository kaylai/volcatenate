# Gallery

Worked examples that show volcatenate doing something concrete — comparing backends on a real sample, running a sensitivity sweep, replicating a published figure, or producing a specific kind of plot. Each entry is a self-contained Jupyter notebook (rendered here via nbsphinx) with the full code, the inputs, and the resulting figure.

```{note}
**This gallery is a stub.** The structure below is the intended shape; most entries are not yet written. Use the [template](#how-to-add-a-gallery-entry) at the bottom of this page to add new entries one at a time. See the [tracking checklist](#tracking-checklist) for which entries are drafted, which are next up, and which are aspirational.
```

The categories below are organised by **what question the entry answers**, not by which backend it uses — most entries touch multiple backends. The two existing example notebooks ([minimal_config](../examples/minimal_config.ipynb), [full_config](../examples/full_config.ipynb)) live under "Quickstart" rather than in the legacy `examples/` directory once they are migrated; for now they remain in their current location and the gallery cross-links to them.

## Quickstart

Smallest end-to-end runs for users who want to copy-paste-modify rather than read documentation.

| Title | Status | What it shows |
| ----- | ------ | ------------- |
| **Single-sample saturation pressure across every backend** | **stub** | Five lines of code: load Fuego from `~/PythonGit/Sulfur_Comparison_Paper/Model_Inputs/`, run `calculate_saturation_pressure` against EVo / VolFe / MAGEC / SulfurX / VESIcal, print the resulting `saturation_pressures.csv`. The "hello world" of volcatenate. |
| **Closed-system degassing path, side-by-side** | **stub** | Same Fuego sample, full degassing run via `calculate_degassing` for each backend, plot `wmST` (melt sulfur) vs. P on a single axes. The plot that motivates the whole package. |
| **Reading a sample from CSV vs. constructing a `MeltComposition` directly** | **stub** | Three equivalent ways to provide sample data (CSV row, dict, explicit `MeltComposition`). Cross-references [sample_data.md](../sample_data.md). |

## Redox / fO2

Concrete versions of the five scenarios from the "Worked examples — fO2 initialization" section in [config_options.md](../config_options.md). Each is a runnable notebook so readers can poke at the inputs.

| Title | Status | What it shows |
| ----- | ------ | ------------- |
| **Scenario 1: sample with only `Fe3FeT`, all backends in `auto` mode** | **stub** | Direct runnable version of Example 1 in the config reference. Outputs the standardized `logfO2` / `dFMQ` / `Fe3Fet_m` columns at the saturation pressure for each backend; shows the small numerical differences across backends due to KC91A vs. Sun-Yao-2024. |
| **Scenario 2: sample with only `dNNO`, divergent MAGEC behavior** | **stub** | Runnable Example 2. Highlights the WARNING-level log line MAGEC emits when its wrapper does the 1-bar KC91 inversion. Reads `~/PythonGit/volcatenate/run_X/log.txt` and quotes the warning. |
| **Scenario 3: `Fe3FeT` and `dFMQ` mutually consistent, SulfurX divergence** | **stub** | Runnable Example 3. Constructs a sample with both indicators (computed to be consistent at run T, P) and shows that all four backends agree; then perturbs `dFMQ` by 0.5 and shows SulfurX diverges from the other three. |
| **Scenario 4: strict-mode `fe3fet` raises** | **stub** | Runnable Example 4. Shows the `ValueError` traceback and how to handle it in batch runs (`try` / `except` / continue). |
| **Scenario 5: `evo.fo2_source = "absolute"` and the dFMQ workaround for the other backends** | **stub** | Runnable Example 5. Shows how to compute the equivalent dFMQ at run T, P and apply it to the other three backends so all four start at the same absolute fO2. |
| **Sensitivity to Fe redox model choice (KC91 vs. ONeill18 vs. Borisov18)** | **stub** | Holds composition and pressure fixed; sweeps `evo.fo2_model` and `volfe.fo2_model` through their three options. Plots resulting `Fe3Fet_m` vs. P. Useful for users wondering whether the choice matters for their problem. |

## Sulfur

Concrete cross-backend sulfur runs, paralleling the "Sulfur deep-dive — cross-backend model choices" section in [config_options.md](../config_options.md).

| Title | Status | What it shows |
| ----- | ------ | ------------- |
| **Cross-backend O'Neill family recipe** | **stub** | Runnable version of the YAML recipe from the sulfur deep-dive ("O'Neill family across all four backends"). Plots `wmST` vs. P for all four backends and walks through where they agree and where EVo terminates early. |
| **Sulfide saturation: enforcement vs. no enforcement** | **stub** | Same sample, two runs: defaults (no saturation check, all four backends), then with saturation enforcement on (`evo.s_sat_warn = true`, `volfe.sulfur_saturation = true`, `magec.sulfide_sat = 1`, `sulfurx.sulfide_pre = 1`). Side-by-side melt-S evolution. |
| **S6+/ST sensitivity: Nash 2019 vs. ONeill & Mavrogenes 2022 vs. Boulliung 2023** | **stub** | Holds backend choice fixed (e.g., MAGEC), sweeps `s_redox` through 2 / 4 / 5. Plots resulting `S6_ST` ratio vs. fO2 across the run. |
| **Sulfide phase composition (SulfurX `sulfide.fe`, `sulfide.s`)** | **aspirational** | SulfurX-only. Sweeps the equilibrium sulfide phase composition (Fe-rich vs. Cu / Ni-bearing) and shows the effect on SCSS and on melt S evolution. |

## Workflows

Practical runs that solve real production problems (batch comparisons, reproducibility, debugging).

| Title | Status | What it shows |
| ----- | ------ | ------------- |
| **Per-sample overrides for a heterogeneous batch** | **stub** | Single config run on four samples (MORB, Kilauea, Fuego, Fogo) with per-sample `co2_sol` overrides for VolFe and per-sample `p_start_kbar` overrides for MAGEC. Cross-references [configuration.md](../configuration.md#per-sample-overrides). |
| **Reproducible runs: save and replay a run bundle** | **stub** | Saves the run bundle JSON, then on a second machine (or a clean checkout) replays it via `volcatenate.reproducible.replay`. Verifies bit-for-bit reproducibility of standardized output. Cross-references [run_bundles.md](../run_bundles.md). |
| **Debugging a failed run with `verbose = true` and `log_file`** | **stub** | A sample that intentionally fails (e.g., volatile budget too low for any saturation, or a strict-mode redox mismatch). Shows the WARNING / DEBUG log lines and how to interpret them. |
| **Comparing the same sample at different hypothetical redox states** | **stub** | The pattern from the [Comparing the same sample at different hypothetical redox states](../config_options.md#comparing-the-same-sample-at-different-hypothetical-redox-states) subsection: two `MeltComposition` instances, same composition, different redox. Shows the resulting standardized output side-by-side. |

## Visualisation recipes

Plotting patterns volcatenate users commonly need but the package itself does not bake in.

| Title | Status | What it shows |
| ----- | ------ | ------------- |
| **Multi-panel degassing plots with `volcatenate.plotting`** | **stub** | The built-in plotly / matplotlib helpers driven from a comparison run. Outputs a 4-panel figure (gas evolution, melt evolution, fO2 evolution, fugacity coefficients). Useful as a reference for what the helpers do without reading the plotting source. |
| **Custom colour palettes for backend comparison plots** | **stub** | Defining a per-backend colour map and applying it consistently across saturation-pressure plots, degassing-path plots, and sensitivity sweeps. |
| **Standardized output columns: which columns mean what** | **stub** | Tabular cheat-sheet of the columns in the standardized output DataFrame — `wmST`, `wmH2O`, `Fe3Fet_m`, `logfO2`, `dFMQ`, `vapor_wt`, etc. — with a short note on which backends populate each. Could be a runnable notebook that introspects an actual output DataFrame and labels every column. |

## Replication

Notebooks that reproduce specific published figures end-to-end. Highest-effort entries; aspirational until a paper-comparison run is finalised.

| Title | Status | What it shows |
| ----- | ------ | ------------- |
| **Sulfur Comparison Paper Fig. X — four-backend comparison for the Fuego inclusion suite** | **aspirational** | Driven by `~/PythonGit/Sulfur_Comparison_Paper/Model_Runs/run_all_models/run_volcatenate.ipynb`; lifts the figure-generation cells into a self-contained gallery entry. Will need to land after the paper figures are stable. |
| **Replicating Sun & Yao (2024) MAGEC paper figures via volcatenate** | **aspirational** | Uses MAGEC alone (single-backend mode) to replicate one figure from the original MAGEC paper, demonstrating that the wrapper is not changing the underlying model behaviour. |
| **Replicating Hughes et al. (2024) VolFe basalt examples** | **aspirational** | Same idea for VolFe. |

## How to add a gallery entry

1. **Pick a category** above (or add a new one if the entry doesn't fit). Keep categories question-shaped, not backend-shaped.
2. **Add a Jupyter notebook** at `docs/gallery/<category>/<short-name>.ipynb` (e.g. `docs/gallery/redox/scenario1_fe3fet_only.ipynb`). Notebooks should:
    - Have a single H1 title at the top matching the gallery card title.
    - Open with a 2–4 sentence "What this shows" abstract right under the title — readers should know in 10 seconds whether the entry is what they want.
    - End with a "Where to look next" section linking to (a) the relevant section in [config_options.md](../config_options.md), (b) the upstream model paper(s), and (c) any related gallery entries.
    - Keep cell outputs **small** (truncate DataFrames to a few rows; use `plotly` `to_image` or save figures to PNG so the rendered HTML stays under ~200 KB per entry).
    - Be **runnable from a clean checkout** with the volcatenate test fixtures or with sample data committed under `docs/gallery/_data/`. Do not depend on `~/PythonGit/Sulfur_Comparison_Paper/` for inputs — copy the sample row in.
    - Be deterministic: pin model versions (`evo.solver_dir`, `magec.solver_dir`, etc.) where possible, and use fixed seeds.
3. **Add the notebook to the toctree below** (the hidden one at the bottom of this page) and to the table in the matching category above.
4. **Build the docs locally** (`cd docs && make clean html`) and confirm the new entry's thumbnail appears and the rendered notebook does not blow up the build.

## Tracking checklist

Use this list to coordinate which entries are next. Status values:

- **stub** — listed in the gallery, not yet written.
- **drafted** — notebook exists in the repo, may need polish.
- **published** — rendered cleanly in the live docs and reviewed.
- **aspirational** — wanted, but blocked on something (paper figures finalised, upstream model release, etc.).

When you finish an entry, change `**stub**` → `**drafted**` in the table above; when you've reviewed the rendered HTML, `**drafted**` → `**published**`.

## Hidden toctree

The toctree below registers every gallery entry's notebook with Sphinx so the cross-references and search index work. Add a new line per notebook as it lands.

```{toctree}
:maxdepth: 1
:hidden:

```

<!-- TODO: replace the empty toctree above with `gallery/quickstart/<entry>` etc. as notebooks land. -->
