# Benchmarking

> **Status: work in progress.** No benchmarks have actually been run yet. This page documents the *plan* for how volcatenate will validate its wrapper output against each backend's published model outputs, the reference parameters we intend to use, and the open questions about each backend's reproducibility. The configuration values listed here are taken from the cited publications and the corresponding source repositories; **none of them have been executed through volcatenate and compared to a published figure**. Treat every "match against the paper" claim below as pending verification until this notice is removed.

## What a benchmark means here

A volcatenate "benchmark" is a single named run that:

1. Takes the exact parameter set that produced a figure in the relevant model's primary publication (or the figure's supplement, where the paper points there).
2. Runs that parameter set through volcatenate's wrapper of that backend.
3. Compares the standardized output (volcatenate's column-renamed DataFrame) against the corresponding published curve, point set, or table.
4. Records the deviation: ideally a quantitative metric (e.g. max relative error in saturation pressure, max absolute error in S6+/S_total along a degassing path), but at minimum a visual overlay.

The goal is not novelty — it is to confirm that volcatenate's wrapping layer does not silently change a backend's published behavior. If a benchmark fails, the cause is one of:

- A wrapper bug in volcatenate (composition handed off in the wrong shape, unit confusion, column rename collision, etc.).
- A version drift between the upstream backend revision the paper used and the revision pinned by [`TESTED_*_VERSION`](https://github.com/kaylai/volcatenate/blob/main/src/volcatenate/versions.py) in volcatenate.
- A genuinely under-specified parameter in the source publication.

Each of these is actionable in a different way, so the benchmark output should make the distinction visible.

## Per-backend reference parameters

### SulfurX — Ding et al. (2023) Fuego and Mauna Kea

**Source:** Ding, S., Plank, T., Wallace, P. J., & Rasmussen, D. J. (2023). Sulfur_X: A model of sulfur degassing during magma ascent. *Geochemistry, Geophysics, Geosystems*, 24, e2022GC010552. [https://doi.org/10.1029/2022GC010552](https://doi.org/10.1029/2022GC010552). Parameters below are from **Supporting Information Table S.1** ("Inputs for Fuego and Mauna Kea examples").

The Fuego figures appear as Figure 6 (S–CO₂ and S–H₂O degassing), Figure 7 (S, CO₂, H₂O versus pressure with all three S-Fe speciation models), and Figure 8 (S, fugacities, and molar species comparison to D-Compress) in §4.1 of the main paper. The Mauna Kea figures are in §4.2. Each table column below lists the SulfurX variable name (matching the paper's nomenclature), the value, and the corresponding `SulfurXConfig` field in volcatenate.

| SulfurX variable | Fuego | Mauna Kea | `SulfurXConfig` field |
|---|---|---|---|
| `temperature` (°C) | 1030 | 1150 | `MeltComposition.T_C` (per-sample, not on the config) |
| `delta_FMQ` | 1.2 | 0.5 | `MeltComposition.dFMQ` (per-sample) |
| `H2O_initial` (wt.%) | 4.5 | 0.6 | `MeltComposition.H2O` (per-sample) |
| `CO2_initial` (ppm) | 3300 | 4000 | `MeltComposition.CO2` × 10⁴ (per-sample; CO₂ is wt% on the config) |
| `S_initial` (ppm) | 2650 | 1500 | `MeltComposition.S` × 10⁴ (per-sample) |
| `COH_model` | 1 | 0 | `coh_model` (see reproducibility note below) |
| `fO2_tracker` | 1 | 1 | `fo2_tracker` |
| `l` (pressure steps) | 300 | 600 | `n_steps` |
| `m` | 300 | 600 | (not exposed; `m == l` in volcatenate's wrapping) |
| `S_Fe_choice` | 1 | 6.3 | `s_fe_choice` |
| `sigma` | 0.01 | 0.01 | `sigma` |
| `slope_h2o` | −0.713 | (not specified) | `slope_h2o` |
| `constant_h2o` | 3.689 | (not specified) | `constant_h2o` |
| `INT` (paper) / `INC` (source) | — | 50 | `kd_low_p_increment` |
| `BAR` (MPa) | 0 | 5 | `kd_low_p_threshold_mpa` |

**Key observations for Fuego:**

- `BAR = 0` means the low-pressure kd override is disabled for the Fuego run. `INT` is left blank in Table S.1 because it has no effect when `BAR = 0`. Any oscillations in the last few pressure steps of a Fuego reproduction will need to be addressed via the other tuning levers documented in §S1.5.3 of the supplement (smaller `sigma`, finer `l`, or terminating the run at higher pressure) rather than via INC/BAR.
- `S_Fe_choice = 1` (O'Neill & Mavrogenes 2022) is the S-Fe speciation model used for the canonical Fuego figures. Figures showing the Nash and Muth & Wallace speciation curves use the same other parameters with only `S_Fe_choice` changed.

**Key observations for Mauna Kea:**

- `BAR = 5 MPa` and `INT = 50` mean the low-pressure kd override **is** active for Mauna Kea below 5 MPa, and uses an increment of 50 (not the shipped default of 20).
- `S_Fe_choice = 6.3` is a non-integer value, which means SulfurX uses the "modified Muth & Wallace" branch with `6.3` substituted for the final constant in the model equation. The volcatenate field is type-hinted as `int` but accepts and forwards `float` values unchanged (see `SulfurXConfig` documentation for details).

> **Reproducibility note: COH solubility model selection.** Section 4.1 of the main paper describes the Fuego degassing run as using the COH degassing model of Iacono-Marziano et al. (2012). Table S.1 of the supplement lists `COH_model = 1` for Fuego, which corresponds to the VolatileCalc parameterisation (Newman & Lowenstern, 2002) per the supplement's own §S1.2.1 description and per the conditional in `degassingrun.py`. The volcatenate benchmark uses `coh_model = [TODO]` to match `[TODO: either Table S.1 or §4.1 figures]`. *This benchmark has not yet been run; the parameter selection is pending verification against published outputs.*

> **Note on `main_Fuego.py` defaults.** The `main_Fuego.py` script shipped in the SulfurX repository sets `l = 600` and `sigma = 0.005` at the top of the file, while Table S.1 of the supplement lists `l = 300` and `sigma = 0.01` for the Fuego run. Running the shipped script unchanged therefore won't reproduce the published Fuego figures exactly. Either set is internally self-consistent — `l` and `sigma` together control the trade-off between pressure-step granularity and per-step solver tolerance — but the supplement values are the canonical ones for reproducing the paper. *This observation is based on file inspection; a side-by-side run comparing the two parameter sets has not yet been done.*

### VESIcal — [TODO]

**Source:** [TODO — Iacono-Marziano et al. (2012); Newman & Lowenstern (2002); Dixon (1997); Liu et al. (2005); MagmaSat / Ghiorso & Gualda (2015) as applicable; cite the figure-set we are reproducing].

| VESIcal variable | Value | `VESIcalConfig` field |
|---|---|---|
| `[TODO]` | `[TODO]` | `[TODO]` |

*Benchmark not yet defined.*

### VolFe — [TODO]

**Source:** [TODO — Hughes et al. (2023, 2024); cite the figure-set we are reproducing].

| VolFe variable | Value | `VolFeConfig` field |
|---|---|---|
| `[TODO]` | `[TODO]` | `[TODO]` |

*Benchmark not yet defined.*

### EVo — [TODO]

**Source:** [TODO — Liggins et al. (2022); cite the figure-set we are reproducing].

| EVo variable | Value | `EVoConfig` field |
|---|---|---|
| `[TODO]` | `[TODO]` | `[TODO]` |

*Benchmark not yet defined.*

### MAGEC — [TODO]

**Source:** [TODO — Burgisser & Scaillet (2024) or equivalent; cite the figure-set we are reproducing].

| MAGEC variable | Value | `MAGECConfig` field |
|---|---|---|
| `[TODO]` | `[TODO]` | `[TODO]` |

*Benchmark not yet defined.*

### D-Compress

D-Compress integration in volcatenate is currently a stub. No benchmark planned until the integration is in place.

## Status

| Backend | Reference identified | Parameters recorded | Run executed | Output compared |
|---|---|---|---|---|
| SulfurX (Fuego) | ✓ Ding et al. (2023) Table S.1 | ✓ above | ✗ | ✗ |
| SulfurX (Mauna Kea) | ✓ Ding et al. (2023) Table S.1 | ✓ above | ✗ | ✗ |
| VESIcal | ✗ | ✗ | ✗ | ✗ |
| VolFe | ✗ | ✗ | ✗ | ✗ |
| EVo | ✗ | ✗ | ✗ | ✗ |
| MAGEC | ✗ | ✗ | ✗ | ✗ |
| D-Compress | n/a — integration stub | n/a | n/a | n/a |

When a benchmark is executed and the output compared, this table is the canonical place to update its status. Add a short note (one or two sentences) below the table summarising the deviation observed and whether it was attributed to wrapper, version, or specification.
