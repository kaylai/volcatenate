"""Standardized output column names — single source of truth.

Every model backend produces DataFrames using these exact column names.
Downstream plotting code depends on these names matching precisely.
"""

# --- Pressure & temperature ---
P_BARS = "P_bars"
T_C = "T_C"

# --- Melt volatile concentrations ---
H2OT_M_WTPC = "H2OT_m_wtpc"       # total H2O in melt (wt%)
CO2T_M_PPMW = "CO2T_m_ppmw"       # total CO2 in melt (ppm by weight)
ST_M_PPMW = "ST_m_ppmw"           # total S in melt (ppm by weight)

# --- Melt volatile concentrations (normalized to initial value) ---
H2OT_M_WTPC_NORM = "H2OT_m_wtpc_norm"
CO2T_M_PPMW_NORM = "CO2T_m_ppmw_norm"
ST_M_PPMW_NORM = "ST_m_ppmw_norm"

# --- Redox ---
FE3FET_M = "Fe3Fet_m"             # Fe3+/FeT ratio in melt
S6ST_M = "S6St_m"                 # S6+/ST ratio in melt
LOGFO2 = "logfO2"                 # log10(fO2)
DFMQ = "dFMQ"                     # fO2 relative to FMQ buffer

# --- Vapor mass ---
VAPOR_WT = "vapor_wt"             # vapor mass fraction (0-1)

# --- Vapor mole fractions ---
O2_V_MF = "O2_v_mf"
CO2_V_MF = "CO2_v_mf"
CO_V_MF = "CO_v_mf"
H2O_V_MF = "H2O_v_mf"
H2_V_MF = "H2_v_mf"
S2_V_MF = "S2_v_mf"
SO2_V_MF = "SO2_v_mf"
H2S_V_MF = "H2S_v_mf"
CH4_V_MF = "CH4_v_mf"
OCS_V_MF = "OCS_v_mf"

# --- Derived ---
CS_V_MF = "CS_v_mf"               # Elemental C/S ratio in vapor (atom-weighted)

# --- Species groupings for elemental C/S ratio ---
# Maps vapor mole-fraction column → number of C (or S) atoms per molecule.
# OCS contains 1 C and 1 S, so it appears in both dicts.
# S2 contains 2 S atoms per molecule.
C_SPECIES: dict[str, float] = {
    CO2_V_MF: 1.0,
    CO_V_MF:  1.0,
    CH4_V_MF: 1.0,
    OCS_V_MF: 1.0,
}
S_SPECIES: dict[str, float] = {
    SO2_V_MF: 1.0,
    H2S_V_MF: 1.0,
    S2_V_MF:  2.0,
    OCS_V_MF: 1.0,
}

# --- All vapor mole fraction columns ---
VAPOR_MF_COLUMNS = [
    O2_V_MF, CO2_V_MF, CO_V_MF, H2O_V_MF, H2_V_MF,
    S2_V_MF, SO2_V_MF, H2S_V_MF, CH4_V_MF, OCS_V_MF,
]

# --- The standard output column set (order matters for CSV output) ---
STANDARD_COLUMNS = [
    P_BARS,
    H2OT_M_WTPC, CO2T_M_PPMW, ST_M_PPMW,
    FE3FET_M, S6ST_M, LOGFO2, DFMQ,
    VAPOR_WT,
    *VAPOR_MF_COLUMNS,
    CS_V_MF,
]

# Columns that may also be carried through if the backend produces them.
# These are *normalized* derived values and are written to CSV when present
# but are not required.
OPTIONAL_COLUMNS = [
    H2OT_M_WTPC_NORM, CO2T_M_PPMW_NORM, ST_M_PPMW_NORM,
]
