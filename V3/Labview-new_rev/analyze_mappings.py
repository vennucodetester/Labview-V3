#!/usr/bin/env python3
"""
Simple analysis of ID6SU12WE-4.json to see what's actually mapped
and compare with what we need for calculations.
"""

import json

def analyze_mappings():
    print("🔍 ANALYZING ID6SU12WE-4.json MAPPINGS")
    print("=" * 60)
    
    # Load the JSON
    with open('ID6SU12WE-4.json', 'r') as f:
        data = json.load(f)
    
    # Get sensor roles
    sensor_roles = data.get('diagramModel', {}).get('sensor_roles', {})
    
    print(f"📊 Total mappings found: {len(sensor_roles)}")
    print()
    
    # What we need for 8-point cycle calculations
    required_mappings = {
        # Compressor
        "compressor_a91fd4.SP": "Suction Pressure",
        "compressor_a91fd4.DP": "Discharge Pressure", 
        "compressor_a91fd4.RPM": "Compressor RPM",
        "compressor_a91fd4.inlet": "Suction line into Comp",
        "compressor_a91fd4.outlet": "Discharge line from Comp",
        
        # TXV
        "txv_18e195.inlet": "TXV Inlet Temperature",
        
        # Condenser
        "condenser_fba9eb.outlet": "Condenser Outlet Temperature",
        
        # Evaporator outlets (for superheat)
        "evaporator_3408df.outlet_circuit_1": "Left Circuit 1 Outlet",
        "evaporator_3408df.outlet_circuit_2": "Left Circuit 2 Outlet", 
        "evaporator_3408df.outlet_circuit_3": "Left Circuit 3 Outlet",
        "evaporator_3408df.outlet_circuit_4": "Left Circuit 4 Outlet",
        "evaporator_3408df.outlet_circuit_5": "Left Circuit 5 Outlet",
        "evaporator_3408df.outlet_circuit_6": "Left Circuit 6 Outlet",
        "evaporator_5b2824.outlet_circuit_1": "Center Circuit 1 Outlet",
        "evaporator_5b2824.outlet_circuit_2": "Center Circuit 2 Outlet",
        "evaporator_5b2824.outlet_circuit_3": "Center Circuit 3 Outlet", 
        "evaporator_5b2824.outlet_circuit_4": "Center Circuit 4 Outlet",
        "evaporator_5b2824.outlet_circuit_5": "Center Circuit 5 Outlet",
        "evaporator_5b2824.outlet_circuit_6": "Center Circuit 6 Outlet",
        "evaporator_3e6d38.outlet_circuit_1": "Right Circuit 1 Outlet",
        "evaporator_3e6d38.outlet_circuit_2": "Right Circuit 2 Outlet",
        "evaporator_3e6d38.outlet_circuit_3": "Right Circuit 3 Outlet",
        "evaporator_3e6d38.outlet_circuit_4": "Right Circuit 4 Outlet", 
        "evaporator_3e6d38.outlet_circuit_5": "Right Circuit 5 Outlet",
        "evaporator_3e6d38.outlet_circuit_6": "Right Circuit 6 Outlet"
    }
    
    print("🎯 CHECKING CRITICAL MAPPINGS:")
    print("-" * 40)
    
    found_mappings = {}
    missing_mappings = []
    
    for port_key, description in required_mappings.items():
        if port_key in sensor_roles:
            csv_column = sensor_roles[port_key]
            found_mappings[port_key] = csv_column
            print(f"✅ {port_key}")
            print(f"   → {csv_column}")
            print(f"   → {description}")
        else:
            missing_mappings.append(port_key)
            print(f"❌ {port_key}")
            print(f"   → NOT MAPPED")
            print(f"   → {description}")
        print()
    
    print("📋 SUMMARY:")
    print("-" * 20)
    print(f"✅ Found: {len(found_mappings)}")
    print(f"❌ Missing: {len(missing_mappings)}")
    print(f"📊 Total Required: {len(required_mappings)}")
    
    if missing_mappings:
        print(f"\n🚨 MISSING CRITICAL MAPPINGS:")
        for port in missing_mappings:
            print(f"   - {port}")
    
    print(f"\n🔍 ALL ACTUAL MAPPINGS:")
    print("-" * 30)
    for port, csv_col in sensor_roles.items():
        print(f"{port} → {csv_col}")
    
    return found_mappings, missing_mappings

if __name__ == "__main__":
    analyze_mappings()


