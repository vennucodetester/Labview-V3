#!/usr/bin/env python3
"""
Quick test to verify the enhanced process diagram renders correctly.
This creates a standalone window showing the enhanced process diagram.
"""

from PyQt6.QtWidgets import QApplication
from process_diagram_audit_widget import ProcessDiagramAuditWidget
import sys

# Sample test data
test_row_data = {
    '1_evap_inlet': {'t': 35, 'p': 45, 'sh': 0, 'sc': None},
    '2_evap_outlet': {'t': 45, 'p': 47, 'sh': 10, 'sc': None},
    '3_comp_inlet': {'t': 47, 'p': 48, 'sh': 12, 'sc': None},
    '4_comp_outlet': {'t': 135, 'p': 320, 'sh': 50, 'sc': None},
    '5_cond_outlet': {'t': 92, 'p': 315, 'sh': None, 'sc': 5},
    '6_txv_outlet': {'t': 35, 'p': 45, 'sh': 0, 'sc': None},
}

if __name__ == '__main__':
    app = QApplication(sys.argv)

    print("=" * 60)
    print("ENHANCED PROCESS DIAGRAM TEST")
    print("=" * 60)
    print("\nYou should see:")
    print("  ✓ Compressor with rotor blades and rotation arrow")
    print("  ✓ Heat exchangers with tube lines and fins")
    print("  ✓ TXV with brass actuator on top")
    print("  ✓ Drop shadows under all components")
    print("  ✓ Temperature-colored accent strips")
    print("  ✓ State labels with gradient backgrounds")
    print("  ✓ Export button in the header")
    print("\nClick the 'Export' button to save as PDF/SVG to verify vector quality!")
    print("=" * 60)

    # Create the enhanced widget
    widget = ProcessDiagramAuditWidget(test_row_data)
    widget.setWindowTitle("Enhanced Process Diagram Test - LH Circuit")
    widget.resize(900, 350)
    widget.show()

    sys.exit(app.exec())
