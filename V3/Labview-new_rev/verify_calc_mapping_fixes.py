"""
verify_calc_mapping_fixes.py

Quick verification harness for two mapping fixes:
1) Robust DataFrame column resolution (whitespace/case tolerant)
2) Single-coil (non-modular) fallback mapping into LH roles

Run:
  python verify_calc_mapping_fixes.py
"""

from types import SimpleNamespace

import pandas as pd

from calculation_orchestrator import run_batch_processing


def test_a_robust_mapping_trailing_spaces() -> None:
    print("\n=== Test A: robust mapping (trailing spaces) ===")
    model = {
        "components": {
            "comp1": {"type": "Compressor", "properties": {}},
            "txv_r": {"type": "TXV", "properties": {"circuit_label": "Right"}},
            "evap_r": {"type": "Evaporator", "properties": {"circuit_label": "Right", "circuits": 1}},
            "s_sp": {"type": "Sensor", "properties": {"measurement_type": "Suction Pressure", "circuit_label": "None"}},
            "s_dp": {"type": "Sensor", "properties": {"measurement_type": "Discharge Pressure", "circuit_label": "None"}},
        },
        "sensor_roles": {
            # pressures (inline sensors)
            "Sensor.s_sp.measurement": "Suction Pressure",
            "Sensor.s_dp.measurement": "Discharge Pressure",
            # compressor temps + rpm
            "Compressor.comp1.inlet": "Suction line into Comp",
            "Compressor.comp1.outlet": "Discharge line from Comp",
            "Compressor.comp1.RPM": "Compressor RPM",
            # RH circuit mappings with trailing spaces
            "TXV.txv_r.inlet": "Right TXV Inlet ",
            "TXV.txv_r.outlet": "Right TXV Outlet ",
            "Evaporator.evap_r.inlet_circuit_1": "Right Coil Inlet ",
            "Evaporator.evap_r.outlet_circuit_1": "Right Coil Outlet ",
        },
    }

    # DataFrame headers intentionally do NOT include trailing spaces
    df = pd.DataFrame(
        {
            "Suction Pressure": [45.0],
            "Discharge Pressure": [180.0],
            "Suction line into Comp": [40.0],
            "Discharge line from Comp": [150.0],
            "Compressor RPM": [3600.0],
            "Right TXV Inlet": [95.0],
            "Right TXV Outlet": [35.0],
            "Right Coil Inlet": [36.0],
            "Right Coil Outlet": [38.0],
        }
    )

    dm = SimpleNamespace(diagram_model=model, rated_inputs={"gpm_water": None}, refrigerant="R410A")
    _ = run_batch_processing(dm, df)
    print("If you see T_4b-rh / _avg_T_2a-RH mapped to non-spaced headers above, Test A passed.")


def test_b_single_coil_fallback() -> None:
    print("\n=== Test B: single-coil fallback (no circuit labels) ===")
    model = {
        "components": {
            "comp1": {"type": "Compressor", "properties": {}},
            "txv1": {"type": "TXV", "properties": {"circuit_label": "None"}},
            "evap1": {"type": "Evaporator", "properties": {"circuit_label": "None", "circuits": 2}},
            "s_sp": {"type": "Sensor", "properties": {"measurement_type": "Suction Pressure", "circuit_label": "None"}},
            "s_dp": {"type": "Sensor", "properties": {"measurement_type": "Discharge Pressure", "circuit_label": "None"}},
        },
        "sensor_roles": {
            "Sensor.s_sp.measurement": "Suction Pressure",
            "Sensor.s_dp.measurement": "Discharge Pressure",
            "Compressor.comp1.inlet": "Suction line into Comp",
            "Compressor.comp1.outlet": "Discharge line from Comp",
            "Compressor.comp1.RPM": "Compressor RPM",
            "TXV.txv1.inlet": "TXV Inlet Temp",
            "TXV.txv1.outlet": "TXV Outlet Temp",
            "Evaporator.evap1.inlet_circuit_1": "Coil In 1",
            "Evaporator.evap1.inlet_circuit_2": "Coil In 2",
            "Evaporator.evap1.outlet_circuit_1": "Coil Out 1",
            "Evaporator.evap1.outlet_circuit_2": "Coil Out 2",
        },
    }

    df = pd.DataFrame(
        {
            "Suction Pressure": [48.0],
            "Discharge Pressure": [175.0],
            "Suction line into Comp": [39.0],
            "Discharge line from Comp": [145.0],
            "Compressor RPM": [3550.0],
            "TXV Inlet Temp": [90.0],
            "TXV Outlet Temp": [34.0],
            "Coil In 1": [35.0],
            "Coil In 2": [35.5],
            "Coil Out 1": [38.0],
            "Coil Out 2": [38.5],
        }
    )

    dm = SimpleNamespace(diagram_model=model, rated_inputs={"gpm_water": None}, refrigerant="R410A")
    _ = run_batch_processing(dm, df)
    print("If you see 'Single-coil fallback applied' and LH keys mapped above, Test B passed.")


if __name__ == "__main__":
    test_a_robust_mapping_trailing_spaces()
    test_b_single_coil_fallback()

