# -*- coding: utf-8 -*-
"""
Plots the R290 P-h diagram for the LH, CTR, and RH circuits
by loading and analyzing the 'audit_export.csv' file.

This version manually draws the saturation dome to bypass
CoolProp.Plots errors on newer Python versions (like 3.13).
"""

import matplotlib.pyplot as plt
import CoolProp.CoolProp as CP
# from CoolProp.Plots import PropertyPlot  # <-- REMOVED: Bypassing this buggy module
import sys
import pandas as pd
import numpy as np
import os # Import os to check path

# --- Helper Functions from your methodology ---

def fahrenheit_to_kelvin(temp_f):
    """Converts Fahrenheit to Kelvin"""
    return (temp_f - 32.0) / 1.8 + 273.15

def psig_to_pa_abs(psig):
    """Converts gauge pressure (psig) to absolute pressure (Pascals)"""
    # Use standard atmospheric pressure (14.696 psi, not 14.7) for better accuracy
    return (psig + 14.696) * 6894.757

# --- Main Calculation Function ---

def load_and_calculate_data(csv_file='audit_export.csv', pressure_threshold=85):
    """
    Loads the CSV, filters for 'On Time' data, and calculates the
    average enthalpy for all state points.
    """
    print(f"Loading data from '{csv_file}'...")
    if not os.path.exists(csv_file):
        print(f"Error: '{csv_file}' not found in the directory.")
        print(f"Current directory is: {os.getcwd()}")
        print("Please make sure the CSV file is in the same folder as this script.")
        return None, None
        
    try:
        df_full = pd.read_csv(csv_file)
    except Exception as e:
        print(f"Error loading CSV: {e}")
        return None, None

    # 1. Filter for "On Time" data
    # Check for trailing spaces in column names
    liquid_pressure_col = 'Liquid Pressure '
    suction_pressure_col = 'Suction Presure '
    
    if liquid_pressure_col not in df_full.columns:
        print(f"Error: Column '{liquid_pressure_col}' not found in CSV.")
        print(f"Available columns: {df_full.columns.to_list()}")
        return None, None

    df_on_time = df_full[df_full[liquid_pressure_col] >= pressure_threshold].copy()
    if df_on_time.empty:
        print(f"Error: No 'On Time' data found with Liquid Pressure >= {pressure_threshold} psig.")
        return None, None
    
    print(f"Successfully filtered 'On Time' data ({len(df_on_time)} rows). Calculating averages...")

    # 2. Calculate Average Pressures (Pascals) and Temperatures (Kelvin)
    # Use .strip() on column names just in case
    P_suc_pa = psig_to_pa_abs(df_on_time['Suction Presure '].mean())
    P_cond_pa = psig_to_pa_abs(df_on_time['Liquid Pressure '].mean())

    T_2b_K = fahrenheit_to_kelvin(df_on_time['Suction line into Comp'].mean())
    T_3a_K = fahrenheit_to_kelvin(df_on_time['Discharge line from comp'].mean())
    T_3b_K = fahrenheit_to_kelvin(df_on_time['Ref Temp in HeatX'].mean())
    T_4a_K = fahrenheit_to_kelvin(df_on_time['Ref Temp out HeatX'].mean())

    T_2a_LH_K = fahrenheit_to_kelvin(df_on_time['Left TXV Bulb'].mean())
    T_2a_CTR_K = fahrenheit_to_kelvin(df_on_time['CTR TXV Bulb'].mean())
    T_2a_RH_K = fahrenheit_to_kelvin(df_on_time['Right TXV Bulb '].mean())

    T_4b_LH_K = fahrenheit_to_kelvin(df_on_time['Left TXV Inlet'].mean())
    T_4b_CTR_K = fahrenheit_to_kelvin(df_on_time['CTR TXV Inlet'].mean())
    T_4b_RH_K = fahrenheit_to_kelvin(df_on_time['Right TXV Inlet '].mean())

    # 3. Calculate Enthalpies using CoolProp (and convert J/kg to kJ/kg)
    print("Calculating enthalpies with CoolProp...")
    try:
        common_points = {
            'P_suc_pa': P_suc_pa,
            'P_cond_pa': P_cond_pa,
            'h_2b': CP.PropsSI('H', 'T', T_2b_K, 'P', P_suc_pa, 'R290') / 1000,
            'h_3a': CP.PropsSI('H', 'T', T_3a_K, 'P', P_cond_pa, 'R290') / 1000,
            'h_3b': CP.PropsSI('H', 'T', T_3b_K, 'P', P_cond_pa, 'R290') / 1000,
            'h_4a': CP.PropsSI('H', 'T', T_4a_K, 'P', P_cond_pa, 'R290') / 1000,
        }
        
        circuit_points = {
            'LH': {
                'h_2a': CP.PropsSI('H', 'T', T_2a_LH_K, 'P', P_suc_pa, 'R290') / 1000,
                'h_4b': CP.PropsSI('H', 'T', T_4b_LH_K, 'P', P_cond_pa, 'R290') / 1000,
            },
            'CTR': {
                'h_2a': CP.PropsSI('H', 'T', T_2a_CTR_K, 'P', P_suc_pa, 'R290') / 1000,
                'h_4b': CP.PropsSI('H', 'T', T_4b_CTR_K, 'P', P_cond_pa, 'R290') / 1000,
            },
            'RH': {
                'h_2a': CP.PropsSI('H', 'T', T_2a_RH_K, 'P', P_suc_pa, 'R290') / 1000,
                'h_4b': CP.PropsSI('H', 'T', T_4b_RH_K, 'P', P_cond_pa, 'R290') / 1000,
            }
        }
        print("Calculations complete.")
        return common_points, circuit_points

    except Exception as e:
        print(f"Error during CoolProp calculation. Is CoolProp installed?")
        print(f"Details: {e}")
        return None, None


def plot_refrigeration_cycles(common_points, circuit_points):
    """
    Plots the R290 P-h diagram for the LH, CTR, and RH circuits
    using calculated data.
    """
    
    # --- Extract data from the calculated dictionaries ---
    P_suc_pa = common_points['P_suc_pa']
    P_cond_pa = common_points['P_cond_pa']
    
    h_2b = common_points['h_2b']
    h_3a = common_points['h_3a']
    h_3b = common_points['h_3b']
    h_4a = common_points['h_4a']
    
    h_2a_LH = circuit_points['LH']['h_2a']
    h_4b_LH = circuit_points['LH']['h_4b']
    
    h_2a_CTR = circuit_points['CTR']['h_2a']
    h_4b_CTR = circuit_points['CTR']['h_4b']
    
    h_2a_RH = circuit_points['RH']['h_2a']
    h_4b_RH = circuit_points['RH']['h_4b']
    # ----------------------------------------------------

    print("Data loaded. Initializing MANUAL P-h diagram for R290...")

    # 1. Initialize a manual Matplotlib plot
    fig, ax = plt.subplots(figsize=(12, 8))
    
    # 2. Manually calculate and plot the saturation dome
    try:
        crit_press = CP.PropsSI('Pcrit', 'R290')
        min_press = CP.PropsSI('Pmin', 'R290') + 1000 # Start slightly above min
        
        # Create a logarithmic array of pressures from min to just below critical
        p_bubble = np.geomspace(min_press, crit_press * 0.999, 100) 
        
        h_L = [CP.PropsSI('H', 'P', p, 'Q', 0, 'R290') / 1000 for p in p_bubble]
        h_V = [CP.PropsSI('H', 'P', p, 'Q', 1, 'R290') / 1000 for p in p_bubble]
        
        # Plot the dome
        ax.plot(h_L, p_bubble, 'k', linewidth=2, label='Saturation Dome (Liquid)')
        ax.plot(h_V, p_bubble, 'k', linewidth=2, label='Saturation Dome (Vapor)')
        
    except Exception as e:
        print(f"Error: Could not manually calculate saturation dome. Is CoolProp installed?")
        print(f"Details: {e}")
        return

    # 3. Set plot scales and labels
    ax.set_yscale('log')
    ax.set_xlabel('Enthalpy (h) [kJ/kg]', fontsize=12)
    ax.set_ylabel('Pressure (P) [Pa]', fontsize=12)
    ax.grid(True, which='both', linestyle='--', linewidth=0.5)
    
    print("Plot background generated. Plotting cycles...")

    # 4. Define the 8-point cycle paths for each circuit
    
    print("Plot background generated. Plotting cycles...")

    # 3. Define the 8-point cycle paths for each circuit
    
    # --- LH Circuit Path ---
    h_cycle_lh = [h_2b, h_3a, h_3b, h_4a, h_4b_LH, h_4b_LH, h_2a_LH, h_2b]
    p_cycle_lh = [P_suc_pa, P_cond_pa, P_cond_pa, P_cond_pa, P_cond_pa, P_suc_pa, P_suc_pa, P_suc_pa]
    
    # --- CTR Circuit Path ---
    h_cycle_ctr = [h_2b, h_3a, h_3b, h_4a, h_4b_CTR, h_4b_CTR, h_2a_CTR, h_2b]
    p_cycle_ctr = [P_suc_pa, P_cond_pa, P_cond_pa, P_cond_pa, P_cond_pa, P_suc_pa, P_suc_pa, P_suc_pa]
    
    # --- RH Circuit Path ---
    h_cycle_rh = [h_2b, h_3a, h_3b, h_4a, h_4b_RH, h_4b_RH, h_2a_RH, h_2b]
    p_cycle_rh = [P_suc_pa, P_cond_pa, P_cond_pa, P_cond_pa, P_cond_pa, P_suc_pa, P_suc_pa, P_suc_pa]

    # 5. Plot the cycles
    
    # Plot LH Circuit (Blue)
    ax.plot(h_cycle_lh, p_cycle_lh, 'o-', color='blue', linewidth=2.5, markersize=8, label='LH Circuit')
    
    # Plot CTR Circuit (Green)
    ax.plot(h_cycle_ctr, p_cycle_ctr, 's-', color='green', linewidth=2.0, markersize=7, label='CTR Circuit')
    
    # Plot RH Circuit (Red)
    ax.plot(h_cycle_rh, p_cycle_rh, '^-', color='red', linewidth=2.0, markersize=7, label='RH Circuit')

    # 6. Add text labels for the common points
    ax.text(h_2b, P_suc_pa * 1.1, '2b\n(Comp Suction)', ha='center', fontsize=9)
    ax.text(h_3a, P_cond_pa * 1.1, '3a\n(Comp Discharge)', ha='center', fontsize=9)
    ax.text(h_3b, P_cond_pa * 1.1, '3b', ha='left', fontsize=9)
    ax.text(h_4a, P_cond_pa * 1.1, '4a\n(Cond Outlet)', ha='right', fontsize=9)

    # 7. Finalize Plot
    ax.set_title('R290 P-h Diagram - 3 Circuit Overlay (Calculated Average Data)', fontsize=16)
    ax.legend(loc='best', fontsize=12) # Changed to 'best'
    fig.tight_layout()
    
    # Save the plot to a file
    try:
        output_filename = "R290_PH_Diagram_Overlay.png"
        fig.savefig(output_filename)
        print("\nSuccess!")
        print(f"P-h Diagram saved as '{output_filename}' in the current directory:")
        print(os.path.join(os.getcwd(), output_filename))

    except Exception as e:
        print(f"\nError: Could not save the plot file.")
        print(f"Details: {e}")

def main():
    """
    Main function to load, calculate, and plot the data.
    """
    # Set the default encoding for stdout to handle potential print errors
    if sys.stdout.encoding != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            # This might fail in some environments like IDLE
            pass

    # This requires pandas, matplotlib, and coolprop to be installed:
    # pip install pandas matplotlib coolprop
    try:
        # 1. Load and calculate data from CSV
        common_points, circuit_points = load_and_calculate_data()
        
        # 2. If data is valid, plot it
        if common_points and circuit_points:
            plot_refrigeration_cycles(common_points, circuit_points)
        else:
            print("Could not generate plot due to data loading/calculation errors.")

    except ImportError:
        print("Error: This script requires 'pandas', 'matplotlib', and 'coolprop'.")
        print("Please install them using: pip install pandas matplotlib coolprop")
    except Exception as e:
        print(f"An unexpected error occurred in main: {e}")

if __name__ == '__main__':
    main()

