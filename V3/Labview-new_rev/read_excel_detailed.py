import pandas as pd
import json

# Read the Excel file with multi-row headers
excel_path = r'c:\LAB DATA ANALYZER\GEMINI 2.0\DIAGNOSTIC TOOL\Calculations-DDT.xlsx'

# Read with first two rows as headers
df = pd.read_excel(excel_path, sheet_name=0, header=[0, 1])

print("=" * 100)
print("COMPLETE EXCEL STRUCTURE - CALCULATION OUTPUT FORMAT")
print("=" * 100)

print("\nMulti-level column structure:")
print("-" * 100)

# Extract the structure
structure = []
for col in df.columns:
    section = col[0]
    field = col[1]
    structure.append({
        'section': section,
        'field': field
    })
    print(f"Section: {section:30s} | Field: {field}")

print("\n" + "=" * 100)
print("GROUPED BY SECTION")
print("=" * 100)

current_section = None
for item in structure:
    if item['section'] != current_section and not item['section'].startswith('Unnamed'):
        current_section = item['section']
        print(f"\n## {current_section}")
        print("-" * 80)
    print(f"   - {item['field']}")

# Save to JSON
output = {
    'calculation_sections': []
}

current_section_name = None
current_fields = []

for item in structure:
    section = item['section']
    field = item['field']
    
    if not section.startswith('Unnamed'):
        # New section
        if current_section_name and current_fields:
            output['calculation_sections'].append({
                'section_name': current_section_name,
                'fields': current_fields
            })
        current_section_name = section
        current_fields = [field]
    else:
        # Same section, add field
        if current_section_name:
            current_fields.append(field)

# Add the last section
if current_section_name and current_fields:
    output['calculation_sections'].append({
        'section_name': current_section_name,
        'fields': current_fields
    })

with open('calculation_output_structure.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print("\n" + "=" * 100)
print("SUMMARY")
print("=" * 100)
print(f"Total sections: {len(output['calculation_sections'])}")
for section in output['calculation_sections']:
    print(f"  - {section['section_name']:30s} : {len(section['fields'])} fields")

print("\n" + "=" * 100)
print("Output structure saved to: calculation_output_structure.json")
print("=" * 100)
