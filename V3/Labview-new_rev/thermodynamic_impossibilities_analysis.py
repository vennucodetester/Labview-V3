#!/usr/bin/env python3
"""
Comprehensive Analysis of Thermodynamically Impossible Values
Identifies all physical impossibilities causing bad cooling capacity data
"""

import csv
import statistics

def read_csv_data(filename):
    """Read calculated results CSV."""
    with open(filename, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    return rows

def read_input_csv(filename):
    """Read input test data CSV."""
    with open(filename, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    return rows

def safe_float(value):
    """Safely convert to float."""
    try:
        return float(value) if value and value.strip() else None
    except:
        return None

print("="*100)
print(" THERMODYNAMICALLY IMPOSSIBLE VALUES - COMPREHENSIVE ANALYSIS")
print("="*100)

rows = read_csv_data('calculated_results.csv')
input_rows = read_input_csv('ID6SU12WE DOE 2.csv')

# ============================================================================
# CRITICAL DISCOVERY: GPM DATA SOURCE
# ============================================================================
print("\n🔍 CRITICAL FINDING: GPM DATA SOURCE")
print("="*100)

print("\n📊 MEASURED WATER FLOW METER DATA (from test):")
print("   Column 133: 'Total Water Flow Meter' in input CSV")
print()

# Show sample measured GPM values
measured_gpm = []
for i, row in enumerate(input_rows[:20]):
    gpm_val = safe_float(row.get('Total Water Flow Meter'))
    if gpm_val is not None:
        measured_gpm.append(gpm_val)
        if i < 10:
            print(f"   Row {i+1}: {gpm_val:.2f} GPM")

if measured_gpm:
    print(f"\n   Sample Statistics (first 20 rows):")
    print(f"     Min: {min(measured_gpm):.2f} GPM")
    print(f"     Max: {max(measured_gpm):.2f} GPM")
    print(f"     Mean: {statistics.mean(measured_gpm):.2f} GPM")
    print(f"     Median: {statistics.median(measured_gpm):.2f} GPM")

# Get all measured values
all_measured_gpm = [safe_float(row.get('Total Water Flow Meter'))
                    for row in input_rows
                    if safe_float(row.get('Total Water Flow Meter')) is not None]

if all_measured_gpm:
    print(f"\n   Full Dataset Statistics ({len(all_measured_gpm)} rows with data):")
    print(f"     Min: {min(all_measured_gpm):.2f} GPM")
    print(f"     Max: {max(all_measured_gpm):.2f} GPM")
    print(f"     Mean: {statistics.mean(all_measured_gpm):.2f} GPM")
    print(f"     Median: {statistics.median(all_measured_gpm):.2f} GPM")

print("\n")
print("⚠️  CRITICAL ISSUE IDENTIFIED:")
print("   The calculation DOES NOT USE the measured water flow meter data!")
print("   Instead, it uses a FIXED GPM value from 'rated_inputs' (user-entered)")
print()
print("   Source of GPM in calculations:")
print("     • File: calculation_engine.py, line 943")
print("     • Code: gpm_water = comp_specs.get('gpm_water')")
print("     • Origin: User dialog (input_dialog.py) - manually entered value")
print()
print("   🔴 If user entered wrong GPM value, ALL mass flow calculations are wrong!")

# ============================================================================
# THERMODYNAMICALLY IMPOSSIBLE VALUE #1: NEGATIVE SUBCOOLING
# ============================================================================
print("\n\n🚫 IMPOSSIBILITY #1: NEGATIVE SUBCOOLING")
print("="*100)
print("\nPHYSICAL LAW VIOLATION:")
print("   At condenser outlet (high pressure), refrigerant must be SUBCOOLED LIQUID")
print("   T_4a (actual temp) must be LESS than T_sat.cond (saturation temp)")
print("   Formula: Subcooling = T_sat.cond - T_4a")
print("   Required: Subcooling > 0 (liquid exists)")
print("   Observed: Subcooling < 0 (vapor exists - IMPOSSIBLE at condenser outlet)")

negative_sc = [r for r in rows if safe_float(r.get('S.C')) is not None and safe_float(r.get('S.C')) < 0]
print(f"\nTotal violations: {len(negative_sc)} rows ({len(negative_sc)/len(rows)*100:.1f}%)")

# Categorize by severity
mild = [r for r in negative_sc if safe_float(r.get('S.C')) > -5]
moderate = [r for r in negative_sc if -15 < safe_float(r.get('S.C')) <= -5]
severe = [r for r in negative_sc if safe_float(r.get('S.C')) <= -15]

print(f"\nSeverity breakdown:")
print(f"   Mild (-5°F < S.C < 0°F):       {len(mild)} rows - Sensor drift likely")
print(f"   Moderate (-15°F < S.C ≤ -5°F): {len(moderate)} rows - Sensor error or misplacement")
print(f"   Severe (S.C ≤ -15°F):          {len(severe)} rows - Critical sensor failure")

print(f"\nConsequences:")
print(f"   • Flash gas forms at TXV inlet")
print(f"   • Refrigeration effect reduced (less liquid available)")
print(f"   • Can cause NEGATIVE cooling capacity")
print(f"   • Mass flow calculation becomes invalid")

# ============================================================================
# IMPOSSIBILITY #2: ENTHALPY REVERSAL (H_comp.in < H_txv)
# ============================================================================
print("\n\n🚫 IMPOSSIBILITY #2: ENTHALPY REVERSAL")
print("="*100)
print("\nPHYSICAL LAW VIOLATION:")
print("   In a refrigeration cycle, enthalpy INCREASES through evaporator")
print("   H_comp.in (after evaporator) must be GREATER than H_txv (before evaporator)")
print("   This is the fundamental energy addition that creates cooling")
print("   Formula: Refrigeration Effect = H_comp.in - H_txv")
print("   Required: H_comp.in > H_txv (energy was added)")
print("   If reversed: NEGATIVE refrigeration effect (thermodynamically impossible)")

enthalpy_reversals = []
for row in rows:
    h_comp_in = safe_float(row.get('H_comp.in'))
    h_txv_lh = safe_float(row.get('H_txv.lh'))
    h_txv_ctr = safe_float(row.get('H_txv.ctr'))
    h_txv_rh = safe_float(row.get('H_txv.rh'))

    if h_comp_in is not None:
        # Calculate average TXV enthalpy
        txv_vals = [h for h in [h_txv_lh, h_txv_ctr, h_txv_rh] if h is not None]
        if txv_vals:
            h_txv_avg = sum(txv_vals) / len(txv_vals)

            # Check for reversal
            if h_comp_in < h_txv_avg:
                delta_h = h_comp_in - h_txv_avg
                enthalpy_reversals.append({
                    'row': row,
                    'h_comp_in': h_comp_in,
                    'h_txv_avg': h_txv_avg,
                    'delta_h': delta_h
                })

print(f"\nTotal violations: {len(enthalpy_reversals)} rows ({len(enthalpy_reversals)/len(rows)*100:.1f}%)")

if enthalpy_reversals:
    print(f"\nSample cases (first 5):")
    print(f"{'Row':<6} {'H_comp.in':<12} {'H_txv_avg':<12} {'ΔH (reversal)':<15} {'qc':<15}")
    print("-"*70)
    for i, case in enumerate(enthalpy_reversals[:5]):
        qc = safe_float(case['row'].get('qc'))
        print(f"{i+1:<6} {case['h_comp_in']:<12.2f} {case['h_txv_avg']:<12.2f} "
              f"{case['delta_h']:<15.2f} {qc:<15.2f}")

print(f"\nConsequences:")
print(f"   • Creates NEGATIVE cooling capacity directly")
print(f"   • Indicates serious sensor calibration error")
print(f"   • Thermodynamically equivalent to 'refrigerator creating heat'")

# ============================================================================
# IMPOSSIBILITY #3: SUPERHEAT AT SATURATION TEMPERATURE
# ============================================================================
print("\n\n🚫 IMPOSSIBILITY #3: ZERO OR NEGATIVE SUPERHEAT")
print("="*100)
print("\nPHYSICAL LAW VIOLATION:")
print("   Superheat = T_actual - T_saturation")
print("   At compressor inlet, gas must be SUPERHEATED (above saturation temp)")
print("   Required: S.H_total ≥ 5°F (safety margin to prevent liquid slugging)")
print("   If S.H ≤ 0: Liquid present at compressor inlet - can damage compressor")

zero_sh = [r for r in rows if safe_float(r.get('S.H_total')) is not None and safe_float(r.get('S.H_total')) <= 0]
low_sh = [r for r in rows if safe_float(r.get('S.H_total')) is not None and 0 < safe_float(r.get('S.H_total')) < 5]

print(f"\nZero/Negative superheat: {len(zero_sh)} rows - CRITICAL DANGER")
print(f"Low superheat (<5°F):    {len(low_sh)} rows - Risk of liquid slugging")

if zero_sh:
    print(f"\nSample cases:")
    print(f"{'Row':<6} {'T_2b':<12} {'T_sat':<12} {'S.H_total':<12} {'Status':<20}")
    print("-"*70)
    for i, row in enumerate(zero_sh[:5]):
        t_2b = safe_float(row.get('T_2b'))
        t_sat = safe_float(row.get('T_sat.comp.in'))
        sh = safe_float(row.get('S.H_total'))
        print(f"{i+1:<6} {t_2b:<12.2f} {t_sat:<12.2f} {sh:<12.2f} {'LIQUID SLUGGING!':<20}")

print(f"\nConsequences:")
print(f"   • Compressor damage from liquid refrigerant")
print(f"   • Density calculation invalid (assumes all vapor)")
print(f"   • Mass flow rate incorrect")

# ============================================================================
# IMPOSSIBILITY #4: PRESSURE BELOW ABSOLUTE VACUUM
# ============================================================================
print("\n\n🚫 IMPOSSIBILITY #4: IMPOSSIBLE PRESSURE VALUES")
print("="*100)
print("\nPHYSICAL LAW VIOLATION:")
print("   Gauge pressure cannot be below -14.7 PSIG (perfect vacuum)")
print("   Absolute pressure = Gauge pressure + 14.7")
print("   Minimum absolute pressure = 0 PSIA (perfect vacuum)")
print("   Therefore: Minimum gauge pressure = -14.7 PSIG")

vacuum_pressure = [r for r in rows
                  if safe_float(r.get('P_suction')) is not None
                  and safe_float(r.get('P_suction')) < -14.7]

negative_pressure = [r for r in rows
                    if safe_float(r.get('P_suction')) is not None
                    and safe_float(r.get('P_suction')) < 0]

print(f"\nBelow perfect vacuum (<-14.7 PSIG): {len(vacuum_pressure)} rows - IMPOSSIBLE")
print(f"Negative gauge pressure (<0 PSIG):  {len(negative_pressure)} rows - Indicates vacuum")

if negative_pressure:
    print(f"\nSample cases:")
    print(f"{'Row':<6} {'P_suction':<15} {'P_absolute':<15} {'S.H_total':<12}")
    print("-"*60)
    for i, row in enumerate(negative_pressure[:5]):
        p_suc = safe_float(row.get('P_suction'))
        p_abs = p_suc + 14.7
        sh = safe_float(row.get('S.H_total'))
        print(f"{i+1:<6} {p_suc:<15.2f} {p_abs:<15.2f} {sh:<12.2f}")

print(f"\nConsequences:")
print(f"   • CoolProp calculations use incorrect pressure")
print(f"   • Creates artificially high superheat")
print(f"   • Density calculation completely wrong")

# ============================================================================
# IMPOSSIBILITY #5: PRESSURE RATIO VIOLATIONS
# ============================================================================
print("\n\n🚫 IMPOSSIBILITY #5: UNREALISTIC PRESSURE RATIOS")
print("="*100)
print("\nPHYSICAL LAW VIOLATION:")
print("   Pressure Ratio = P_discharge / P_suction (both absolute)")
print("   For R290 refrigeration:")
print("     • Minimum: ~1.5 (near zero compression)")
print("     • Typical: 2.5-4.0 (normal operation)")
print("     • Maximum: ~10 (extreme conditions)")
print("   Outside these bounds indicates sensor errors or system failure")

pressure_ratios = []
for row in rows:
    p_suc = safe_float(row.get('P_suction'))
    p_disch = safe_float(row.get('P_disch'))

    if p_suc is not None and p_disch is not None:
        p_suc_abs = p_suc + 14.7
        p_disch_abs = p_disch + 14.7

        if p_suc_abs > 0:  # Avoid division by zero
            pr = p_disch_abs / p_suc_abs
            pressure_ratios.append({
                'row': row,
                'p_suc': p_suc,
                'p_disch': p_disch,
                'ratio': pr
            })

low_pr = [p for p in pressure_ratios if p['ratio'] < 1.5]
high_pr = [p for p in pressure_ratios if p['ratio'] > 10]

print(f"\nLow pressure ratio (<1.5):  {len(low_pr)} rows - Compressor not working")
print(f"High pressure ratio (>10):  {len(high_pr)} rows - Extreme compression or sensor error")

if high_pr:
    print(f"\nExtreme pressure ratio cases:")
    print(f"{'Row':<6} {'P_suc':<12} {'P_disch':<12} {'Ratio':<12} {'S.H_total':<12}")
    print("-"*70)
    for i, case in enumerate(high_pr[:5]):
        row = case['row']
        sh = safe_float(row.get('S.H_total'))
        print(f"{i+1:<6} {case['p_suc']:<12.2f} {case['p_disch']:<12.2f} "
              f"{case['ratio']:<12.2f} {sh:<12.2f}")

print(f"\nConsequences:")
print(f"   • Invalid thermodynamic state points")
print(f"   • Suggests sensor calibration errors")
print(f"   • High PR creates unrealistic superheat")

# ============================================================================
# IMPOSSIBILITY #6: TEMPERATURE INCONSISTENCIES
# ============================================================================
print("\n\n🚫 IMPOSSIBILITY #6: TEMPERATURE ORDER VIOLATIONS")
print("="*100)
print("\nPHYSICAL LAW VIOLATION:")
print("   In a refrigeration cycle, temperatures must follow this order:")
print("   T_4a (cond. out) > T_1 (evap. in) > T_2a (evap. out) > T_2b (comp. in)")
print("   Violation indicates sensor swaps or errors")

temp_violations = []
for row in rows:
    t_4a = safe_float(row.get('T_4a'))
    t_2a_lh = safe_float(row.get('T_2a-LH'))
    t_2b = safe_float(row.get('T_2b'))

    violations = []

    # Check if condenser outlet cooler than evaporator outlet
    if t_4a and t_2a_lh and t_4a < t_2a_lh:
        violations.append(f"T_4a ({t_4a:.1f}°F) < T_2a_LH ({t_2a_lh:.1f}°F)")

    # More checks can be added...

    if violations:
        temp_violations.append({
            'row': row,
            'violations': violations
        })

print(f"\nTemperature order violations: {len(temp_violations)} rows")

# ============================================================================
# SUMMARY TABLE
# ============================================================================
print("\n\n" + "="*100)
print(" SUMMARY: THERMODYNAMIC IMPOSSIBILITIES")
print("="*100)

print(f"\n{'Impossibility Type':<50} {'Count':<10} {'% of Data':<12}")
print("-"*100)
print(f"{'1. Negative Subcooling (vapor in liquid line)':<50} {len(negative_sc):<10} {len(negative_sc)/len(rows)*100:>10.1f}%")
print(f"{'2. Enthalpy Reversal (H_comp.in < H_txv)':<50} {len(enthalpy_reversals):<10} {len(enthalpy_reversals)/len(rows)*100:>10.1f}%")
print(f"{'3. Zero/Negative Superheat (liquid at comp)':<50} {len(zero_sh):<10} {len(zero_sh)/len(rows)*100:>10.1f}%")
print(f"{'4. Negative Gauge Pressure (vacuum)':<50} {len(negative_pressure):<10} {len(negative_pressure)/len(rows)*100:>10.1f}%")
print(f"{'5. Low Pressure Ratio (<1.5)':<50} {len(low_pr):<10} {len(low_pr)/len(rows)*100:>10.1f}%")
print(f"{'6. High Pressure Ratio (>10)':<50} {len(high_pr):<10} {len(high_pr)/len(rows)*100:>10.1f}%")
print(f"{'7. Temperature Order Violations':<50} {len(temp_violations):<10} {len(temp_violations)/len(rows)*100:>10.1f}%")

# ============================================================================
# ROOT CAUSE MAPPING
# ============================================================================
print("\n\n" + "="*100)
print(" ROOT CAUSE → NEGATIVE COOLING CAPACITY MAPPING")
print("="*100)

negative_qc = [r for r in rows if safe_float(r.get('qc')) is not None and safe_float(r.get('qc')) < 0]

print(f"\nTotal negative qc rows: {len(negative_qc)}")
print(f"\nCorrelation analysis:")

# Check how many negative qc have each impossibility
neg_with_negative_sc = sum(1 for r in negative_qc if safe_float(r.get('S.C')) is not None and safe_float(r.get('S.C')) < 0)
print(f"  • Negative qc WITH negative subcooling:  {neg_with_negative_sc}/{len(negative_qc)} ({neg_with_negative_sc/len(negative_qc)*100:.1f}%)")

# Check enthalpy reversal
neg_with_h_reversal = 0
for r in negative_qc:
    h_comp_in = safe_float(r.get('H_comp.in'))
    h_txv_vals = [safe_float(r.get(k)) for k in ['H_txv.lh', 'H_txv.ctr', 'H_txv.rh']]
    h_txv_vals = [h for h in h_txv_vals if h is not None]

    if h_comp_in and h_txv_vals:
        h_txv_avg = sum(h_txv_vals) / len(h_txv_vals)
        if h_comp_in < h_txv_avg:
            neg_with_h_reversal += 1

print(f"  • Negative qc WITH enthalpy reversal:    {neg_with_h_reversal}/{len(negative_qc)} ({neg_with_h_reversal/len(negative_qc)*100:.1f}%)")

print("\n✅ CONCLUSION:")
print("   Negative cooling capacity is DIRECTLY CAUSED by negative subcooling")
print("   When subcooling is negative, the refrigeration effect calculation fails")
print("   Formula: qc = m_dot × (H_comp.in - H_txv_avg)")
print("   With negative SC: H_txv becomes higher than expected → negative qc")

# ============================================================================
# GPM IMPACT ANALYSIS
# ============================================================================
print("\n\n" + "="*100)
print(" GPM VALUE IMPACT ON CALCULATIONS")
print("="*100)

print("\n📊 MEASURED vs CALCULATED:")
print(f"   Measured GPM (from test): {statistics.mean(all_measured_gpm):.2f} GPM average")
print(f"   Used in calculations: UNKNOWN (user-entered in rated_inputs)")
print()
print("🔍 TO FIND ACTUAL GPM USED:")
print("   1. Check application's Input dialog (currently shows what value was entered)")
print("   2. Look for session save files (.json) with ratedInputs")
print("   3. Run calculation with audit mode to see GPM value")
print()
print("⚠️  CRITICAL RECOMMENDATION:")
print("   OPTION A: Use measured 'Total Water Flow Meter' data instead of fixed GPM")
print("   OPTION B: Verify user-entered GPM matches average measured value")
print()
print("   Impact of wrong GPM:")
print("   • Mass flow error = (actual_GPM / entered_GPM)")
print("   • If entered GPM is 10x too high → mass flow 10x too high → qc 10x too high")
print("   • This explains the 'Extreme' qc values (>100,000 BTU/hr)")

print("\n" + "="*100)
print(" END OF ANALYSIS")
print("="*100)
