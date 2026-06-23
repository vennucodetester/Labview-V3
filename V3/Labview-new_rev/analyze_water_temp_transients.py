#!/usr/bin/env python3
"""
Thermodynamic Analysis: Water Temperature Transients and System Stability

This script analyzes the relationship between water temperature swings,
discharge pressure variations, and data quality in the refrigeration system.

Focus areas:
1. Water temperature swing patterns and magnitude
2. Cascading effects on discharge pressure and subcooling
3. Steady-state vs transient period identification
4. Proper filtering methods for transient data
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
import json

def calculate_rolling_statistics(series: pd.Series, window: int) -> Dict:
    """Calculate rolling statistics for a time series."""
    return {
        'mean': series.rolling(window=window, center=True).mean(),
        'std': series.rolling(window=window, center=True).std(),
        'min': series.rolling(window=window, center=True).min(),
        'max': series.rolling(window=window, center=True).max(),
        'range': series.rolling(window=window, center=True).max() -
                 series.rolling(window=window, center=True).min()
    }

def identify_steady_state_periods(df: pd.DataFrame,
                                   column: str,
                                   window: int = 10,
                                   stability_threshold: float = 0.5) -> pd.Series:
    """
    Identify steady-state periods based on rate of change and stability.

    A period is considered steady-state if:
    - Standard deviation within window is below threshold
    - Rate of change is minimal
    """
    rolling_std = df[column].rolling(window=window, center=True).std()
    is_steady = rolling_std < stability_threshold
    return is_steady

def analyze_water_temperature_swings(input_file: str, calculated_file: str):
    """Main analysis function."""

    print("=" * 80)
    print("THERMODYNAMIC ANALYSIS: WATER TEMPERATURE TRANSIENTS")
    print("=" * 80)
    print()

    # Read data
    print("Loading data files...")
    df_input = pd.read_csv(input_file)
    df_calc = pd.read_csv(calculated_file)

    # Clean column names (remove leading/trailing spaces)
    df_input.columns = df_input.columns.str.strip()
    df_calc.columns = df_calc.columns.str.strip()

    print(f"Input data: {len(df_input)} rows")
    print(f"Calculated data: {len(df_calc)} rows")
    print()

    # ============================================================================
    # PART 1: WATER TEMPERATURE ANALYSIS
    # ============================================================================
    print("=" * 80)
    print("PART 1: WATER TEMPERATURE SWING ANALYSIS")
    print("=" * 80)
    print()

    water_in = df_input['Water in HeatX'].dropna()
    water_out = df_input['Water out HeatX'].dropna()
    delta_t_water = water_in - water_out

    print("Water Inlet Temperature (°F):")
    print(f"  Mean:   {water_in.mean():.2f} °F")
    print(f"  Std:    {water_in.std():.2f} °F")
    print(f"  Min:    {water_in.min():.2f} °F")
    print(f"  Max:    {water_in.max():.2f} °F")
    print(f"  Range:  {water_in.max() - water_in.min():.2f} °F")
    print()

    print("Water Outlet Temperature (°F):")
    print(f"  Mean:   {water_out.mean():.2f} °F")
    print(f"  Std:    {water_out.std():.2f} °F")
    print(f"  Min:    {water_out.min():.2f} °F")
    print(f"  Max:    {water_out.max():.2f} °F")
    print(f"  Range:  {water_out.max() - water_out.min():.2f} °F")
    print()

    print("Water Temperature Difference ΔT (°F):")
    print(f"  Mean:   {delta_t_water.mean():.2f} °F")
    print(f"  Std:    {delta_t_water.std():.2f} °F")
    print(f"  Min:    {delta_t_water.min():.2f} °F")
    print(f"  Max:    {delta_t_water.max():.2f} °F")
    print(f"  Range:  {delta_t_water.max() - delta_t_water.min():.2f} °F")
    print()

    # Calculate rate of change for water inlet temperature
    water_in_diff = water_in.diff().abs()
    print("Water Inlet Temperature Rate of Change (°F per sample):")
    print(f"  Mean:   {water_in_diff.mean():.3f} °F/sample")
    print(f"  Median: {water_in_diff.median():.3f} °F/sample")
    print(f"  90th %: {water_in_diff.quantile(0.90):.3f} °F/sample")
    print(f"  Max:    {water_in_diff.max():.3f} °F/sample")
    print()

    # Rolling statistics for water inlet (30-point window ~5 min if 10 sec sampling)
    print("Rolling Statistics (30-point window ~5 minutes):")
    water_in_rolling = calculate_rolling_statistics(water_in, window=30)
    print(f"  Max rolling std:   {water_in_rolling['std'].max():.3f} °F")
    print(f"  Max rolling range: {water_in_rolling['range'].max():.3f} °F")
    print(f"  Mean rolling std:  {water_in_rolling['std'].mean():.3f} °F")
    print()

    # ============================================================================
    # PART 2: PRESSURE ANALYSIS AND CORRELATION
    # ============================================================================
    print("=" * 80)
    print("PART 2: DISCHARGE PRESSURE VARIATION ANALYSIS")
    print("=" * 80)
    print()

    # Liquid pressure is discharge pressure
    liquid_pressure = df_input['Liquid Pressure'].dropna()

    print("Discharge/Liquid Pressure (psig):")
    print(f"  Mean:   {liquid_pressure.mean():.2f} psig")
    print(f"  Std:    {liquid_pressure.std():.2f} psig")
    print(f"  Min:    {liquid_pressure.min():.2f} psig")
    print(f"  Max:    {liquid_pressure.max():.2f} psig")
    print(f"  Range:  {liquid_pressure.max() - liquid_pressure.min():.2f} psig")
    print()

    # Rate of change for pressure
    pressure_diff = liquid_pressure.diff().abs()
    print("Discharge Pressure Rate of Change (psig per sample):")
    print(f"  Mean:   {pressure_diff.mean():.3f} psig/sample")
    print(f"  Median: {pressure_diff.median():.3f} psig/sample")
    print(f"  90th %: {pressure_diff.quantile(0.90):.3f} psig/sample")
    print(f"  Max:    {pressure_diff.max():.3f} psig/sample")
    print()

    # Rolling statistics for pressure
    pressure_rolling = calculate_rolling_statistics(liquid_pressure, window=30)
    print("Discharge Pressure Rolling Statistics (30-point window):")
    print(f"  Max rolling std:   {pressure_rolling['std'].max():.3f} psig")
    print(f"  Max rolling range: {pressure_rolling['range'].max():.3f} psig")
    print(f"  Mean rolling std:  {pressure_rolling['std'].mean():.3f} psig")
    print()

    # Correlation between water temp and pressure
    # Align the series
    min_len = min(len(water_in), len(liquid_pressure))
    water_in_aligned = water_in.iloc[:min_len].reset_index(drop=True)
    pressure_aligned = liquid_pressure.iloc[:min_len].reset_index(drop=True)

    correlation = water_in_aligned.corr(pressure_aligned)
    print(f"Correlation between Water Inlet Temp and Discharge Pressure: {correlation:.3f}")
    print()

    # ============================================================================
    # PART 3: SUBCOOLING AND TRANSIENT EFFECTS
    # ============================================================================
    print("=" * 80)
    print("PART 3: SUBCOOLING VARIATION AND TRANSIENT EFFECTS")
    print("=" * 80)
    print()

    subcooling = df_calc['S.C'].dropna()

    print("Subcooling (°F):")
    print(f"  Mean:   {subcooling.mean():.2f} °F")
    print(f"  Std:    {subcooling.std():.2f} °F")
    print(f"  Min:    {subcooling.min():.2f} °F")
    print(f"  Max:    {subcooling.max():.2f} °F")
    print(f"  Range:  {subcooling.max() - subcooling.min():.2f} °F")
    print()

    negative_sc_count = (subcooling < 0).sum()
    negative_sc_pct = (negative_sc_count / len(subcooling)) * 100
    print(f"Negative subcooling occurrences: {negative_sc_count} ({negative_sc_pct:.1f}%)")
    print()

    # Analyze subcooling in ranges
    print("Subcooling Distribution:")
    print(f"  < -10°F:    {(subcooling < -10).sum()} rows ({(subcooling < -10).sum()/len(subcooling)*100:.1f}%)")
    print(f"  -10 to 0°F: {((subcooling >= -10) & (subcooling < 0)).sum()} rows ({((subcooling >= -10) & (subcooling < 0)).sum()/len(subcooling)*100:.1f}%)")
    print(f"  0 to 5°F:   {((subcooling >= 0) & (subcooling < 5)).sum()} rows ({((subcooling >= 0) & (subcooling < 5)).sum()/len(subcooling)*100:.1f}%)")
    print(f"  5 to 10°F:  {((subcooling >= 5) & (subcooling < 10)).sum()} rows ({((subcooling >= 5) & (subcooling < 10)).sum()/len(subcooling)*100:.1f}%)")
    print(f"  > 10°F:     {(subcooling >= 10).sum()} rows ({(subcooling >= 10).sum()/len(subcooling)*100:.1f}%)")
    print()

    # ============================================================================
    # PART 4: STEADY-STATE IDENTIFICATION
    # ============================================================================
    print("=" * 80)
    print("PART 4: STEADY-STATE vs TRANSIENT PERIOD IDENTIFICATION")
    print("=" * 80)
    print()

    # Identify steady-state periods based on water temp stability
    df_input['water_steady'] = identify_steady_state_periods(
        df_input, 'Water in HeatX', window=20, stability_threshold=0.5
    )

    # Identify steady-state based on pressure stability
    df_input['pressure_steady'] = identify_steady_state_periods(
        df_input, 'Liquid Pressure', window=20, stability_threshold=1.0
    )

    # Combined steady-state: both water and pressure stable
    df_input['combined_steady'] = df_input['water_steady'] & df_input['pressure_steady']

    steady_count = df_input['combined_steady'].sum()
    steady_pct = (steady_count / len(df_input)) * 100

    print(f"Steady-state periods identified: {steady_count} / {len(df_input)} ({steady_pct:.1f}%)")
    print(f"Transient periods: {len(df_input) - steady_count} / {len(df_input)} ({100-steady_pct:.1f}%)")
    print()

    print("Steady-state criteria:")
    print("  - Water inlet temp rolling std < 0.5°F over 20 samples")
    print("  - Discharge pressure rolling std < 1.0 psig over 20 samples")
    print()

    # ============================================================================
    # PART 5: DATA QUALITY CORRELATION WITH STABILITY
    # ============================================================================
    print("=" * 80)
    print("PART 5: DATA QUALITY vs STABILITY CORRELATION")
    print("=" * 80)
    print()

    # Merge calculated results with steady-state indicators
    # Assuming row correspondence between input and calculated
    if len(df_input) == len(df_calc):
        df_calc['water_steady'] = df_input['water_steady'].values
        df_calc['pressure_steady'] = df_input['pressure_steady'].values
        df_calc['combined_steady'] = df_input['combined_steady'].values

        # Analyze qc quality by stability
        df_calc['qc_quality'] = pd.cut(df_calc['qc'],
                                       bins=[-np.inf, 0, 10000, 40000, np.inf],
                                       labels=['Negative', 'Low', 'Good', 'High'])

        print("Data Quality by Stability Status:")
        print()

        # Cross-tabulation
        crosstab = pd.crosstab(df_calc['qc_quality'], df_calc['combined_steady'],
                               normalize='columns', margins=True)
        print("Proportion of each quality category in Transient vs Steady-State:")
        print(crosstab)
        print()

        # Subcooling by stability
        print("Subcooling Statistics by Stability:")
        print()
        steady_sc = df_calc[df_calc['combined_steady'] == True]['S.C']
        transient_sc = df_calc[df_calc['combined_steady'] == False]['S.C']

        print("Steady-State Subcooling:")
        print(f"  Count:  {len(steady_sc)}")
        print(f"  Mean:   {steady_sc.mean():.2f} °F")
        print(f"  Std:    {steady_sc.std():.2f} °F")
        print(f"  Min:    {steady_sc.min():.2f} °F")
        print(f"  Max:    {steady_sc.max():.2f} °F")
        print(f"  Negative: {(steady_sc < 0).sum()} ({(steady_sc < 0).sum()/len(steady_sc)*100:.1f}%)")
        print()

        print("Transient Subcooling:")
        print(f"  Count:  {len(transient_sc)}")
        print(f"  Mean:   {transient_sc.mean():.2f} °F")
        print(f"  Std:    {transient_sc.std():.2f} °F")
        print(f"  Min:    {transient_sc.min():.2f} °F")
        print(f"  Max:    {transient_sc.max():.2f} °F")
        print(f"  Negative: {(transient_sc < 0).sum()} ({(transient_sc < 0).sum()/len(transient_sc)*100:.1f}%)")
        print()

        # qc quality by stability
        print("Cooling Capacity by Stability:")
        print()
        steady_qc = df_calc[df_calc['combined_steady'] == True]['qc']
        transient_qc = df_calc[df_calc['combined_steady'] == False]['qc']

        print("Steady-State qc:")
        print(f"  Count:  {len(steady_qc)}")
        print(f"  Mean:   {steady_qc.mean():.0f} BTU/hr")
        print(f"  Median: {steady_qc.median():.0f} BTU/hr")
        print(f"  Std:    {steady_qc.std():.0f} BTU/hr")
        print(f"  Good range (10k-40k): {((steady_qc >= 10000) & (steady_qc <= 40000)).sum()} ({((steady_qc >= 10000) & (steady_qc <= 40000)).sum()/len(steady_qc)*100:.1f}%)")
        print()

        print("Transient qc:")
        print(f"  Count:  {len(transient_qc)}")
        print(f"  Mean:   {transient_qc.mean():.0f} BTU/hr")
        print(f"  Median: {transient_qc.median():.0f} BTU/hr")
        print(f"  Std:    {transient_qc.std():.0f} BTU/hr")
        print(f"  Good range (10k-40k): {((transient_qc >= 10000) & (transient_qc <= 40000)).sum()} ({((transient_qc >= 10000) & (transient_qc <= 40000)).sum()/len(transient_qc)*100:.1f}%)")
        print()

    # ============================================================================
    # PART 6: MOVING AVERAGE ANALYSIS
    # ============================================================================
    print("=" * 80)
    print("PART 6: MOVING AVERAGE FILTERING EFFECTIVENESS")
    print("=" * 80)
    print()

    # Apply moving average to key parameters
    window_sizes = [5, 10, 20, 30]

    print("Effect of Moving Average on Water Inlet Temperature:")
    for window in window_sizes:
        water_in_ma = water_in.rolling(window=window, center=True).mean()
        std_reduction = (1 - water_in_ma.std() / water_in.std()) * 100
        print(f"  {window}-point MA: Std reduced by {std_reduction:.1f}% ({water_in.std():.2f} → {water_in_ma.std():.2f} °F)")
    print()

    print("Effect of Moving Average on Discharge Pressure:")
    for window in window_sizes:
        pressure_ma = liquid_pressure.rolling(window=window, center=True).mean()
        std_reduction = (1 - pressure_ma.std() / liquid_pressure.std()) * 100
        print(f"  {window}-point MA: Std reduced by {std_reduction:.1f}% ({liquid_pressure.std():.2f} → {pressure_ma.std():.2f} psig)")
    print()

    # ============================================================================
    # PART 7: THERMODYNAMIC CONSIDERATIONS FOR NEGATIVE SUBCOOLING
    # ============================================================================
    print("=" * 80)
    print("PART 7: THERMODYNAMIC ANALYSIS OF NEGATIVE SUBCOOLING")
    print("=" * 80)
    print()

    print("Can negative subcooling exist in real systems?")
    print()
    print("SCENARIO 1: Measurement During Transients")
    print("  - Water temperature increases rapidly")
    print("  - Condensing pressure rises (follows water temp)")
    print("  - Saturation temperature increases")
    print("  - Liquid line sensor (T_4a) responds slower than pressure sensor")
    print("  - Result: APPARENT negative subcooling during transition")
    print("  - Duration: Temporary (seconds to minutes)")
    print()

    print("SCENARIO 2: Pressure Drop Effects")
    print("  - Pressure measured at compressor discharge")
    print("  - Temperature measured downstream after pressure drop")
    print("  - Using discharge pressure to calculate T_sat may be incorrect")
    print("  - Actual liquid line pressure is lower → lower T_sat")
    print("  - Result: FALSE negative subcooling due to reference pressure mismatch")
    print()

    print("SCENARIO 3: Flash Gas in Liquid Line (TRUE thermodynamic problem)")
    print("  - Insufficient subcooling at condenser outlet")
    print("  - Pressure drop in liquid line causes refrigerant to flash")
    print("  - Two-phase flow enters TXV")
    print("  - Result: REAL negative subcooling - SYSTEM MALFUNCTION")
    print("  - This WILL cause capacity problems")
    print()

    # Analyze if negative subcooling correlates with high pressure drop
    if len(df_input) == len(df_calc):
        # Get discharge pressure and suction pressure
        p_discharge = df_input['Liquid Pressure']
        p_suction = df_input['Suction Presure']  # Note: misspelled in data

        df_analysis = pd.DataFrame({
            'subcooling': df_calc['S.C'],
            'p_discharge': p_discharge,
            'p_suction': p_suction,
            'qc': df_calc['qc']
        }).dropna()

        df_analysis['pressure_ratio'] = df_analysis['p_discharge'] / df_analysis['p_suction']

        neg_sc = df_analysis[df_analysis['subcooling'] < 0]
        pos_sc = df_analysis[df_analysis['subcooling'] >= 0]

        print("Pressure Ratio Analysis:")
        print()
        print(f"Negative Subcooling Cases (n={len(neg_sc)}):")
        print(f"  Mean pressure ratio: {neg_sc['pressure_ratio'].mean():.2f}")
        print(f"  Mean discharge pressure: {neg_sc['p_discharge'].mean():.1f} psig")
        print()
        print(f"Positive Subcooling Cases (n={len(pos_sc)}):")
        print(f"  Mean pressure ratio: {pos_sc['pressure_ratio'].mean():.2f}")
        print(f"  Mean discharge pressure: {pos_sc['p_discharge'].mean():.1f} psig")
        print()

    # ============================================================================
    # PART 8: FILTERING RECOMMENDATIONS
    # ============================================================================
    print("=" * 80)
    print("PART 8: RECOMMENDED DATA FILTERING STRATEGIES")
    print("=" * 80)
    print()

    print("STRATEGY 1: Steady-State Detection (RECOMMENDED PRIMARY METHOD)")
    print("-" * 80)
    print("Filter Criteria:")
    print("  1. Rolling std of water inlet temp < 0.5°F (20-point window)")
    print("  2. Rolling std of discharge pressure < 1.0 psig (20-point window)")
    print("  3. Rate of change < threshold for key parameters")
    print()
    print("Advantages:")
    print("  - Addresses root cause (transient conditions)")
    print("  - No arbitrary thresholds on results")
    print("  - Physically meaningful")
    print("  - Allows negative subcooling during steady-state if real")
    print()
    print("Implementation:")
    print("  - Calculate rolling statistics on input sensors")
    print("  - Flag rows where stability criteria NOT met")
    print("  - Option to exclude transient data OR flag with warning")
    print()

    print("STRATEGY 2: Moving Average Smoothing")
    print("-" * 80)
    print("Filter Method:")
    print("  1. Apply 10-20 point moving average to sensor inputs")
    print("  2. Recalculate thermodynamic properties from smoothed inputs")
    print("  3. Use smoothed values for performance calculations")
    print()
    print("Advantages:")
    print("  - Reduces noise and transient spikes")
    print("  - Preserves all data (no exclusion)")
    print("  - Simple to implement")
    print()
    print("Disadvantages:")
    print("  - May mask real rapid changes")
    print("  - Edge effects at start/end of data")
    print("  - Requires re-calculation of all properties")
    print()

    print("STRATEGY 3: Multi-Criteria Physical Validation")
    print("-" * 80)
    print("Filter Criteria (apply during steady-state only):")
    print("  1. Subcooling: -2°F < SC < 20°F (allow small negative during transient)")
    print("  2. Superheat: 5°F < SH < 30°F")
    print("  3. Pressure ratio: 2.0 < PR < 4.0 for R290")
    print("  4. Cooling capacity: Must be positive")
    print("  5. Mass flow rate: Within reasonable bounds (50-500 lb/hr)")
    print("  6. ΔT water: 1°F < ΔT < 15°F")
    print()
    print("Advantages:")
    print("  - Multiple cross-checks")
    print("  - Catches multiple error types")
    print()
    print("Disadvantages:")
    print("  - Arbitrary thresholds")
    print("  - May reject valid unusual operating points")
    print()

    print("STRATEGY 4: Outlier Detection (Statistical)")
    print("-" * 80)
    print("Filter Method:")
    print("  1. Calculate Z-scores for key outputs (qc, mass flow, etc.)")
    print("  2. Flag values > 3 standard deviations from mean")
    print("  3. Use robust statistics (median, IQR) instead of mean/std")
    print()
    print("Advantages:")
    print("  - Data-driven, not assumption-based")
    print("  - Adapts to actual data distribution")
    print()
    print("Disadvantages:")
    print("  - May reject valid extreme operating conditions")
    print("  - Doesn't use physical knowledge")
    print()

    print("=" * 80)
    print("FINAL RECOMMENDATION")
    print("=" * 80)
    print()
    print("HYBRID APPROACH:")
    print()
    print("PRIMARY FILTER: Steady-State Detection")
    print("  → Exclude data during transient water temperature or pressure changes")
    print("  → This addresses the root cause of most bad data")
    print()
    print("SECONDARY FILTER: Physical Bounds (Loose)")
    print("  → Apply only to steady-state data")
    print("  → Allow negative subcooling if: |SC| < 2°F and qc is reasonable")
    print("  → Flag severe violations: SC < -5°F, SH < 3°F, qc < 0, etc.")
    print()
    print("OPTIONAL: Moving Average for Visualization")
    print("  → Apply 10-point MA to smooth plots")
    print("  → Do NOT use for excluding data")
    print()
    print("This approach:")
    print("  ✓ Respects physical reality (transients exist)")
    print("  ✓ Uses measurement timing as primary criterion")
    print("  ✓ Allows unexpected but valid data")
    print("  ✓ Provides clear user control")
    print()

    # ============================================================================
    # SUMMARY STATISTICS
    # ============================================================================
    print("=" * 80)
    print("SUMMARY STATISTICS")
    print("=" * 80)
    print()

    if len(df_input) == len(df_calc):
        steady_state_data = df_calc[df_calc['combined_steady'] == True]

        print(f"Total data points: {len(df_calc)}")
        print(f"Steady-state points: {len(steady_state_data)} ({len(steady_state_data)/len(df_calc)*100:.1f}%)")
        print()

        print("If using steady-state filtering only:")
        good_steady = ((steady_state_data['qc'] >= 10000) &
                       (steady_state_data['qc'] <= 40000)).sum()
        print(f"  Good quality data (10k-40k BTU/hr): {good_steady} rows ({good_steady/len(steady_state_data)*100:.1f}% of steady-state)")

        neg_sc_steady = (steady_state_data['S.C'] < 0).sum()
        print(f"  Negative subcooling in steady-state: {neg_sc_steady} ({neg_sc_steady/len(steady_state_data)*100:.1f}%)")
        print()

        # Save filtered data
        steady_state_data.to_csv('steady_state_filtered_data.csv', index=False)
        print("Steady-state filtered data saved to: steady_state_filtered_data.csv")
        print()

if __name__ == '__main__':
    input_file = 'ID6SU12WE DOE 2.csv'
    calculated_file = 'calculated_results.csv'

    try:
        analyze_water_temperature_swings(input_file, calculated_file)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
