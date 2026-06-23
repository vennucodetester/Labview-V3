"""
Debug script to check p-h diagram data extraction
"""
import pandas as pd
from coolprop_calculator import ThermodynamicCalculator
from data_manager import DataManager

# Initialize
data_manager = DataManager()
calculator = ThermodynamicCalculator()

# Load CSV
csv_file = "ID6SU12WE DOE 2.csv"
print(f"Loading {csv_file}...")
data_manager.load_csv(csv_file)
print(f"CSV loaded: {len(data_manager.csv_data)} rows")

# Filter by pressure threshold
threshold = 40.0  # PSI
print(f"\nFiltering by pressure threshold: {threshold} PSI...")
filtered_data = data_manager.filter_by_pressure_threshold(threshold)

if filtered_data is None or filtered_data.empty:
    print("No data matched threshold!")
else:
    print(f"Filtered data: {len(filtered_data)} rows")
    
    # Calculate thermodynamic properties
    print(f"\nCalculating thermodynamic properties...")
    calculated_data = calculator.process_dataframe(filtered_data)
    print(f"Calculated data shape: {calculated_data.shape}")
    print(f"Calculated data columns ({len(calculated_data.columns)}): {list(calculated_data.columns)[:30]}")
    
    # Skip units row for analysis
    data_for_analysis = calculated_data.iloc[1:].reset_index(drop=True)
    print(f"\nData for analysis (skip units row): {len(data_for_analysis)} rows")
    
    # Get first data row
    first_row = data_for_analysis.iloc[0]
    print(f"\n" + "="*70)
    print(f"First data row analysis:")
    print(f"="*70)
    
    # Check key pressure columns
    for col in ['P_suc', 'P_cond', 'P_suc_psig', 'P_liq_psig']:
        if col in first_row.index:
            val = first_row[col]
            print(f"\n{col}: {val}")
            if col == 'P_suc':
                print(f"  → In MPa: {val/1e6:.2f}")
                print(f"  → In bar: {val/1e5:.2f}")
            elif col == 'P_cond':
                print(f"  → In MPa: {val/1e6:.2f}")
                print(f"  → In bar: {val/1e5:.2f}")
    
    # Check key enthalpy columns
    print(f"\nEnthalpy values (kJ/kg):")
    for col in ['h_2a', 'h_2a_LH', 'h_2b', 'h_3a', 'h_3b', 'h_4a', 'h_4b_LH']:
        if col in first_row.index:
            val = first_row[col]
            print(f"  {col}: {val:.2f}")
    
    # Check expected ranges
    print(f"\n" + "="*70)
    print(f"Checking against expected ranges:")
    print(f"="*70)
    
    # From System Information:
    # Suction Pressure: 33.18 psig ≈ 229 kPa ≈ 0.229 MPa ≈ 229000 Pa
    # Liquid Pressure: 133.12 psig ≈ 918 kPa ≈ 0.918 MPa ≈ 918000 Pa
    
    P_suc_expected_pa = 33.18 * 6894.757  # Convert PSIG to Pa
    P_cond_expected_pa = 133.12 * 6894.757
    
    print(f"\nExpected pressure ranges (from System Information):")
    print(f"  P_suc: ~{P_suc_expected_pa:.0f} Pa ({P_suc_expected_pa/1e5:.1f} bar)")
    print(f"  P_cond: ~{P_cond_expected_pa:.0f} Pa ({P_cond_expected_pa/1e5:.1f} bar)")
    
    if 'P_suc' in first_row.index:
        P_suc_val = first_row['P_suc']
        print(f"\nActual P_suc: {P_suc_val:.0f} Pa ({P_suc_val/1e5:.1f} bar)")
        diff = abs(P_suc_val - P_suc_expected_pa) / P_suc_expected_pa * 100
        print(f"  Difference: {diff:.1f}%")
    
    if 'P_cond' in first_row.index:
        P_cond_val = first_row['P_cond']
        print(f"\nActual P_cond: {P_cond_val:.0f} Pa ({P_cond_val/1e5:.1f} bar)")
        diff = abs(P_cond_val - P_cond_expected_pa) / P_cond_expected_pa * 100
        print(f"  Difference: {diff:.1f}%")
    
    # Check enthalpy ranges
    print(f"\nExpected enthalpy ranges (R290):")
    print(f"  Typical range: 200-550 kJ/kg")
    
    h_values = []
    for col in ['h_2a', 'h_2a_LH', 'h_2b', 'h_3a', 'h_3b', 'h_4a', 'h_4b_LH']:
        if col in first_row.index:
            h_val = first_row[col]
            h_values.append((col, h_val))
            in_range = 200 < h_val < 700
            print(f"  {col}: {h_val:.2f} kJ/kg {'✓' if in_range else '✗ OUT OF RANGE'}")
    
    print(f"\n" + "="*70)
    print(f"Summary:")
    print(f"="*70)
    print(f"Total columns: {len(first_row)}")
    print(f"Data appears {'VALID' if len(h_values) > 0 else 'INVALID'}")
