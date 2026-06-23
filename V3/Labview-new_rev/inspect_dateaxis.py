#!/usr/bin/env python3
import inspect
import pyqtgraph as pg
from datetime import datetime
from time import gmtime
import time as time_mod

# Get DateAxisItem source
source_lines = inspect.getsource(pg.DateAxisItem).split('\n')

print("=" * 80)
print("DateAxisItem source inspection")
print("=" * 80)

# Find key methods
found_methods = {
    'tickStrings': [],
    'utcfromtimestamp': [],
    'strftime': [],
}

for i, line in enumerate(source_lines):
    if any(method in line for method in found_methods.keys()):
        found_methods[[m for m in found_methods.keys() if m in line][0]].append(i)

# Print relevant sections
print("\nFull tickStrings method:")
for i, line in enumerate(source_lines):
    if 'def tickStrings' in line:
        # Print the full method
        indent_level = len(line) - len(line.lstrip())
        for j in range(i, min(i + 30, len(source_lines))):
            current_indent = len(source_lines[j]) - len(source_lines[j].lstrip())
            if j > i and source_lines[j].strip() and current_indent <= indent_level:
                break
            print(f"{j}: {source_lines[j]}")
        break

print("\n" + "=" * 80)
print("Testing DateAxisItem behavior")
print("=" * 80)

# Create a DateAxisItem and test its methods
axis = pg.DateAxisItem()
print(f"\nDefault utcOffset: {axis.utcOffset}")

# Test tickStrings method
test_values = [1744524152]  # Our CSV timestamp as raw Unix
test_strings = axis.tickStrings(test_values, axis, None)
print(f"\nTest Unix timestamp: {test_values[0]}")
print(f"DateAxisItem.tickStrings output: {test_strings}")

# What time is that?
print(f"Unix to UTC: {datetime.utcfromtimestamp(test_values[0])}")
print(f"Unix to local: {datetime.fromtimestamp(test_values[0])}")

# Now test with adjusted value
test_values2 = [1744542152]  # CSV + offset
test_strings2 = axis.tickStrings(test_values2, axis, None)
print(f"\nTest Unix timestamp: {test_values2[0]} (CSV + 18000)")
print(f"DateAxisItem.tickStrings output: {test_strings2}")
print(f"Unix to UTC: {datetime.utcfromtimestamp(test_values2[0])}")
print(f"Unix to local: {datetime.fromtimestamp(test_values2[0])}")
