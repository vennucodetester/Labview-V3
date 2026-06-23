#!/usr/bin/env python3
"""
Test the DateAxisItem fix with actual plotting
"""

import pandas as pd
import time

print("=" * 80)
print("TESTING DATEAXISITEM FIX")
print("=" * 80)

# Get timezone offset
if time.daylight:
    offset_sec = time.altzone
    tz_name = time.tzname[1]
else:
    offset_sec = time.timezone
    tz_name = time.tzname[0]

print(f"\nSystem timezone: {tz_name}")
print(f"Timezone offset: {offset_sec}s ({-offset_sec/3600:.0f} hours)")

# Create a simple timestamp (local time from CSV)
csv_timestamp = pd.Timestamp('2025-04-13 06:02:32')
print(f"\nCSV shows (local time): {csv_timestamp}")

# Raw Unix conversion (old, wrong method)
print(f"\n--- OLD METHOD (WRONG) ---")
unix_raw = int(csv_timestamp.value // 10**9)
print(f"Treating CSV as UTC, Unix: {unix_raw}")
print(f"DateAxisItem calculates: utcfromtimestamp({unix_raw} - {offset_sec}) = {pd.to_datetime(unix_raw - offset_sec, unit='s')}")
print(f"  This is WRONG - shows {pd.to_datetime(unix_raw - offset_sec, unit='s')} instead of {csv_timestamp}")

# FIXED method: Convert local to UTC first
print(f"\n--- NEW METHOD (FIXED) ---")
# CSV time is local, add offset to convert to UTC
# offset_sec is positive for west of UTC, so UTC = Local + offset_sec
utc_timestamp = csv_timestamp + pd.Timedelta(seconds=offset_sec)
print(f"Convert local to UTC: {csv_timestamp} + {offset_sec}s (5 hours) = {utc_timestamp}")

# Now convert this UTC time to Unix
unix_fixed = int(utc_timestamp.value // 10**9)
print(f"UTC timestamp as Unix: {unix_fixed}")

# What does DateAxisItem display?
displayed = pd.to_datetime(unix_fixed - offset_sec, unit='s')
print(f"DateAxisItem calculates: utcfromtimestamp({unix_fixed} - {offset_sec}) = {displayed}")
print(f"This should equal CSV time: {displayed == csv_timestamp}")

# Verify
if displayed == csv_timestamp:
    print("\n✅ FIX WORKS! DateAxisItem will display correct time")
    print(f"   CSV shows: {csv_timestamp}")
    print(f"   Graph shows: {displayed}")
else:
    print(f"\n❌ FIX FAILED!")
    print(f"   Expected: {csv_timestamp}")
    print(f"   Got: {displayed}")

print("\n" + "=" * 80)
