# How YAML config fields propagate into each backend

This is a plain-English reference explaining what each setting in your
volcatenate YAML config actually *does* once it reaches the underlying
model. It complements [configuration.md](configuration.md) (which
documents the YAML structure) and the
[hidden-values audit](../.claude/notes/config_audit.md) (which lists
every value that volcatenate hardcodes or pulls silently from the
sample composition).

The doc is organized one backend per section, ordered from simplest to
most involved:

1. [VESIcal](#vesical)
2. [VolFe](#volfe)
3. [EVo](#evo)
4. [MAGEC](#magec)
5. [SulfurX](#sulfurx)

Each section has the same structure:

- **Where the YAML lands** — the full call chain from YAML to backend.
- **Field-by-field table** — what each setting actually does to the
  calculation.
- **Hidden behaviors** — things volcatenate hardcodes or pulls from
  the `MeltComposition`, that you can't see in the YAML.
- **Fallback chains** — what happens when the option you picked
  doesn't have a matching value on the sample.

Throughout, when you see a redox indicator referenced in plain English:

- **Fe3+/FeT** — the ferric ratio of total iron in the melt; a direct
  measurement-derived number.
- **dFMQ** — log fO2 relative to the FMQ (fayalite-magnetite-quartz)
  buffer at the same T (and usually 1 bar).
- **dNNO** — log fO2 relative to the NNO (nickel-nickel oxide) buffer.

Anything *italicized in this doc* is a comment from the writer, not
canonical documentation. `> ⚠️ TODO` markers indicate places where
the author was not 100% sure of the backend behavior and the reader
should treat the surrounding text as best-guess.

---

## What gets pulled from the sample, in every backend

Before diving in, here is the universal rule: **the sample composition
provided via CSV or `MeltComposition` is always the source of truth
for chemistry**, and the YAML config never shadows it. Specifically,
across every backend the following come from the sample, not the YAML:

| Source on `MeltComposition`                                                         | Used as                                                                                                                                                                                                                                                                                  |
| ------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `T_C`                                                                               | Temperature for every backend (converted to Kelvin where needed).                                                                                                                                                                                                                        |
| `SiO2`, `TiO2`, `Al2O3`, `MnO`, `MgO`, `CaO`, `Na2O`, `K2O`, `P2O5` | Major-oxide chemistry.                                                                                                                                                                                                                                                                   |
| `FeOT`                                                                              | Total iron, split into FeO/Fe2O3 by each backend's own iron-redox handling (see[composition.py:55](../src/volcatenate/composition.py)).                                                                                                                                                     |
| `H2O` (wt%)                                                                         | Bulk water. Some backends want wt%, some want ppm — volcatenate converts. <-- user feedback: for H₂O, CO₂, and S: note that all H is taken in as H₂O (species in the melt not considered for inputs)... unless this isn't true?                                                      |
| `CO2` (wt%)                                                                         | Bulk CO2. Often converted to ppm internally. <-- user feedback: "often" is vague.                                                                                                                                                                                                        |
| `S` (wt%)                                                                           | Bulk sulfur.                                                                                                                                                                                                                                                                             |
| `Fe3FeT`, `dNNO`, `dFMQ`                                                        | Redox indicators in an input composition. Each backend implements this differently (documented below). <-- user feedback. I reworded. Check it is correct. This is important since there are so many redox options in backends. Be explicity here if this can be overridden in the Yaml. |
| `Xppm`                                                                              | "Other" trace species (Ar/Ne) — VolFe only.                                                                                                                                                                                                                                             |

When a wrapper says "from the composition," that's where it comes from.

---

## VESIcal

VESIcal is the simplest backend — it models only H₂O–CO₂ degassing
(no sulfur, no Fe redox), so the wrapper is short and the YAML surface
is tiny.

### Where the YAML lands

```
volcatenate_config.yaml
  └── vesical:
       └── RunConfig.vesical (VESIcalConfig dataclass)
            └── Backend.calculate_degassing()
                 └── model.calculate_degassing_path()
```

Wrapper code: [backends/vesical.py](../src/volcatenate/backends/vesical.py).

The "VESIcal model" being used (Dixon, Iacono-Marziano, MagmaSat, …)
is **not** controlled by the YAML — it's selected by the **backend
name** you pass to `calculate_degassing` / `run_comparison`, e.g.
`models=["VESIcal_Iacono"]`. See the `VARIANT_MAP` at
[backends/vesical.py:28](../src/volcatenate/backends/vesical.py).

### Field-by-field

| YAML key              | What it does (plain English)                                                                                                                                                                         | Backend option                                           | Gotchas                                                                                       |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `steps`             | How many pressure steps in the degassing path. More steps = smoother curves but slower.                                                                                                              | `model.calculate_degassing_path(steps=…)`             | VESIcal divides the (P_sat → final_pressure) range into this many steps. 101 is the default. |
| `final_pressure`    | The pressure (bar) at which the degassing run ends.                                                                                                                                                  | `model.calculate_degassing_path(final_pressure=…)`    | Set this to ~1 bar for full atmospheric degassing, or higher to stop early.                   |
| `fractionate_vapor` | A number between 0 and 1: what fraction of vapor is removed from the melt at each step.`0` = closed-system (vapor stays in equilibrium), `1` = open-system (vapor is fully extracted each step). | `model.calculate_degassing_path(fractionate_vapor=…)` | Intermediate values are physically unusual but allowed.                                       |
| `overrides`         | Per-sample dict of any of the above fields, e.g.`{Fogo: {steps: 50}}`.                                                                                                                             | (resolved in `resolve_sample_config`)                  | Unknown field names are warned and ignored.                                                   |

### Hidden behaviors

- **Variant selection**: the actual VESIcal solubility model is chosen
  by the *backend name*, not by config. E.g. `"VESIcal_Iacono"` →
  `"IaconoMarziano"`, `"VESIcal_MS"` → `"MagmaSat"`. See
  `VARIANT_MAP` at [backends/vesical.py:28](../src/volcatenate/backends/vesical.py).
- **Saturation pressure calls always use `pressure="saturation"`** —
  i.e. VESIcal computes the starting pressure itself from the
  sample's H₂O+CO₂. There is no way to ask for a fixed starting P.
- **Iron is sent both ways** ([backends/vesical.py:163-167](../src/volcatenate/backends/vesical.py)):
  if the sample provides speciated `FeO` and `Fe2O3`, both are sent;
  otherwise FeOT is sent as `FeO`. This matters only for MagmaSat,
  which uses Fe redox internally.
- **Warnings are silenced** during the run with `warnings.simplefilter("ignore")` ([backends/vesical.py:85](../src/volcatenate/backends/vesical.py)) — VESIcal emits many petrological-range warnings that volcatenate suppresses to keep logs clean.

### Fallback chains

VESIcal does not use any of the redox indicators (`Fe3FeT`, `dFMQ`,
`dNNO`) — it doesn't model fO2 except internally for MagmaSat. So
there is no fallback chain to document.

---

## VolFe

VolFe is a Python C-O-H-S-Fe degassing model with a large set of
toggles for solubility, fugacity, and equilibrium constants. Almost
every YAML field maps 1-to-1 to a VolFe internal option name.

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
| `fo2_column`                                                                                                          | **Volcatenate-specific**, not a VolFe option. Tells the wrapper which redox indicator on the sample to send to VolFe. Choices: `'DNNO'`, `'Fe3FeT'`, `'DFMQ'`.                                                                                                    | (drives `_build_setup_df`)                                                                                                                            | Has a fallback chain — see below. The chosen column becomes a column in the VolFe input DataFrame.                               |
| `gassing_style`                                                                                                       | `'closed'` keeps the exsolved vapor in equilibrium with the melt at every step; `'open'` removes the vapor instantly each step.                                                                                                                                           | `gassing_style`                                                                                                                                       | `open` produces lower vapor S/C ratios as light volatiles escape early.                                                         |
| `gassing_direction`                                                                                                   | `'degas'` runs P from saturation downward (normal eruptive path). `'regas'` runs upward — useful for testing what happens during recompression.                                                                                                                          | `gassing_direction`                                                                                                                                   | Almost always `degas` for natural studies.                                                                                      |
| `bulk_composition`                                                                                                    | What "bulk" composition VolFe initializes with.`'melt-only'` = the sample melt, with vapor appearing as P drops. `'melt+vapor_wtg'` = melt + a fixed weight fraction of pre-existing vapor. `'melt+vapor_initialCO2'` = melt + vapor that holds a specific initial CO2. | `bulk_composition`                                                                                                                                    | Pre-existing vapor changes total volatile budget; only matters for unusual cases where you have evidence of pre-segregated vapor. |
| `coh_species`                                                                                                         | Which C-O-H species VolFe carries in melt and vapor.`'yes_H2_CO_CH4_melt'` = full speciation including H2, CO, CH4 dissolved in the melt. `'no_H2_CO_CH4_melt'` = only CO2/H2O in the melt (others only in vapor). `'H2O-CO2 only'` = strictly two-component.           | `COH_species`                                                                                                                                         | Affects redox-sensitive volatile speciation, especially at reduced fO2.                                                           |
| `h2s_melt`                                                                                                            | If `true`, treats H2Smol as a dissolved melt species (not just in vapor).                                                                                                                                                                                                   | `H2S_m`                                                                                                                                               | Generally `true` for proper sulfur mass balance below ~FMQ.                                                                     |
| `species_x`                                                                                                           | Identity of the inert "X" trace species:`'Ar'` or `'Ne'`. Only used if your sample has a non-zero `Xppm`.                                                                                                                                                               | `species X`                                                                                                                                           | Default sample data has Xppm=0, so this is moot unless you supply it.                                                             |
| `fo2_model`                                                                                                           | The fO2 ↔ Fe3+/FeT relationship:`'Kress91A'` = Kress & Carmichael 1991 with the "A" parameterisation, `'Kress91'`, `'ONeill18'`, `'Borisov18'`.                                                                                                                      | `fO2`                                                                                                                                                 | Small (~0.1 log unit) differences between options for typical basalts.                                                            |
| `fmq_buffer`                                                                                                          | Which equation defines FMQ for buffer-relative fO2:`'Frost91'` (default) or `'ONeill87'`. Matters when the sample provides DFMQ.                                                                                                                                          | `FMQbuffer`                                                                                                                                           | Frost91 is what most modern data are reported relative to.                                                                        |
| `co2_sol`, `h2o_sol`, `h2_sol`, `sulfide_sol`, `sulfate_sol`, `h2s_sol`, `ch4_sol`, `co_sol`, `x_sol` | Selects which solubility law VolFe uses for each volatile. Each takes a string like `'MORB_Dixon95'`, `'Basalt_Hughes24'`, `'ONeill21dil'`, etc.                                                                                                                        | `carbon dioxide`, `water`, `hydrogen`, `sulfide`, `sulfate`, `hydrogen sulfide`, `methane`, `carbon monoxide`, `species X solubility` | The choice of solubility model is often*the* dominant driver of inter-model disagreement. See VolFe docs for the full list.     |
| `c_spec_comp`, `h_spec_comp`                                                                                        | "Speciation composition" choices for CO2-mol/CO3²⁻ (`Cspeccomp`) and H2Omol/OH (`Hspeccomp`). They control which composition-dependent expressions are used to split molecular vs ionic dissolved species.                                                              | `Cspeccomp`, `Hspeccomp`                                                                                                                            | Mostly cosmetic for total-volatile budgets.                                                                                       |
| `scss`, `scas`                                                                                                      | Sulfide-saturation (`SCSS`) and anhydrite/sulfate-saturation (`SCAS`) models. Strings like `'ONeill21hyd'`, `'Zajacz19_pss'`. Only consulted when `sulfur_saturation=true`.                                                                                         | `SCSS`, `SCAS`                                                                                                                                      | If `sulfur_saturation=false`, the value is sent to VolFe but never used.                                                        |
| `ideal_gas`                                                                                                           | If `true`, ALL fugacity coefficients (y_*) are forced to 1 (vapor treated as ideal).                                                                                                                                                                                        | `ideal_gas`                                                                                                                                           | A good sanity-check at low pressure; spurious at high P.                                                                          |
| `y_co2`, `y_so2`, `y_h2s`, `y_h2`, `y_o2`, `y_s2`, `y_co`, `y_ch4`, `y_h2o`, `y_ocs`                | Per-species fugacity-coefficient model. e.g.`'Shi92'` = Shi & Saxena 1992, `'Holland91'` = Holland & Powell 1991.                                                                                                                                                         | `y_CO2`, `y_SO2`, etc.                                                                                                                              | Overridden if `ideal_gas=true`.                                                                                                 |
| `k_hosg`, `k_osg`, `k_cohg`, `k_ocsg`                                                                           | Equilibrium-constant models for the gas-phase reactions: H2S formation (½S2 + H2O = H2S + ½O2), SO2 formation (½S2 + O2 = SO2), CH4 oxidation (CH4 + 2 O2 = CO2 + 2 H2O), and OCS formation.                                                                               | `KHOSg`, `KOSg`, `KCOHg`, `KOCSg`                                                                                                               | Multiple-choice strings, e.g.`'Ohmoto97'`, `'Moussallam19'`.                                                                  |
| `overrides`                                                                                                           | Per-sample overrides as `{sample: {field: value}}`.                                                                                                                                                                                                                         | (resolved in `resolve_sample_config`)                                                                                                                 | Unknown field names are warned and ignored.                                                                                       |

### Hidden behaviors — VolFe

These are sent to VolFe by volcatenate but are **not** in the YAML.
They are hardcoded in [backends/volfe.py:_build_models_df](../src/volcatenate/backends/volfe.py)
or fall through to VolFe's built-in defaults via
`vf.make_df_and_add_model_defaults`.

| VolFe option                                                                                                                                                                                                                                                                          | volcatenate value          | Meaning                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `output csv`                                                                                                                                                                                                                                                                        | `"False"`                | volcatenate handles output itself; tells VolFe not to write CSVs.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `print status`                                                                                                                                                                                                                                                                      | `"False"`                | Tells VolFe not to print progress; volcatenate captures stdout via `_quiet_volfe()`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| `starting_P`                                                                                                                                                                                                                                                                        | `"Pvsat"` (default)      | VolFe always starts the degassing run at the saturation pressure it finds itself.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `P_variation`                                                                                                                                                                                                                                                                       | `"polybaric"` (default)  | Pressure varies (vs. isobaric).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `T_variation`                                                                                                                                                                                                                                                                       | `"isothermal"` (default) | Temperature held fixed (vs. polythermal).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `eq_Fe`                                                                                                                                                                                                                                                                             | `"yes"` (default)        | **Major behaviour switch.** When `"yes"`, VolFe enforces Fe redox equilibrium with fO2 at every pressure step — i.e. fO2 is computed from melt species (`mdv.f_O2`), and Fe3+/FeT is recomputed from fO2 each step ([VolFe/calculations.py:435](../../Volatile_Models/VolFe/src/VolFe/calculations.py)). When `"no"`, fO2 is taken from the gas (`gas_mf["O2"] * y_O2 * P`) and Fe is held fixed ([VolFe/calculations.py:433](../../Volatile_Models/VolFe/src/VolFe/calculations.py)). For natural degassing studies, `"yes"` is essentially always correct. |
| `crystallisation`, `isotopes`, `sulfur_is_sat`, `melt composition`, `NNObuffer`, `Hspeciation`, `solve_species`, `density`, `mass_volume`, `calc_sat`, `bulk_O`, `setup`, `high precision`, isotope `alpha_*`/`beta_factors`, single-option K constants | VolFe defaults             | Pass-through; volcatenate doesn't set them. The audit ([config_audit.md](../.claude/notes/config_audit.md)) lists planned promotions.                                                                                                                                                                                                                                                                                                                                                                                                                                      |

> ⚠️ TODO: `solve_species`, `mass_volume`, `calc_sat`, and `bulk_O` are
> listed as "internal" by VolFe but their semantic effect on the
> calculation has not been fully verified — see the audit for open
> questions.

#### What gets pulled from the sample

In `_build_setup_df` ([backends/volfe.py:149](../src/volcatenate/backends/volfe.py)):

- `Sample`, `T_C`, all major oxides (incl. `FeOT`), `H2O` (wt%),
  `CO2ppm` (= CO2_wt% × 10000), `STppm` (= S_wt% × 10000),
  `Xppm` are all read directly from the `MeltComposition`.
- The fO2 indicator column (`Fe3FeT` / `DNNO` / `DFMQ`) is added
  according to `cfg.fo2_column` and the fallback chain below.

### Fallback chain — VolFe fO2 column

Logic at [backends/volfe.py:171-192](../src/volcatenate/backends/volfe.py):

1. If `fo2_column == "DNNO"` and the sample has `dNNO` → send `DNNO`.
2. If `fo2_column == "Fe3FeT"`:
   - If the sample has speciated Fe (or explicit Fe3FeT) → send `Fe3FeT`.
   - Else if it has `dNNO` → send `DNNO` (silent fallback).
   - Else if it has `dFMQ` → send `DFMQ` (silent fallback).
3. If `fo2_column == "DFMQ"` and the sample has `dFMQ` → send `DFMQ`.
4. Otherwise (none of the above match): try `Fe3FeT`, then `dNNO`, then `dFMQ` in that order.

> ⚠️ The current behavior is **silent** — no warning is logged if the
> wrapper falls back from the requested column. The audit proposes a
> `fo2_source` knob to make this explicit.

If none of `Fe3FeT`, `dNNO`, `dFMQ` are available, no fO2 column is
added and VolFe will use its own default initialization.

---

## EVo

EVo is run via three YAML files (`chem.yaml`, `env.yaml`, `output.yaml`)
that volcatenate writes to a per-sample work directory, then calls
`evo.run_evo()` on. EVo prints prolifically to stdout, so volcatenate
wraps the call in a `_quiet_evo()` context that routes everything to
the logger at DEBUG level.

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

The columns "Backend option" use the *exact* key written into
`env.yaml` (or `chem.yaml`), since that's the file EVo reads.

| YAML key                                               | What it does (plain English)                                                                                                                                                                     | env.yaml key                                           | Gotchas                                                                                                                                                 |
| ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `gas_system`                                         | Which gas species are tracked.`'cohs'` = full C-O-H-S system. Other choices include `'coh'` (no sulfur), `'cos'`, `'cohsn'` (with N).                                                    | `GAS_SYS`                                            | Reducing the system (e.g.`'coh'`) is faster but obviously omits S.                                                                                    |
| `fo2_buffer`                                         | Which buffer EVo uses when fO2 is set as an offset.`'FMQ'`, `'NNO'`, `'IW'`, …                                                                                                            | `FO2_buffer`                                         | **Often overridden** by `_pick_evo_buffer` based on what's available on the composition — see fallback below.                                  |
| `fe_system`                                          | If `true`, EVo iterates Fe redox equilibrium with fO2 at every step (analogous to VolFe `eq_Fe="yes"`). If `false`, Fe is held fixed.                                                      | `FE_SYSTEM`                                          | `true` is the realistic choice.                                                                                                                       |
| `find_saturation`                                    | If `true`, EVo computes its starting pressure itself from the bulk volatiles (saturation pressure). If `false`, EVo starts at `p_start` and assumes that's correct.                        | `FIND_SATURATION`                                    | Default `true` is what you almost always want.                                                                                                        |
| `atomic_mass_set`                                    | If `true`, ignore the wt% volatiles in chem.yaml and use the `atomic_h/c/s/n` ppm values instead. If `false`, use the sample's H2O/CO2/S directly.                                         | `ATOMIC_MASS_SET`                                    | Volcatenate users should leave this `false` — the H2O/CO2/S of the sample is what we want.                                                           |
| `ocs`                                                | Include OCS as a vapor species (`true`) or not (`false`).                                                                                                                                    | `OCS`                                                | Adds a coupling between C and S vapor; small effect except at low fO2.                                                                                  |
| `dp_min`, `dp_max`                                 | Minimum/maximum pressure step (bar) the adaptive integrator will take. EVo varies its step size to balance speed and accuracy;`dp_min` lets it slow down near steep transitions.               | `DP_MIN`, `DP_MAX`                                 | Smaller `dp_max` = smoother curves, slower runs.                                                                                                      |
| `mass`                                               | System mass (g) — total bulk mass for mass-balance bookkeeping.                                                                                                                                 | `MASS`                                               | Almost always 100 g (the default); doesn't affect intensive results, only the absolute mass of vapor produced.                                          |
| `p_start`                                            | Starting pressure (bar). Only used if `find_saturation=false`. Otherwise EVo computes its own start.                                                                                           | `P_START`                                            | Set well above expected satP if you're not auto-finding.                                                                                                |
| `p_stop`                                             | Final pressure (bar).                                                                                                                                                                            | `P_STOP`                                             | Default 1 bar = atmospheric.                                                                                                                            |
| `wgt`                                                | Initial gas weight fraction (≈ 1e-5). EVo seeds an infinitesimal vapor phase to start the iteration.                                                                                            | `WgT`                                                | Numerical seed; rarely needs changing.                                                                                                                  |
| `loss_frac`                                          | For open-system runs (`run_type=open`): fraction of vapor *retained* per step. `0.9999` (default) means almost everything is kept (≈ closed); `0.0` would mean perfect vapor stripping. | `LOSS_FRAC`                                          | Confusingly named — read it as "fraction of vapor that stays in equilibrium with the melt for one more step."                                          |
| `run_type`                                           | `'closed'` or `'open'`. Open-system requires `loss_frac < 1`.                                                                                                                              | `RUN_TYPE`                                           | For saturation-pressure runs the wrapper hardcodes `run_type="closed"` regardless of config ([backends/evo.py:131](../src/volcatenate/backends/evo.py)). |
| `atomic_h`, `atomic_c`, `atomic_s`, `atomic_n` | Atomic-mass-fraction (ppm) volatile budgets. Only used when `atomic_mass_set=true`.                                                                                                            | `ATOMIC_H`, `ATOMIC_C`, `ATOMIC_S`, `ATOMIC_N` | Default values are placeholders.                                                                                                                        |
| `nitrogen_set`                                       | If `true`, send N to EVo (currently uses a small hardcoded `NITROGEN_START=0.0001`, *not* a value from `MeltComposition`).                                                               | `NITROGEN_SET`                                       | Real N support is partial; the audit proposes wiring this through to a sample-level value.                                                              |
| `graphite_saturated`                                 | If `true`, EVo starts the system as graphite-saturated.                                                                                                                                        | `GRAPHITE_SATURATED`                                 | Use only when you really mean it; rare for natural basalts.                                                                                             |
| `h2o_model`                                          | Which H2O solubility law EVo uses. e.g.`'burguisser2015'`.                                                                                                                                     | `H2O_MODEL`                                          | Big knob — different models give meaningfully different H2O contents at the same P.                                                                    |
| `h2_model`                                           | H2 solubility law. e.g.`'gaillard2003'`.                                                                                                                                                       | `H2_MODEL`                                           | Only matters at reduced fO2 where H2 in the melt is non-trivial.                                                                                        |
| `c_model`                                            | CO2/CO3²⁻ solubility law. e.g.`'burguisser2015'`.                                                                                                                                            | `C_MODEL`                                            | Set to match `h2o_model` from the same paper for consistency.                                                                                         |
| `co_model`                                           | CO solubility law. e.g.`'armstrong2015'`.                                                                                                                                                      | `CO_MODEL`                                           | Reduced-fO2 only.                                                                                                                                       |
| `ch4_model`                                          | CH4 solubility law. e.g.`'ardia2013'`.                                                                                                                                                         | `CH4_MODEL`                                          | Strongly reduced (below FMQ-2) or experimental settings.                                                                                                |
| `sulfide_capacity`                                   | Sulfide capacity model (controls how much S²⁻ the melt can hold). e.g.`'oneill2020'`.                                                                                                        | `SULFIDE_CAPACITY`                                   | Affects S degassing under reducing conditions.                                                                                                          |
| `sulfate_capacity`                                   | Sulfate capacity model. e.g.`'nash2019'`.                                                                                                                                                      | `SULFATE_CAPACITY`                                   | Affects S degassing under oxidising conditions.                                                                                                         |
| `scss`                                               | Sulfide-saturation model.                                                                                                                                                                        | `SCSS`                                               | If a sulfide phase is implied; gates how much S the melt can carry.                                                                                     |
| `n_model`                                            | Nitrogen solubility law. e.g.`'libourel2003'`.                                                                                                                                                 | `N_MODEL`                                            | Only used when `nitrogen_set=true`.                                                                                                                   |
| `density_model`                                      | Melt density model (used for converting mass ↔ volume in the bookkeeping).                                                                                                                      | `DENSITY_MODEL`                                      | Cosmetic for most outputs.                                                                                                                              |
| `fo2_model`                                          | fO2 ↔ Fe3+/FeT relationship. e.g.`'kc1991'` = Kress & Carmichael 1991.                                                                                                                        | `FO2_MODEL`                                          | Same role as VolFe `fo2_model`.                                                                                                                       |
| `fmq_model`                                          | Definition of the FMQ buffer (when fO2 is reported relative to FMQ). e.g.`'frost1991'`.                                                                                                        | `FMQ_MODEL`                                          |                                                                                                                                                         |
| `overrides`                                          | Per-sample overrides.                                                                                                                                                                            | (resolved in `resolve_sample_config`)                |                                                                                                                                                         |

### Hidden behaviors — EVo

In `_write_yaml_configs` at [backends/evo.py:259](../src/volcatenate/backends/evo.py):

| env.yaml key                                                 | volcatenate value                                               | Meaning                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| ------------------------------------------------------------ | --------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `COMPOSITION`                                              | `"basalt"`                                                    | Drives EVo's SiO2-range sanity check ([EVo/readin.py:212-217](../../Volatile_Models/EVo/src/evo/readin.py)) and the K_HOSg / K_OSg branch ([EVo/dgs_classes.py:693-723](../../Volatile_Models/EVo/src/evo/dgs_classes.py)) which selects coefficients per composition. **`basalt` = SiO2 in 45–55%; `phonolite` = 52–63%; `rhyolite` = 65–80%**. If your sample's SiO2 is out of range, EVo would normally ask "continue?" — volcatenate auto-answers yes (with a Python warning) via `_auto_yes` ([backends/evo.py:35](../src/volcatenate/backends/evo.py)). |
| `RUN_TYPE`                                                 | `"closed"` for satP runs; `cfg.run_type` for degassing runs | Passed per-call.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `SINGLE_STEP`                                              | `False`                                                       | Volcatenate never does single-pressure runs (would be a future promotion).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `S_SAT_WARN`                                               | `False`                                                       | Suppresses S-saturation warnings inside EVo.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `FO2_SET`                                                  | `False`                                                       | Volcatenate never sets absolute fO2; uses buffer or Fe3+/FeT instead.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| `FH2_SET`, `FH2O_SET`, `FCO2_SET`                      | `False`                                                       | Same — volcatenate always initializes from wt% volatiles, not absolute fugacities.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| `WTH2O_SET`, `WTCO2_SET`, `SULFUR_SET`                 | `True`                                                        | Always; values come from `comp.H2O / 100`, `comp.CO2 / 100`, `comp.S / 100` (wt% → weight fraction).                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `WTH2O_START`, `WTCO2_START`, `SULFUR_START`           | computed from `MeltComposition`                               | See above.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `T_START`                                                  | `comp.T_C + 273.15`                                           | Kelvin.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `NITROGEN_START`                                           | `0.0001`                                                      | Tiny placeholder.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `GRAPHITE_START`                                           | `0.0001`                                                      | Tiny placeholder.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `FH2_START`, `FH2O_START`, `FCO2_START`, `FO2_START` | hardcoded constants (0.24, 1000, 1, 0.0)                        | Unused because the matching `*_SET` flags are `False`, but EVo requires them to be present.                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |

#### chem.yaml epsilon trick

When an oxide is exactly 0 in the sample, volcatenate writes `1e-10`
instead, **because EVo's internal `single_cat()` silently drops keys
with value 0**, and downstream functions then crash with KeyError on
species like `mno`. See [backends/evo.py:283](../src/volcatenate/backends/evo.py).
Result: even "absent" minor oxides are present at 1e-10 in the
calculation. Effect on results is numerically negligible.

#### Iron split

In `chem.yaml`, FeOT is split into FeO + Fe2O3 using
`comp.fe3fet_computed` ([backends/evo.py:286-293](../src/volcatenate/backends/evo.py)):

```
FEO   = FeOT * (1 - Fe3FeT)
FE2O3 = FeOT * Fe3FeT * (159.69 / (2 * 71.844))   # MW conversion
```

If `fe3fet_computed` is NaN (no redox indicator at all), the wrapper
sends `FEO = FeOT, FE2O3 = 0`, leaving fO2 to be set by the buffer.

#### output.yaml

Always written with all five plot flags `False`. EVo's plotting is
unused because volcatenate makes its own figures.

### Fallback chain — EVo fO2 buffer

`_pick_evo_buffer` at [backends/evo.py:228](../src/volcatenate/backends/evo.py):

1. If the sample has `dNNO` → use `FO2_buffer="NNO"` with offset `dNNO`.
2. Else if the sample has `dFMQ` → use `FO2_buffer="FMQ"` with offset `dFMQ`.
3. Else → fall back to `cfg.fo2_buffer` (e.g. "FMQ") with offset 0, and emit a warning.

**Important:** the variable `FO2_buffer_SET` is set to `True` *only when
no Fe3+/FeT split is present in chem.yaml* ([backends/evo.py:341](../src/volcatenate/backends/evo.py)).
That means: **if the sample provides Fe3+/FeT, the buffer choice is
ignored entirely**, because EVo computes fO2 from the iron speciation.
Buffer-relative offsets only matter for samples without Fe3+/FeT.

> Practical consequence: changing `evo.fo2_buffer` in your YAML has
> *no effect* on samples that have Fe3+/FeT data.

---

## MAGEC

MAGEC is the most awkward backend: it's a compiled MATLAB solver
(`.p` file) called via subprocess. Volcatenate writes a CSV input
file, generates a .m script that builds a MATLAB struct of settings,
and runs `matlab -batch …`.

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
| `fe_redox`     | Choice of Fe redox model.`1` = Sun & Yao 2024, `2` = KC91 (Kress & Carmichael 1991), `3` = Hirschmann 2022.                   | `Fe32_opt`                                              | KC91 is what volcatenate's*own* internal redox conversion uses (see fallback chain below).       |
| `s_redox`      | S6+/ST relationship.`1`=Sun & Yao 2024, `2`=Nash 2019, `3`=Jugo 2010, `4`=O'Neill 2022, `5`=Boulliung 2023.               | `S62_opt`                                               |                                                                                                    |
| `scss`         | SCSS model.`1`=Blanchard 2021, `2`=Fortin 2015, `3`=Smythe 2017, `4`=O'Neill 2021.                                          | `SCSS_opt`                                              |                                                                                                    |
| `sulfide_cap`  | Sulfide capacity model.`1`=Nzotta 1999, `2`=O'Neill 2021, `3`=Boulliung 2023.                                                 | `S2max_opt`                                             |                                                                                                    |
| `co2_sol`      | CO2 solubility model.`1`=IM2012, `2`=Liu 2005, `3.x`=Burgisser 2015.                                                          | `CO2_opt`                                               |                                                                                                    |
| `h2o_sol`      | H2O solubility. Same options as `co2_sol`.                                                                                        | `H2O_opt`                                               |                                                                                                    |
| `co_sol`       | CO solubility.`1`=Armstrong 2015, `2.x`=Yoshioka 2019.                                                                          | `CO_opt`                                                |                                                                                                    |
| `adiabatic`    | `0` = isothermal (T held fixed). Other values would model decompression-induced cooling.                                          | `adiabat_r`                                             | Use `0` for almost all natural-degassing studies.                                                |
| `solver`       | MATLAB solver choice:`1`=lsqnonlin, `2`=fsolve.                                                                                 | `solver_opt`                                            | `2` is volcatenate's default. fsolve tends to be more robust for MAGEC.                          |
| `gas_behavior` | `1` = real gas (use fugacity coefficients), `2` = ideal.                                                                        | `ideal`                                                 |                                                                                                    |
| `o2_balance`   | `0` = total oxygen is conserved (mass-balance), `1` = fO2 is held to a fixed buffer.                                            | `buffer`                                                | `0` is the realistic eruptive scenario.                                                          |
| `redox_option` | Which redox indicator to*send* to MAGEC: `'logfO2'`, `'dFMQ'`, `'Fe3+/FeT'`, or `'S6+/ST'`.                               | input CSV `Initial redox options` column                | Has a multi-tier fallback chain — see below.                                                      |
| `p_start_kbar` | Starting pressure (kbar) for MAGEC's pressure grid.                                                                                 | input CSV column                                          | If satP is*higher* than `p_start_kbar`, MAGEC will not find saturation — increase this value. |
| `p_final_kbar` | Final pressure (kbar).                                                                                                              | input CSV column                                          |                                                                                                    |
| `n_steps`      | Number of pressure steps in the grid. Volcatenate creates a*log-spaced* grid from `p_start_kbar` down to `p_final_kbar`.      | (used by `np.logspace` in `_build_sample_input_rows`) | More steps = smoother curves, longer runtime.                                                      |
| `timeout`      | Subprocess timeout (seconds). MATLAB will be killed after this. Default 300s. Batch satP scales this as `timeout + 10*n_samples`. | (subprocess.run)                                          | If MAGEC hangs (typical when satP is outside range), the run is aborted and a warning logged.      |
| `overrides`    | Per-sample overrides.                                                                                                               | (resolved in `resolve_sample_config`)                   |                                                                                                    |

### Hidden behaviors — MAGEC

In `_build_sample_input_rows` at [backends/magec.py:368](../src/volcatenate/backends/magec.py):

| MAGEC field            | volcatenate value | Meaning                                                                                                                                            |
| ---------------------- | ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `melt_Cr2O3 (wt%)`   | `0.0`           | The `MeltComposition` doesn't carry Cr2O3, so it's hardcoded to zero. (MAGEC supplement examples are also zero for this column on most samples.) |
| `Reference`          | `"auto_satP"`   | Tells MAGEC to compute the saturation pressure itself rather than use a user-supplied reference P.                                                 |
| `Reference P (kbar)` | `np.nan`        | Only used when `Reference != "auto_satP"`; left NaN.                                                                                             |

#### Anhydrous renormalization

MAGEC expects oxide columns on a **volatile-free basis summing to
100 wt%**. Because typical petrological data have totals of ~99–100%
*including* H2O+CO2+S, the oxides themselves sum to ~96–98%.
Volcatenate normalizes each oxide ([backends/magec.py:450-464](../src/volcatenate/backends/magec.py)):

```
norm = 100.0 / (SiO2 + TiO2 + … + P2O5)
sio2_out = sio2 * norm
…
```

#### Volatile mol → elemental conversion

MAGEC expects `Bulk_H`, `Bulk_C`, `Bulk_S` in elemental wt% (not
H2O / CO2 / S wt%). Volcatenate does this conversion in
[backends/magec.py:466-482](../src/volcatenate/backends/magec.py):

```
Bulk_H = H2O_wt% * norm * (2/18)    # = 1/9, ratio of 2*M_H to M_H2O
Bulk_C = CO2_wt% * norm * (12/44)   # = 3/11, ratio of M_C to M_CO2
Bulk_S = S_wt%   * norm
```

The molecular weights are deliberately **rounded** (18 instead of
18.015, 44 instead of 44.01) — this matches the convention used by
the MAGEC author internally. Faithfulness to the original code is
prioritized over chemical precision.

> ⚠️ MAGEC itself appears to expect already-elemental Bulk_H/C/S in its
> input format (see the supplement's `example1.xlsx`). The conversion
> happens entirely on the volcatenate side; MAGEC does not re-do it.

#### Compositional inputs

In `_build_sample_input_rows`:

- All major oxides come from the `MeltComposition` (after the
  anhydrous renormalization above).
- `T_degas (C)` ← `comp.T_C`.
- `Bulk_H/C/S` ← computed from `comp.H2O`, `comp.CO2`, `comp.S` as above.
- `Initial redox options` and `Initial redox values` ← determined by the
  fallback chain below.
- The pressure grid is **log-spaced** (not linear) from `p_start_kbar`
  down to `p_final_kbar` with `n_steps` points.

### Fallback chain — MAGEC redox (the worst offender)

This is the single most consequential silent transformation in
volcatenate. Logic at [backends/magec.py:378-443](../src/volcatenate/backends/magec.py):

1. Honor `cfg.redox_option`:
   - `redox_option == "Fe3+/FeT"` and the sample has speciated
     Fe (or explicit Fe3FeT) → send `Fe3+/FeT`.
   - `redox_option == "dFMQ"` and the sample has `dFMQ` → send `dFMQ`.
   - `redox_option == "logfO2"` → no automatic source; falls through.
2. **Fallback** (if step 1 produced no value):
   - If `Fe3+/FeT` is available → use it.
   - Else if `dNNO` or `dFMQ` is available → **internally compute
     Fe3+/FeT via Kress & Carmichael 1991** (using the Frost-1991
     buffer at 1 bar to convert dNNO/dFMQ → logfO2, then KC91 →
     Fe3+/FeT), and send that as `Fe3+/FeT` to MAGEC. A warning is
     logged. See [backends/magec.py:402-431](../src/volcatenate/backends/magec.py).
3. If everything fails → `ValueError("No usable redox indicator")`.

> ⚠️ The KC91 substitution in step 2 is **substantively different**
> from what the user might expect:
>
> - The user asked for `dFMQ` → MAGEC actually receives `Fe3+/FeT`.
> - The conversion uses KC91 + Frost91 FMQ at **1 bar**, not at the
>   sample's actual P.
> - This is intentional, because MAGEC's own dFMQ→logfO2 path is less
>   robust than its Fe3+/FeT path.
> - It is logged as a warning but the user might not see warnings in
>   their notebook.
>
> The audit ([config_audit.md](../.claude/notes/config_audit.md))
> proposes a `redox_source` knob to make this explicit.

---

## SulfurX

SulfurX is a Python library that is not pip-installable — it has to be
on `sys.path` via `config.sulfurx.path`. Volcatenate calls into its
internal modules directly (`Iacono_Marziano_COH`, `degassingrun`,
`OxygenFugacity`, etc.) rather than going through a single entry point.

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
| `coh_model`                   | Which C-O-H solubility code is used.`0` = Iacono-Marziano, `1` = VolatileCalc.                                                                                                                                            | `COH_model`                                             | These are different solubility families; results can differ by tens of percent.                                                                 |
| `slope_h2o`, `constant_h2o` | The two coefficients for the K2O-vs-H2O regression used inside Iacono-Marziano:`K2O = slope * H2O + constant`. The defaults are calibrated for Etna-like compositions.                                                      | `a`, `b` (passed to `IaconoMarziano(a=…, b=…)`)   | If your sample is far from the calibration set (e.g. a MORB), these may be wrong; consult the IM 2012 paper.                                    |
| `n_steps`                     | Number of pressure-grid points from satP down to ~0. SulfurX's loop runs once per step.                                                                                                                                       | `n_steps`                                               | More = smoother curves; SulfurX's degassing loop is slow per step (each can run ~100k inner iterations), so this affects runtime substantially. |
| `fo2_tracker`                 | `0` = fO2 is held to a fixed buffer offset (you specify dFMQ; the run keeps the melt at that dFMQ throughout). `1` = fO2 evolves with degassing (electron balance is tracked, melt redox responds to S and Fe degassing). | (selects `degassing_redox` vs `degassing_noredox`)    | `1` is the realistic choice for natural eruptive degassing.                                                                                   |
| `s_fe_choice`                 | S6+/ST model:`0` = Nash 2019, `1` = O'Neill & Mavrogenes 2022.                                                                                                                                                            | `S_Fe_choice` (and `model_choice` in `Sulfur_Iron`) |                                                                                                                                                 |
| `sigma`                       | log10 fO2 tolerance (numerical) for the per-step redox solver. Smaller = tighter convergence, slower.                                                                                                                         | `sigma`                                                 | Default `0.005` is typical; rarely needs changing.                                                                                            |
| `sulfide_pre`                 | If `1`, the model checks SCSS at each step and precipitates sulfide if S exceeds it (clipping melt S). If `0`, no sulfide phase ever forms.                                                                               | `sulfide_pre`                                           |                                                                                                                                                 |
| `overrides`                   | Per-sample overrides.                                                                                                                                                                                                         | (resolved in `resolve_sample_config`)                   |                                                                                                                                                 |

### Hidden behaviors — SulfurX

In `_run_degassing` at [backends/sulfurx.py:335](../src/volcatenate/backends/sulfurx.py):

| Variable                          | volcatenate value                             | Meaning                                                                                                                           |
| --------------------------------- | --------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `choice` (crystallization flag) | `0` (no crystallization)                    | SulfurX supports a fractional-crystallization mode; volcatenate disables it.                                                      |
| `open_degassing`                | `0` (closed)                                | Closed-system degassing; open-system is hardcoded off.                                                                            |
| `d34s_initial`                  | `0.0`                                       | δ³⁴S isotope tracking is disabled by hardcoded zero.                                                                           |
| `sulfide` (sulfide composition) | `{Fe: 65.43, Ni: 0, Cu: 0, O: 0, S: 36.47}` | The composition of the equilibrium sulfide phase used for SCSS calculations. Hardcoded to the SulfurX `main_Fuego.py` defaults. |

#### Composition monkey-patch (very important!)

SulfurX has a class `degassingrun.MeltComposition` whose constructor
**hardcodes a specific Hawaiian basalt composition** (when `choice=0`).
Inside the degassing loop, every pressure step creates a fresh
`MeltComposition(...)` and feeds it to IaconoMarziano, OxygenFugacity,
etc. If the *real* sample composition differs from the Hawaiian basalt,
the initial conditions (computed with the real composition) and the
per-step calculations (using the hardcoded one) become inconsistent,
and SulfurX's inner solver hangs at 100k iterations.

`_patch_composition` ([backends/sulfurx.py:209](../src/volcatenate/backends/sulfurx.py))
replaces `degassingrun.MeltComposition` with a tiny wrapper that
returns the *volcatenate* sample composition (normalized to 100 wt%)
for every call inside the loop. The original class is restored on exit.

> If you are reading SulfurX docs and wondering whether your sample
> composition was used: **yes**. The monkey-patch is in place every
> time volcatenate runs SulfurX.

#### Robust satP search

SulfurX's IM saturation-pressure solver uses a single `scipy.root` call
seeded from `pressure*10` MPa, and silently returns the seed unchanged
on non-convergence. This is fragile. Volcatenate replaces it with
`_find_saturation_pressure_im` at
[backends/sulfurx.py:76](../src/volcatenate/backends/sulfurx.py), which:

1. Tries 11 starting pressures (10–400 MPa) × 3 starting `XH2O_f`
   guesses (0.01, 0.5, 0.9) = 33 attempts.
2. Filters out non-convergent (where the solver didn't move from the seed).
3. Clusters converged results within 200-bar windows.
4. Picks the *lowest-pressure* cluster with ≥ 2 members (true
   solutions attract many starting guesses).
5. Returns the median P_sat and XH2O_f from the winning cluster.

This is volcatenate's own algorithm — there is no equivalent in the
upstream SulfurX. It applies to both `calculate_saturation_pressure`
and to step 1 of the degassing run.

### Fallback chain — SulfurX dFMQ

`_compute_delta_fmq` at [backends/sulfurx.py:275](../src/volcatenate/backends/sulfurx.py):

SulfurX needs a single `delta_FMQ` value to set fO2. Volcatenate
computes it from whichever redox indicator the sample provides:

1. If the sample has `dFMQ` → use it directly.
2. Else if it has Fe3+/FeT (from speciated Fe or explicit `Fe3FeT`) →
   invert KC91 at 1 bar to get logfO2, subtract Frost-1991 FMQ at the
   sample's T → dFMQ. Logged at INFO.
3. Else if it has `dNNO` → convert via Frost-1991:
   `dFMQ = dNNO + (NNO(T) - FMQ(T))` at 1 bar. Logged at INFO.
4. Else → `ValueError("SulfurX requires a redox constraint")`.

The temperature-dependent NNO–FMQ offset (≈ 0.74 at 1200 °C, 0.75 at
1030 °C) is computed properly — this used to be approximated as a
constant 0.7 in older versions, which was wrong by ~0.04–0.05 log
units.

The KC91 inversion uses Brent's method (`scipy.optimize.brentq`)
over the logfO2 range −25 to 0, which is generous (IW−5 to HM+5).
If Brent's method fails, the wrapper falls through to the dNNO
path with a warning.

---

## Quick cross-reference

If you change one of the following YAML knobs, here is roughly what
happens across all backends.

### "I want closed-system degassing"

| Backend | YAML setting                                      |
| ------- | ------------------------------------------------- |
| VESIcal | `vesical.fractionate_vapor: 0.0`                |
| VolFe   | `volfe.gassing_style: closed`                   |
| EVo     | `evo.run_type: closed` (default)                |
| MAGEC   | always closed (no toggle exposed)                 |
| SulfurX | always closed (`open_degassing` hardcoded to 0) |

### "I want open-system degassing"

| Backend | YAML setting                                       |
| ------- | -------------------------------------------------- |
| VESIcal | `vesical.fractionate_vapor: 1.0`                 |
| VolFe   | `volfe.gassing_style: open`                      |
| EVo     | `evo.run_type: open` AND `evo.loss_frac < 1.0` |
| MAGEC   | not currently exposed                              |
| SulfurX | not currently exposed                              |

### "I want to use my own dFMQ value"

| Backend | What you need on the sample                                                                                                      | What the wrapper sends                             |
| ------- | -------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------- |
| VESIcal | (no fO2 input)                                                                                                                   | n/a                                                |
| VolFe   | `dFMQ` and `volfe.fo2_column: DFMQ`                                                                                          | `DFMQ` column                                    |
| EVo     | `dFMQ` (auto-picked by `_pick_evo_buffer`)                                                                                   | `FO2_buffer=FMQ`, offset = sample dFMQ           |
| MAGEC   | `dFMQ` and `magec.redox_option: dFMQ` — **but** the wrapper may convert it to Fe3+/FeT via KC91 anyway (see fallback) | `dFMQ` *or* `Fe3+/FeT` (silent substitution) |
| SulfurX | `dFMQ` (always preferred when present)                                                                                         | `delta_FMQ`                                      |

### Solubility-model choice

The single biggest driver of inter-model disagreement is solubility.
Each backend has its own solubility-model knobs:

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

- [`configuration.md`](configuration.md) — top-level YAML schema and
  loading.
- [`run_bundles.md`](run_bundles.md) — reproducible run bundles
  (which include the resolved config so you can replay).
- [`.claude/notes/config_audit.md`](../.claude/notes/config_audit.md) —
  full audit of every hardcoded literal, every silent fallback, and
  the proposed promotions for upcoming releases.
- The wrapper modules under
  [`src/volcatenate/backends/`](../src/volcatenate/backends/) —
  read these whenever the doc above is unclear; they are short and
  the source of truth.
