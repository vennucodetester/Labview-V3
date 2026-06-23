"""
Extract and display exact values for p-h diagram plotting
"""
import pandas as pd
import numpy as np
from coolprop_calculator import ThermodynamicCalculator
from data_manager import DataManager

# Initialize
data_manager = DataManager()
calculator = ThermodynamicCalculator()

# Load CSV
print("="*80)
print("LOADING DATA")
print("="*80)
csv_file = "ID6SU12WE DOE 2.csv"
data_manager.load_csv(csv_file)
print(f"✓ CSV loaded: {len(data_manager.csv_data)} rows")

# Filter by pressure threshold
threshold = 40.0  # PSI
print(f"\nFiltering by pressure threshold: {threshold} PSI...")
filtered_data = data_manager.filter_by_pressure_threshold(threshold)
print(f"✓ Filtered data: {len(filtered_data)} rows")

# Calculate thermodynamic properties
print(f"\nCalculating thermodynamic properties...")
calculated_data = calculator.process_dataframe(filtered_data)
print(f"✓ Calculated data shape: {calculated_data.shape}")

# Skip units row for analysis
data_for_analysis = calculated_data.iloc[1:].reset_index(drop=True)
print(f"✓ Data for analysis (units row skipped): {len(data_for_analysis)} rows")

# Get first data row (latest/most recent)
first_row = data_for_analysis.iloc[0]

print("\n" + "="*80)
print("EXTRACTION FROM FIRST ROW (Most Recent Data Point)")
print("="*80)

# Extract pressure values
print(f"\nPRESSURES (Pascals):")
print(f"  P_suc (Suction):     {first_row['P_suc']:.0f} Pa = {first_row['P_suc']/1e5:.2f} bar")
print(f"  P_cond (Condenser):  {first_row['P_cond']:.0f} Pa = {first_row['P_cond']/1e5:.2f} bar")

# Extract all enthalpy values
print(f"\nENTHALPY VALUES (kJ/kg):")
print(f"  COMMON POINTS (same for all circuits):")
print(f"    h_2b (suction line):       {first_row['h_2b']:.2f} kJ/kg")
print(f"    h_3a (discharge line):     {first_row['h_3a']:.2f} kJ/kg")
print(f"    h_3b (condenser inlet):    {first_row['h_3b']:.2f} kJ/kg")
if 'h_4a' in first_row.index:
    print(f"    h_4a (condenser outlet):   {first_row['h_4a']:.2f} kJ/kg")

print(f"\n  LEFT HAND (LH) CIRCUIT:")
print(f"    h_2a_LH (TXV bulb):        {first_row['h_2a_LH']:.2f} kJ/kg")
print(f"    h_4b_LH (TXV inlet):       {first_row['h_4b_LH']:.2f} kJ/kg")

print(f"\n  CENTER (CTR) CIRCUIT:")
print(f"    h_2a_CTR (TXV bulb):       {first_row['h_2a_CTR']:.2f} kJ/kg")
print(f"    h_4b_CTR (TXV inlet):      {first_row['h_4b_CTR']:.2f} kJ/kg")

print(f"\n  RIGHT HAND (RH) CIRCUIT:")
print(f"    h_2a_RH (TXV bulb):        {first_row['h_2a_RH']:.2f} kJ/kg")
print(f"    h_4b_RH (TXV inlet):       {first_row['h_4b_RH']:.2f} kJ/kg")

print("\n" + "="*80)
print("PLOT DATA FOR EACH CIRCUIT")
print("="*80)

P_suc = first_row['P_suc']
P_cond = first_row['P_cond']

# Common points
common_data = {
    '2b': {'h': first_row['h_2b'], 'P': P_suc},
    '3a': {'h': first_row['h_3a'], 'P': P_cond},
    '3b': {'h': first_row['h_3b'], 'P': P_cond},
}
if 'h_4a' in first_row.index:
    common_data['4a'] = {'h': first_row['h_4a'], 'P': P_cond}

# LEFT HAND CIRCUIT
print(f"\n{'LEFT HAND (LH) CIRCUIT':^80}")
print(f"{'-'*80}")
lh_cycle = {
    '2a': {'h': first_row['h_2a_LH'], 'P': P_suc},
    '2b': {'h': first_row['h_2b'], 'P': P_suc},
    '3a': {'h': first_row['h_3a'], 'P': P_cond},
    '3b': {'h': first_row['h_3b'], 'P': P_cond},
    '4b': {'h': first_row['h_4b_LH'], 'P': P_cond},
}
if 'h_4a' in first_row.index:
    lh_cycle['4a'] = {'h': first_row['h_4a'], 'P': P_cond}

cycle_order = ['2a', '2b', '3a', '3b', '4a', '4b']
print(f"\nCycle path order: {' → '.join(cycle_order)}")
print(f"\nPoint Data:")
for point in cycle_order:
    if point in lh_cycle:
        data = lh_cycle[point]
        print(f"  {point}: h = {data['h']:7.2f} kJ/kg,  P = {data['P']:9.0f} Pa ({data['P']/1e5:6.2f} bar)")

# CENTER CIRCUIT
print(f"\n{'CENTER (CTR) CIRCUIT':^80}")
print(f"{'-'*80}")
ctr_cycle = {
    '2a': {'h': first_row['h_2a_CTR'], 'P': P_suc},
    '2b': {'h': first_row['h_2b'], 'P': P_suc},
    '3a': {'h': first_row['h_3a'], 'P': P_cond},
    '3b': {'h': first_row['h_3b'], 'P': P_cond},
    '4b': {'h': first_row['h_4b_CTR'], 'P': P_cond},
}
if 'h_4a' in first_row.index:
    ctr_cycle['4a'] = {'h': first_row['h_4a'], 'P': P_cond}

print(f"\nCycle path order: {' → '.join(cycle_order)}")
print(f"\nPoint Data:")
for point in cycle_order:
    if point in ctr_cycle:
        data = ctr_cycle[point]
        print(f"  {point}: h = {data['h']:7.2f} kJ/kg,  P = {data['P']:9.0f} Pa ({data['P']/1e5:6.2f} bar)")

# RIGHT HAND CIRCUIT
print(f"\n{'RIGHT HAND (RH) CIRCUIT':^80}")
print(f"{'-'*80}")
rh_cycle = {
    '2a': {'h': first_row['h_2a_RH'], 'P': P_suc},
    '2b': {'h': first_row['h_2b'], 'P': P_suc},
    '3a': {'h': first_row['h_3a'], 'P': P_cond},
    '3b': {'h': first_row['h_3b'], 'P': P_cond},
    '4b': {'h': first_row['h_4b_RH'], 'P': P_cond},
}
if 'h_4a' in first_row.index:
    rh_cycle['4a'] = {'h': first_row['h_4a'], 'P': P_cond}

print(f"\nCycle path order: {' → '.join(cycle_order)}")
print(f"\nPoint Data:")
for point in cycle_order:
    if point in rh_cycle:
        data = rh_cycle[point]
        print(f"  {point}: h = {data['h']:7.2f} kJ/kg,  P = {data['P']:9.0f} Pa ({data['P']/1e5:6.2f} bar)")

print("\n" + "="*80)
print("AXIS RANGES FOR P-H DIAGRAM")
print("="*80)

# Collect all h and P values
all_h = []
all_P = []
for cycle in [lh_cycle, ctr_cycle, rh_cycle]:
    for point_data in cycle.values():
        all_h.append(point_data['h'])
        all_P.append(point_data['P'])

h_min = min(all_h)
h_max = max(all_h)
P_min = min(all_P)
P_max = max(all_P)

print(f"\nX-AXIS (Enthalpy):")
print(f"  Min value in data: {h_min:.2f} kJ/kg")
print(f"  Max value in data: {h_max:.2f} kJ/kg")
print(f"  Recommended range: 250-550 kJ/kg")
print(f"  Use xlim: (250, 550)")

print(f"\nY-AXIS (Pressure, logarithmic):")
print(f"  Min value in data: {P_min:.0f} Pa ({P_min/1e5:.2f} bar)")
print(f"  Max value in data: {P_max:.0f} Pa ({P_max/1e5:.2f} bar)")
print(f"  Recommended range: 0.05 MPa to 4.5 MPa (0.05e5 Pa to 4.5e6 Pa)")
print(f"  Use ylim: (0.05e5, 4.5e6)")
print(f"  Use log scale: yes")

print("\n" + "="*80)
print("EXPECTED vs ACTUAL (from System Information file)")
print("="*80)
print(f"\nFrom System Information:")
print(f"  Expected P_suc: 33.18 psig = {33.18 * 6894.757:.0f} Pa ({33.18 * 6894.757/1e5:.2f} bar)")
print(f"  Expected P_cond: 133.12 psig = {133.12 * 6894.757:.0f} Pa ({133.12 * 6894.757/1e5:.2f} bar)")

print(f"\nActual from data:")
print(f"  Actual P_suc: {P_suc:.0f} Pa ({P_suc/1e5:.2f} bar)")
print(f"  Actual P_cond: {P_cond:.0f} Pa ({P_cond/1e5:.2f} bar)")

expected_p_suc = 33.18 * 6894.757
expected_p_cond = 133.12 * 6894.757
print(f"\nDifference:")
print(f"  P_suc diff: {abs(P_suc - expected_p_suc)/expected_p_suc * 100:.1f}%")
print(f"  P_cond diff: {abs(P_cond - expected_p_cond)/expected_p_cond * 100:.1f}%")
