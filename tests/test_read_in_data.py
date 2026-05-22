from __future__ import annotations

import pandas as pd


def test_load_data_xco2_without_xh2o_no_keyerror(tmp_path):
    """loadData must not crash if XCO2_fl is present but XH2O_fl is absent."""
    from volcatenate.compat import loadData

    vesical_dir = tmp_path / "VESIcal" / "VESIcal_MS"
    vesical_dir.mkdir(parents=True)

    # CSV has XCO2_fl but deliberately omits XH2O_fl
    df_out = pd.DataFrame(
        {
            "P_bars": [1000.0],
            "XCO2_fl": [0.5],
        }
    )
    (vesical_dir / "kilauea.csv").write_text(df_out.to_csv(index=False))

    # Should not raise KeyError — the XH2O_fl guard prevents it
    data_morb, data_kil, data_fuego, data_fogo = loadData(
        model_names=["VESIcal_MS"],
        topdirectory_name=str(tmp_path),
    )
    assert "VESIcal_MS" in data_kil, "VESIcal_MS should be loaded without error"
    # CO2_v_mf / H2O_v_mf should NOT be mapped since XH2O_fl is missing
    assert (
        "CO2_v_mf" not in data_kil["VESIcal_MS"].columns
        or "XCO2_fl" not in data_kil["VESIcal_MS"].columns
    ), "CO2_v_mf should not be mapped when XH2O_fl is absent"


def test_iter_tool_csv_dirs_skips_missing_tool_dir(tmp_path):
    """Tools not present on disk are silently skipped (no error)."""
    from volcatenate.core import _iter_tool_csv_dirs

    (tmp_path / "EVo").mkdir()

    pairs = _iter_tool_csv_dirs(str(tmp_path), tools=["EVo", "VolFe"])

    assert pairs == [("EVo", str(tmp_path / "EVo"))]


def test_iter_tool_csv_dirs_resolves_vesical_variants(tmp_path):
    """VESIcal variants live one level deeper at
    ``output_dir/VESIcal/<full_model_name>`` (the same layout written by
    :func:`export_degassing_paths`) and must resolve when listed by
    full model name in `tools`."""
    from volcatenate.core import _iter_tool_csv_dirs

    (tmp_path / "VESIcal" / "VESIcal_Dixon").mkdir(parents=True)
    (tmp_path / "VESIcal" / "VESIcal_IaconoMarziano").mkdir(parents=True)

    pairs = _iter_tool_csv_dirs(
        str(tmp_path),
        tools=["VESIcal_Dixon", "VESIcal_IaconoMarziano"],
    )

    assert (
        "VESIcal_Dixon",
        str(tmp_path / "VESIcal" / "VESIcal_Dixon"),
    ) in pairs
    assert (
        "VESIcal_IaconoMarziano",
        str(tmp_path / "VESIcal" / "VESIcal_IaconoMarziano"),
    ) in pairs
    assert len(pairs) == 2


def test_iter_tool_csv_dirs_whitelists_tools(tmp_path):
    """_iter_tool_csv_dirs must return only directories named in `tools`."""
    from volcatenate.core import _iter_tool_csv_dirs

    (tmp_path / "EVo").mkdir()
    (tmp_path / "saturation_pressures_details").mkdir()
    (tmp_path / "resolved_inputs").mkdir()
    (tmp_path / "MyTool").mkdir()

    pairs = _iter_tool_csv_dirs(str(tmp_path), tools=["EVo"])

    assert pairs == [("EVo", str(tmp_path / "EVo"))], (
        f"Expected only EVo entry, got {pairs}; "
        "_iter_tool_csv_dirs is still enumerating arbitrary subdirs"
    )
