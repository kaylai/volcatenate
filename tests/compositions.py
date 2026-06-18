"""Standard test melt compositions, shared across the test suite.

Hard-coded from ``examples/example_satP_input.csv`` so any test can import a
canonical composition instead of re-declaring one. Import what you need:

    from .compositions import KILAUEA, MORB

These are also the reference compositions the backend benchmarks in
``tests/backend_benchmarks/`` were generated against — do not edit the values
without regenerating those references.
"""

MORB = {
    "Sample": "MORB",
    "T_C": 1100.0,
    "SiO2": 47.40,
    "TiO2": 1.01,
    "Al2O3": 17.64,
    "FeOT": 7.98,
    "MnO": 0.00,
    "MgO": 7.63,
    "CaO": 12.44,
    "Na2O": 2.65,
    "K2O": 0.03,
    "P2O5": 0.08,
    "H2O": 0.2,
    "CO2": 0.11,
    "S": 0.142,
    "Fe3FeT": 0.1,
}

KILAUEA = {
    "Sample": "Kilauea",
    "T_C": 1200.0,
    "SiO2": 50.19,
    "TiO2": 2.34,
    "Al2O3": 12.79,
    "FeOT": 11.34,
    "MnO": 0.18,
    "MgO": 9.23,
    "CaO": 10.44,
    "Na2O": 2.39,
    "K2O": 0.43,
    "P2O5": 0.27,
    "H2O": 0.3,
    "CO2": 0.08,
    "S": 0.15,
    "Fe3FeT": 0.18,
}

FUEGO = {
    "Sample": "Fuego",
    "T_C": 1030.0,
    "SiO2": 51.46,
    "TiO2": 1.06,
    "Al2O3": 17.43,
    "FeOT": 9.42,
    "MnO": 0.19,
    "MgO": 3.78,
    "CaO": 7.99,
    "Na2O": 3.47,
    "K2O": 0.78,
    "P2O5": 0.24,
    "H2O": 4.5,
    "CO2": 0.33,
    "S": 0.265,
    "Fe3FeT": 0.24,
}

FOGO = {
    "Sample": "Fogo",
    "T_C": 1200.0,
    "SiO2": 42.40,
    "TiO2": 3.26,
    "Al2O3": 11.17,
    "FeOT": 12.00,
    "MnO": 0.14,
    "MgO": 9.55,
    "CaO": 13.31,
    "Na2O": 3.36,
    "K2O": 1.57,
    "P2O5": 0.75,
    "H2O": 2.11,
    "CO2": 1.152,
    "S": 0.469,
    "dNNO": 0.7,
}
