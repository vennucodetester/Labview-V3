"""
Input Dialog for Rated Performance Inputs

Provides a clean popup dialog for entering the 7 rated performance inputs
required for volumetric efficiency calculations.

Created as part of Goal-2 implementation to replace the confusing inputs_widget.py tab.
Updated for Goal-2C to include rated capacity and rated power.
"""

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QDoubleSpinBox,
                             QDialogButtonBox, QLabel, QGroupBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class InputDialog(QDialog):
    """
    Dialog for entering rated performance inputs and system parameters.

    This dialog collects:
    1. Rated Cooling Capacity (BTU/hr) - for validation/comparison
    2. Rated Power Consumption (W) - for COP calculations
    3. Water Flow Rate (GPM) - for water-side mass flow calculations
    """

    # Field definitions: (internal_name, user-friendly_label)
    FIELD_DEFINITIONS = [
        ('rated_capacity_btu_hr', 'Rated Cooling Capacity (BTU/hr)'),
        ('rated_power_w', 'Rated Power Consumption (W)'),
        ('gpm_water', 'Water Flow Rate (GPM)'),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Enter Rated Performance Inputs")
        self.setModal(True)
        self.setMinimumWidth(500)

        # Dictionary to store QDoubleSpinBox widgets
        self.fields = {}

        self._setup_ui()

    def _setup_ui(self):
        """Create the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Title label
        title = QLabel("Rated Performance Inputs")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title.setFont(title_font)
        layout.addWidget(title)

        # Instructions
        instructions = QLabel(
            "Enter the rated performance values and system parameters.\n"
            "Water flow rate is required for water-side mass flow calculations."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(instructions)

        # Group box for inputs
        input_group = QGroupBox("System Parameters")
        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # Create spinbox for each field
        for field_name, field_label in self.FIELD_DEFINITIONS:
            spinbox = QDoubleSpinBox()
            spinbox.setRange(0.0, 999999.0)  # Allow large values
            spinbox.setDecimals(2)  # 2 decimal places
            spinbox.setSingleStep(1.0)  # Step size
            spinbox.setMinimumWidth(150)
            spinbox.setAlignment(Qt.AlignmentFlag.AlignRight)

            # Store reference
            self.fields[field_name] = spinbox

            # Add to form
            form_layout.addRow(f"{field_label}:", spinbox)

        input_group.setLayout(form_layout)
        layout.addWidget(input_group)

        # Button box (OK / Cancel)
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_data(self) -> dict:
        """
        Get the current values from all spinboxes.

        Returns:
            dict: Dictionary with field names as keys and float values.
                  Returns 0.0 for unset fields (default spinbox value).
        """
        data = {}
        for field_name, spinbox in self.fields.items():
            value = spinbox.value()
            # Store None if value is 0 (unset), otherwise store the actual value
            data[field_name] = None if value == 0.0 else value
        return data

    def set_data(self, data: dict):
        """
        Pre-fill the spinboxes with existing data.

        Args:
            data: Dictionary with field names as keys and float values.
                  Missing or None values will be set to 0.0.
        """
        if data is None:
            data = {}

        for field_name, spinbox in self.fields.items():
            value = data.get(field_name)
            if value is not None:
                try:
                    spinbox.setValue(float(value))
                except (ValueError, TypeError):
                    spinbox.setValue(0.0)
            else:
                spinbox.setValue(0.0)

    def validate_data(self) -> tuple[bool, str]:
        """
        Validate that all required fields are filled.

        Returns:
            tuple: (is_valid, error_message)
                   is_valid: True if all fields have non-zero values
                   error_message: Describes which fields are missing
        """
        missing_fields = []

        for field_name, spinbox in self.fields.items():
            if spinbox.value() == 0.0:
                # Find the user-friendly label
                label = next(
                    (label for name, label in self.FIELD_DEFINITIONS if name == field_name),
                    field_name
                )
                missing_fields.append(label)

        if missing_fields:
            message = "The following fields are missing or zero:\n\n" + "\n".join(f"• {f}" for f in missing_fields)
            return False, message

        return True, ""

    def accept(self):
        """
        Override accept to optionally validate before closing.

        Currently allows closing even with empty fields (lenient approach).
        Validation happens in calculations_widget before running calculations.
        """
        # Optional: Uncomment to enforce validation before closing
        # is_valid, error_message = self.validate_data()
        # if not is_valid:
        #     from PyQt6.QtWidgets import QMessageBox
        #     QMessageBox.warning(self, "Incomplete Data", error_message)
        #     return  # Don't close dialog

        super().accept()


# Example usage / testing
if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    dialog = InputDialog()

    # Test pre-filling with data
    test_data = {
        'rated_capacity_btu_hr': 12000.0,
        'rated_power_w': 1000.0,
        'gpm_water': 5.0,
    }
    dialog.set_data(test_data)

    if dialog.exec() == QDialog.DialogCode.Accepted:
        result = dialog.get_data()
        print("User entered:")
        for key, value in result.items():
            print(f"  {key}: {value}")
    else:
        print("User cancelled")

    sys.exit(0)
