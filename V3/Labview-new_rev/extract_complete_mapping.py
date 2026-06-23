import pandas as pd
import json

# Read the Excel file properly
excel_path = r'c:\LAB DATA ANALYZER\GEMINI 2.0\DIAGNOSTIC TOOL\Calculations-DDT.xlsx'

# Read without treating any row as header first
df_raw = pd.read_excel(excel_path, sheet_name=0, header=None)

print("=" * 100)
print("COMPLETE CALCULATION OUTPUT STRUCTURE")
print("=" * 100)

# Row 0 contains section headers (merged cells)
# Row 1 contains field labels
# Row 2 contains sensor mappings

row0 = df_raw.iloc[0].tolist()  # Section headers
row1 = df_raw.iloc[1].tolist()  # Field labels  
row2 = df_raw.iloc[2].tolist() if len(df_raw) > 2 else []  # Sensor labels

print("\nComplete Column Mapping:")
print("-" * 100)

complete_structure = []
current_section = None

for i, (section, field, sensor) in enumerate(zip(row0, row1, row2)):
    # Update current section when we hit a non-NaN section header
    if pd.notna(section) and str(section).strip():
        current_section = str(section).strip()
    
    field_str = str(field).strip() if pd.notna(field) else ""
    sensor_str = str(sensor).strip() if pd.notna(sensor) else ""
    
    entry = {
        'column_index': i,
        'section': current_section,
        'field': field_str,
        'sensor_label': sensor_str
    }
    complete_structure.append(entry)
    
    print(f"{i:3d} | {current_section:25s} | {field_str:20s} | {sensor_str}")

# Group by section
print("\n" + "=" * 100)
print("GROUPED BY SECTION WITH SENSOR MAPPINGS")
print("=" * 100)

sections = {}
for entry in complete_structure:
    section = entry['section']
    if section not in sections:
        sections[section] = []
    sections[section].append({
        'field': entry['field'],
        'sensor_label': entry['sensor_label']
    })

for section_name, fields in sections.items():
    print(f"\n### {section_name}")
    print("-" * 80)
    for field_info in fields:
        field = field_info['field']
        sensor = field_info['sensor_label']
        if sensor and sensor != 'nan':
            print(f"  {field:25s} → {sensor}")
        else:
            print(f"  {field:25s} (calculated)")

# Save complete structure
output = {
    'title': 'Refrigeration System Calculation Output Structure',
    'description': 'Complete mapping of calculation sections, fields, and sensor labels',
    'sections': []
}

for section_name, fields in sections.items():
    if section_name and section_name != 'None':
        section_data = {
            'section_name': section_name,
            'fields': []
        }
        for field_info in fields:
            if field_info['field'] and field_info['field'] != 'nan':
                section_data['fields'].append({
                    'field_name': field_info['field'],
                    'sensor_label': field_info['sensor_label'] if field_info['sensor_label'] != 'nan' else None,
                    'is_calculated': field_info['sensor_label'] == 'nan' or not field_info['sensor_label']
                })
        if section_data['fields']:
            output['sections'].append(section_data)

with open('complete_calculation_structure.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print("\n" + "=" * 100)
print("SUMMARY")
print("=" * 100)
print(f"Total sections: {len(output['sections'])}")
for section in output['sections']:
    sensor_count = sum(1 for f in section['fields'] if not f['is_calculated'])
    calc_count = sum(1 for f in section['fields'] if f['is_calculated'])
    print(f"  {section['section_name']:30s} : {len(section['fields'])} fields ({sensor_count} sensors, {calc_count} calculated)")

print("\n" + "=" * 100)
print("Complete structure saved to: complete_calculation_structure.json")
print("=" * 100)
