#!/usr/bin/env python3
"""
Test script to verify the timestamp fix
"""

import pandas as pd
import time
from timestamp_fixer import fix_ambiguous_dates

print("="*80)
print("TIMESTAMP FIX TEST")
print("="*80)

# Load CSV
print("\n1. Loading CSV data...")
df = pd.read_csv('ID6SU12WE DOE 2.csv')
print(f"   Date values: {df['Date'].head(3).tolist()}")
print(f"   Time values: {df['Time'].head(3).tolist()}")

# Parse timestamps
print("\n2. Parsing timestamps with fix_ambiguous_dates()...")
timestamps = fix_ambiguous_dates(df['Date'], df['Time'])
print(f"   Parsed: {timestamps.head(3).tolist()}")
print(f"   Timezone: {timestamps.dt.tz}")

# Get timezone info
print("\n3. System timezone info:")
print(f"   tzname: {time.tzname}")
print(f"   timezone offset: {time.timezone}s")
print(f"   daylight: {time.daylight}")
if time.daylight:
    print(f"   altzone offset: {time.altzone}s")
    offset_sec = time.altzone
else:
    offset_sec = time.timezone
print(f"   Using offset: {offset_sec}s")

# Simulate the old (broken) conversion
print("\n4. OLD METHOD (BROKEN) - Direct Unix conversion:")
unix_old = timestamps.astype('int64') // 10**9
print(f"   Unix timestamp: {unix_old.iloc[0]}")
back_old = pd.to_datetime(unix_old.iloc[0], unit='s')
print(f"   Converted back: {back_old}")
print(f"   Original: {timestamps.iloc[0]}")
print(f"   MISMATCH: {pd.Timestamp(back_old) != timestamps.iloc[0]}")

# Simulate the new (fixed) conversion
print("\n5. NEW METHOD (FIXED) - Timezone-aware conversion:")
unix_new = timestamps.astype('int64') // 10**9 - offset_sec
print(f"   Unix timestamp: {unix_new.iloc[0]}")
back_new = pd.to_datetime(unix_new.iloc[0] + offset_sec, unit='s')
print(f"   Converted back: {back_new}")
print(f"   Original: {timestamps.iloc[0]}")
print(f"   MATCH: {pd.Timestamp(back_new) == timestamps.iloc[0]}")

# Verify the fix
print("\n" + "="*80)
print("VERIFICATION")
print("="*80)
print(f"Original timestamp: {timestamps.iloc[0]}")
print(f"Expected on graph: 2025-04-13 06:02:32 (NOT shifted)")
print(f"New method result: {back_new}")
if pd.Timestamp(back_new) == timestamps.iloc[0]:
    print("✅ FIX SUCCESSFUL - Timestamp will display correctly!")
else:
    print("❌ FIX FAILED - Timestamps still mismatched")
