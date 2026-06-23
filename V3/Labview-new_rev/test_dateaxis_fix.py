#!/usr/bin/env python3
"""
Test the DateAxisItem fix with actual plotting
"""

import pandas as pd
import pyqtgraph as pg
from pyqtgraph import PlotWidget
import time
import sys

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

# Create a simple timestamp
csv_timestamp = pd.Timestamp('2025-04-13 06:02:32')
print(f"\nCSV shows: {csv_timestamp}")

# Raw Unix conversion (old, wrong method)
unix_raw = int(csv_timestamp.value // 10**9)
print(f"\nOLD METHOD (raw Unix): {unix_raw}")
print(f"  What DateAxisItem displays: {pd.to_datetime(unix_raw - offset_sec, unit='s')}")
print(f"  (This is WRONG - shifted backward)")

# Fixed Unix conversion
unix_fixed = unix_raw - offset_sec
print(f"\nFIXED METHOD (adjusted Unix): {unix_fixed}")
print(f"  What DateAxisItem displays: {pd.to_datetime(unix_fixed - offset_sec, unit='s')}")
print(f"  (This should match CSV: {csv_timestamp})")

# Verify
display_time = pd.to_datetime(unix_fixed - offset_sec, unit='s')
if display_time == csv_timestamp:
    print("\n✅ FIX WORKS! DateAxisItem will display correct time")
else:
    print(f"\n❌ FIX FAILED!")
    print(f"   Expected: {csv_timestamp}")
    print(f"   Got: {display_time}")

print("\n" + "=" * 80)

# Now test with actual pyqtgraph if running GUI is available
try:
    from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout
    
    app = QApplication.instance()
    if app is None:
        print("\nCreating Qt application for visual test...")
        app = QApplication(sys.argv)
    
    # Create test window
    print("Creating test window with DateAxisItem...")
    plot_widget = pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem()})
    plot_widget.setTitle("Timestamp Display Test")
    plot_widget.getAxis('bottom').setLabel('Time (should show 2025-04-13 06:02:32)')
    plot_widget.getAxis('left').setLabel('Value')
    
    # Plot both methods for comparison
    x_old = [unix_raw]
    x_fixed = [unix_fixed]
    y = [42.0]
    
    pen_old = pg.mkPen(color='red', width=2)
    pen_fixed = pg.mkPen(color='green', width=2)
    
    plot_widget.plot(x_old, y, pen=pen_old, symbol='o', symbolSize=10, name='OLD (wrong)')
    plot_widget.plot(x_fixed, y, pen=pen_fixed, symbol='s', symbolSize=10, name='FIXED (correct)')
    
    plot_widget.addLegend()
    plot_widget.resize(800, 400)
    plot_widget.show()
    
    print("Window opened. Check the X-axis label:")
    print(f"  - Red point (old method) should be at 01:02:32")
    print(f"  - Green point (fixed method) should be at 06:02:32")
    print("\nClose the window to exit...")
    
    # Only run event loop if not in testing mode
    if '--no-gui' not in sys.argv:
        sys.exit(app.exec_())
    
except Exception as e:
    print(f"\nCould not create GUI test: {e}")
    print("(This is OK if running in headless environment)")
