#!/usr/bin/env python3
"""
Analyze cooling capacity ranges and identify root causes of bad data.
"""

import csv
import statistics

def read_csv_data(filename):
    """Read calculated results CSV."""
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

def analyze_range(rows, range_name, condition):
    """Analyze a specific qc range and identify root causes."""

    # Filter rows in this range
    filtered_rows = [r for r in rows if condition(safe_float(r.get('qc')))]

    if not filtered_rows:
        print(f"\n{'='*80}")
        print(f"{range_name}: NO DATA")
        print(f"{'='*80}")
        return

    print(f"\n{'='*80}")
    print(f"{range_name}: {len(filtered_rows)} rows")
    print(f"{'='*80}")

    # Collect key metrics
    metrics = {
        'P_suction': [],
        'P_disch': [],
        'T_2b': [],
        'T_3a': [],
        'T_4a': [],
        'T_waterin': [],
        'T_waterout': [],
        'S.H_total': [],
        'S.C': [],
        'm_dot': [],
        'qc': [],
        'T_2a-LH': [],
        'T_2a-ctr': [],
        'T_2a-RH': [],
        'T_4b-lh': [],
        'T_4b-ctr': [],
        'T_4b-rh': [],
        'H_comp.in': [],
        'H_txv.lh': [],
        'H_txv.ctr': [],
        'H_txv.rh': []
    }

    for row in filtered_rows:
        for key in metrics.keys():
            val = safe_float(row.get(key))
            if val is not None:
                metrics[key].append(val)

    # Print statistics
    print(f"\nKEY OPERATING PARAMETERS:")
    print(f"{'Parameter':<20} {'Count':<8} {'Min':<12} {'Max':<12} {'Mean':<12} {'StdDev':<12}")
    print(f"{'-'*80}")

    for key in ['P_suction', 'P_disch', 'T_2b', 'T_3a', 'T_4a', 'S.H_total', 'S.C', 'm_dot', 'qc']:
        values = metrics.get(key, [])
        if values:
            count = len(values)
            min_val = min(values)
            max_val = max(values)
            mean_val = statistics.mean(values)
            std_val = statistics.stdev(values) if len(values) > 1 else 0
            print(f"{key:<20} {count:<8} {min_val:<12.2f} {max_val:<12.2f} {mean_val:<12.2f} {std_val:<12.2f}")
        else:
            print(f"{key:<20} {'0':<8} {'N/A':<12} {'N/A':<12} {'N/A':<12} {'N/A':<12}")

    # Water temperature analysis
    print(f"\nWATER TEMPERATURE ANALYSIS:")
    t_in = metrics.get('T_waterin', [])
    t_out = metrics.get('T_waterout', [])
    if t_in and t_out:
        delta_t = [out - in_ for out, in_ in zip(t_out, t_in) if out is not None and in_ is not None]
        if delta_t:
            print(f"  Water ΔT: Min={min(delta_t):.2f}°F, Max={max(delta_t):.2f}°F, Mean={statistics.mean(delta_t):.2f}°F")

            # Check for anomalies
            if any(dt < 0 for dt in delta_t):
                neg_count = sum(1 for dt in delta_t if dt < 0)
                print(f"  ⚠️  WARNING: {neg_count} rows with NEGATIVE water ΔT (T_out < T_in) - indicates sensor swap or error")
            if any(dt < 1 for dt in delta_t):
                low_count = sum(1 for dt in delta_t if dt < 1)
                print(f"  ⚠️  WARNING: {low_count} rows with very LOW water ΔT (<1°F) - weak heat transfer")
    else:
        print(f"  Water temperature data missing")

    # Pressure ratio analysis
    p_suc = metrics.get('P_suction', [])
    p_disch = metrics.get('P_disch', [])
    if p_suc and p_disch:
        pressure_ratios = [(d + 14.7) / (s + 14.7) for d, s in zip(p_disch, p_suc)
                          if s is not None and d is not None and s > -14.7]
        if pressure_ratios:
            print(f"\nPRESSURE RATIO ANALYSIS:")
            print(f"  Pressure Ratio: Min={min(pressure_ratios):.2f}, Max={max(pressure_ratios):.2f}, Mean={statistics.mean(pressure_ratios):.2f}")

            if any(pr < 1.5 for pr in pressure_ratios):
                low_pr = sum(1 for pr in pressure_ratios if pr < 1.5)
                print(f"  ⚠️  WARNING: {low_pr} rows with LOW pressure ratio (<1.5) - compressor not working properly")
            if any(pr > 10 for pr in pressure_ratios):
                high_pr = sum(1 for pr in pressure_ratios if pr > 10)
                print(f"  ⚠️  WARNING: {high_pr} rows with HIGH pressure ratio (>10) - excessive compression")

    # Superheat analysis
    sh = metrics.get('S.H_total', [])
    if sh:
        print(f"\nSUPERHEAT ANALYSIS:")
        print(f"  Superheat: Min={min(sh):.2f}°F, Max={max(sh):.2f}°F, Mean={statistics.mean(sh):.2f}°F")

        if any(s < 5 for s in sh):
            low_sh = sum(1 for s in sh if s < 5)
            print(f"  ⚠️  WARNING: {low_sh} rows with LOW superheat (<5°F) - risk of liquid slugging")
        if any(s > 30 for s in sh):
            high_sh = sum(1 for s in sh if s > 30)
            print(f"  ⚠️  WARNING: {high_sh} rows with HIGH superheat (>30°F) - reduced capacity")

    # Subcooling analysis
    sc = metrics.get('S.C', [])
    if sc:
        print(f"\nSUBCOOLING ANALYSIS:")
        print(f"  Subcooling: Min={min(sc):.2f}°F, Max={max(sc):.2f}°F, Mean={statistics.mean(sc):.2f}°F")

        if any(s < 0 for s in sc):
            neg_sc = sum(1 for s in sc if s < 0)
            print(f"  ⚠️  WARNING: {neg_sc} rows with NEGATIVE subcooling - vapor in liquid line!")
        if any(s > 40 for s in sc):
            high_sc = sum(1 for s in sc if s > 40)
            print(f"  ⚠️  WARNING: {high_sc} rows with excessive subcooling (>40°F)")

    # Enthalpy analysis for negative qc
    h_in = metrics.get('H_comp.in', [])
    h_txv_values = []
    for key in ['H_txv.lh', 'H_txv.ctr', 'H_txv.rh']:
        h_txv_values.extend(metrics.get(key, []))

    if h_in and h_txv_values and 'Negative' in range_name:
        print(f"\nENTHALPY ANALYSIS (for negative qc):")
        print(f"  H_comp.in: Min={min(h_in):.2f}, Max={max(h_in):.2f}, Mean={statistics.mean(h_in):.2f} kJ/kg")
        print(f"  H_txv (avg): Min={min(h_txv_values):.2f}, Max={max(h_txv_values):.2f}, Mean={statistics.mean(h_txv_values):.2f} kJ/kg")

        # Check if H_comp.in < H_txv (thermodynamically impossible)
        impossible = sum(1 for h_c in h_in for h_t in h_txv_values if h_c < h_t)
        if impossible > 0:
            print(f"  🔴 CRITICAL: Enthalpy at compressor inlet LOWER than TXV inlet")
            print(f"             This is thermodynamically IMPOSSIBLE - indicates sensor errors")

def main():
    print("="*80)
    print("COOLING CAPACITY RANGE ANALYSIS - ROOT CAUSE INVESTIGATION")
    print("="*80)

    rows = read_csv_data('calculated_results.csv')

    # Define ranges
    ranges = [
        ("NEGATIVE COOLING CAPACITY (< 0 BTU/hr)", lambda x: x is not None and x < 0),
        ("VERY LOW (0 to 10,000 BTU/hr)", lambda x: x is not None and x >= 0 and x < 10000),
        ("✓ GOOD DATA (10,000 to 40,000 BTU/hr)", lambda x: x is not None and x >= 10000 and x < 40000),
        ("HIGH (40,000 to 100,000 BTU/hr)", lambda x: x is not None and x >= 40000 and x < 100000),
        ("EXTREME (≥ 100,000 BTU/hr)", lambda x: x is not None and x >= 100000)
    ]

    for range_name, condition in ranges:
        analyze_range(rows, range_name, condition)

    print(f"\n{'='*80}")
    print("ANALYSIS COMPLETE")
    print(f"{'='*80}")

if __name__ == '__main__':
    main()
