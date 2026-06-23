#!/usr/bin/env python3
"""
Verify GPM usage in calculations - trace the exact flow of GPM value
"""

import json
import csv

def safe_float(value):
    """Safely convert to float."""
    try:
        return float(value) if value and value.strip() else None
    except:
        return None

print("="*100)
print(" GPM USAGE VERIFICATION ANALYSIS")
print("="*100)

# Load session file to get GPM
with open('ID6SU12WE-12.json', 'r') as f:
    session = json.load(f)

gpm_from_session = session.get('ratedInputs', {}).get('gpm_water')
print(f"\n1. GPM from session file (ID6SU12WE-12.json):")
print(f"   ratedInputs.gpm_water = {gpm_from_session} GPM")

# Load calculated results
with open('calculated_results.csv', 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

print(f"\n2. Calculated results analysis:")
print(f"   Total rows: {len(rows)}")

# Analyze first few rows
print(f"\n3. Sample calculations (first 5 rows):")
print(f"{'Row':<5} {'T_in':<8} {'T_out':<8} {'ΔT':<8} {'m_dot':<12} {'qc':<15}")
print("-"*70)

for i, row in enumerate(rows[:5]):
    t_in = safe_float(row.get('T_waterin'))
    t_out = safe_float(row.get('T_waterout'))
    m_dot = safe_float(row.get('m_dot'))
    qc = safe_float(row.get('qc'))

    delta_t = None
    if t_in is not None and t_out is not None:
        delta_t = t_out - t_in

    print(f"{i+1:<5} {t_in if t_in else 'N/A':<8.2f} {t_out if t_out else 'N/A':<8.2f} "
          f"{delta_t if delta_t else 'N/A':<8.2f} {m_dot if m_dot else 'N/A':<12.2f} "
          f"{qc if qc else 'N/A':<15.2f}")

# REVERSE CALCULATE GPM from m_dot
print(f"\n4. REVERSE ENGINEERING GPM from calculated m_dot:")
print(f"   Formula: Q_water = 500.4 × GPM × ΔT")
print(f"           m_dot = Q_water / Δh_condenser")
print(f"   Therefore: GPM = (m_dot × Δh) / (500.4 × ΔT)")
print()

sample_row = rows[1]  # Row 2 has good data
t_in = safe_float(sample_row.get('T_waterin'))
t_out = safe_float(sample_row.get('T_waterout'))
m_dot = safe_float(sample_row.get('m_dot'))
h_3a = safe_float(sample_row.get('h_3a'))  # Compressor outlet enthalpy
h_4a = safe_float(sample_row.get('h_4a'))  # Condenser outlet enthalpy

if all(x is not None for x in [t_in, t_out, m_dot, h_3a, h_4a]):
    delta_t_water = t_out - t_in
    delta_h_condenser_kjkg = h_3a - h_4a

    # Convert kJ/kg to BTU/lb: multiply by 0.4299
    delta_h_condenser_btulb = delta_h_condenser_kjkg * 0.4299

    # Q_water = m_dot × Δh
    q_water = m_dot * delta_h_condenser_btulb

    # GPM = Q_water / (500.4 × ΔT)
    gpm_calculated = q_water / (500.4 * delta_t_water)

    print(f"   Using Row 2 (sample with good data):")
    print(f"     T_waterin = {t_in:.2f}°F")
    print(f"     T_waterout = {t_out:.2f}°F")
    print(f"     ΔT_water = {delta_t_water:.2f}°F")
    print(f"     m_dot (calculated) = {m_dot:.2f} lb/hr")
    print(f"     H_3a = {h_3a:.2f} kJ/kg")
    print(f"     H_4a = {h_4a:.2f} kJ/kg")
    print(f"     Δh_condenser = {delta_h_condenser_kjkg:.2f} kJ/kg = {delta_h_condenser_btulb:.2f} BTU/lb")
    print(f"     Q_water = m_dot × Δh = {m_dot:.2f} × {delta_h_condenser_btulb:.2f} = {q_water:.2f} BTU/hr")
    print(f"     GPM = Q_water / (500.4 × ΔT) = {q_water:.2f} / (500.4 × {delta_t_water:.2f})")
    print(f"     GPM = {gpm_calculated:.4f}")
    print()
    print(f"   ✅ EXPECTED GPM from session: {gpm_from_session}")
    print(f"   🔍 ACTUAL GPM used in calculation: {gpm_calculated:.4f}")
    print()

    if abs(gpm_calculated - gpm_from_session) < 0.1:
        print(f"   ✅ MATCH! Calculations correctly used {gpm_from_session} GPM")
    else:
        print(f"   ❌ MISMATCH!")
        print(f"   Expected: {gpm_from_session} GPM")
        print(f"   Got: {gpm_calculated:.4f} GPM")
        print(f"   Error: {((gpm_calculated / gpm_from_session) - 1) * 100:.1f}%")

# Check statistical distribution
print(f"\n5. Statistical analysis of mass flow rates:")

# Separate by qc range
good_mdot = []
negative_mdot = []
extreme_mdot = []

for row in rows:
    qc = safe_float(row.get('qc'))
    m_dot = safe_float(row.get('m_dot'))

    if qc is not None and m_dot is not None:
        if 10000 <= qc <= 40000:
            good_mdot.append(m_dot)
        elif qc < 0:
            negative_mdot.append(m_dot)
        elif qc >= 100000:
            extreme_mdot.append(m_dot)

print(f"   Good data (10K-40K BTU/hr):     {len(good_mdot)} rows")
if good_mdot:
    print(f"     m_dot range: {min(good_mdot):.2f} to {max(good_mdot):.2f} lb/hr")
    print(f"     m_dot average: {sum(good_mdot)/len(good_mdot):.2f} lb/hr")

print(f"\n   Negative qc data:               {len(negative_mdot)} rows")
if negative_mdot:
    print(f"     m_dot range: {min(negative_mdot):.2f} to {max(negative_mdot):.2f} lb/hr")
    print(f"     m_dot average: {sum(negative_mdot)/len(negative_mdot):.2f} lb/hr")

print(f"\n   Extreme qc data (>100K BTU/hr): {len(extreme_mdot)} rows")
if extreme_mdot:
    print(f"     m_dot range: {min(extreme_mdot):.2f} to {max(extreme_mdot):.2f} lb/hr")
    print(f"     m_dot average: {sum(extreme_mdot)/len(extreme_mdot):.2f} lb/hr")

# Calculate ratio
if good_mdot and extreme_mdot:
    avg_good = sum(good_mdot)/len(good_mdot)
    avg_extreme = sum(extreme_mdot)/len(extreme_mdot)
    ratio = avg_extreme / avg_good
    print(f"\n   Ratio: extreme/good = {ratio:.2f}x")
    print(f"\n   If GPM was wrong by this ratio:")
    print(f"     Entered: {gpm_from_session} GPM")
    print(f"     Actual used: {gpm_from_session * ratio:.2f} GPM (implied)")

print(f"\n6. CONCLUSION:")
print(f"   If reverse-calculated GPM ≈ {gpm_from_session}, then 8 GPM IS being used correctly")
print(f"   If reverse-calculated GPM ≠ {gpm_from_session}, then there's a code bug")
print(f"   The mass flow variation suggests something ELSE is wrong, not GPM")

print("\n" + "="*100)
