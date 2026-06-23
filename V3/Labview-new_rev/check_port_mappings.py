"""
check_port_mappings.py

Analyzes a saved .json configuration file and checks if all required ports
for 8-point cycle calculations are properly mapped to CSV columns.

Usage:
    python check_port_mappings.py your_config.json

This script will:
    1. Load your .json file
    2. Check which ports are mapped
    3. Tell you what's missing
    4. Show you exactly what to map
"""

import json
import sys
import os

def print_header(title):
    """Print a nice header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)

def print_section(title):
    """Print a section title."""
    print(f"\n{title}:")
    print("-" * 80)

def check_port_mappings(json_file):
    """
    Analyze the JSON file and check if all required ports are mapped.
    
    Args:
        json_file: Path to the .json configuration file
    
    Returns:
        True if all required ports are mapped, False otherwise
    """
    
    print_header("PORT MAPPING ANALYSIS")
    
    # Load JSON file
    print(f"\n📂 Loading: {json_file}")
    
    if not os.path.exists(json_file):
        print(f"❌ ERROR: File not found: {json_file}")
        return False
    
    try:
        with open(json_file, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ ERROR: Could not load JSON file: {e}")
        return False
    
    print("✅ JSON file loaded successfully")
    
    # Get components and sensor roles
    # Try different JSON formats
    components = data.get('components', {})
    sensor_roles = data.get('sensor_roles', {})
    
    if not components:
        # Try diagramModel format
        components = data.get('diagramModel', {}).get('components', {})
        sensor_roles = data.get('diagramModel', {}).get('sensor_roles', {})
    
    if not components:
        # Try old diagram format
        components = data.get('diagram', {}).get('components', {})
        sensor_roles = data.get('diagram', {}).get('sensor_roles', {})
    
    if not components:
        print("❌ ERROR: No components found in diagram")
        return False
    
    print(f"✅ Found {len(components)} components in diagram")
    print(f"✅ Found {len(sensor_roles)} sensor mappings")
    
    # Define required mappings for 8-point cycle
    required_mappings = {
        'critical': [],  # Must have
        'recommended': [],  # Should have
        'optional': []  # Nice to have
    }
    
    # Find components and build requirements
    compressor_id = None
    condenser_id = None
    txv_ids = []
    evaporator_ids = []
    
    for comp_id, comp in components.items():
        comp_type = comp.get('type')
        
        if comp_type == 'Compressor':
            compressor_id = comp_id
        elif comp_type == 'Condenser':
            condenser_id = comp_id
        elif comp_type == 'TXV':
            txv_ids.append(comp_id)
        elif comp_type == 'Evaporator':
            evaporator_ids.append(comp_id)
    
    # Build requirements based on found components
    if compressor_id:
        # Check for Suction Pressure (inline Sensor or legacy Compressor.SP)
        from port_resolver import find_sensor_by_measurement_type
        sp_comp_id, _ = find_sensor_by_measurement_type(model, 'Suction Pressure')
        if not sp_comp_id:
            required_mappings['critical'].append({
                'role_key': f'Compressor.{compressor_id}.SP',
                'label': 'Suction Pressure (inline Sensor or Compressor SP)',
                'description': 'Low-side pressure for ON-time filtering and calculations. Place an inline Sensor with type "Suction Pressure".',
                'example_csv': 'Suction Presure'
            })
        # Check for Discharge Pressure (inline Sensor or legacy Compressor.DP)
        dp_comp_id, _ = find_sensor_by_measurement_type(model, 'Discharge Pressure')
        if not dp_comp_id:
            required_mappings['critical'].append({
                'role_key': f'Compressor.{compressor_id}.DP',
                'label': 'Discharge Pressure (inline Sensor or Compressor DP)',
                'description': 'High-side pressure for calculations. Place an inline Sensor with type "Discharge Pressure".',
                'example_csv': 'Liquid Pressure'
            })
        required_mappings['critical'].append({
            'role_key': f'Compressor.{compressor_id}.inlet',
            'label': 'Compressor Inlet Temperature',
            'description': 'State 2b - Compressor inlet temp for superheat and mass flow',
            'example_csv': 'Suction line into Comp'
        })
        required_mappings['critical'].append({
            'role_key': f'Compressor.{compressor_id}.outlet',
            'label': 'Compressor Outlet Temperature',
            'description': 'State 3a - Compressor discharge temp for superheat',
            'example_csv': 'Discharge line from comp'
        })
        required_mappings['critical'].append({
            'role_key': f'Compressor.{compressor_id}.RPM',
            'label': 'Compressor Speed (RPM)',
            'description': 'Compressor speed for mass flow rate calculation',
            'example_csv': 'Compressor RPM'
        })
    
    if condenser_id:
        required_mappings['recommended'].append({
            'role_key': f'Condenser.{condenser_id}.outlet',
            'label': 'Condenser Outlet Temperature',
            'description': 'State 4a - Condenser outlet temp for subcooling',
            'example_csv': 'Case inlet after filter drier'
        })
        required_mappings['optional'].append({
            'role_key': f'Condenser.{condenser_id}.inlet',
            'label': 'Condenser Inlet Temperature',
            'description': 'State 3b - Condenser inlet temp (optional)',
            'example_csv': '(Not typically available in CSV)'
        })
    
    for txv_id in txv_ids:
        comp = components[txv_id]
        label = comp.get('properties', {}).get('circuit_label', 'Unknown')
        required_mappings['critical'].append({
            'role_key': f'TXV.{txv_id}.inlet',
            'label': f'TXV Inlet Temperature ({label})',
            'description': f'State 4b - TXV inlet temp for subcooling ({label} circuit)',
            'example_csv': f'{label} TXV Inlet' if label != 'Unknown' else 'TXV Inlet'
        })
    
    for evap_id in evaporator_ids:
        comp = components[evap_id]
        label = comp.get('properties', {}).get('circuit_label', 'Unknown')
        circuits = comp.get('properties', {}).get('circuits', 1)
        
        for i in range(1, circuits + 1):
            required_mappings['critical'].append({
                'role_key': f'Evaporator.{evap_id}.outlet_circuit_{i}',
                'label': f'Evaporator Outlet Temperature ({label} Circuit {i})',
                'description': f'State 2a - Evaporator outlet temp for superheat ({label})',
                'example_csv': f'{label} Coil Out {i}' if label != 'Unknown' else f'Coil Out {i}'
            })
    
    # Check which mappings are present
    print_section("CRITICAL MAPPINGS (Required for calculations)")
    critical_missing = []
    for req in required_mappings['critical']:
        role_key = req['role_key']
        mapped_sensor = sensor_roles.get(role_key)
        
        if mapped_sensor:
            print(f"✅ {req['label']}")
            print(f"   Mapped to: \"{mapped_sensor}\"")
        else:
            print(f"❌ {req['label']}")
            print(f"   NOT MAPPED - {req['description']}")
            print(f"   Example CSV column: \"{req['example_csv']}\"")
            critical_missing.append(req)
    
    print_section("RECOMMENDED MAPPINGS (Should have for complete analysis)")
    recommended_missing = []
    for req in required_mappings['recommended']:
        role_key = req['role_key']
        mapped_sensor = sensor_roles.get(role_key)
        
        if mapped_sensor:
            print(f"✅ {req['label']}")
            print(f"   Mapped to: \"{mapped_sensor}\"")
        else:
            print(f"⚠️  {req['label']}")
            print(f"   NOT MAPPED - {req['description']}")
            print(f"   Example CSV column: \"{req['example_csv']}\"")
            recommended_missing.append(req)
    
    print_section("OPTIONAL MAPPINGS (Nice to have)")
    for req in required_mappings['optional']:
        role_key = req['role_key']
        mapped_sensor = sensor_roles.get(role_key)
        
        if mapped_sensor:
            print(f"✅ {req['label']}")
            print(f"   Mapped to: \"{mapped_sensor}\"")
        else:
            print(f"ℹ️  {req['label']}")
            print(f"   NOT MAPPED - {req['description']}")
    
    # Summary
    print_header("SUMMARY")
    
    total_critical = len(required_mappings['critical'])
    total_recommended = len(required_mappings['recommended'])
    mapped_critical = total_critical - len(critical_missing)
    mapped_recommended = total_recommended - len(recommended_missing)
    
    print(f"\n📊 Critical Mappings: {mapped_critical}/{total_critical} mapped")
    print(f"📊 Recommended Mappings: {mapped_recommended}/{total_recommended} mapped")
    
    if not critical_missing:
        print("\n🎉 SUCCESS! All critical ports are mapped!")
        print("✅ Your configuration is ready for 8-point cycle calculations")
        
        if recommended_missing:
            print("\n💡 TIP: Consider mapping recommended ports for complete analysis:")
            for req in recommended_missing:
                print(f"   - {req['label']}")
        
        return True
    else:
        print("\n❌ MISSING CRITICAL MAPPINGS!")
        print("⚠️  You need to map these ports before calculations will work:\n")
        
        for i, req in enumerate(critical_missing, 1):
            print(f"{i}. {req['label']}")
            print(f"   Port: {req['role_key']}")
            print(f"   Map to CSV column: \"{req['example_csv']}\"")
            print(f"   Why: {req['description']}\n")
        
        print("📝 HOW TO FIX:")
        print("   1. Open your app")
        print("   2. Load this configuration file")
        print("   3. Hover over each port to see what it needs")
        print("   4. Click the port and select the CSV column")
        print("   5. Save the configuration")
        print("   6. Run this script again to verify")
        
        return False

def main():
    """Main entry point."""
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 25 + "PORT MAPPING CHECKER" + " " * 34 + "║")
    print("╚" + "=" * 78 + "╝")
    
    # Check if a JSON file was provided
    if len(sys.argv) > 1:
        json_file = sys.argv[1]
    else:
        # Default to ID6SU12WE-3.json
        json_file = "ID6SU12WE-3.json"
    
    # Check if file exists
    if not os.path.exists(json_file):
        print(f"\n❌ ERROR: File not found: {json_file}")
        print("\nUsage:")
        print("   python check_port_mappings.py [config_file.json]")
        print("\nExample:")
        print("   python check_port_mappings.py ID6SU12WE-3.json")
        print("\nAvailable .json files in current directory:")
        json_files = [f for f in os.listdir('.') if f.endswith('.json')]
        if json_files:
            for f in json_files:
                print(f"   - {f}")
        else:
            print("   (No .json files found)")
        sys.exit(1)
    
    # Run the check
    success = check_port_mappings(json_file)
    
    print("\n" + "=" * 80 + "\n")
    
    # Exit with appropriate code
    if success:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()

