from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from test_request_library import PART_FIELD_DEFS


class NewPartDialog(QDialog):
    """Asked once when a new supplier part number enters a catalog."""

    def __init__(self, part_type: str, model: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"New {part_type} - add to catalog")
        self._fields = {}

        lay = QVBoxLayout(self)
        intro = QLabel(
            f"Supplier part number '<b>{model}</b>' is new to the "
            f"{part_type} catalog.\nEnter its datasheet values once."
        )
        intro.setWordWrap(True)
        lay.addWidget(intro)

        form = QFormLayout()
        for key, label, kind in PART_FIELD_DEFS.get(part_type, []):
            if isinstance(kind, tuple) and kind[0] == "choice":
                widget = QComboBox()
                widget.addItems(kind[1])
            else:
                widget = QLineEdit()
                if kind == "float":
                    widget.setPlaceholderText("number")
                    widget.setMaximumWidth(160)
            self._fields[key] = (widget, kind)
            form.addRow(label + ":", widget)
        lay.addLayout(form)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def specs(self) -> dict:
        out = {}
        for key, (widget, kind) in self._fields.items():
            if isinstance(widget, QComboBox):
                value = widget.currentText().strip()
            else:
                value = widget.text().strip()
            if not value:
                continue
            if kind == "float":
                try:
                    out[key] = float(value)
                except ValueError:
                    continue
            else:
                out[key] = value
        return out
