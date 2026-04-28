# How YAML config fields propagate into each backend

This is a plain-English reference explaining what each setting in your volcatenate YAML config actually *does* once it reaches the underlying model. It complements [configuration.md](configuration.md) (which documents the YAML structure) and the hidden-values audit kept in the project's internal notes (which lists every value that volcatenate hardcodes or pulls silently from the sample composition).

The doc is organized one backend per section, ordered from simplest to most involved:

1. [VESIcal](#vesical)
2. [VolFe](#volfe)
3. [EVo](#evo)
4. [MAGEC](#magec)
5. [SulfurX](#sulfurx)

Each section has the same structure:

- **Where the YAML lands** — the full call chain from YAML to backend.
- **Field-by-field table** — what each setting actually does to the calculation.
- **Hidden behaviors** — things volcatenate hardcodes or pulls from the `MeltComposition`, that you can't see in the YAML.
- **Fallback chains** — what happens when the option you picked doesn't have a matching value on the sample.

Throughout, when you see a redox indicator referenced in plain English:

- **Fe3+/FeT** — the ferric ratio of total iron in the melt; a direct measurement-derived number.
- **dFMQ** — log fO2 relative to the FMQ (fayalite-magnetite-quartz) buffer at the same T (and usually 1 bar).
- **dNNO** — log fO2 relative to the NNO (nickel-nickel oxide) buffer.

---

## What gets pulled from the sample, in every backend

Before diving in, here is the universal rule: **the sample composition provided via CSV or `MeltComposition` is always the source of truth for chemistry**, and the YAML config never shadows it. Specifically, across every backend the following come from the sample, not the YAML:

| Source on `MeltComposition`                                                         | Used as                                                                                                                                                                                                                |
| ------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `T_C`                                                                               | Temperature for every backend (converted to Kelvin where needed).                                                                                                                                                      |
| `SiO2`, `TiO2`, `Al2O3`, `Cr2O3`, `MnO`, `MgO`, `CaO`, `Na2O`, `K2O`, `P2O5` | Major-oxide chemistry. (`Cr2O3` is read by MAGEC; the other backends ignore it.)                                                                                                                                          |
| `FeOT`                                                                              | Total iron, split into FeO/Fe2O3 by each backend's own iron-redox handling (see [composition.py:55](../src/volcatenate/composition.py)).                                                                              |
| `H2O` (wt%)                                                                         | Bulk H₂O, taken in as the neutral oxide H₂O (not as separate H2 / H₂O molecular / CH₄ melt species). Whether a backend then re-speciates it internally depends on the backend logic and on the user's COH-species setting.        |
| `CO2` (wt%)                                                                         | Bulk CO2, taken in as neutral CO2.                                                                                                                                                                                     |
| `S` (wt%)                                                                           | Bulk sulfur, taken in as elemental S.                                                                                                                                                                                  |
| `Fe3FeT`, `dNNO`, `dFMQ`                                                        | Redox indicators. Whether a given backend uses Fe3+/FeT, dNNO, or dFMQ is controlled by a per-backend YAML setting — see each backend's "Field-by-field" table for the exact setting name and the per-backend fallback chain. |
| `Xppm`                                                                              | "Other" trace species (Ar/Ne) — VolFe only.                                                                                                                                                                           |

Volcatenate consumes the volatile fields in different units depending on the backend: VolFe and SulfurX want CO2 and S in ppm, so the wrapper multiplies the wt% values by 10000 before passing them in; EVo wants mass fractions, so the wrapper divides the wt% values by 100; H2O is passed in as wt% directly to all backends that want it, except that EVo's H2O is also divided by 100 to a mass fraction. None of these rescalings change the underlying meaning — they are just the unit each backend's input format expects.

Per-backend redox-indicator preference is controlled by these YAML fields: `evo.fo2_source` (auto / fe3fet / buffer / absolute); `volfe.fo2_column` (DNNO/Fe3FeT/DFMQ) plus `volfe.fo2_source` (auto / fe3fet / dnno / dfmq); `magec.redox_option` (logfO2 / dFMQ / Fe3+/FeT / S6+/ST) plus `magec.redox_source` (auto / fe3fet / dfmq / dnno / kc91_from_buffer); SulfurX has no equivalent setting — it always tries `dFMQ` first, then Fe3+/FeT (via KC91 inversion at 1 bar), then `dNNO` (via Frost-1991 buffer offset).

When a wrapper says "from the composition," that's where it comes from.

### Logging

The volcatenate log file (`RunConfig.log_file`) is truncated on the first call within a Python process and **appended** thereafter, so multiple `calculate_*` calls in the same notebook accumulate into one log instead of clobbering each other. To restart from a clean file mid-session, call `volcatenate.log.reset_log_file_tracking()` before the next call.

### Output CSV schema

The DataFrames returned by `calculate_degassing` and friends contain a fixed set of columns ([`columns.STANDARD_COLUMNS`](../src/volcatenate/columns.py)). When backends produce extra intermediate columns (e.g. MAGEC's `Run_ID`, `_sample`), those are stripped on write via [`convert.to_standard_schema`](../src/volcatenate/convert.py), which is wired into `export_degassing_paths` so the on-disk CSV is always the canonical schema.

---

## VESIcal

VESIcal is the simplest backend — it models only H₂O–CO₂ degassing (no sulfur, no Fe redox), so the wrapper is short and the YAML surface is tiny.

### Where the YAML lands

```
volcatenate_config.yaml
  └── vesical:
       └── RunConfig.vesical (VESIcalConfig dataclass)
            └── Backend.calculate_degassing()
                 └── model.calculate_degassing_path()
```

Wrapper code: [backends/vesical.py](../src/volcatenate/backends/vesical.py).

The "VESIcal model" being used (Dixon, Iacono-Marziano, MagmaSat, …) is **not** controlled by the YAML — it's selected by the **backend name** you pass to `calculate_degassing` / `run_comparison`, e.g. `models=["VESIcal_Iacono"]`. See the `VARIANT_MAP` at [backends/vesical.py:28](../src/volcatenate/backends/vesical.py).

### Field-by-field

| YAML key              | What it does (plain English)                                                                                                                                                                         | Backend option                                           | Gotchas                                                                                       |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `steps`             | How many pressure steps in the degassing path. More steps = smoother curves but slower.                                                                                                              | `model.calculate_degassing_path(steps=…)`             | VESIcal divides the (P_sat → final_pressure) range into this many steps. 101 is the default. |
| `final_pressure`    | The pressure (bar) at which the degassing run ends.                                                                                                                                                  | `model.calculate_degassing_path(final_pressure=…)`    | Set this to ~1 bar for full atmospheric degassing, or higher to stop early.                   |
| `fractionate_vapor` | A number between 0 and 1: what fraction of vapor is removed from the melt at each step. `0` = closed-system (vapor stays in equilibrium), `1` = open-system (vapor is fully extracted each step). | `model.calculate_degassing_path(fractionate_vapor=…)` | Intermediate values are physically unusual but allowed.                                       |
| `overrides`         | Per-sample dict of any of the above fields, e.g. `{Fogo: {steps: 50}}`.                                                                                                                             | (resolved in `resolve_sample_config`)                  | Unknown field names are warned and ignored.                                                   |

### Hidden behaviors

- **Variant selection**: the actual VESIcal solubility model is chosen by the *backend name*, not by config. E.g. `"VESIcal_Iacono"` → `"IaconoMarziano"`, `"VESIcal_MS"` → `"MagmaSat"`. See `VARIANT_MAP` at [backends/vesical.py:28](../src/volcatenate/backends/vesical.py).
- **Saturation pressure calls always use `pressure="saturation"`** — i.e. VESIcal computes the starting pressure itself from the sample's H₂O+CO₂. There is no way to ask for a fixed starting P.
- **Iron is sent both ways** ([backends/vesical.py:163-167](../src/volcatenate/backends/vesical.py)): if the sample provides speciated `FeO` and `Fe2O3`, both are sent; otherwise FeOT is sent as `FeO`. This matters only for MagmaSat, which uses Fe redox internally.
- **Warnings are silenced** during the run with `warnings.simplefilter("ignore")` ([backends/vesical.py:86](../src/volcatenate/backends/vesical.py)) — VESIcal emits many petrological-range warnings that volcatenate suppresses to keep logs clean.

### Fallback chains

VESIcal does not use any of the redox indicators (`Fe3FeT`, `dFMQ`, `dNNO`) — it doesn't model fO2 except internally for MagmaSat. So there is no fallback chain to document.

---

## VolFe

VolFe is a Python C-O-H-S-Fe degassing model with a large set of toggles for solubility, fugacity, and equilibrium constants. Almost every YAML field maps 1-to-1 to a VolFe internal option name.

### Where the YAML lands

```
volcatenate_config.yaml
  └── volfe:
       └── RunConfig.volfe (VolFeConfig dataclass)
            ├── _build_setup_df()    → sample/composition + fO2 indicator
            └── _build_models_df()   → all the model-option toggles
                 └── vf.calc_gassing(setup_df, models=models_df)
```

Wrapper code: [backends/volfe.py](../src/volcatenate/backends/volfe.py).

### Field-by-field — VolFe

| YAML key                                                                                                                | What it does (plain English)                                                                                                                                                                                                                                                  | VolFe option                                                                                                                                            | Gotchas                                                                                                                           |
| ----------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `sulfur_saturation`                                                                                                   | If `true`, VolFe checks for sulfide/sulfate saturation at every pressure step and clips dissolved S to the SCSS/SCAS value when it would exceed it. If `false`, the bulk S is treated as a soluble component throughout.                                                  | `sulfur_saturation`                                                                                                                                   | Strongly affects the gas/melt sulfur partitioning when S is high.                                                                 |
| `graphite_saturation`                                                                                                 | Similar idea but for graphite — clips melt CO/CH4 if a graphite-saturation criterion is reached.                                                                                                                                                                             | `graphite_saturation`                                                                                                                                 | Most basaltic systems are not graphite-saturated; default `false` is usually right.                                             |
| `sulfur_is_sat`                                                                                                       | If `"yes"`, the melt is treated as already sulfur-saturated at the starting pressure (rather than approaching saturation only as P drops).                                                                                                                                  | `sulfur_is_sat`                                                                                                                                       |                                                                                                                                   |
| `fo2_column`                                                                                                          | **Volcatenate-specific**, not a VolFe option. Tells the wrapper which redox indicator on the sample to send to VolFe. Choices: `'DNNO'`, `'Fe3FeT'`, `'DFMQ'`.                                                                                                    | (drives `_build_setup_df`)                                                                                                                            | Has a fallback chain — see below. The chosen column becomes a column in the VolFe input DataFrame.                               |
| `fo2_source`                                                                                                          | Strictness for the choice above. `'auto'` falls through Fe3+/FeT → dNNO → dFMQ when the requested column is missing (logged at INFO each time). `'fe3fet'`/`'dnno'`/`'dfmq'` raise `ValueError` if the named column is missing on the sample.                          | (drives `_resolve_volfe_redox`)                                                                                                                       | Use a strict mode in batch runs to fail loudly instead of silently selecting a different redox path.                              |
| `gassing_style`                                                                                                       | `'closed'` keeps the exsolved vapor in equilibrium with the melt at every step; `'open'` removes the vapor instantly each step.                                                                                                                                           | `gassing_style`                                                                                                                                       | `open` produces lower vapor S/C ratios as light volatiles escape early.                                                         |
| `gassing_direction`                                                                                                   | `'degas'` runs P from saturation downward (normal eruptive path). `'regas'` runs upward — useful for testing what happens during recompression.                                                                                                                          | `gassing_direction`                                                                                                                                   | Almost always `degas` for natural studies.                                                                                      |
| `bulk_composition`                                                                                                    | What "bulk" composition VolFe initializes with. `'melt-only'` = the sample melt, with vapor appearing as P drops. `'melt+vapor_wtg'` = melt + a fixed weight fraction of pre-existing vapor. `'melt+vapor_initialCO2'` = melt + vapor that holds a specific initial CO2. | `bulk_composition`                                                                                                                                    | Pre-existing vapor changes total volatile budget; only matters for unusual cases where you have evidence of pre-segregated vapor. |
| `starting_p`                                                                                                          | `'Pvsat'` (the default) starts the run at the saturation pressure VolFe finds itself; `'set'` switches VolFe into a user-supplied-starting-P mode, but volcatenate does not currently expose the actual starting P value, so `'set'` is only useful in combination with VolFe's own defaults.                                                                                                                    | `starting_P`                                                                                                                                          |                                                                                                                                   |
| `p_variation`                                                                                                         | `'polybaric'` (P varies through the run, normal degassing) or `'isobaric'`.                                                                                                                                                                                               | `P_variation`                                                                                                                                         |                                                                                                                                   |
| `t_variation`                                                                                                         | `'isothermal'` (T held fixed) or `'polythermal'`.                                                                                                                                                                                                                            | `T_variation`                                                                                                                                         |                                                                                                                                   |
| `eq_fe`                                                                                                               | `'yes'` enforces Fe redox equilibrium with fO2 each pressure step (fO2 from `mdv.f_O2`, Fe3+/FeT recomputed each step, [VolFe/calculations.py:435]). `'no'` freezes Fe and takes fO2 from the gas.                                                                       | `eq_Fe`                                                                                                                                               | For natural degassing studies, `'yes'` is essentially always correct.                                                           |
| `bulk_o`                                                                                                              | `'exc_S'` (default) excludes sulfur-bound oxygen from bulk-O accounting; `'inc_S'` includes it. Affects how O budgets are tracked but not the gas-melt thermodynamic equilibrium.                                                                                          | `bulk_O`                                                                                                                                              |                                                                                                                                   |
| `calc_sat`                                                                                                            | Saturation-pressure search mode. `'fO2_melt'` (default) drives the satP root-find via melt fO2; `'fO2_fX'` uses the X species fugacity instead.                                                                                                                            | `calc_sat`                                                                                                                                            |                                                                                                                                   |
| `crystallisation`                                                                                                     | `'no'` (default) or `'yes'` — track crystallization during degassing.                                                                                                                                                                                                     | `crystallisation`                                                                                                                                     |                                                                                                                                   |
| `coh_species`                                                                                                         | Which C-O-H species VolFe carries in melt and vapor. `'yes_H2_CO_CH4_melt'` = full speciation including H2, CO, CH4 dissolved in the melt. `'no_H2_CO_CH4_melt'` = only CO2/H2O in the melt (others only in vapor). `'H2O-CO2 only'` = strictly two-component.           | `COH_species`                                                                                                                                         | Affects redox-sensitive volatile speciation, especially at reduced fO2.                                                           |
| `h2s_melt`                                                                                                            | If `true`, treats H2Smol as a dissolved melt species (not just in vapor).                                                                                                                                                                                                   | `H2S_m`                                                                                                                                               | Generally `true` for proper sulfur mass balance below ~FMQ.                                                                     |
| `species_x`                                                                                                           | Identity of the inert "X" trace species: `'Ar'` or `'Ne'`. Only used if your sample has a non-zero `Xppm`.                                                                                                                                                               | `species X`                                                                                                                                           | Default sample data has Xppm=0, so this is moot unless you supply it.                                                             |
| `h_speciation`                                                                                                        | H melt speciation submodel. Currently only `"none"` is supported by VolFe (kept here so users can see it exists).                                                                                                                                                          | `Hspeciation`                                                                                                                                         |                                                                                                                                   |
| `density`                                                                                                             | Melt density model used for mass↔volume bookkeeping inside VolFe.                                                                                                                                                                                                          | `density`                                                                                                                                             |                                                                                                                                   |
| `melt_composition`                                                                                                    | Melt-composition family for parameterizations (e.g. `'Basalt'`).                                                                                                                                                                                                           | `melt composition`                                                                                                                                    |                                                                                                                                   |
| `fo2_model`                                                                                                           | The fO2 ↔ Fe3+/FeT relationship: `'Kress91A'` (default), `'Kress91'`, `'ONeill18'`, `'Borisov18'`.                                                                                                                                                                      | `fO2`                                                                                                                                                 | Small (~0.1 log unit) differences between options for typical basalts.                                                            |
| `fmq_buffer`                                                                                                          | Which equation defines FMQ for buffer-relative fO2: `'Frost91'` (default) or `'ONeill87'`. Matters when the sample provides DFMQ.                                                                                                                                          | `FMQbuffer`                                                                                                                                           | Frost91 is what most modern data are reported relative to.                                                                        |
| `nno_buffer`                                                                                                          | Which equation defines NNO for buffer-relative fO2.                                                                                                                                                                                                                          | `NNObuffer`                                                                                                                                           |                                                                                                                                   |
| `co2_sol`, `h2o_sol`, `h2_sol`, `sulfide_sol`, `sulfate_sol`, `h2s_sol`, `ch4_sol`, `co_sol`, `x_sol` | Selects which solubility law VolFe uses for each volatile. Each takes a string like `'MORB_Dixon95'`, `'Basalt_Hughes24'`, `'ONeill21dil'`, etc.                                                                                                                        | `carbon dioxide`, `water`, `hydrogen`, `sulfide`, `sulfate`, `hydrogen sulfide`, `methane`, `carbon monoxide`, `species X solubility` | The choice of solubility model is often *the* dominant driver of inter-model disagreement. See VolFe docs for the full list.     |
| `c_spec_comp`, `h_spec_comp`                                                                                        | "Speciation composition" choices for CO2-mol/CO3²⁻ (`Cspeccomp`) and H2Omol/OH (`Hspeccomp`). They control which composition-dependent expressions are used to split molecular vs ionic dissolved species.                                                              | `Cspeccomp`, `Hspeccomp`                                                                                                                            | Mostly cosmetic for total-volatile budgets.                                                                                       |
| `scss`, `scas`                                                                                                      | Sulfide-saturation (`SCSS`) and anhydrite/sulfate-saturation (`SCAS`) models. Strings like `'ONeill21hyd'`, `'Zajacz19_pss'`. Only consulted when `sulfur_saturation=true`.                                                                                         | `SCSS`, `SCAS`                                                                                                                                      | If `sulfur_saturation=false`, the value is sent to VolFe but never used.                                                        |
| `ideal_gas`                                                                                                           | If `true`, ALL fugacity coefficients (y_*) are forced to 1 (vapor treated as ideal).                                                                                                                                                                                        | `ideal_gas`                                                                                                                                           | A good sanity-check at low pressure; spurious at high P.                                                                          |
| `y_co2`, `y_so2`, `y_h2s`, `y_h2`, `y_o2`, `y_s2`, `y_co`, `y_ch4`, `y_h2o`, `y_ocs`, `y_x`              | Per-species fugacity-coefficient model. e.g. `'Shi92'` = Shi & Saxena 1992, `'Holland91'` = Holland & Powell 1991.                                                                                                                                                        | `y_CO2`, `y_SO2`, etc.                                                                                                                              | Overridden if `ideal_gas=true`.                                                                                                 |
| `k_hog`, `k_hosg`, `k_osg`, `k_osg2`, `k_cog`, `k_cohg`, `k_ocsg`, `k_cos`                              | Equilibrium-constant models for the gas-phase reactions: H2 + ½O2 = H2O, ½S2 + H2O = H2S + ½O2, ½S2 + O2 = SO2, the sulfate equilibrium, CO + ½O2 = CO2, CH4 + 2O2 = CO2 + 2H2O, OCS, and the carbonate solubility eq.                                                  | `KHOg`, `KHOSg`, `KOSg`, `KOSg2`, `KCOg`, `KCOHg`, `KOCSg`, `KCOs`                                                            | Multiple-choice strings, e.g. `'Ohmoto97'`, `'Moussallam19'`, `'ONeill22'`.                                                  |
| `carbonylsulfide`                                                                                                     | Name of the OCS species in VolFe's vapor list (default `'COS'`).                                                                                                                                                                                                            | `carbonylsulfide`                                                                                                                                     |                                                                                                                                   |
| `isotopes`                                                                                                            | `'no'` (default) skips isotope tracking; `'yes'` activates the isotope solver (then the `alpha_*` and `beta_factors` fields below matter).                                                                                                                              | `isotopes`                                                                                                                                            |                                                                                                                                   |
| `beta_factors`, `alpha_h_*`, `alpha_c_*`, `alpha_s_*`, `alpha_so2_so4`, `alpha_h2s_s`                       | Beta factors and isotope α model identifiers (e.g. `'Rust04'`, `'Lee24'`). Only used when `isotopes='yes'`.                                                                                                                                                            | `beta_factors`, `alpha_*`                                                                                                                         |                                                                                                                                   |
| `error`, `high_precision`                                                                                         | Numerical tolerance for the solver and a flag to run in slower-but-tighter precision mode.                                                                                                                                                                                   | `error`, `high precision`                                                                                                                           |                                                                                                                                   |
| `overrides`                                                                                                           | Per-sample overrides as `{sample: {field: value}}`.                                                                                                                                                                                                                         | (resolved in `resolve_sample_config`)                                                                                                                 | Unknown field names are warned and ignored.                                                                                       |

### Hidden behaviors — VolFe

These are sent to VolFe by volcatenate but are **not** in the YAML. They are hardcoded in [backends/volfe.py:_build_models_df](../src/volcatenate/backends/volfe.py) or fall through to VolFe's built-in defaults via `vf.make_df_and_add_model_defaults`.

| VolFe option       | volcatenate value | Meaning                                                                                                                                                                                                                                  |
| ------------------ | ----------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `output csv`     | `"False"`       | volcatenate handles output itself; tells VolFe not to write CSVs.                                                                                                                                                                        |
| `print status`   | `"False"`       | Tells VolFe not to print progress; volcatenate captures stdout via `_quiet_volfe()`.                                                                                                                                                   |
| `solve_species`  | (left to default) | Internal solver hint that VolFe re-sets during the calculation ([equilibrium_equations.py:39-60]), so any user-set value would be clobbered. Volcatenate keeps it out of the YAML to make this clear.                                  |
| `mass_volume`    | `"mass"`        | The `"volume"` branch is marked NEEDS FIXING upstream and is unsafe to expose; volcatenate pins this to `"mass"`.                                                                                                                    |
| `setup`          | (left to default) | Debug-only flag.                                                                                                                                                                                                                         |

#### What gets pulled from the sample

In `_build_setup_df` ([backends/volfe.py:173](../src/volcatenate/backends/volfe.py)):

- `Sample`, `T_C`, all major oxides (incl. `FeOT`), `H2O` (wt%), `CO2ppm` (= CO2_wt% × 10000), `STppm` (= S_wt% × 10000), `Xppm` are all read directly from the `MeltComposition`.
- The fO2 indicator column (`Fe3FeT` / `DNNO` / `DFMQ`) is added according to `cfg.fo2_column` and `cfg.fo2_source` per the fallback chain below.

### Fallback chain — VolFe fO2 column

Logic at [backends/volfe.py:_resolve_volfe_redox](../src/volcatenate/backends/volfe.py):

In **`fo2_source="auto"`** mode (the default), the wrapper first tries to honor `fo2_column`. If the requested column is missing on the sample, it falls back through Fe3+/FeT → dNNO → dFMQ in that order, **logging the choice at INFO** so the path is visible in the log file:

1. If `fo2_column == "DNNO"` and the sample has `dNNO` → send `DNNO`.
2. If `fo2_column == "DFMQ"` and the sample has `dFMQ` → send `DFMQ`.
3. If `fo2_column == "Fe3FeT"` and the sample has Fe3+/FeT (speciated or explicit) → send `Fe3FeT`.
4. Otherwise: try Fe3+/FeT, then `dNNO`, then `dFMQ` — first hit wins, with an INFO line naming the fallback.
5. If none are available: raise `ValueError`.

In **strict modes** (`fo2_source="fe3fet"`, `"dnno"`, `"dfmq"`), the wrapper requires that exact source on the sample and raises `ValueError` if it is missing — there is no silent substitution.

---

## EVo

EVo is run via three YAML files (`chem.yaml`, `env.yaml`, `output.yaml`) that volcatenate writes to a per-sample work directory, then calls `evo.run_evo()` on. EVo prints prolifically to stdout, so volcatenate wraps the call in a `_quiet_evo()` context that routes everything to the logger at DEBUG level.

### Where the YAML lands

```
volcatenate_config.yaml
  └── evo:
       └── RunConfig.evo (EVoConfig dataclass)
            └── _write_yaml_configs()
                 ├── chem.yaml   (oxides + Fe split)
                 ├── env.yaml    (run options + volatiles + fO2)
                 └── output.yaml (plot toggles, all False)
                      └── evo.run_evo(chem, env, output)
```

Wrapper code: [backends/evo.py](../src/volcatenate/backends/evo.py).

### Field-by-field — EVo

The columns "Backend option" use the *exact* key written into `env.yaml` (or `chem.yaml`), since that's the file EVo reads.

| YAML key                                               | What it does (plain English)                                                                                                                                                                                                                                                                       | env.yaml key                                           | Gotchas                                                                                                                                                 |
| ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `gas_system`                                         | Which gas species are tracked. `'cohs'` = full C-O-H-S system. Other choices include `'coh'` (no sulfur), `'cos'`, `'cohsn'` (with N).                                                                                                                                                       | `GAS_SYS`                                            | Reducing the system (e.g. `'coh'`) is faster but obviously omits S.                                                                                   |
| `composition`                                        | EVo's composition family — `'basalt'`, `'phonolite'`, or `'rhyolite'`. Drives EVo's SiO2-range sanity check ([EVo/readin.py:212-217]) and the K_HOSg / K_OSg branch ([EVo/dgs_classes.py:693-723]) which selects coefficients per composition.                                              | `COMPOSITION`                                        | `basalt` = SiO2 in 45–55%; `phonolite` = 52–63%; `rhyolite` = 65–80%. If your sample's SiO2 is out of range, EVo would normally ask "continue?" — volcatenate auto-answers yes via `_auto_yes`. |
| `fo2_buffer`                                         | Which buffer EVo uses when fO2 is set as an offset. `'FMQ'`, `'NNO'`, `'IW'`, …                                                                                                                                                                                                              | `FO2_buffer`                                         | Only relevant when `fo2_source="auto"` falls back to a buffer, or when `fo2_source="buffer"`. Has no effect when Fe3+/FeT data is present.            |
| `fe_system`                                          | If `true`, EVo iterates Fe redox equilibrium with fO2 at every step (analogous to VolFe `eq_Fe="yes"`). If `false`, Fe is held fixed.                                                                                                                                                          | `FE_SYSTEM`                                          | `true` is the realistic choice.                                                                                                                       |
| `find_saturation`                                    | If `true`, EVo computes its starting pressure itself from the bulk volatiles (saturation pressure). If `false`, EVo starts at `p_start` and assumes that's correct.                                                                                                                            | `FIND_SATURATION`                                    | Default `true` is what you almost always want.                                                                                                        |
| `single_step`                                        | Single-pressure run (only meaningful when `find_saturation=False`).                                                                                                                                                                                                                                | `SINGLE_STEP`                                        | Default `False`.                                                                                                                                      |
| `s_sat_warn`                                         | If `true`, EVo prints its own warning when sulfide saturation is reached (volcatenate routes this through the logger). Default `false` silences it.                                                                                                                                              | `S_SAT_WARN`                                         |                                                                                                                                                         |
| `atomic_mass_set`                                    | If `true`, ignore the wt% volatiles in chem.yaml and use the `atomic_h/c/s/n` ppm values instead. If `false`, use the sample's H2O/CO2/S directly.                                                                                                                                             | `ATOMIC_MASS_SET`                                    | Volcatenate users should leave this `false` — the H2O/CO2/S of the sample is what we want.                                                           |
| `ocs`                                                | Include OCS as a vapor species (`true`) or not (`false`).                                                                                                                                                                                                                                          | `OCS`                                                | Adds a coupling between C and S vapor; small effect except at low fO2.                                                                                  |
| `dp_min`, `dp_max`                                 | Minimum/maximum pressure step (bar) the adaptive integrator will take.                                                                                                                                                                                                                             | `DP_MIN`, `DP_MAX`                                 | Smaller `dp_max` = smoother curves, slower runs.                                                                                                      |
| `mass`                                               | System mass (g) — total bulk mass for mass-balance bookkeeping.                                                                                                                                                                                                                                   | `MASS`                                               | Almost always 100 g (the default); doesn't affect intensive results, only the absolute mass of vapor produced.                                          |
| `p_start`                                            | Starting pressure (bar). Only used if `find_saturation=false`. Otherwise EVo computes its own start.                                                                                                                                                                                              | `P_START`                                            | Set well above expected satP if you're not auto-finding.                                                                                                |
| `p_stop`                                             | Final pressure (bar).                                                                                                                                                                                                                                                                              | `P_STOP`                                             | Default 1 bar = atmospheric.                                                                                                                            |
| `wgt`                                                | Initial gas weight fraction (≈ 1e-5). EVo seeds an infinitesimal vapor phase to start the iteration.                                                                                                                                                                                              | `WgT`                                                | Numerical seed; rarely needs changing.                                                                                                                  |
| `loss_frac`                                          | For open-system runs (`run_type=open`): fraction of vapor *retained* per step. `0.9999` (default) means almost everything is kept (≈ closed); `0.0` would mean perfect vapor stripping.                                                                                                       | `LOSS_FRAC`                                          | Confusingly named — read it as "fraction of vapor that stays in equilibrium with the melt for one more step."                                          |
| `run_type`                                           | `'closed'` or `'open'`. Open-system requires `loss_frac < 1`.                                                                                                                                                                                                                                  | `RUN_TYPE`                                           | For saturation-pressure runs the wrapper hardcodes `run_type="closed"` regardless of config ([backends/evo.py:132](../src/volcatenate/backends/evo.py)). |
| `atomic_h`, `atomic_c`, `atomic_s`, `atomic_n` | Atomic-mass-fraction (ppm) volatile budgets. Only used when `atomic_mass_set=true`.                                                                                                                                                                                                              | `ATOMIC_H`, `ATOMIC_C`, `ATOMIC_S`, `ATOMIC_N` | Default values are placeholders.                                                                                                                        |
| `nitrogen_set`, `nitrogen_start`                 | If `nitrogen_set=true`, EVo adds N as a tracked species; `nitrogen_start` is the starting N mass fraction (default `1e-4`, a tiny seed).                                                                                                                                                       | `NITROGEN_SET`, `NITROGEN_START`                 |                                                                                                                                                         |
| `graphite_saturated`, `graphite_start`           | If `graphite_saturated=true`, EVo starts the system as graphite-saturated; `graphite_start` is the starting graphite mass fraction.                                                                                                                                                            | `GRAPHITE_SATURATED`, `GRAPHITE_START`           | Use only when you really mean it; rare for natural basalts.                                                                                           |
| `fo2_source`                                         | How the starting fO2 is set. `'auto'` (default) prefers Fe3+/FeT, falls back to dNNO/dFMQ buffer with offset, then to `fo2_buffer` at offset 0 — every choice logged at INFO. `'fe3fet'` requires Fe3+/FeT on the sample (raises if missing). `'buffer'` requires the matching `dNNO` / `dFMQ` offset. `'absolute'` sets fO2 to `fo2_start` (in bar) via `FO2_SET=True`. | (drives `FO2_buffer_SET`, `FO2_SET`, `FO2_START`) | In `'absolute'` mode the wrapper does **not** split FeOT into FeO+Fe2O3 in chem.yaml — EVo refuses both at once.                                  |
| `fo2_set`, `fo2_start`                           | Absolute-fO2 entry point. Only consulted when `fo2_source='absolute'`; in that mode `fo2_set` must be `true` and `fo2_start` > 0 (bar).                                                                                                                                                  | `FO2_SET`, `FO2_START`                           |                                                                                                                                                         |
| `fh2_set`, `fh2_start`                           | Set H2 fugacity as an explicit starting condition. Default `false` (EVo derives H2 from H2O+fO2).                                                                                                                                                                                                | `FH2_SET`, `FH2_START`                           |                                                                                                                                                         |
| `fh2o_set`, `fh2o_start`                         | Set H2O fugacity as an explicit starting condition.                                                                                                                                                                                                                                                | `FH2O_SET`, `FH2O_START`                         |                                                                                                                                                         |
| `fco2_set`, `fco2_start`                         | Set CO2 fugacity as an explicit starting condition.                                                                                                                                                                                                                                                | `FCO2_SET`, `FCO2_START`                         |                                                                                                                                                         |
| `h2o_model`                                          | Which H2O solubility law EVo uses. e.g. `'burguisser2015'`.                                                                                                                                                                                                                                       | `H2O_MODEL`                                          | High-leverage choice — different models give meaningfully different H2O contents at the same P.                                                        |
| `h2_model`                                           | H2 solubility law. e.g. `'gaillard2003'`.                                                                                                                                                                                                                                                         | `H2_MODEL`                                           | Only matters at reduced fO2 where H2 in the melt is non-trivial.                                                                                        |
| `c_model`                                            | CO2/CO3²⁻ solubility law. e.g. `'burguisser2015'`.                                                                                                                                                                                                                                              | `C_MODEL`                                            | Set to match `h2o_model` from the same paper for consistency.                                                                                         |
| `co_model`                                           | CO solubility law. e.g. `'armstrong2015'`.                                                                                                                                                                                                                                                        | `CO_MODEL`                                           | Reduced-fO2 only.                                                                                                                                       |
| `ch4_model`                                          | CH4 solubility law. e.g. `'ardia2013'`.                                                                                                                                                                                                                                                           | `CH4_MODEL`                                          | Strongly reduced (below FMQ-2) or experimental settings.                                                                                                |
| `sulfide_capacity`                                   | Sulfide capacity model (controls how much S²⁻ the melt can hold). e.g. `'oneill2020'`.                                                                                                                                                                                                          | `SULFIDE_CAPACITY`                                   | Affects S degassing under reducing conditions.                                                                                                          |
| `sulfate_capacity`                                   | Sulfate capacity model. e.g. `'nash2019'`.                                                                                                                                                                                                                                                        | `SULFATE_CAPACITY`                                   | Affects S degassing under oxidising conditions.                                                                                                         |
| `scss`                                               | Sulfide-saturation model.                                                                                                                                                                                                                                                                          | `SCSS`                                               | If a sulfide phase is implied; gates how much S the melt can carry.                                                                                     |
| `n_model`                                            | Nitrogen solubility law. e.g. `'libourel2003'`.                                                                                                                                                                                                                                                   | `N_MODEL`                                            | Only used when `nitrogen_set=true`.                                                                                                                   |
| `density_model`                                      | Melt density model (used for converting mass ↔ volume in the bookkeeping).                                                                                                                                                                                                                        | `DENSITY_MODEL`                                      | Cosmetic for most outputs.                                                                                                                              |
| `fo2_model`                                          | fO2 ↔ Fe3+/FeT relationship. e.g. `'kc1991'` = Kress & Carmichael 1991.                                                                                                                                                                                                                          | `FO2_MODEL`                                          | Same role as VolFe `fo2_model`.                                                                                                                       |
| `fmq_model`                                          | Definition of the FMQ buffer (when fO2 is reported relative to FMQ). e.g. `'frost1991'`.                                                                                                                                                                                                          | `FMQ_MODEL`                                          |                                                                                                                                                         |
| `overrides`                                          | Per-sample overrides.                                                                                                                                                                                                                                                                              | (resolved in `resolve_sample_config`)                |                                                                                                                                                         |

### Hidden behaviors — EVo

In `_write_yaml_configs` at [backends/evo.py](../src/volcatenate/backends/evo.py):

| env.yaml key                                                 | volcatenate value                                               | Meaning                                                                                                                                                                                                                                          |
| ------------------------------------------------------------ | --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `RUN_TYPE`                                                 | `"closed"` for satP runs; `cfg.run_type` for degassing runs | Volcatenate forces `run_type="closed"` for the saturation-pressure call regardless of config, then honors `cfg.run_type` for the degassing run.                                                                                                |
| `WTH2O_SET`, `WTCO2_SET`, `SULFUR_SET`                 | `True`                                                        | Always; values come from `comp.H2O / 100`, `comp.CO2 / 100`, `comp.S / 100` (wt% → weight fraction).                                                                                                                                       |
| `WTH2O_START`, `WTCO2_START`, `SULFUR_START`           | computed from `MeltComposition`                               | See above.                                                                                                                                                                                                                                       |
| `T_START`                                                  | `comp.T_C + 273.15`                                           | Kelvin.                                                                                                                                                                                                                                          |
| `FO2_buffer_SET`, `FO2_SET`, `FO2_buffer_START`, `FO2_START` | computed from `cfg.fo2_source`                          | These four are populated together by `_resolve_fo2_source` based on `fo2_source` and the indicators on the sample. See the fallback section below.                                                                                                |

#### chem.yaml epsilon trick

When an oxide is exactly 0 in the sample, volcatenate writes `1e-10` instead, **because EVo's internal `single_cat()` silently drops keys with value 0**, and downstream functions then crash with KeyError on species like `mno`. See [backends/evo.py:403](../src/volcatenate/backends/evo.py). Result: even "absent" minor oxides are present at 1e-10 in the calculation. Effect on results is numerically negligible.

#### Iron split

In `chem.yaml`, FeOT is split into FeO + Fe2O3 using `comp.fe3fet_computed` ([backends/evo.py](../src/volcatenate/backends/evo.py)):

```
FEO   = FeOT * (1 - Fe3FeT)
FE2O3 = FeOT * Fe3FeT * (159.69 / (2 * 71.844))   # MW conversion
```

If `fe3fet_computed` is NaN (no redox indicator at all), the wrapper sends `FEO = FeOT, FE2O3 = 0`, leaving fO2 to be set by the buffer. If `fo2_source="absolute"`, the wrapper deliberately **skips** the split and sends `FEO = FeOT, FE2O3 = 0` even when Fe3+/FeT is available — EVo refuses to accept both `FO2_SET=True` and a non-zero Fe2O3 simultaneously ([EVo/readin.py:164]).

#### output.yaml

Always written with all five plot flags `False`. EVo's plotting is unused because volcatenate makes its own figures.

### Fallback chain — EVo fO2 source

`_resolve_fo2_source` at [backends/evo.py](../src/volcatenate/backends/evo.py) dispatches on `cfg.fo2_source`. `_pick_evo_buffer` is the auxiliary that selects between the NNO and FMQ offsets when a buffer path is taken.

In **`fo2_source="auto"`** mode (the default), the chain is:

1. If the sample has Fe3+/FeT (speciated FeO+Fe2O3 or explicit `Fe3FeT`) → drive fO2 via the iron split in chem.yaml. `FO2_buffer_SET=False`, `FO2_SET=False`. Logged at INFO.
2. Else if `comp.dNNO` is set → `FO2_buffer="NNO"`, `FO2_buffer_START=dNNO`. Logged at INFO.
3. Else if `comp.dFMQ` is set → `FO2_buffer="FMQ"`, `FO2_buffer_START=dFMQ`. Logged at INFO.
4. Else → fall back to `cfg.fo2_buffer` (e.g. "FMQ") with offset `0`, and emit a warning.

In **strict modes**:

- `'fe3fet'` — require Fe3+/FeT (or speciated Fe) on the sample; raise `ValueError` otherwise.
- `'buffer'` — require the buffer-relative offset matching `cfg.fo2_buffer` (`dNNO` if `fo2_buffer="NNO"`, `dFMQ` if `fo2_buffer="FMQ"`); raise `ValueError` if missing. `"IW"` is allowed but uses offset `0` (no comp field exists).
- `'absolute'` — set fO2 to `cfg.fo2_start` (bar) via `FO2_SET=True`. Iron split is skipped (see above).

In every mode the wrapper logs an INFO line naming the source it actually used, so the chosen path is visible in the log file rather than silent.

---

## MAGEC

MAGEC is the most awkward backend: it's a compiled MATLAB solver (`.p` file) called via subprocess. Volcatenate writes a CSV input file, generates a .m script that builds a MATLAB struct of settings, and runs `matlab -batch …`.

### Where the YAML lands

```
volcatenate_config.yaml
  └── magec:
       └── RunConfig.magec (MAGECConfig dataclass)
            ├── _build_sample_input_rows()    → per-pressure-step rows for the input CSV
            └── _build_settings_matlab_struct() → MATLAB struct(...) literal
                 └── _run_magec_matlab()
                      └── matlab -batch "MAGEC_CSV_Wrapper(in.csv, out.csv, settings)"
                           └── MAGEC_Solver_v1b.p
```

Wrapper code: [backends/magec.py](../src/volcatenate/backends/magec.py).

### Field-by-field — MAGEC

| YAML key         | What it does (plain English)                                                                                                        | MATLAB struct field                                       | Gotchas                                                                                            |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `solver_dir`   | Path to the directory containing `MAGEC_Solver_v1b.p`. Auto-detected; set explicitly if detection fails.                          | (added to MATLAB path)                                    |                                                                                                    |
| `matlab_bin`   | Path to the `matlab` binary. Auto-detected from `$PATH` or common installs.                                                     | (used in subprocess)                                      | Set env var `MATLAB_BIN` to override globally.                                                   |
| `sulfide_sat`  | `1`/`0` — whether MAGEC enforces sulfide saturation at each step.                                                              | `sat_sulfide`                                           |                                                                                                    |
| `sulfate_sat`  | `1`/`0` — whether MAGEC enforces sulfate (anhydrite) saturation.                                                               | `sat_sulfate`                                           |                                                                                                    |
| `graphite_sat` | `1`/`0` — graphite saturation.                                                                                                 | `sat_graphite`                                          |                                                                                                    |
| `fe_redox`     | Choice of Fe redox model. `1` = Sun & Yao 2024, `2` = KC91 (Kress & Carmichael 1991), `3` = Hirschmann 2022.                   | `Fe32_opt`                                              | KC91 is what volcatenate's *own* internal redox conversion uses (see fallback chain below).       |
| `s_redox`      | S6+/ST relationship. `1`=Sun & Yao 2024, `2`=Nash 2019, `3`=Jugo 2010, `4`=O'Neill 2022, `5`=Boulliung 2023.               | `S62_opt`                                               |                                                                                                    |
| `scss`         | SCSS model. `1`=Blanchard 2021, `2`=Fortin 2015, `3`=Smythe 2017, `4`=O'Neill 2021.                                          | `SCSS_opt`                                              |                                                                                                    |
| `sulfide_cap`  | Sulfide capacity model. `1`=Nzotta 1999, `2`=O'Neill 2021, `3`=Boulliung 2023.                                                 | `S2max_opt`                                             |                                                                                                    |
| `co2_sol`      | CO2 solubility model. `1`=IM2012, `2`=Liu 2005, `3.x`=Burgisser 2015.                                                          | `CO2_opt`                                               |                                                                                                    |
| `h2o_sol`      | H2O solubility. Same options as `co2_sol`.                                                                                        | `H2O_opt`                                               |                                                                                                    |
| `co_sol`       | CO solubility. `1`=Armstrong 2015, `2.x`=Yoshioka 2019.                                                                          | `CO_opt`                                                |                                                                                                    |
| `adiabatic`    | `0` = isothermal (T held fixed). Other values would model decompression-induced cooling.                                          | `adiabat_r`                                             | Use `0` for almost all natural-degassing studies.                                                |
| `solver`       | MATLAB solver choice: `1`=lsqnonlin, `2`=fsolve.                                                                                 | `solver_opt`                                            | `2` is volcatenate's default. fsolve tends to be more robust for MAGEC.                          |
| `gas_behavior` | `1` = real gas (use fugacity coefficients), `2` = ideal.                                                                        | `ideal`                                                 |                                                                                                    |
| `o2_balance`   | `0` = total oxygen is conserved (mass-balance), `1` = fO2 is held to a fixed buffer.                                            | `buffer`                                                | `0` is the realistic eruptive scenario.                                                          |
| `redox_option` | Which redox indicator to *send* to MAGEC: `'logfO2'`, `'dFMQ'`, `'Fe3+/FeT'`, or `'S6+/ST'`.                               | input CSV `Initial redox options` column                | Has a multi-tier fallback chain — see below.                                                      |
| `redox_source` | Strictness for `redox_option`: `'auto'`, `'fe3fet'`, `'dfmq'`, `'dnno'`, `'kc91_from_buffer'`. See the fallback section below.                                                    | (drives `_resolve_magec_redox`)                       |                                                                                                    |
| `p_start_kbar` | Starting pressure (kbar) for MAGEC's pressure grid.                                                                                 | input CSV column                                          | If satP is *higher* than `p_start_kbar`, MAGEC will not find saturation — increase this value. |
| `p_final_kbar` | Final pressure (kbar).                                                                                                              | input CSV column                                          |                                                                                                    |
| `n_steps`      | Number of pressure steps in the grid. Volcatenate creates a *log-spaced* grid from `p_start_kbar` down to `p_final_kbar`.      | (used by `np.logspace` in `_build_sample_input_rows`) | More steps = smoother curves, longer runtime.                                                      |
| `timeout`      | Subprocess timeout (seconds). MATLAB will be killed after this. Default 300s. Batch satP scales this as `timeout + 10*n_samples`. | (subprocess.run)                                          | If MAGEC hangs (typical when satP is outside range), the run is aborted and a warning logged.      |
| `overrides`    | Per-sample overrides.                                                                                                               | (resolved in `resolve_sample_config`)                   |                                                                                                    |

### Hidden behaviors — MAGEC

In `_build_sample_input_rows` at [backends/magec.py](../src/volcatenate/backends/magec.py):

| MAGEC field            | volcatenate value | Meaning                                                                                                                                                                                                                  |
| ---------------------- | ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `Reference`          | `"auto_satP"`   | Tells MAGEC to compute the saturation pressure itself rather than use a user-supplied reference P. The alternate "referenced" mode (where you'd set `Reference P (kbar)`) is not surfaced because we always want auto-satP. |
| `Reference P (kbar)` | `np.nan`        | Only used when `Reference != "auto_satP"`; left NaN.                                                                                                                                                                   |

#### Cr2O3 from the sample

`Cr2O3` is now a real `MeltComposition` field (the CSV reader picks it up if present and defaults to 0 otherwise). MAGEC's `melt_Cr2O3 (wt%)` column is populated from `comp.Cr2O3` and flows through the anhydrous renormalization alongside the other oxides. There is no longer a hardcoded zero; if your sample carries a real Cr2O3 value it ends up in MAGEC's input.

#### Anhydrous renormalization

MAGEC expects oxide columns on a **volatile-free basis summing to 100 wt%**. Because typical petrological data have totals of ~99–100% *including* H2O+CO2+S, the oxides themselves sum to ~96–98%. Volcatenate normalizes each oxide ([backends/magec.py](../src/volcatenate/backends/magec.py)):

```
norm = 100.0 / (SiO2 + TiO2 + Al2O3 + Cr2O3 + FeOT + MnO + MgO + CaO + Na2O + K2O + P2O5)
sio2_out = sio2 * norm
…
```

#### Volatile molecular → elemental conversion

MAGEC expects `Bulk_H`, `Bulk_C`, `Bulk_S` in elemental wt% (not H2O / CO2 / S wt%). Volcatenate does this conversion in [backends/magec.py](../src/volcatenate/backends/magec.py):

```
_H2O_TO_H = 2.0 / 18    # 1/9, ratio of 2*M_H to M_H2O
_CO2_TO_C = 12.0 / 44   # 3/11, ratio of M_C to M_CO2
Bulk_H = H2O_wt% * norm * _H2O_TO_H
Bulk_C = CO2_wt% * norm * _CO2_TO_C
Bulk_S = S_wt%   * norm
```

The molecular weights are deliberately the rounded integers (18 instead of 18.015, 44 instead of 44.01) — this matches the convention used by the MAGEC author in the Sun & Yao 2024 example files (`example1.xlsx` etc.). Faithfulness to the upstream convention is prioritized over chemical precision. **MAGEC does not perform this conversion internally**; volcatenate is responsible for it.

#### Compositional inputs

In `_build_sample_input_rows`:

- All major oxides (incl. Cr2O3) come from the `MeltComposition` (after the anhydrous renormalization above).
- `T_degas (C)` ← `comp.T_C`.
- `Bulk_H/C/S` ← computed from `comp.H2O`, `comp.CO2`, `comp.S` as above.
- `Initial redox options` and `Initial redox values` ← determined by `_resolve_magec_redox` per the fallback chain below.
- The pressure grid is **log-spaced** (not linear) from `p_start_kbar` down to `p_final_kbar` with `n_steps` points.

### Fallback chain — MAGEC redox

MAGEC's redox handling is the most consequential redox decision in volcatenate, because in some modes the wrapper performs its own KC91 conversion that changes which indicator MAGEC actually sees. Logic at [backends/magec.py:_resolve_magec_redox](../src/volcatenate/backends/magec.py).

In **`redox_source="auto"`** mode (the default):

1. Honor `cfg.redox_option` if the matching indicator is present on the sample. `Fe3+/FeT` → use it; `dFMQ` → use it. (`logfO2` and `S6+/ST` have no direct comp source and fall through.)
2. If the requested option's indicator is missing but Fe3+/FeT is available → send `Fe3+/FeT`. Logged at INFO.
3. Last resort: if neither Fe3+/FeT nor a directly-honored option is available but `dNNO` or `dFMQ` is, **internally compute Fe3+/FeT via Kress & Carmichael 1991** (using the Frost-1991 buffer at 1 bar to convert dNNO/dFMQ → logfO2, then KC91 inverse → Fe3+/FeT) and send that as `Fe3+/FeT` to MAGEC. **This is logged at WARNING** and the message points to `redox_source='kc91_from_buffer'` to make the choice explicit. The result is substantively different from what the user asked for: the user asked for `dFMQ`, MAGEC actually receives `Fe3+/FeT`, and the conversion uses 1 bar (not the sample's actual P).
4. If everything fails → `ValueError("No usable redox indicator")`.

In **strict modes**:

- `'fe3fet'` — require Fe3+/FeT; raise `ValueError` if missing.
- `'dfmq'` — require `dFMQ`; raise `ValueError` if missing.
- `'dnno'` — raises `ValueError` informatively, because **MAGEC does not accept dNNO directly** as a redox column. Use `'kc91_from_buffer'` to convert dNNO → Fe3+/FeT.
- `'kc91_from_buffer'` — explicitly opt into the KC91 conversion from `dNNO` or `dFMQ` even when Fe3+/FeT is also present. Logged at INFO; raises if the conversion fails or both buffer indicators are missing.

> ⚠️ The KC91 substitution path in `auto` mode is volcatenate's own calculation, not something MAGEC does. If you want guaranteed transparency about which indicator is reaching MAGEC, set `redox_source` to a strict mode and let the wrapper raise on missing data instead of silently substituting.

---

## SulfurX

SulfurX is a Python library that is not pip-installable — it has to be on `sys.path` via `config.sulfurx.path`. Volcatenate calls into its internal modules directly (`Iacono_Marziano_COH`, `degassingrun`, `OxygenFugacity`, etc.) rather than going through a single entry point.

### Where the YAML lands

```
volcatenate_config.yaml
  └── sulfurx:
       └── RunConfig.sulfurx (SulfurXConfig dataclass)
            └── _run_degassing()
                 ├── _find_saturation_pressure_im()  → robust satP
                 ├── _compute_delta_fmq()            → fO2 conversion
                 ├── _patch_composition()            → monkey-patches SulfurX's
                 │                                     hardcoded MeltComposition
                 └── COHS_degassing.degassing_redox / degassing_noredox
                      → row-by-row results DataFrame
```

Wrapper code: [backends/sulfurx.py](../src/volcatenate/backends/sulfurx.py).

### Field-by-field — SulfurX

| YAML key                        | What it does (plain English)                                                                                                                                                                                                  | SulfurX variable                                          | Gotchas                                                                                                                                         |
| ------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `path`                        | Filesystem path to the SulfurX source directory. Auto-detected.                                                                                                                                                               | (added to `sys.path`)                                   | Set `SULFURX_PATH` env var as alternative.                                                                                                    |
| `coh_model`                   | Which C-O-H solubility code is used. `0` = Iacono-Marziano, `1` = VolatileCalc.                                                                                                                                            | `COH_model`                                             | These are different solubility families; results can differ by tens of percent.                                                                 |
| `slope_h2o`, `constant_h2o` | The two coefficients for the K2O-vs-H2O regression used inside Iacono-Marziano: `K2O = slope * H2O + constant`. The defaults are calibrated for Etna-like compositions.                                                      | `a`, `b` (passed to `IaconoMarziano(a=…, b=…)`)   | If your sample is far from the calibration set (e.g. a MORB), these may be wrong; consult the IM 2012 paper.                                    |
| `n_steps`                     | Number of pressure-grid points from satP down to ~0. SulfurX's loop runs once per step.                                                                                                                                       | `n_steps`                                               | More = smoother curves; SulfurX's degassing loop is slow per step (each can run ~100k inner iterations), so this affects runtime substantially. |
| `fo2_tracker`                 | `0` = fO2 is held to a fixed buffer offset (you specify dFMQ; the run keeps the melt at that dFMQ throughout). `1` = fO2 evolves with degassing (electron balance is tracked, melt redox responds to S and Fe degassing). | (selects `degassing_redox` vs `degassing_noredox`)    | `1` is the realistic choice for natural eruptive degassing.                                                                                   |
| `s_fe_choice`                 | S6+/ST model: `0` = Nash 2019, `1` = O'Neill & Mavrogenes 2022.                                                                                                                                                            | `S_Fe_choice` (and `model_choice` in `Sulfur_Iron`) |                                                                                                                                                 |
| `sigma`                       | log10 fO2 tolerance (numerical) for the per-step redox solver. Smaller = tighter convergence, slower.                                                                                                                         | `sigma`                                                 | Default `0.005` is typical; rarely needs changing.                                                                                            |
| `sulfide_pre`                 | If `1`, the model checks SCSS at each step and precipitates sulfide if S exceeds it (clipping melt S). If `0`, no sulfide phase ever forms.                                                                               | `sulfide_pre`                                           |                                                                                                                                                 |
| `crystallization`             | `0` = no crystallization (the only path SulfurX exercises today). `1` would enable the fractional-crystallization branch.                                                                                                  | `choice`                                                |                                                                                                                                                 |
| `open_degassing`              | `0` = closed-system degassing (default); `1` = open-system. Wired through but not heavily tested.                                                                                                                            | `open_degassing`                                        |                                                                                                                                                 |
| `d34s_initial`                | Initial bulk δ³⁴S, used when isotope tracking is wired up.                                                                                                                                                                  | `d34s_initial`                                          |                                                                                                                                                 |
| `sulfide`                     | Nested mapping describing the equilibrium sulfide phase composition (used for SCSS calculations) — `fe`, `ni`, `cu`, `o`, `s` weight percent **of the sulfide phase**, not the melt. Defaults `Fe65.43, S36.47` match `main_Fuego.py`. | (passed to SulfurX's sulfide-saturation routines)     |                                                                                                                                                 |
| `overrides`                   | Per-sample overrides.                                                                                                                                                                                                         | (resolved in `resolve_sample_config`)                   |                                                                                                                                                 |

### Hidden behaviors — SulfurX

In `_run_degassing` at [backends/sulfurx.py](../src/volcatenate/backends/sulfurx.py):

The fields previously hardcoded in this section (`choice` for crystallization, `open_degassing`, `d34s_initial`, and the sulfide-phase composition) are now real config fields exposed in YAML — see the field table above. Defaults match the SulfurX `main_Fuego.py` reference run, so existing configs without those keys continue to behave exactly as before.

#### Composition monkey-patch (very important!)

SulfurX has a class `degassingrun.MeltComposition` whose constructor **hardcodes a specific Hawaiian basalt composition** (when `choice=0`). Inside the degassing loop, every pressure step creates a fresh `MeltComposition(...)` and feeds it to IaconoMarziano, OxygenFugacity, etc. If the *real* sample composition differs from the Hawaiian basalt, the initial conditions (computed with the real composition) and the per-step calculations (using the hardcoded one) become inconsistent, and SulfurX's inner solver hangs at 100k iterations.

`_patch_composition` ([backends/sulfurx.py](../src/volcatenate/backends/sulfurx.py)) replaces `degassingrun.MeltComposition` with a tiny wrapper that returns the *volcatenate* sample composition (normalized to 100 wt%) for every call inside the loop. The original class is restored on exit.

> If you are reading SulfurX docs and wondering whether your sample composition was used: **yes**. The monkey-patch is in place every time volcatenate runs SulfurX.

#### Robust satP search

SulfurX's IM saturation-pressure solver uses a single `scipy.root` call seeded from `pressure*10` MPa, and silently returns the seed unchanged on non-convergence. This is fragile. Volcatenate replaces it with `_find_saturation_pressure_im` at [backends/sulfurx.py](../src/volcatenate/backends/sulfurx.py), which:

1. Tries 11 starting pressures (10–400 MPa) × 3 starting `XH2O_f` guesses (0.01, 0.5, 0.9) = 33 attempts.
2. Filters out non-convergent (where the solver didn't move from the seed).
3. Clusters converged results within 200-bar windows.
4. Picks the *lowest-pressure* cluster with ≥ 2 members (true solutions attract many starting guesses).
5. Returns the median P_sat and XH2O_f from the winning cluster.

This is volcatenate's own algorithm — there is no equivalent in the upstream SulfurX. It applies to both `calculate_saturation_pressure` and to step 1 of the degassing run.

### Fallback chain — SulfurX dFMQ

`_compute_delta_fmq` at [backends/sulfurx.py](../src/volcatenate/backends/sulfurx.py) is the existing clean explicit cascade — SulfurX has no `redox_source` setting; it always tries the indicators in this fixed order and logs the choice at INFO:

1. If the sample has `dFMQ` → use it directly.
2. Else if it has Fe3+/FeT (from speciated Fe or explicit `Fe3FeT`) → invert KC91 at 1 bar to get logfO2, subtract Frost-1991 FMQ at the sample's T → dFMQ. Logged at INFO.
3. Else if it has `dNNO` → convert via Frost-1991: `dFMQ = dNNO + (NNO(T) - FMQ(T))` at 1 bar. Logged at INFO.
4. Else → `ValueError("SulfurX requires a redox constraint")`.

The temperature-dependent NNO–FMQ offset (≈ 0.74 at 1200 °C, 0.75 at 1030 °C) is computed properly — this used to be approximated as a constant 0.7 in older versions, which was wrong by ~0.04–0.05 log units.

The KC91 inversion uses Brent's method (`scipy.optimize.brentq`) over the logfO2 range −25 to 0, which is generous (IW−5 to HM+5). If Brent's method fails, the wrapper falls through to the dNNO path with a warning.

---

## Quick cross-reference

If you change one of the following YAML knobs, here is roughly what happens across all backends.

### "I want closed-system degassing"

| Backend | YAML setting                                      |
| ------- | ------------------------------------------------- |
| VESIcal | `vesical.fractionate_vapor: 0.0`                |
| VolFe   | `volfe.gassing_style: closed`                   |
| EVo     | `evo.run_type: closed` (default)                |
| MAGEC   | always closed (no toggle exposed)                 |
| SulfurX | `sulfurx.open_degassing: 0` (default)           |

### "I want open-system degassing"

| Backend | YAML setting                                       |
| ------- | -------------------------------------------------- |
| VESIcal | `vesical.fractionate_vapor: 1.0`                 |
| VolFe   | `volfe.gassing_style: open`                      |
| EVo     | `evo.run_type: open` AND `evo.loss_frac < 1.0` |
| MAGEC   | not currently exposed                              |
| SulfurX | `sulfurx.open_degassing: 1`                      |

### "I want to use my own dFMQ value"

| Backend | What you need on the sample                                                                                                      | What the wrapper sends                             |
| ------- | -------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------- |
| VESIcal | (no fO2 input)                                                                                                                   | n/a                                                |
| VolFe   | `dFMQ` and `volfe.fo2_column: DFMQ`                                                                                          | `DFMQ` column                                    |
| EVo     | `dFMQ` (auto-picked when `fo2_source="auto"`)                                                                                | `FO2_buffer=FMQ`, offset = sample dFMQ           |
| MAGEC   | `dFMQ` and `magec.redox_option: dFMQ`. Use `magec.redox_source: dfmq` to refuse the silent KC91 conversion.                  | `dFMQ` directly, **or** `Fe3+/FeT` via KC91 if `redox_source="auto"` and Fe3+/FeT was used instead. |
| SulfurX | `dFMQ` (always preferred when present)                                                                                         | `delta_FMQ`                                      |

### Solubility-model choice

The single biggest driver of inter-model disagreement is solubility. Each backend has its own solubility-model knobs:

| Volatile        | VolFe                 | EVo                      | MAGEC                 | SulfurX                                 |
| --------------- | --------------------- | ------------------------ | --------------------- | --------------------------------------- |
| H2O             | `volfe.h2o_sol`     | `evo.h2o_model`        | `magec.h2o_sol`     | `sulfurx.coh_model` (paired with CO2) |
| CO2             | `volfe.co2_sol`     | `evo.c_model`          | `magec.co2_sol`     | `sulfurx.coh_model`                   |
| H2              | `volfe.h2_sol`      | `evo.h2_model`         | (not exposed)         | n/a                                     |
| CO              | `volfe.co_sol`      | `evo.co_model`         | `magec.co_sol`      | n/a                                     |
| CH4             | `volfe.ch4_sol`     | `evo.ch4_model`        | (not exposed)         | n/a                                     |
| Sulfide (S²⁻) | `volfe.sulfide_sol` | `evo.sulfide_capacity` | `magec.sulfide_cap` | (built-in)                              |
| Sulfate (S⁶⁺) | `volfe.sulfate_sol` | `evo.sulfate_capacity` | (built-in)            | (built-in)                              |
| H2S             | `volfe.h2s_sol`     | (built-in)               | (built-in)            | (built-in)                              |

VESIcal is omitted (no sulfur, and only one solubility law per variant).

---

## Where to look next

- [`configuration.md`](configuration.md) — top-level YAML schema and loading.
- [`run_bundles.md`](run_bundles.md) — reproducible run bundles (which include the resolved config so you can replay).
- The wrapper modules under `src/volcatenate/backends/` — read these whenever the doc above is unclear; they are short and are the source of truth.
- The project's internal config audit — full list of every hardcoded literal, every silent fallback, and proposed promotions for upcoming releases (kept alongside the repo, not published).
