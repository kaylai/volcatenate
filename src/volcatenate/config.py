"""Configuration dataclasses for each model backend.

Defaults match the settings used in the Sulfur Comparison Paper.

Configuration can be set in Python or loaded from a YAML file::

    # Python-only
    from volcatenate.config import RunConfig, EVoConfig
    config = RunConfig(evo=EVoConfig(p_stop=10))

    # From YAML (edit only the fields you need)
    from volcatenate.config import load_config, save_config
    save_config(RunConfig(), "volcatenate_config.yaml")   # generate template
    config = load_config("volcatenate_config.yaml")       # load it back
"""

from __future__ import annotations

import glob
import os
import platform
import shutil
from dataclasses import dataclass, field, fields, is_dataclass, replace, MISSING as dataclass_field_missing
from typing import Any, Literal, Type, TypeVar

from volcatenate.log import logger


# ── Auto-detection helpers ───────────────────────────────────────

def _find_matlab() -> str:
    """Try to locate the MATLAB binary automatically.

    Search order:
      1. ``MATLAB_BIN`` environment variable
      2. ``matlab`` on ``$PATH`` (via ``shutil.which``)
      3. Common installation directories (macOS / Linux / Windows)

    Returns ``""`` if nothing is found.
    """
    # 1. Explicit environment variable
    env = os.environ.get("MATLAB_BIN", "")
    if env and os.path.isfile(env):
        return env

    # 2. On $PATH
    on_path = shutil.which("matlab")
    if on_path:
        return on_path

    # 3. Common installation directories
    system = platform.system()
    candidates: list[str] = []

    if system == "Darwin":
        # macOS: /Applications/MATLAB_R20*.app/bin/matlab (newest first)
        candidates = sorted(
            glob.glob("/Applications/MATLAB_R*.app/bin/matlab"),
            reverse=True,
        )
    elif system == "Linux":
        candidates = sorted(
            glob.glob("/usr/local/MATLAB/R*/bin/matlab"),
            reverse=True,
        )
    elif system == "Windows":
        candidates = sorted(
            glob.glob("C:\\Program Files\\MATLAB\\R*\\bin\\matlab.exe"),
            reverse=True,
        )

    for c in candidates:
        if os.path.isfile(c):
            return c

    return ""


def _find_magec_solver() -> str:
    """Try to locate the MAGEC solver directory automatically.

    Search order:
      1. ``MAGEC_SOLVER_DIR`` environment variable
      2. Directory containing ``MAGEC_Solver_v1b.p`` anywhere under
         common locations (home directory, ``~/MAGEC*``, etc.)

    Returns ``""`` if nothing is found.
    """
    # 1. Explicit environment variable
    env = os.environ.get("MAGEC_SOLVER_DIR", "")
    if env and os.path.isdir(env):
        return env

    # 2. Search common locations for the compiled solver file
    home = os.path.expanduser("~")
    search_roots = [
        os.path.join(home, "PythonGit", "Volatile_Models", "MAGEC*"),
        os.path.join(home, "MAGEC*"),
        os.path.join(home, "Documents", "MAGEC*"),
        os.path.join(home, "Desktop", "MAGEC*"),
    ]

    for pattern in search_roots:
        for root in sorted(glob.glob(pattern), reverse=True):
            matches = glob.glob(
                os.path.join(root, "**", "MAGEC_Solver_v1b.p"),
                recursive=True,
            )
            if matches:
                return os.path.dirname(matches[0])

    return ""


def _find_sulfurx() -> str:
    """Try to locate the SulfurX installation directory automatically.

    Search order:
      1. ``SULFURX_PATH`` environment variable
      2. Directory containing ``Iacono_Marziano_COH.py`` under
         common locations.

    Returns ``""`` if nothing is found.
    """
    # 1. Explicit environment variable
    env = os.environ.get("SULFURX_PATH", "")
    if env and os.path.isdir(env):
        return env

    # 2. Search common locations
    home = os.path.expanduser("~")
    search_roots = [
        os.path.join(home, "PythonGit", "Volatile_Models", "Sulfur*"),
        os.path.join(home, "Sulfur*"),
        os.path.join(home, "Documents", "Sulfur*"),
        os.path.join(home, "Desktop", "Sulfur*"),
    ]

    for pattern in search_roots:
        for root in sorted(glob.glob(pattern), reverse=True):
            marker = os.path.join(root, "Iacono_Marziano_COH.py")
            if os.path.isfile(marker):
                return root
            # Check one level deeper
            matches = glob.glob(os.path.join(root, "*", "Iacono_Marziano_COH.py"))
            if matches:
                return os.path.dirname(matches[0])

    return ""


@dataclass
class VESIcalConfig:
    """VESIcal model configuration.

    The solubility model is selected by the backend name passed to
    ``calculate_*`` (e.g. ``"VESIcal_Iacono"``, ``"VESIcal_Dixon"``),
    not by config.
    """

    steps: int = 101
    final_pressure: float = 1.0       # bar
    fractionate_vapor: float = 0.0    # 0 = closed, 1 = open

    # Per-sample overrides: {sample_name: {field_name: value}}
    # Example: {"Fogo": {"steps": 50, "final_pressure": 10.0}}
    # Unknown field names are warned and skipped at resolution time.
    overrides: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class VolFeConfig:
    """VolFe model configuration.

    Always sourced from the input ``MeltComposition`` (not config):
      - Sample name, ``T_C``, all major oxides, ``H2O`` (wt%),
        ``CO2`` (→ ppm), ``S`` (→ ppm), ``Xppm``
      - The redox column used (``DNNO`` / ``Fe3FeT`` / ``DFMQ``) is
        chosen by ``fo2_column`` and ``fo2_source`` below.

    Always managed by volcatenate (not exposed here):
      - VolFe ``output csv`` — always False; volcatenate handles
        its own output.
      - VolFe ``print status`` — always False; volcatenate routes
        logging through its own logger.
      - VolFe ``solve_species`` — internal solver hint that VolFe
        re-sets during the calculation, so user-set values are
        clobbered ([equilibrium_equations.py:39-60]).
      - VolFe ``mass_volume`` — left at "mass"; the "volume" branch
        is marked NEEDS FIXING upstream and is unsafe.
      - VolFe ``setup`` — debug-only flag.

    See ``docs/config_propagation.md`` for the full mapping of fields
    here onto VolFe's own model option names.
    """

    # ── Saturation ───────────────────────────────────────────────────
    sulfur_saturation: bool = False
    graphite_saturation: bool = False
    sulfur_is_sat: Literal["yes", "no"] = "no"  # Treat melt as sulfur-saturated at start

    # ── Redox input ──────────────────────────────────────────────────
    # ``fo2_column`` is the volcatenate-specific knob for which redox
    # column to feed into VolFe's ``setup_df`` (DNNO / Fe3FeT / DFMQ).
    # ``fo2_source`` controls how strictly that choice is enforced:
    #   "auto" — fall back through the priority chain if the requested
    #            column is missing (current behavior, with INFO logging).
    #   "fe3fet"/"dnno"/"dfmq" — require that exact column on the comp
    #            and raise if missing.
    fo2_column: str = "Fe3FeT"        # 'DNNO', 'Fe3FeT', or 'DFMQ'
    fo2_source: Literal["auto", "fe3fet", "dnno", "dfmq"] = "auto"

    # ── Degassing geometry ───────────────────────────────────────────
    gassing_style: str = "closed"       # 'closed' or 'open'
    gassing_direction: str = "degas"    # 'degas' or 'regas'
    bulk_composition: str = "melt-only" # 'melt-only', 'melt+vapor_wtg', 'melt+vapor_initialCO2'
    starting_p: Literal["Pvsat", "set"] = "Pvsat"   # Where to start: at saturation pressure or at a user-set P
    p_variation: Literal["polybaric", "isobaric"] = "polybaric"
    t_variation: Literal["isothermal", "polythermal"] = "isothermal"
    crystallisation: Literal["no", "yes"] = "no"     # Track crystallization during degassing

    # ── Iron / oxygen redox handling ─────────────────────────────────
    # eq_Fe="yes" tracks Fe redox equilibrium with fO2 every step.
    # eq_Fe="no" freezes Fe (sets wt_Fe=0 internally), decoupling
    # iron from gas-phase chemistry. See VolFe calculations.py:433-447.
    eq_fe: Literal["yes", "no"] = "yes"
    bulk_o: Literal["exc_S", "inc_S"] = "exc_S"      # Whether sulfur-bound O is included in bulk O accounting
    calc_sat: Literal["fO2_melt", "fO2_fX"] = "fO2_melt"  # Saturation-pressure search mode

    # ── Species ──────────────────────────────────────────────────────
    coh_species: str = "yes_H2_CO_CH4_melt"  # COH species in melt and vapor
    h2s_melt: bool = True               # H2S as dissolved melt species
    species_x: str = "Ar"               # Chemical identity of species X ('Ar' or 'Ne')
    h_speciation: str = "none"          # H melt speciation (only "none" supported by VolFe today)

    # ── Oxygen fugacity ──────────────────────────────────────────────
    fo2_model: str = "Kress91A"          # fO2–Fe3+/FeT relationship
    fmq_buffer: str = "Frost91"          # FMQ buffer parameterisation
    nno_buffer: str = "Frost91"          # NNO buffer parameterisation

    # ── Bulk physical model ──────────────────────────────────────────
    density: str = "DensityX"            # Melt density model
    melt_composition: str = "Basalt"     # Melt-composition family for parameterizations

    # ── Solubility constants ─────────────────────────────────────────
    co2_sol: str = "MORB_Dixon95"        # CO2T solubility constant
    h2o_sol: str = "Basalt_Hughes24"     # H2O solubility constant
    h2_sol: str = "Basalt_Hughes24"      # H2 solubility constant
    sulfide_sol: str = "ONeill21dil"     # S2- solubility constant
    sulfate_sol: str = "ONeill22dil"     # S6+ solubility constant
    h2s_sol: str = "Basalt_Hughes24"     # H2S solubility constant
    ch4_sol: str = "Basalt_Ardia13"      # CH4 solubility constant
    co_sol: str = "Basalt_Hughes24"      # CO solubility constant
    x_sol: str = "Ar_Basalt_Hughes25"    # Species X solubility constant
    c_spec_comp: str = "Basalt"          # CO2mol/CO32- speciation model
    h_spec_comp: str = "MORB_HughesIP"   # H2Omol/OH- speciation model

    # ── Saturation conditions ────────────────────────────────────────
    scss: str = "ONeill21hyd"            # SCSS model
    scas: str = "Zajacz19_pss"           # SCAS model

    # ── Fugacity coefficients ────────────────────────────────────────
    ideal_gas: bool = False              # Treat all vapor species as ideal gases
    y_co2: str = "Shi92"                 # CO2 fugacity coefficient
    y_so2: str = "Shi92_Hughes23"        # SO2 fugacity coefficient
    y_h2s: str = "Shi92_Hughes24"        # H2S fugacity coefficient
    y_h2: str = "Shaw64"                 # H2 fugacity coefficient
    y_o2: str = "Shi92"                  # O2 fugacity coefficient
    y_s2: str = "Shi92"                  # S2 fugacity coefficient
    y_co: str = "Shi92"                  # CO fugacity coefficient
    y_ch4: str = "Shi92"                 # CH4 fugacity coefficient
    y_h2o: str = "Holland91"             # H2O fugacity coefficient
    y_ocs: str = "Shi92"                 # OCS fugacity coefficient
    y_x: str = "ideal"                   # Species X fugacity coefficient

    # ── Equilibrium constants (string model identifiers) ─────────────
    k_hog: str = "Ohmoto97"             # H2 + 0.5 O2 = H2O
    k_hosg: str = "Ohmoto97"            # H2S equilibrium (0.5S2 + H2O = H2S + 0.5O2)
    k_osg: str = "Ohmoto97"             # SO2 equilibrium (0.5S2 + O2 = SO2)
    k_osg2: str = "ONeill22"            # SO4 / sulfate equilibrium
    k_cog: str = "Ohmoto97"             # CO + 0.5 O2 = CO2
    k_cohg: str = "Ohmoto97"            # CH4 equilibrium (CH4 + 2O2 = CO2 + 2H2O)
    k_ocsg: str = "Moussallam19"         # OCS equilibrium
    k_cos: str = "Holloway92"           # CO2 / carbonate solubility eq.
    carbonylsulfide: str = "COS"         # Carbonyl-sulfide species name

    # ── Isotopes ─────────────────────────────────────────────────────
    # All of these only matter when isotopes="yes". They are string
    # model identifiers (e.g. "Rust04", "Lee24"), not numeric values.
    isotopes: Literal["no", "yes"] = "no"
    beta_factors: str = "Richet77"
    alpha_h_ch4v_ch4m: str = "no fractionation"
    alpha_h_h2v_h2m: str = "no fractionation"
    alpha_h_h2ov_ohmm: str = "Rust04"
    alpha_h_h2ov_h2om: str = "Rust04"
    alpha_h_h2sv_h2sm: str = "no fractionation"
    alpha_c_ch4v_ch4m: str = "no fractionation"
    alpha_c_cov_com: str = "no fractionation"
    alpha_c_co2v_co2t: str = "Lee24"
    alpha_c_co2v_co2m: str = "Blank93"
    alpha_c_co2v_co32mm: str = "Lee24"
    alpha_s_h2sv_h2sm: str = "no fractionation"
    alpha_so2_so4: str = "Fiege15"
    alpha_h2s_s: str = "Fiege15"

    # ── Numerical / runtime ──────────────────────────────────────────
    error: float = 0.1                 # Numerical tolerance for the solver
    high_precision: bool = False       # Run in high-precision mode (slower)

    # Per-sample overrides: {sample_name: {field_name: value}}
    # Example: {"Fogo": {"gassing_style": "open", "scss": "Fortin15"}}
    # Unknown field names are warned and skipped at resolution time.
    overrides: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class EVoConfig:
    """EVo model configuration.

    Always sourced from the input ``MeltComposition`` (not config):
      - Sample name, ``T_C``, all major oxides
      - ``WTH2O_START`` ← ``comp.H2O / 100``
      - ``WTCO2_START`` ← ``comp.CO2 / 100``
      - ``SULFUR_START`` ← ``comp.S / 100``
      - FeO/Fe2O3 split written into ``chem.yaml`` from
        ``comp.fe3fet_computed``

    Always managed by volcatenate (not exposed here):
      - ``WTH2O_SET``, ``WTCO2_SET``, ``SULFUR_SET`` — always True
      - ``FO2_buffer_SET`` — True only when no Fe3+/FeT data on the
        sample (controlled by the ``fo2_source`` knob below)
      - ``FO2_buffer`` / ``FO2_buffer_START`` — picked from
        ``comp.dNNO`` / ``comp.dFMQ`` when buffering is active
      - ``output.yaml`` plot flags — all False (volcatenate uses its
        own DataFrames, not EVo's plot output)

    See ``docs/config_propagation.md`` for the full mapping of fields
    here onto EVo's own ``env.yaml`` / ``chem.yaml`` keys.
    """

    gas_system: str = "cohs"
    composition: Literal["basalt", "phonolite", "rhyolite"] = "basalt"
    fo2_buffer: str = "FMQ"
    fe_system: bool = True
    find_saturation: bool = True
    single_step: bool = False         # If True, runs at a single P,T; only meaningful when find_saturation is False
    s_sat_warn: bool = False          # If True, EVo prints a warning when sulfide saturation is reached
    atomic_mass_set: bool = False
    ocs: bool = False                 # Include OCS as a gas species
    dp_min: int = 1
    dp_max: int = 100
    mass: int = 100
    p_start: int = 3000              # bar
    p_stop: int = 1                  # bar
    wgt: float = 0.00001             # Initial gas weight fraction
    loss_frac: float = 0.9999        # Gas loss fraction per step (open-system)
    run_type: str = "closed"           # 'closed' or 'open' (open requires loss_frac < 1)

    # Volatile initialization as atomic mass fractions (ppm).
    # Only used when atomic_mass_set = True.
    atomic_h: float = 500
    atomic_c: float = 200
    atomic_s: float = 4000
    atomic_n: float = 10

    # Nitrogen and graphite
    nitrogen_set: bool = False        # Set N from composition (if True, uses N from MeltComposition)
    nitrogen_start: float = 0.0001    # Starting N mass fraction when nitrogen_set is True and comp.N missing
    graphite_saturated: bool = False  # Graphite saturation at start
    graphite_start: float = 0.0001    # Initial graphite mass fraction when graphite_saturated is True

    # ── How fO2 is set at the start of the run ───────────────────────
    # See ``_pick_evo_buffer`` and ``_apply_fo2_source`` in
    # backends/evo.py for the exact semantics.
    #
    #   "auto"     — current default behavior. Picks the best available
    #                source on the sample (Fe3+/FeT > dNNO > dFMQ > the
    #                ``fo2_buffer`` field below at offset 0). Logs the
    #                choice; never raises.
    #   "fe3fet"   — require Fe3+/FeT (or speciated FeO+Fe2O3) on the
    #                sample. Raises if missing.
    #   "buffer"   — require ``comp.dNNO`` or ``comp.dFMQ`` on the
    #                sample (whichever matches ``fo2_buffer``). Raises
    #                if missing.
    #   "absolute" — set absolute fO2 from ``fo2_start`` (in bar).
    #                Bypasses the iron split entirely.
    fo2_source: Literal["auto", "fe3fet", "buffer", "absolute"] = "auto"

    # Absolute fugacity entry points. EVo's ``env.yaml`` exposes these
    # as alternate ways to initialize redox / fugacity. Most users do
    # NOT need them — the default (``fo2_source="auto"``) drives EVo
    # via Fe3+/FeT or the buffer path. Set ``fo2_source="absolute"``
    # and ``fo2_start`` to use ``FO2_SET=True`` mode.
    fo2_set: bool = False             # EVo env.yaml FO2_SET — written from fo2_source
    fo2_start: float = 0.0            # Absolute fO2 (bar). Used only when fo2_source="absolute"
    fh2_set: bool = False             # EVo env.yaml FH2_SET — set H2 fugacity as a starting condition
    fh2_start: float = 0.24           # H2 fugacity (bar)
    fh2o_set: bool = False            # EVo env.yaml FH2O_SET — set H2O fugacity as a starting condition
    fh2o_start: float = 1000.0        # H2O fugacity (bar)
    fco2_set: bool = False            # EVo env.yaml FCO2_SET — set CO2 fugacity as a starting condition
    fco2_start: float = 1.0           # CO2 fugacity (bar)

    # Solubility model selections
    h2o_model: str = "burguisser2015"
    h2_model: str = "gaillard2003"
    c_model: str = "burguisser2015"
    co_model: str = "armstrong2015"
    ch4_model: str = "ardia2013"
    sulfide_capacity: str = "oneill2020"
    sulfate_capacity: str = "nash2019"
    scss: str = "liu2007"
    n_model: str = "libourel2003"
    density_model: str = "spera2000"
    fo2_model: str = "kc1991"
    fmq_model: str = "frost1991"

    # Per-sample overrides: {sample_name: {field_name: value}}
    # Example: {"MORB": {"dp_max": 25}, "Fogo": {"p_start": 5000, "gas_system": "coh"}}
    # Unknown field names are warned and skipped at resolution time.
    overrides: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class MAGECConfig:
    """MAGEC model configuration (MATLAB subprocess).

    Always sourced from the input ``MeltComposition`` (not config):
      - Sample name, ``T_C``, all major oxides (incl. ``Cr2O3``),
        ``H2O``, ``CO2``, ``S``
      - The redox indicator (Fe3+/FeT, dNNO, dFMQ) is selected per
        ``redox_option`` and ``redox_source`` below.

    Always managed by volcatenate (not exposed here):
      - MAGEC's ``Reference`` column = ``"auto_satP"``, telling MAGEC
        to search for the saturation pressure rather than using a
        user-supplied initial pressure (the alternate "referenced"
        mode where you'd set ``Reference P (kbar)`` is not surfaced
        because volcatenate always wants auto satP).
      - ``Bulk_H``/``Bulk_C``/``Bulk_S`` are converted from H2O/CO2/S
        wt% via the rounded molecular-weight ratios from the
        Sun & Yao 2024 example files (2/18, 12/44).
      - Anhydrous renormalization to 100 wt% before passing to MAGEC.

    The *solver_dir* and *matlab_bin* paths are auto-detected at
    import time.  You can also set the environment variables
    ``MAGEC_SOLVER_DIR`` and ``MATLAB_BIN`` to override detection.
    """

    solver_dir: str = field(default_factory=_find_magec_solver)
    matlab_bin: str = field(default_factory=_find_matlab)

    # Model settings (14 options matching MAGEC's settings sheet)
    sulfide_sat: int = 0       # (1) Yes; (0) No
    sulfate_sat: int = 0       # (1) Yes; (0) No
    graphite_sat: int = 0      # (1) Yes; (0) No
    fe_redox: int = 1          # (1) Sun & Yao 2024; (2) KC91; (3) Hirschmann 2022
    s_redox: int = 1           # (1) Sun & Yao 2024; (2) Nash 2019; (3) Jugo 2010;
                               #   (4) O'Neill 2022; (5) Boulliung 2023
    scss: int = 1              # (1) Blanchard 2021; (2) Fortin 2015;
                               #   (3) Smythe 2017; (4) O'Neill 2021
    sulfide_cap: int = 1       # (1) Nzotta 1999; (2) O'Neill 2021; (3) Boulliung 2023
    co2_sol: int = 1           # (1) IM2012; (2) Liu 2005; (3.x) Burgisser 2015
    h2o_sol: int = 1           # (1) IM2012; (2) Liu 2005; (3.x) Burgisser 2015
    co_sol: int = 1            # (1) Armstrong 2015; (2.x) Yoshioka 2019
    adiabatic: int = 0         # 0 = isothermal
    solver: int = 2            # (1) lsqnonlin; (2) fsolve
    gas_behavior: int = 1      # (1) real gas; (2) ideal
    o2_balance: int = 0        # (0) Total O balanced; (1) fixed fO2 buffer

    # ── Redox selection ──────────────────────────────────────────────
    # ``redox_option`` is the column name MAGEC will read.
    # ``redox_source`` controls how strictly that choice is enforced
    # and whether the wrapper is allowed to do its own KC91 conversion
    # when only buffer-relative redox (dNNO / dFMQ) is on the sample:
    #
    #   "auto"               — current behavior. Honors redox_option
    #                          when possible, falls through to whichever
    #                          indicator the comp does have, and as a
    #                          last resort computes Fe3+/FeT from
    #                          dNNO/dFMQ via KC91 + Frost-1991 buffer
    #                          at 1 bar (a substantively different
    #                          calculation, logged at WARNING).
    #   "fe3fet" / "dfmq" / "dnno"
    #                        — require that exact indicator on the
    #                          sample; raise ValueError if missing.
    #   "kc91_from_buffer"   — explicitly opt into the KC91 conversion
    #                          even when Fe3+/FeT is also available.
    redox_option: str = "Fe3+/FeT"   # 'logfO2', 'dFMQ', 'Fe3+/FeT', or 'S6+/ST'
    redox_source: Literal["auto", "fe3fet", "dfmq", "dnno", "kc91_from_buffer"] = "auto"
    p_start_kbar: float = 3.0
    p_final_kbar: float = 0.001
    n_steps: int = 100

    # Subprocess timeout (seconds) — if MAGEC hangs (e.g. saturation
    # pressure outside search range), it will be killed after this.
    timeout: int = 300

    # Per-sample overrides: {sample_name: {field_name: value}}
    # Example: {"Fogo": {"p_start_kbar": 8.0}}
    # Unknown field names are warned and skipped at resolution time.
    overrides: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class SulfurXSulfideConfig:
    """Sulfide phase composition for SulfurX.

    SulfurX needs an explicit sulfide composition to compute sulfide
    saturation behavior. Default values follow ``main_Fuego.py`` from
    the SulfurX distribution (Fe65.43, S36.47 — a near-stoichiometric
    pyrrhotite). All values are weight percent of the sulfide phase
    (not the melt).
    """

    fe: float = 65.43
    ni: float = 0.0
    cu: float = 0.0
    o: float = 0.0
    s: float = 36.47


@dataclass
class SulfurXConfig:
    """SulfurX model configuration.

    Always sourced from the input ``MeltComposition`` (not config):
      - Sample name, ``T_C``, all major oxides, ``H2O`` (wt%),
        ``CO2`` (→ ppm), ``S`` (→ ppm)
      - The starting ``delta_FMQ`` is computed from whichever redox
        indicator the sample carries (``dFMQ`` direct, then Fe3+/FeT
        via KC91, then ``dNNO`` via Frost-1991 buffer offset). See
        :func:`backends.sulfurx._compute_delta_fmq`.

    Always managed by volcatenate (not exposed here):
      - SulfurX bundles a hardcoded reference composition (Fuego) into
        its internal ``MeltComposition`` class. The volcatenate
        wrapper monkey-patches that class so SulfurX uses the
        sample composition you actually passed in.

    The *path* is auto-detected at import time.  You can also set
    the environment variable ``SULFURX_PATH`` to override detection.
    """

    path: str = field(default_factory=_find_sulfurx)
    coh_model: int = 0                # 0 = Iacono-Marziano, 1 = VolatileCalc
    slope_h2o: float = -0.3396        # K2O-H2O relationship: K2O = a * H2O + b
    constant_h2o: float = 2.7
    n_steps: int = 600                # Pressure grid steps for degassing
    fo2_tracker: int = 1              # 0 = buffered fO2, 1 = redox evolution
    s_fe_choice: int = 1              # S speciation model: 0=Nash, 1=O'Neill&Mavrogenes
    sigma: float = 0.005              # log10fO2 tolerance for redox calculation
    sulfide_pre: int = 0              # 0 = no sulfide precipitation, 1 = enabled

    # Crystallization / degassing geometry (previously hardcoded).
    crystallization: int = 0          # 0 = no crystallization (the only path SulfurX exercises today)
    open_degassing: int = 0           # 0 = closed-system degassing, 1 = open-system
    d34s_initial: float = 0.0         # Initial bulk d34S (only used when isotope tracking is wired up)

    # Sulfide phase composition (SulfurX uses this for sulfide saturation).
    sulfide: SulfurXSulfideConfig = field(default_factory=SulfurXSulfideConfig)

    # Per-sample overrides: {sample_name: {field_name: value}}
    # Example: {"Fogo": {"n_steps": 100, "sigma": 0.001}}
    # Unknown field names are warned and skipped at resolution time.
    overrides: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class DCompressConfig:
    """DCompress model configuration (stub)."""

    pass


@dataclass
class RunConfig:
    """Top-level configuration composing all model configs.

    Parameters
    ----------
    output_dir : str
        Root directory for all output files (results CSVs, figures,
        raw tool output).  Default ``""`` means the current working
        directory.
    raw_output_dir : str
        Subdirectory (relative to *output_dir*) for raw model files
        — EVo YAML configs, MAGEC MATLAB scripts, per-sample
        subdirectories, etc.  Default ``"raw_tool_output"``.
    keep_raw_output : bool
        If *True* (default), all raw tool output files are retained
        in *raw_output_dir* for inspection.  If *False*, raw files
        are cleaned up after each model run completes, keeping only
        the final result DataFrames in memory.
    """

    output_dir: str = "."
    raw_output_dir: str = "raw_tool_output"
    keep_raw_output: bool = True
    verbose: bool = False
    log_file: str = ""
    show_progress: bool = True
    save_bundle: str = ""
    bundle_comments: str = ""

    vesical: VESIcalConfig = field(default_factory=VESIcalConfig)
    volfe: VolFeConfig = field(default_factory=VolFeConfig)
    evo: EVoConfig = field(default_factory=EVoConfig)
    magec: MAGECConfig = field(default_factory=MAGECConfig)
    sulfurx: SulfurXConfig = field(default_factory=SulfurXConfig)
    dcompress: DCompressConfig = field(default_factory=DCompressConfig)


# ── Bundled default config ────────────────────────────────────────────

_DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "default_config.yaml")


def default_config_path() -> str:
    """Return the path to the bundled default config YAML.

    The file contains all settings with their paper-default values and
    inline comments.  **Do not edit this file directly** — it lives
    inside the installed package and will be overwritten on reinstall.

    Instead, copy it to your project and edit the copy::

        # Easiest — from the command line:
        volcatenate init-config

        # Or in Python:
        import shutil, volcatenate
        shutil.copy(volcatenate.default_config_path(), "volcatenate_config.yaml")
    """
    return _DEFAULT_CONFIG_PATH


# ── Inline comments for YAML export ──────────────────────────────────
# Maps (section, field_name) → comment string.  Used by save_config()
# to produce human-readable YAML with the same documentation as the
# dataclass definitions above.

_FIELD_COMMENTS: dict[tuple[str, str], str] = {
    # top-level
    ("_top", "output_dir"):          "Root directory for all output (default: working directory)",
    ("_top", "raw_output_dir"):     "Subdirectory for raw model files (EVo YAML, MAGEC scripts, etc.)",
    ("_top", "keep_raw_output"):    "Keep raw tool output files after run",
    ("_top", "verbose"):             "Print progress to terminal",
    ("_top", "log_file"):            "Write all output to this file (empty = no log file)",
    ("_top", "show_progress"):       "Show rich progress bars (True/False)",
    ("_top", "save_bundle"):         "Path to save reproducible JSON bundle (empty = don't save)",
    ("_top", "bundle_comments"):     "Free-text notes recorded in the run bundle (provenance only; ignored on replay)",
    # VESIcal
    ("vesical", "steps"):            "Number of degassing steps",
    ("vesical", "final_pressure"):   "bar",
    ("vesical", "fractionate_vapor"): "0 = closed-system, 1 = open-system",
    ("vesical", "overrides"):        "Per-sample overrides, e.g. {Fogo: {steps: 50}}",
    # VolFe
    ("volfe", "sulfur_saturation"):  "",
    ("volfe", "graphite_saturation"): "",
    ("volfe", "fo2_column"):         "'DNNO', 'Fe3FeT', or 'DFMQ'",
    ("volfe", "gassing_style"):      "'closed' or 'open'",
    ("volfe", "gassing_direction"):  "'degas' or 'regas'",
    ("volfe", "bulk_composition"):   "'melt-only', 'melt+vapor_wtg', or 'melt+vapor_initialCO2'",
    ("volfe", "coh_species"):        "'yes_H2_CO_CH4_melt', 'no_H2_CO_CH4_melt', or 'H2O-CO2 only'",
    ("volfe", "h2s_melt"):           "Include H2Smol as dissolved melt species",
    ("volfe", "species_x"):          "'Ar' or 'Ne'",
    ("volfe", "fo2_model"):          "fO2-Fe3+/FeT model: 'Kress91A', 'Kress91', 'ONeill18', 'Borisov18'",
    ("volfe", "fmq_buffer"):         "FMQ buffer: 'Frost91' or 'ONeill87'",
    ("volfe", "co2_sol"):            "CO2T solubility constant",
    ("volfe", "h2o_sol"):            "H2O solubility constant",
    ("volfe", "h2_sol"):             "H2 solubility constant",
    ("volfe", "sulfide_sol"):        "S2- solubility constant",
    ("volfe", "sulfate_sol"):        "S6+ solubility constant",
    ("volfe", "h2s_sol"):            "H2S solubility constant",
    ("volfe", "ch4_sol"):            "CH4 solubility constant",
    ("volfe", "co_sol"):             "CO solubility constant",
    ("volfe", "x_sol"):              "Species X solubility constant",
    ("volfe", "c_spec_comp"):        "CO2mol/CO32- speciation model",
    ("volfe", "h_spec_comp"):        "H2Omol/OH- speciation model",
    ("volfe", "scss"):               "SCSS model",
    ("volfe", "scas"):               "SCAS model",
    ("volfe", "ideal_gas"):          "Treat all vapor species as ideal gases",
    ("volfe", "y_co2"):              "CO2 fugacity coefficient model",
    ("volfe", "y_so2"):              "SO2 fugacity coefficient model",
    ("volfe", "y_h2s"):              "H2S fugacity coefficient model",
    ("volfe", "y_h2"):               "H2 fugacity coefficient model",
    ("volfe", "y_o2"):               "O2 fugacity coefficient model",
    ("volfe", "y_s2"):               "S2 fugacity coefficient model",
    ("volfe", "y_co"):               "CO fugacity coefficient model",
    ("volfe", "y_ch4"):              "CH4 fugacity coefficient model",
    ("volfe", "y_h2o"):              "H2O fugacity coefficient model",
    ("volfe", "y_ocs"):              "OCS fugacity coefficient model",
    ("volfe", "k_hosg"):             "H2S equilibrium constant (0.5S2 + H2O = H2S + 0.5O2)",
    ("volfe", "k_osg"):              "SO2 equilibrium constant (0.5S2 + O2 = SO2)",
    ("volfe", "k_cohg"):             "CH4 equilibrium constant (CH4 + 2O2 = CO2 + 2H2O)",
    ("volfe", "k_ocsg"):             "OCS equilibrium constant",
    ("volfe", "overrides"):          "Per-sample overrides, e.g. {Fogo: {gassing_style: open}}",
    # EVo
    ("evo", "gas_system"):           "'cohs', 'coh', 'cos', etc.",
    ("evo", "fo2_buffer"):           "'FMQ', 'NNO', etc.",
    ("evo", "fe_system"):            "Include Fe redox equilibrium",
    ("evo", "find_saturation"):      "Find saturation pressure automatically",
    ("evo", "atomic_mass_set"):      "Use atomic mass fractions for H/C/S/N",
    ("evo", "ocs"):                  "Include OCS as a gas species",
    ("evo", "dp_min"):               "Minimum pressure step (bar)",
    ("evo", "dp_max"):               "Maximum pressure step (bar)",
    ("evo", "mass"):                 "System mass (g)",
    ("evo", "p_start"):              "Starting pressure (bar)",
    ("evo", "p_stop"):               "Final pressure (bar)",
    ("evo", "wgt"):                  "Initial gas weight fraction",
    ("evo", "loss_frac"):            "Gas loss fraction per step (open-system)",
    ("evo", "run_type"):             "'closed' (default) or 'open' — open-system requires loss_frac < 1",
    ("evo", "atomic_h"):             "Atomic H (ppm) — only used when atomic_mass_set=true",
    ("evo", "atomic_c"):             "Atomic C (ppm) — only used when atomic_mass_set=true",
    ("evo", "atomic_s"):             "Atomic S (ppm) — only used when atomic_mass_set=true",
    ("evo", "atomic_n"):             "Atomic N (ppm) — only used when atomic_mass_set=true",
    ("evo", "nitrogen_set"):         "Set N from composition",
    ("evo", "graphite_saturated"):   "Graphite saturation at start",
    ("evo", "h2o_model"):            "",
    ("evo", "h2_model"):             "",
    ("evo", "c_model"):              "",
    ("evo", "co_model"):             "",
    ("evo", "ch4_model"):            "",
    ("evo", "sulfide_capacity"):     "",
    ("evo", "sulfate_capacity"):     "",
    ("evo", "scss"):                 "",
    ("evo", "n_model"):              "",
    ("evo", "density_model"):        "",
    ("evo", "fo2_model"):            "",
    ("evo", "fmq_model"):            "",
    ("evo", "overrides"):            "Per-sample overrides, e.g. {MORB: {dp_max: 25}}",
    # MAGEC
    ("magec", "solver_dir"):         "Path to MAGEC_Solver_v1b.p directory",
    ("magec", "matlab_bin"):         "Path to MATLAB binary",
    ("magec", "sulfide_sat"):        "(1) Yes; (0) No",
    ("magec", "sulfate_sat"):        "(1) Yes; (0) No",
    ("magec", "graphite_sat"):       "(1) Yes; (0) No",
    ("magec", "fe_redox"):           "(1) Sun & Yao 2024; (2) KC91; (3) Hirschmann 2022",
    ("magec", "s_redox"):            "(1) Sun & Yao 2024; (2) Nash 2019; (3) Jugo 2010; (4) O'Neill 2022; (5) Boulliung 2023",
    ("magec", "scss"):               "(1) Blanchard 2021; (2) Fortin 2015; (3) Smythe 2017; (4) O'Neill 2021",
    ("magec", "sulfide_cap"):        "(1) Nzotta 1999; (2) O'Neill 2021; (3) Boulliung 2023",
    ("magec", "co2_sol"):            "(1) IM2012; (2) Liu 2005; (3.x) Burgisser 2015",
    ("magec", "h2o_sol"):            "(1) IM2012; (2) Liu 2005; (3.x) Burgisser 2015",
    ("magec", "co_sol"):             "(1) Armstrong 2015; (2.x) Yoshioka 2019",
    ("magec", "adiabatic"):          "0 = isothermal",
    ("magec", "solver"):             "(1) lsqnonlin; (2) fsolve",
    ("magec", "gas_behavior"):       "(1) real gas; (2) ideal",
    ("magec", "o2_balance"):         "(0) Total O balanced; (1) fixed fO2 buffer",
    ("magec", "redox_option"):       "'logfO2', 'dFMQ', 'Fe3+/FeT', or 'S6+/ST'",
    ("magec", "p_start_kbar"):       "SatP search start pressure (kbar)",
    ("magec", "p_final_kbar"):       "SatP search end pressure (kbar)",
    ("magec", "n_steps"):            "Number of pressure steps for SatP search",
    ("magec", "overrides"):          "Per-sample overrides, e.g. {Fogo: {p_start_kbar: 8.0}}",
    ("magec", "timeout"):            "MATLAB subprocess timeout (seconds)",
    # SulfurX
    ("sulfurx", "path"):             "Path to SulfurX installation",
    ("sulfurx", "coh_model"):        "0 = Iacono-Marziano, 1 = VolatileCalc",
    ("sulfurx", "slope_h2o"):        "K2O-H2O relationship slope: K2O = a*H2O + b",
    ("sulfurx", "constant_h2o"):     "K2O-H2O relationship intercept",
    ("sulfurx", "n_steps"):          "Pressure grid steps for degassing",
    ("sulfurx", "fo2_tracker"):      "0 = buffered fO2, 1 = redox evolution",
    ("sulfurx", "s_fe_choice"):      "S speciation: 0=Nash, 1=O'Neill&Mavrogenes",
    ("sulfurx", "sigma"):            "log10fO2 tolerance for redox calculation",
    ("sulfurx", "sulfide_pre"):      "0 = no sulfide precipitation, 1 = enabled",
    ("sulfurx", "overrides"):        "Per-sample overrides, e.g. {Fogo: {n_steps: 100}}",
}

# Maps section name → dataclass type (for load_config)
_SECTION_CLASSES: dict[str, Type] = {
    "vesical": VESIcalConfig,
    "volfe": VolFeConfig,
    "evo": EVoConfig,
    "magec": MAGECConfig,
    "sulfurx": SulfurXConfig,
    "dcompress": DCompressConfig,
}


def resolve_sample_config(cfg, sample: str):
    """Return a copy of ``cfg`` with per-sample overrides applied.

    Looks up ``cfg.overrides[sample]``; if absent or empty, returns the
    original ``cfg`` unchanged. Otherwise returns a shallow
    ``dataclasses.replace`` copy with each listed field set.

    Unknown field names emit a warning via the volcatenate logger and
    are skipped (the original value is kept). The ``overrides`` field
    itself cannot be overridden — attempts are warned and skipped.
    """
    sample_overrides = cfg.overrides.get(sample, {})
    if not sample_overrides:
        return cfg
    valid = {f.name for f in fields(type(cfg))}
    resolved = replace(cfg, overrides=dict(cfg.overrides))
    for k, v in sample_overrides.items():
        if k not in valid or k == "overrides":
            logger.warning(
                "[%s] Unknown override field '%s' for sample '%s' — ignored",
                type(cfg).__name__, k, sample,
            )
            continue
        setattr(resolved, k, v)
    return resolved


# ── YAML I/O ─────────────────────────────────────────────────────────

def _format_value(val: object) -> str:
    """Format a Python value for YAML output."""
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, str):
        # Quote strings that could be misinterpreted by YAML
        if val == "" or val in ("true", "false", "null", "yes", "no"):
            return f'"{val}"'
        # Quote strings with special chars
        if any(c in val for c in ":#{}[]|>&*!%@`"):
            return f'"{val}"'
        return val
    if isinstance(val, float):
        s = f"{val}"
        # YAML 1.1 requires a '.' before 'e' for scientific notation
        # (e.g. '1e-05' is parsed as a string, '1.0e-05' as a float)
        if "e" in s and "." not in s:
            s = s.replace("e", ".0e", 1)
        return s
    if isinstance(val, dict):
        if not val:
            return "{}"
        # Inline YAML mapping: {key1: val1, key2: val2}
        items = ", ".join(
            f"{_format_value(k)}: {_format_value(v)}" for k, v in val.items()
        )
        return "{" + items + "}"
    return str(val)


def save_config(config: RunConfig, path: str) -> str:
    """Write a RunConfig to a commented YAML file.

    The generated file includes inline comments describing each
    setting, making it easy to edit.  All current values are written,
    so the file serves as both documentation and configuration.

    Parameters
    ----------
    config : RunConfig
        Configuration to save.
    path : str
        Output YAML file path.

    Returns
    -------
    str
        The path that was written to.
    """
    lines: list[str] = [
        "# volcatenate configuration",
        "# Generated with: volcatenate.config.save_config(RunConfig(), path)",
        "#",
        "# Edit only the settings you need to change.",
        "# Missing keys use defaults (paper settings).",
        "# Load with: config = volcatenate.config.load_config(path)",
        "",
    ]

    # Top-level scalar fields
    for f in fields(RunConfig):
        if f.name in _SECTION_CLASSES:
            continue  # handle sub-configs below
        val = getattr(config, f.name)
        comment = _FIELD_COMMENTS.get(("_top", f.name), "")
        line = f"{f.name}: {_format_value(val)}"
        if comment:
            line += f"  # {comment}"
        lines.append(line)

    # Sub-config sections
    for section_name in _SECTION_CLASSES:
        sub = getattr(config, section_name)
        sub_fields = fields(sub)
        if not sub_fields:
            continue  # skip empty (e.g. DCompressConfig)
        lines.append("")
        lines.append(f"{section_name}:")
        for f in sub_fields:
            val = getattr(sub, f.name)
            comment = _FIELD_COMMENTS.get((section_name, f.name), "")
            # Nested dataclass: write as a YAML mapping at +2 indent.
            if is_dataclass(val) and not isinstance(val, type):
                lines.append(f"  {f.name}:")
                if comment:
                    # Annotate the parent line via a same-line comment.
                    lines[-1] += f"  # {comment}"
                for nf in fields(val):
                    nv = getattr(val, nf.name)
                    ncomment = _FIELD_COMMENTS.get(
                        (f"{section_name}.{f.name}", nf.name), ""
                    )
                    nline = f"    {nf.name}: {_format_value(nv)}"
                    if ncomment:
                        nline += f"  # {ncomment}"
                    lines.append(nline)
                continue

            line = f"  {f.name}: {_format_value(val)}"
            if comment:
                line += f"  # {comment}"
            lines.append(line)

    lines.append("")  # trailing newline

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    return path


T = TypeVar("T")


def _build_dataclass(cls: Type[T], data: dict) -> T:
    """Build a dataclass from a dict, ignoring unknown keys.

    Only keys that match actual field names are passed to the
    constructor; everything else is silently ignored.  Missing
    keys use the dataclass defaults.

    Empty strings are skipped for fields that use ``default_factory``
    (i.e. auto-detected paths) so that auto-detection still runs.

    Nested dataclasses are detected via the field's default
    (``f.default`` or ``f.default_factory()``); when the YAML value
    is a dict, it is recursively built into the nested dataclass.
    """
    field_map = {f.name: f for f in fields(cls)}
    # Fields that use default_factory (auto-detected paths or nested
    # dataclass instances). For path-style fields, an empty string in
    # YAML means "use auto-detection".
    factory_fields = {
        name for name, f in field_map.items()
        if f.default_factory is not dataclass_field_missing
    }
    filtered: dict[str, Any] = {}
    for k, v in data.items():
        if k not in field_map:
            continue
        f = field_map[k]

        # Nested dataclass: recurse if a dict is supplied.
        if isinstance(v, dict):
            nested_default = None
            if f.default is not dataclass_field_missing:
                nested_default = f.default
            elif f.default_factory is not dataclass_field_missing:
                try:
                    nested_default = f.default_factory()
                except Exception:
                    nested_default = None
            if nested_default is not None and is_dataclass(nested_default):
                filtered[k] = _build_dataclass(type(nested_default), v)
                continue

        # Skip empty strings for auto-detected scalar fields → let factory run
        if k in factory_fields and v == "":
            continue
        # Coerce types where needed (YAML may parse ints as floats)
        if f.type == "int" and isinstance(v, float):
            v = int(v)
        filtered[k] = v
    return cls(**filtered)


def _migrate_deprecated_keys(section_name: str, section_data: dict) -> None:
    """Mutate ``section_data`` in place to fold deprecated keys into
    their replacements. Emits a deprecation warning for each migration.
    """
    if section_name == "vesical" and "model" in section_data:
        section_data.pop("model")
        logger.warning(
            "vesical.model is deprecated and ignored; the VESIcal solubility "
            "model is now selected by backend name (e.g. 'VESIcal_Iacono', "
            "'VESIcal_Dixon', 'VESIcal_MS') passed to the calculate_* "
            "functions. Remove vesical.model from your config to silence "
            "this warning."
        )

    if section_name == "magec" and "p_start_overrides" in section_data:
        old = section_data.pop("p_start_overrides") or {}
        new = section_data.setdefault("overrides", {})
        for sample, p_start in old.items():
            # New-shape entry wins on conflict.
            entry = new.setdefault(sample, {})
            entry.setdefault("p_start_kbar", p_start)
        logger.warning(
            "magec.p_start_overrides is deprecated; folded into "
            "magec.overrides as '<sample>: {p_start_kbar: <value>}'. "
            "Update your config to silence this warning."
        )


def load_config(path: str) -> RunConfig:
    """Load a RunConfig from a YAML file.

    Only fields present in the YAML are overridden; everything
    else keeps its dataclass default.  This means a minimal YAML
    with just the settings you want to change works fine::

        # my_config.yaml
        output_dir: my_output
        magec:
          solver_dir: /new/path

    Parameters
    ----------
    path : str
        Path to YAML file.

    Returns
    -------
    RunConfig
    """
    import yaml

    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    kwargs: dict[str, object] = {}

    # Top-level scalar fields
    for f in fields(RunConfig):
        if f.name in _SECTION_CLASSES:
            continue
        if f.name in raw:
            kwargs[f.name] = raw[f.name]

    # Sub-config sections
    for section_name, cls in _SECTION_CLASSES.items():
        if section_name in raw and isinstance(raw[section_name], dict):
            section_data = raw[section_name]
            _migrate_deprecated_keys(section_name, section_data)
            kwargs[section_name] = _build_dataclass(cls, section_data)

    return RunConfig(**kwargs)
