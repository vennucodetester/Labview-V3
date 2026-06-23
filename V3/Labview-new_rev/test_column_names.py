"""Test script to verify clean column names are being used."""

import pandas as pd
from coolprop_calculator import ThermodynamicCalculator, get_calculation_output_columns

# Create a simple test row
test_data = {
    'Timestamp': pd.Timestamp('2025-01-01 12:00:00'),
    'Suction Pressure psig': 50,
    'Liquid Pressure psig': 200,
    'Left TXV Bulb': 45,
    'CTR TXV Bulb': 46,
    'Right TXV Bulb ': 44,
    'Suction line into Comp': 55,
    'Discharge line from comp': 180,
    'Ref Temp in HeatX': 150,
    'Ref Temp out HeatX': 120,
    'Left TXV Inlet': 95,
    'CTR TXV Inlet': 94,
    'Right TXV Inlet ': 96,
    'Air in left evap 6 in LE': 70,
    'Air in left evap 6 in RE': 70,
    'Air in ctr evap 6 in LE': 70,
    'Air in ctr evap 6 in RE': 70,
    'Air in right evap 6 in LE': 70,
    'Air in right evap 6 in RE': 70,
    'Air off left evap 6 in LE': 50,
    'Air off left evap 6 in RE': 50,
    'Air off ctr evap 6 in LE': 50,
    'Air off ctr evap 6 in RE': 50,
    'Air off right evap 6 in LE': 50,
    'Air off right evap 6 in RE': 50,
    'Water in HeatX': 40,
    'Water out HeatX': 45,
    'Compressor RPM': 3000,
}

# Create test DataFrame
df_test = pd.DataFrame([test_data])

# Process with calculator
calc = ThermodynamicCalculator()
df_result = calc.process_dataframe(df_test)

print("\n=== COLUMN NAMES TEST ===\n")

# Get output columns
output_cols = get_calculation_output_columns()

print(f"Total columns in result: {len(df_result.columns)}")
print(f"\nFirst row (units):")
print(df_result.iloc[0][['h_2a', 'h_4b', 'h_2a_LH', 'h_4b_LH']])

print(f"\nChecking for clean column names:")
clean_names_to_check = ['h_2a', 'h_2b', 'h_3a', 'h_3b', 'h_4a', 'h_4b',
                        'h_2a_LH', 'h_2a_CTR', 'h_2a_RH',
                        'h_4b_LH', 'h_4b_CTR', 'h_4b_RH',
                        's_2a', 's_2a_LH', 's_4b_LH']

for col in clean_names_to_check:
    if col in df_result.columns:
        print(f"✓ '{col}' found")
    else:
        print(f"✗ '{col}' NOT found")

print(f"\nChecking that OLD names are NOT in columns (should all be False):")
old_names_to_check = ['h_2a_kJ_kg', 'h_4b_kJ_kg', 'h_2a_LH_kJ_kg', 'h_4b_CTR_kJ_kg']

for col in old_names_to_check:
    if col in df_result.columns:
        print(f"✗ '{col}' found (SHOULD NOT BE HERE)")
    else:
        print(f"✓ '{col}' NOT found (correct)")

print(f"\nData row (second row, index 1):")
print(f"  h_2a = {df_result.loc[1, 'h_2a']:.2f}")
print(f"  h_2a_LH = {df_result.loc[1, 'h_2a_LH']:.2f}")
print(f"  h_4b_LH = {df_result.loc[1, 'h_4b_LH']:.2f}")

print("\n=== TEST COMPLETE ===\n")
