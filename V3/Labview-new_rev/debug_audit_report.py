#!/usr/bin/env python3
"""
Debug script to analyze audit report row data.
This script helps identify what values are actually in row_data vs. what's being displayed.
"""

import sys
import os
import pandas as pd
import json
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def load_data_manager():
    """Load data_manager from saved session or initialize."""
    try:
        from data_manager import DataManager
        from PyQt6.QtWidgets import QApplication
        
        # Create minimal QApplication if needed
        if not QApplication.instance():
            app = QApplication(sys.argv)
        
        # Try to load from session file
        session_file = 'session_autosave.json'
        data_manager = DataManager()
        
        if os.path.exists(session_file):
            try:
                with open(session_file, 'r') as f:
                    session_data = json.load(f)
                    data_manager.load_session(session_file)
                    print(f"[DEBUG] Loaded session from {session_file}")
            except Exception as e:
                print(f"[DEBUG] Could not load session: {e}")
        
        return data_manager
    except Exception as e:
        print(f"[ERROR] Failed to load data_manager: {e}")
        return None

def analyze_row_data(row_data, row_index):
    """Analyze and print all values in row_data."""
    print("\n" + "="*80)
    print(f"ROW {row_index} - COMPLETE DATA DUMP")
    print("="*80)
    
    if not hasattr(row_data, 'index'):
        print("[ERROR] row_data is not a pandas Series")
        return
    
    all_cols = list(row_data.index)
    print(f"\nTotal columns: {len(all_cols)}")
    
    # Group columns by type
    temp_cols = [c for c in all_cols if c.startswith('T_') or 'temp' in c.lower()]
    pressure_cols = [c for c in all_cols if c.startswith('P_') or 'press' in c.lower()]
    enthalpy_cols = [c for c in all_cols if ('h' in str(c).lower() or 'H' in str(c)) and ('comp' in str(c).lower() or 'cond' in str(c).lower() or 'txv' in str(c).lower() or 'coil' in str(c).lower() or any(x in str(c) for x in ['3a', '4a', '2b', '4b']))]
    flow_cols = [c for c in all_cols if 'flow' in c.lower() or 'gpm' in c.lower() or 'm_dot' in c.lower()]
    capacity_cols = [c for c in all_cols if 'qc' in c.lower() or 'capacity' in c.lower()]
    other_cols = [c for c in all_cols if c not in temp_cols + pressure_cols + enthalpy_cols + flow_cols + capacity_cols]
    
    def print_section(name, cols):
        if cols:
            print(f"\n{name} ({len(cols)} columns):")
            for col in sorted(cols):
                val = row_data.get(col) if hasattr(row_data, 'get') else row_data[col]
                if pd.isna(val):
                    print(f"  {col:30s} = NaN")
                else:
                    print(f"  {col:30s} = {val}")
    
    print_section("TEMPERATURES", temp_cols)
    print_section("PRESSURES", pressure_cols)
    print_section("ENTHALPIES", enthalpy_cols)
    print_section("FLOW RATES", flow_cols)
    print_section("CAPACITY", capacity_cols)
    print_section("OTHER", other_cols)
    
    # Key values for audit report
    print("\n" + "="*80)
    print("KEY VALUES FOR AUDIT REPORT")
    print("="*80)
    
    key_tests = [
        ('T_3a', ['T_3a']),
        ('T_4a', ['T_4a']),
        ('P_disch', ['P_disch']),
        ('P_suction', ['P_suction']),
        ('T_2b', ['T_2b']),
        ('T_waterin', ['T_waterin']),
        ('T_waterout', ['T_waterout']),
        ('H_comp.in', ['H_comp.in', 'h_2b', 'H_2b']),
        ('h_3a', ['h_3a', 'H_3a', 'H_comp.out']),
        ('h_4a', ['h_4a', 'H_4a', 'H_cond.out']),
        ('H_txv.lh', ['H_txv.lh', 'h_4b_LH', 'H_4b_LH']),
        ('H_txv.ctr', ['H_txv.ctr', 'h_4b_CTR', 'H_4b_CTR']),
        ('H_txv.rh', ['H_txv.rh', 'h_4b_RH', 'H_4b_RH']),
        ('m_dot', ['m_dot']),
        ('qc', ['qc']),
    ]
    
    for target_name, variants in key_tests:
        found = False
        for variant in variants:
            if variant in all_cols:
                val = row_data.get(variant) if hasattr(row_data, 'get') else row_data[variant]
                if val is not None and not pd.isna(val):
                    print(f"  {target_name:20s} -> {variant:20s} = {val}")
                    found = True
                    break
        if not found:
            print(f"  {target_name:20s} -> NOT FOUND")
    
    # Write to log file
    log_file = f"audit_debug_row_{row_index}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    with open(log_file, 'w') as f:
        f.write(f"ROW {row_index} - COMPLETE DATA DUMP\n")
        f.write("="*80 + "\n\n")
        f.write(f"Total columns: {len(all_cols)}\n\n")
        
        f.write("ALL COLUMNS AND VALUES:\n")
        for col in sorted(all_cols):
            val = row_data.get(col) if hasattr(row_data, 'get') else row_data[col]
            if pd.isna(val):
                f.write(f"{col:30s} = NaN\n")
            else:
                f.write(f"{col:30s} = {val}\n")
        
        f.write("\nKEY VALUES FOR AUDIT REPORT:\n")
        for target_name, variants in key_tests:
            found = False
            for variant in variants:
                if variant in all_cols:
                    val = row_data.get(variant) if hasattr(row_data, 'get') else row_data[variant]
                    if val is not None and not pd.isna(val):
                        f.write(f"{target_name:20s} -> {variant:20s} = {val}\n")
                        found = True
                        break
            if not found:
                f.write(f"{target_name:20s} -> NOT FOUND\n")
    
    print(f"\n[DEBUG] Log written to: {log_file}")

def main():
    """Main function."""
    if len(sys.argv) > 1:
        try:
            row_index = int(sys.argv[1])
        except ValueError:
            print(f"[ERROR] Invalid row index: {sys.argv[1]}")
            return
    else:
        row_index = input("Enter row index to analyze (default: 0): ").strip()
        if not row_index:
            row_index = 0
        else:
            try:
                row_index = int(row_index)
            except ValueError:
                print(f"[ERROR] Invalid row index: {row_index}")
                return
    
    print(f"[DEBUG] Analyzing row {row_index}")
    
    # Load data_manager
    data_manager = load_data_manager()
    if not data_manager:
        print("[ERROR] Could not load data_manager")
        return
    
    # Try to get processed_df
    try:
        # Check if calculations_widget has processed_df
        from calculations_widget import CalculationsWidget
        
        # This won't work directly, we need to simulate the calculation
        # Instead, let's try to load from a saved state or run calculation
        
        print("[DEBUG] Attempting to get processed_df...")
        
        # Try to get filtered data and run calculation
        input_df = data_manager.get_filtered_data()
        if input_df is None or input_df.empty:
            print("[ERROR] No filtered data available")
            print("[INFO] Please run calculations in the application first, or load a session")
            return
        
        print(f"[DEBUG] Found {len(input_df)} rows in filtered data")
        
        # Run calculation to get processed_df
        from calculation_orchestrator import run_batch_processing
        print("[DEBUG] Running calculations...")
        processed_df = run_batch_processing(data_manager, input_df)
        print(f"[DEBUG] Calculations complete. Processed {len(processed_df)} rows")
        
        if row_index >= len(processed_df):
            print(f"[ERROR] Row index {row_index} is out of range (max: {len(processed_df)-1})")
            return
        
        # Get row data
        row_data = processed_df.iloc[row_index]
        print(f"[DEBUG] Retrieved row_data for row {row_index}")
        
        # Analyze
        analyze_row_data(row_data, row_index)
        
    except Exception as e:
        import traceback
        print(f"[ERROR] Exception occurred: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()

