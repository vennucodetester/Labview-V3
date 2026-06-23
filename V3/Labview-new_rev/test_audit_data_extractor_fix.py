"""
Test for audit_data_extractor.py column name fallback fix

This test verifies that the extract_cycle_points method correctly handles
both old and new column naming conventions.
"""

import pandas as pd
from audit_data_extractor import AuditDataExtractor


def test_column_fallback():
    """Test that enthalpy extraction works with both old and new column names."""

    print("="*70)
    print("TEST: Column Name Fallback for Enthalpy Values")
    print("="*70)

    # Test 1: Row with NEW column names (h_2a_LH, h_4b_LH, h_2b)
    print("\n[Test 1] Row with NEW column names")
    row_new = pd.Series({
        'P_suction': 35.0,
        'P_disch': 200.0,
        'h_2a_LH': 420.5,  # NEW name
        'h_4b_LH': 285.3,  # NEW name
        'h_2b': 410.2,     # NEW name
        'T_2a-LH': 45.0,
        'T_4b-lh': 75.0,
        'T_2b': 50.0,
        'S.H_lh coil': 10.0,
        'S.C-txv.lh': 5.0,
    })

    extractor = AuditDataExtractor()
    cycle_points = extractor.extract_cycle_points(row_new, 'LH')

    assert cycle_points['2_evap_outlet']['h'] == 420.5, "Failed to get h_2a_LH"
    assert cycle_points['1_evap_inlet']['h'] == 285.3, "Failed to get h_4b_LH"
    assert cycle_points['3_comp_inlet']['h'] == 410.2, "Failed to get h_2b"
    print("✓ NEW column names work correctly")
    print(f"  - Evap outlet enthalpy: {cycle_points['2_evap_outlet']['h']} kJ/kg")
    print(f"  - TXV inlet enthalpy: {cycle_points['1_evap_inlet']['h']} kJ/kg")
    print(f"  - Comp inlet enthalpy: {cycle_points['3_comp_inlet']['h']} kJ/kg")

    # Test 2: Row with OLD column names (H_coil lh, H_txv.lh, H_comp.in)
    print("\n[Test 2] Row with OLD column names")
    row_old = pd.Series({
        'P_suction': 35.0,
        'P_disch': 200.0,
        'H_coil lh': 418.7,    # OLD name
        'H_txv.lh': 287.1,     # OLD name
        'H_comp.in': 412.3,    # OLD name
        'T_2a-LH': 45.0,
        'T_4b-lh': 75.0,
        'T_2b': 50.0,
        'S.H_lh coil': 10.0,
        'S.C-txv.lh': 5.0,
    })

    cycle_points = extractor.extract_cycle_points(row_old, 'LH')

    assert cycle_points['2_evap_outlet']['h'] == 418.7, "Failed to fallback to H_coil lh"
    assert cycle_points['1_evap_inlet']['h'] == 287.1, "Failed to fallback to H_txv.lh"
    assert cycle_points['3_comp_inlet']['h'] == 412.3, "Failed to fallback to H_comp.in"
    print("✓ OLD column names work correctly (fallback)")
    print(f"  - Evap outlet enthalpy: {cycle_points['2_evap_outlet']['h']} kJ/kg")
    print(f"  - TXV inlet enthalpy: {cycle_points['1_evap_inlet']['h']} kJ/kg")
    print(f"  - Comp inlet enthalpy: {cycle_points['3_comp_inlet']['h']} kJ/kg")

    # Test 3: Row with MIXED column names (new takes priority)
    print("\n[Test 3] Row with BOTH old and new (new should take priority)")
    row_mixed = pd.Series({
        'P_suction': 35.0,
        'P_disch': 200.0,
        'h_2a_LH': 420.0,      # NEW name (should be used)
        'H_coil lh': 999.0,    # OLD name (should be ignored)
        'h_4b_LH': 285.0,      # NEW name (should be used)
        'H_txv.lh': 888.0,     # OLD name (should be ignored)
        'h_2b': 410.0,         # NEW name (should be used)
        'H_comp.in': 777.0,    # OLD name (should be ignored)
        'T_2a-LH': 45.0,
        'T_4b-lh': 75.0,
        'T_2b': 50.0,
        'S.H_lh coil': 10.0,
        'S.C-txv.lh': 5.0,
    })

    cycle_points = extractor.extract_cycle_points(row_mixed, 'LH')

    assert cycle_points['2_evap_outlet']['h'] == 420.0, "Should use NEW name, not old"
    assert cycle_points['1_evap_inlet']['h'] == 285.0, "Should use NEW name, not old"
    assert cycle_points['3_comp_inlet']['h'] == 410.0, "Should use NEW name, not old"
    print("✓ NEW column names take priority when both exist")
    print(f"  - Evap outlet enthalpy: {cycle_points['2_evap_outlet']['h']} (not 999.0)")
    print(f"  - TXV inlet enthalpy: {cycle_points['1_evap_inlet']['h']} (not 888.0)")
    print(f"  - Comp inlet enthalpy: {cycle_points['3_comp_inlet']['h']} (not 777.0)")

    # Test 4: Missing enthalpy columns (should return None and log warning)
    print("\n[Test 4] Row with MISSING enthalpy columns")
    row_missing = pd.Series({
        'P_suction': 35.0,
        'P_disch': 200.0,
        'T_2a-LH': 45.0,
        'T_4b-lh': 75.0,
        'T_2b': 50.0,
        'S.H_lh coil': 10.0,
        'S.C-txv.lh': 5.0,
    })

    cycle_points = extractor.extract_cycle_points(row_missing, 'LH')

    assert cycle_points['2_evap_outlet']['h'] is None, "Should return None when column missing"
    assert cycle_points['1_evap_inlet']['h'] is None, "Should return None when column missing"
    assert cycle_points['3_comp_inlet']['h'] is None, "Should return None when column missing"
    print("✓ Missing columns return None (check logs for warnings)")

    print("\n" + "="*70)
    print("ALL TESTS PASSED ✓")
    print("="*70)
    print("\nFix Summary:")
    print("- Supports both NEW column names (h_2a_LH, h_4b_LH, h_2b)")
    print("- Falls back to OLD column names (H_coil lh, H_txv.lh, H_comp.in)")
    print("- NEW names take priority when both exist")
    print("- Logs warnings when enthalpy columns are missing")
    print("- This should fix the Row 1210 PH diagram issue")


if __name__ == '__main__':
    test_column_fallback()
