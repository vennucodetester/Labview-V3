"""
test_calculations.py

Test script for 8-point cycle calculations.
This script loads your existing configuration and tests all calculations.

Usage:
    python test_calculations.py

What it does:
    1. Loads your existing .json configuration (diagram + CSV)
    2. Runs the 8-point cycle calculations
    3. Prints detailed results
    4. Shows what's working and what's missing
"""

import sys
import os

# Make sure we can import from the current directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_manager import DataManager
from calculation_orchestrator import calculate_full_system

def print_section(title):
    """Print a section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)

def print_subsection(title):
    """Print a subsection header."""
    print(f"\n{title}:")
    print("-" * 80)

def test_calculations(json_file):
    """
    Test the 8-point cycle calculations with a loaded configuration.
    
    Args:
        json_file: Path to your .json configuration file
    """
    
    print_section("8-POINT CYCLE CALCULATION TEST")
    
    # Step 1: Create DataManager
    print("\n[1/5] Creating DataManager...")
    dm = DataManager()
    
    # Step 2: Load configuration
    print(f"[2/5] Loading configuration from: {json_file}")
    success = dm.load_session(json_file)
    
    if not success:
        print("❌ FAILED to load configuration file!")
        print(f"   Make sure the file exists: {json_file}")
        return False
    
    print(f"✅ Configuration loaded successfully")
    
    # Check if CSV data is loaded
    if dm.csv_data is None or dm.csv_data.empty:
        print("❌ No CSV data loaded!")
        print("   The configuration file may not have CSV data.")
        return False
    
    print(f"✅ CSV data loaded: {len(dm.csv_data)} rows, {len(dm.csv_data.columns)} columns")
    
    # Check if diagram has components
    components = dm.diagram_model.get('components', {})
    if not components:
        print("❌ No components in diagram!")
        print("   The configuration file may not have a diagram.")
        return False
    
    print(f"✅ Diagram loaded: {len(components)} components")
    
    # List component types
    comp_types = {}
    for comp_id, comp in components.items():
        comp_type = comp.get('type', 'Unknown')
        comp_types[comp_type] = comp_types.get(comp_type, 0) + 1
    
    print("   Component types:")
    for comp_type, count in comp_types.items():
        print(f"      - {comp_type}: {count}")
    
    # Step 3: Run calculations
    print("\n[3/5] Running 8-point cycle calculations...")
    results = calculate_full_system(dm)
    
    # Step 4: Display results
    print("\n[4/5] Analyzing results...")
    
    print_subsection("CALCULATION STATUS")
    if results['ok']:
        print("✅ Calculations completed successfully!")
    else:
        print("❌ Calculations failed or incomplete")
    
    if results['errors']:
        print("\n⚠️  ERRORS/WARNINGS:")
        for i, error in enumerate(results['errors'], 1):
            print(f"   {i}. {error}")
    else:
        print("✅ No errors")
    
    # ON-Time Filtering
    print_subsection("ON-TIME FILTERING")
    on_time = results['on_time']
    print(f"   Total rows in CSV:     {on_time['total_rows']}")
    print(f"   Rows with comp ON:     {on_time['on_rows']}")
    print(f"   % ON-time:             {on_time['percentage']:.1f}%")
    print(f"   Threshold:             {on_time['threshold_psig']} psig")
    print(f"   Filtering enabled:     {on_time['filtering_enabled']}")
    
    if on_time['percentage'] == 0:
        print("   ⚠️  WARNING: 0% ON-time - check threshold or suction pressure mapping")
    elif on_time['percentage'] == 100:
        print("   ⚠️  WARNING: 100% ON-time - threshold may be too low")
    else:
        print("   ✅ ON-time percentage looks reasonable")
    
    # State Points
    print_subsection("STATE POINTS")
    states = results['state_points']['states']
    
    state_labels = {
        '3a': 'Compressor Outlet',
        '3b': 'Condenser Inlet',
        '4a': 'Condenser Outlet',
        '4b': 'TXV Inlet',
        '1': 'Evaporator Inlet (calculated)',
        '2a': 'Evaporator Outlet',
        '2b': 'Compressor Inlet'
    }
    
    calculated_count = 0
    for state_id, label in state_labels.items():
        if state_id in states:
            state = states[state_id]
            calculated_count += 1
            print(f"\n   ✅ State {state_id}: {label}")
            print(f"      Temperature:  {state['T_F']:.1f} °F ({state['T_K']:.1f} K)")
            print(f"      Pressure:     {state['P_kPa']:.1f} kPa")
            print(f"      Enthalpy:     {state['h_kJkg']:.2f} kJ/kg")
            
            if 'superheat_F' in state:
                sh = state['superheat_F']
                if sh > 0:
                    print(f"      Superheat:    {sh:.1f} °F ✅")
                else:
                    print(f"      Superheat:    {sh:.1f} °F ⚠️ (negative!)")
            
            if 'subcooling_F' in state:
                sc = state['subcooling_F']
                if sc > 0:
                    print(f"      Subcooling:   {sc:.1f} °F ✅")
                else:
                    print(f"      Subcooling:   {sc:.1f} °F ⚠️ (negative!)")
            
            if 'quality_percent' in state:
                q = state['quality_percent']
                if 0 <= q <= 100:
                    print(f"      Vapor Quality: {q:.1f}% ✅")
                else:
                    print(f"      Vapor Quality: {q:.1f}% ⚠️ (out of range!)")
        else:
            print(f"\n   ❌ State {state_id}: {label} - NOT CALCULATED")
    
    print(f"\n   Summary: {calculated_count}/7 state points calculated")
    
    # Pressures
    print_subsection("PRESSURES")
    pressures = results['state_points']['pressures']
    print(f"   Suction Pressure:  {pressures['suction_kPa']:.1f} kPa ({pressures['suction_kPa']/6.895:.1f} psig)")
    print(f"   Liquid Pressure:   {pressures['liquid_kPa']:.1f} kPa ({pressures['liquid_kPa']/6.895:.1f} psig)")
    
    # Mass Flow Rate
    print_subsection("MASS FLOW RATE")
    if results['mass_flow']:
        mf = results['mass_flow']
        print(f"   Theoretical:")
        print(f"      {mf['theoretical_kgh']:.2f} kg/hr")
        print(f"      {mf['theoretical_kgh']*2.20462:.2f} lbs/hr")
        print(f"\n   Actual (with volumetric efficiency):")
        print(f"      {mf['actual_kgh']:.2f} kg/hr")
        print(f"      {mf['actual_lbhr']:.2f} lbs/hr")
        print(f"\n   Inputs:")
        print(f"      Compressor Speed:      {mf['inputs']['speed_rpm']:.0f} RPM")
        print(f"      Displacement:          {mf['inputs']['displacement_cm3']:.2f} cm³/rev")
        print(f"      Density (comp inlet):  {mf['inputs']['density_kgm3']:.2f} kg/m³")
        print(f"      Volumetric Efficiency: {mf['volumetric_efficiency']*100:.1f}%")
        print("   ✅ Mass flow calculated")
    else:
        print("   ❌ Mass flow NOT calculated")
        print("      Need: compressor inlet temp (T_2b), displacement, speed")
    
    # System Performance
    print_subsection("SYSTEM PERFORMANCE")
    if results['performance']:
        perf = results['performance']
        
        if 'cooling_capacity' in perf:
            cc = perf['cooling_capacity']
            print(f"   Cooling Capacity:")
            print(f"      {cc['watts']:.0f} W")
            print(f"      {cc['btu_hr']:.0f} BTU/hr")
            print(f"      {cc['tons']:.2f} tons")
            print("      ✅")
        
        if 'compressor_power' in perf:
            cp = perf['compressor_power']
            print(f"\n   Compressor Power (isentropic):")
            print(f"      {cp['watts']:.0f} W")
            print(f"      {cp['horsepower']:.2f} HP")
            print("      ✅")
        
        if 'heat_rejection' in perf:
            hr = perf['heat_rejection']
            print(f"\n   Heat Rejection:")
            print(f"      {hr['watts']:.0f} W")
            print(f"      {hr['btu_hr']:.0f} BTU/hr")
            print("      ✅")
        
        if 'efficiency' in perf:
            eff = perf['efficiency']
            print(f"\n   Efficiency:")
            cop = eff.get('cop')
            if cop:
                if 2 <= cop <= 5:
                    print(f"      COP: {cop:.2f} ✅ (typical range)")
                elif cop > 5:
                    print(f"      COP: {cop:.2f} ⚠️ (unusually high)")
                else:
                    print(f"      COP: {cop:.2f} ⚠️ (unusually low)")
            
            if 'eer' in eff:
                print(f"      EER: {eff['eer']:.2f}")
    else:
        print("   ❌ System performance NOT calculated")
        print("      Need: mass flow rate + state points")
    
    # Step 5: Summary
    print_section("TEST SUMMARY")
    
    print("\n✅ WORKING:")
    working = []
    if results['ok']:
        working.append("- Calculation engine runs without crashing")
    if on_time['percentage'] > 0 and on_time['percentage'] < 100:
        working.append("- ON-time filtering works")
    if calculated_count >= 4:
        working.append(f"- {calculated_count}/7 state points calculated")
    if results['mass_flow']:
        working.append("- Mass flow rate calculated")
    if results['performance']:
        working.append("- System performance calculated")
    
    if working:
        for item in working:
            print(item)
    else:
        print("   (Nothing working yet)")
    
    print("\n❌ NEEDS ATTENTION:")
    needs_attention = []
    if not results['ok']:
        needs_attention.append("- Calculation failed or incomplete")
    if results['errors']:
        needs_attention.append(f"- {len(results['errors'])} error(s) reported")
    if calculated_count < 4:
        needs_attention.append(f"- Only {calculated_count}/7 state points calculated")
    if not results['mass_flow']:
        needs_attention.append("- Mass flow rate not calculated")
    if not results['performance']:
        needs_attention.append("- System performance not calculated")
    if on_time['percentage'] == 0:
        needs_attention.append("- 0% ON-time (check threshold or sensor mapping)")
    
    if needs_attention:
        for item in needs_attention:
            print(item)
    else:
        print("   🎉 Everything looks good!")
    
    print("\n" + "=" * 80)
    
    return results['ok']


if __name__ == "__main__":
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "8-POINT CYCLE CALCULATION TEST" + " " * 28 + "║")
    print("╚" + "=" * 78 + "╝")
    
    # Check if a JSON file was provided as argument
    if len(sys.argv) > 1:
        json_file = sys.argv[1]
    else:
        # Default to ID6SU12WE-3.json
        json_file = "ID6SU12WE-3.json"
    
    # Check if file exists
    if not os.path.exists(json_file):
        print(f"\n❌ ERROR: File not found: {json_file}")
        print("\nUsage:")
        print("   python test_calculations.py [config_file.json]")
        print("\nExample:")
        print("   python test_calculations.py ID6SU12WE-3.json")
        print("\nAvailable .json files in current directory:")
        json_files = [f for f in os.listdir('.') if f.endswith('.json')]
        if json_files:
            for f in json_files:
                print(f"   - {f}")
        else:
            print("   (No .json files found)")
        sys.exit(1)
    
    # Run the test
    success = test_calculations(json_file)
    
    # Exit with appropriate code
    if success:
        print("\n✅ TEST PASSED - Calculations are working!")
        sys.exit(0)
    else:
        print("\n⚠️  TEST INCOMPLETE - See errors above")
        sys.exit(1)



