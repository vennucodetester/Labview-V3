"""
Debug script to find h_3a, h_4a and other enthalpy values in processed DataFrame.
Run this after calculations are performed to see what columns actually exist.
"""

import pandas as pd
import sys

def debug_enthalpy_columns(processed_df_path=None, row_index=16):
    """
    Debug script to find enthalpy columns in processed DataFrame.
    
    Args:
        processed_df_path: Path to saved processed DataFrame CSV (optional)
        row_index: Row index to check (default 16, matching user's example)
    """
    print("=" * 80)
    print("DEBUGGING ENTHALPY COLUMNS IN PROCESSED DATAFRAME")
    print("=" * 80)
    print()
    
    # If no path provided, we need to access it from the widget
    # For now, let's check what we can access
    print("To use this script:")
    print("1. Run calculations in the application")
    print("2. Export the processed DataFrame to CSV")
    print("3. Run this script with the CSV path")
    print()
    
    if processed_df_path:
        try:
            df = pd.read_csv(processed_df_path)
            print(f"Loaded DataFrame from: {processed_df_path}")
            print(f"Shape: {df.shape[0]} rows × {df.shape[1]} columns")
            print()
        except Exception as e:
            print(f"ERROR loading CSV: {e}")
            return
    
    # Alternative: Try to access from calculations widget if running in app context
    # This would need to be run from within the application
    print("Looking for enthalpy-related columns...")
    print()
    
    # Method 1: List all columns containing 'h' or 'H'
    if processed_df_path:
        all_cols = list(df.columns)
        h_cols = [col for col in all_cols if 'h' in str(col).lower() or 'H' in str(col)]
        
        print(f"Found {len(h_cols)} columns containing 'h' or 'H':")
        for col in sorted(h_cols):
            print(f"  - {col}")
        print()
        
        # Specifically look for h_3a, h_4a, etc.
        target_cols = ['h_3a', 'H_3a', 'h_4a', 'H_4a', 'h_2b', 'H_2b', 
                       'H_comp.in', 'H_comp.out', 'H_cond.out',
                       'h_4b_LH', 'h_4b_CTR', 'h_4b_RH',
                       'H_txv.lh', 'H_txv.ctr', 'H_txv.rh']
        
        print("Checking for target enthalpy columns:")
        found_cols = {}
        for target in target_cols:
            if target in all_cols:
                val = df.iloc[row_index][target] if row_index < len(df) else None
                found_cols[target] = val
                print(f"  ✓ {target}: {val}")
            else:
                # Try case-insensitive search
                matches = [col for col in all_cols if col.lower() == target.lower()]
                if matches:
                    for match in matches:
                        val = df.iloc[row_index][match] if row_index < len(df) else None
                        found_cols[match] = val
                        print(f"  ✓ {match} (case variation of {target}): {val}")
        
        print()
        
        # Show row data access patterns
        if row_index < len(df):
            row_data = df.iloc[row_index]
            print(f"Row {row_index} data access test:")
            print(f"  Type: {type(row_data)}")
            print(f"  Has .get() method: {hasattr(row_data, 'get')}")
            print(f"  Has .index: {hasattr(row_data, 'index')}")
            if hasattr(row_data, 'index'):
                print(f"  Index type: {type(row_data.index)}")
                print(f"  First 10 index values: {list(row_data.index[:10])}")
            print()
            
            # Test different access methods for h_3a
            print("Testing access methods for h_3a:")
            test_names = ['h_3a', 'H_3a', 'h_comp.out', 'H_comp.out']
            for name in test_names:
                if name in row_data.index:
                    val_get = row_data.get(name) if hasattr(row_data, 'get') else None
                    val_idx = row_data[name]
                    print(f"  {name}:")
                    print(f"    In index: Yes")
                    print(f"    .get('{name}'): {val_get}")
                    print(f"    ['{name}']: {val_idx}")
                else:
                    print(f"  {name}: Not in index")
            print()
            
            # Show all columns that might be h_3a or h_4a
            print("All columns that might be h_3a or h_4a:")
            potential_3a = [col for col in all_cols if ('3a' in str(col) or 'comp.out' in str(col).lower()) and ('h' in str(col).lower())]
            potential_4a = [col for col in all_cols if ('4a' in str(col) or 'cond.out' in str(col).lower()) and ('h' in str(col).lower())]
            
            print("  Possible h_3a columns:")
            for col in potential_3a:
                val = row_data[col] if col in row_data.index else None
                print(f"    {col}: {val}")
            
            print("  Possible h_4a columns:")
            for col in potential_4a:
                val = row_data[col] if col in row_data.index else None
                print(f"    {col}: {val}")
    
    print()
    print("=" * 80)
    print("To use in application:")
    print("1. Add this debug code to calculations_widget.py generate_audit_text()")
    print("2. Print all columns at start of Section 6")
    print("3. Find the actual column names being used")
    print("=" * 80)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
        row_idx = int(sys.argv[2]) if len(sys.argv) > 2 else 16
        debug_enthalpy_columns(csv_path, row_idx)
    else:
        print("Usage: python debug_enthalpy_columns.py <processed_df.csv> [row_index]")
        print("Example: python debug_enthalpy_columns.py calculated_results.csv 16")
        debug_enthalpy_columns()

