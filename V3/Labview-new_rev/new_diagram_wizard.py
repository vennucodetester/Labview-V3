"""
new_diagram_wizard.py

NewDiagramWizard — a single scrollable QDialog that collects the configuration
for generating a new refrigeration diagram via diagram_templates.py.

Sections shown/hidden dynamically based on Architecture selection:
  - Modular        → location (SC/Remote), case size, circuits per module
  - Non-Modular    → location (SC/Remote), door count, total circuits
  - Cassette       → unit count, circuits per unit, underlying case (mod size or NM door count)
  - Freedom        → circuits

Always-visible sections:
  - Condenser (hidden for Remote cases)
  - Expansion device (TXV / Cap Tube)
  - Optional components (Filter Dryer, Hot Gas Bypass)
  - Air measurement (Single / Dual discharge curtain)
  - Shelving (shelf rows 3–7)
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QRadioButton,
    QButtonGroup, QCheckBox, QSpinBox, QLabel, QScrollArea,
    QWidget, QFrame, QDialogButtonBox, QSizePolicy, QPushButton,
)
from PyQt6.QtCore import Qt


class NewDiagramWizard(QDialog):
    """Configuration dialog for generating a new refrigeration diagram template."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Diagram — Configuration")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setMinimumHeight(600)

        # --- Scroll wrapper -------------------------------------------------
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        inner_widget = QWidget()
        self._main_layout = QVBoxLayout(inner_widget)
        self._main_layout.setContentsMargins(16, 16, 16, 8)
        self._main_layout.setSpacing(10)
        scroll.setWidget(inner_widget)

        # --- Build all sections ---------------------------------------------
        self._build_architecture_section()
        self._build_modular_section()
        self._build_non_modular_section()
        self._build_cassette_section()
        self._build_freedom_section()
        self._build_condenser_section()
        self._build_expansion_section()
        self._build_optional_section()
        self._build_air_section()
        self._build_shelving_section()

        self._main_layout.addStretch(1)

        # --- "Change template…" button (inside scroll area, above buttons) --
        change_row = QHBoxLayout()
        self._change_template_btn = QPushButton("🔄  Change template for this config…")
        self._change_template_btn.setToolTip(
            "Re-assign which hand-crafted JSON file is used as the template "
            "for the currently selected configuration."
        )
        self._change_template_btn.clicked.connect(self._on_change_template_clicked)
        change_row.addStretch()
        change_row.addWidget(self._change_template_btn)
        self._main_layout.addLayout(change_row)

        # --- Dialog buttons (Cancel / Generate) -----------------------------
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Generate →")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        # --- Initial visibility ---------------------------------------------
        self._on_architecture_changed()

    # =========================================================================
    #  Section builders
    # =========================================================================

    def _build_architecture_section(self):
        gb = QGroupBox("Case Architecture")
        layout = QHBoxLayout(gb)
        layout.setSpacing(12)

        self._arch_group = QButtonGroup(self)
        for idx, text in enumerate(["Modular", "Non-Modular", "Cassette", "Freedom"]):
            rb = QRadioButton(text)
            layout.addWidget(rb)
            self._arch_group.addButton(rb, idx)

        self._arch_group.button(0).setChecked(True)
        self._arch_group.idClicked.connect(self._on_architecture_changed)
        self._main_layout.addWidget(gb)

    def _build_modular_section(self):
        self._mod_gb = QGroupBox("Modular Options")
        layout = QVBoxLayout(self._mod_gb)

        # Location
        loc_row = QHBoxLayout()
        loc_row.addWidget(QLabel("Location:"))
        self._mod_loc_group = QButtonGroup(self)
        rb_sc = QRadioButton("Self-Contained")
        rb_sc.setChecked(True)
        rb_rem = QRadioButton("Remote")
        self._mod_loc_group.addButton(rb_sc, 0)
        self._mod_loc_group.addButton(rb_rem, 1)
        loc_row.addWidget(rb_sc)
        loc_row.addWidget(rb_rem)
        loc_row.addStretch()
        layout.addLayout(loc_row)
        self._mod_loc_group.idClicked.connect(self._on_location_changed)

        # Case size
        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("Case size:"))
        self._mod_size_group = QButtonGroup(self)
        for idx, sz in enumerate(["12 ft", "8 ft", "6 ft", "4 ft"]):
            rb = QRadioButton(sz)
            size_row.addWidget(rb)
            self._mod_size_group.addButton(rb, idx)
        self._mod_size_group.button(0).setChecked(True)
        size_row.addStretch()
        layout.addLayout(size_row)

        # Circuits per module
        circ_row = QHBoxLayout()
        circ_row.addWidget(QLabel("Circuits per module:"))
        self._mod_circuits = QSpinBox()
        self._mod_circuits.setRange(1, 12)
        self._mod_circuits.setValue(6)
        self._mod_circuits.setMaximumWidth(70)
        circ_row.addWidget(self._mod_circuits)
        circ_row.addStretch()
        layout.addLayout(circ_row)

        self._main_layout.addWidget(self._mod_gb)

    def _build_non_modular_section(self):
        self._nm_gb = QGroupBox("Non-Modular Options")
        layout = QVBoxLayout(self._nm_gb)

        # Location
        loc_row = QHBoxLayout()
        loc_row.addWidget(QLabel("Location:"))
        self._nm_loc_group = QButtonGroup(self)
        rb_sc = QRadioButton("Self-Contained")
        rb_sc.setChecked(True)
        rb_rem = QRadioButton("Remote")
        self._nm_loc_group.addButton(rb_sc, 0)
        self._nm_loc_group.addButton(rb_rem, 1)
        loc_row.addWidget(rb_sc)
        loc_row.addWidget(rb_rem)
        loc_row.addStretch()
        layout.addLayout(loc_row)
        self._nm_loc_group.idClicked.connect(self._on_location_changed)

        # Door count
        door_row = QHBoxLayout()
        door_row.addWidget(QLabel("Door count:"))
        self._nm_door_group = QButtonGroup(self)
        for d in range(1, 6):
            rb = QRadioButton(str(d))
            door_row.addWidget(rb)
            self._nm_door_group.addButton(rb, d - 1)
        self._nm_door_group.button(2).setChecked(True)  # default 3 doors
        door_row.addStretch()
        layout.addLayout(door_row)

        # Total circuits
        circ_row = QHBoxLayout()
        circ_row.addWidget(QLabel("Total circuits:"))
        self._nm_circuits = QSpinBox()
        self._nm_circuits.setRange(1, 12)
        self._nm_circuits.setValue(6)
        self._nm_circuits.setMaximumWidth(70)
        circ_row.addWidget(self._nm_circuits)
        circ_row.addStretch()
        layout.addLayout(circ_row)

        self._main_layout.addWidget(self._nm_gb)

    def _build_cassette_section(self):
        self._cas_gb = QGroupBox("Cassette Options")
        layout = QVBoxLayout(self._cas_gb)

        # Number of units
        unit_row = QHBoxLayout()
        unit_row.addWidget(QLabel("Number of cassette units:"))
        self._cas_unit_group = QButtonGroup(self)
        for u in [1, 2, 3]:
            rb = QRadioButton(str(u))
            unit_row.addWidget(rb)
            self._cas_unit_group.addButton(rb, u - 1)
        self._cas_unit_group.button(0).setChecked(True)
        unit_row.addStretch()
        layout.addLayout(unit_row)

        # Circuits per unit
        circ_row = QHBoxLayout()
        circ_row.addWidget(QLabel("Circuits per unit:"))
        self._cas_circuits = QSpinBox()
        self._cas_circuits.setRange(1, 12)
        self._cas_circuits.setValue(6)
        self._cas_circuits.setMaximumWidth(70)
        circ_row.addWidget(self._cas_circuits)
        circ_row.addStretch()
        layout.addLayout(circ_row)

        # Underlying case type
        layout.addWidget(QLabel("Underlying case (drives shelving / fan / air layout):"))
        self._cas_case_type_group = QButtonGroup(self)
        rb_mod = QRadioButton("Modular")
        rb_mod.setChecked(True)
        rb_nm  = QRadioButton("Non-Modular")
        self._cas_case_type_group.addButton(rb_mod, 0)
        self._cas_case_type_group.addButton(rb_nm,  1)
        case_type_row = QHBoxLayout()
        case_type_row.addWidget(rb_mod)
        case_type_row.addWidget(rb_nm)
        case_type_row.addStretch()
        layout.addLayout(case_type_row)
        self._cas_case_type_group.idClicked.connect(self._on_cassette_case_type_changed)

        # Modular sub-row
        self._cas_mod_widget = QWidget()
        cas_mod_row = QHBoxLayout(self._cas_mod_widget)
        cas_mod_row.setContentsMargins(16, 0, 0, 0)
        cas_mod_row.addWidget(QLabel("Case size:"))
        self._cas_size_group = QButtonGroup(self)
        for idx, sz in enumerate(["12 ft", "8 ft", "6 ft", "4 ft"]):
            rb = QRadioButton(sz)
            cas_mod_row.addWidget(rb)
            self._cas_size_group.addButton(rb, idx)
        self._cas_size_group.button(0).setChecked(True)
        cas_mod_row.addStretch()
        layout.addWidget(self._cas_mod_widget)

        # Non-modular sub-row
        self._cas_nm_widget = QWidget()
        cas_nm_row = QHBoxLayout(self._cas_nm_widget)
        cas_nm_row.setContentsMargins(16, 0, 0, 0)
        cas_nm_row.addWidget(QLabel("Door count:"))
        self._cas_door_group = QButtonGroup(self)
        for d in range(1, 6):
            rb = QRadioButton(str(d))
            cas_nm_row.addWidget(rb)
            self._cas_door_group.addButton(rb, d - 1)
        self._cas_door_group.button(2).setChecked(True)
        cas_nm_row.addStretch()
        layout.addWidget(self._cas_nm_widget)
        self._cas_nm_widget.setVisible(False)

        self._main_layout.addWidget(self._cas_gb)

    def _build_freedom_section(self):
        self._free_gb = QGroupBox("Freedom Options")
        layout = QVBoxLayout(self._free_gb)

        circ_row = QHBoxLayout()
        circ_row.addWidget(QLabel("Circuits:"))
        self._free_circuits = QSpinBox()
        self._free_circuits.setRange(1, 12)
        self._free_circuits.setValue(6)
        self._free_circuits.setMaximumWidth(70)
        circ_row.addWidget(self._free_circuits)
        circ_row.addStretch()
        layout.addLayout(circ_row)

        self._main_layout.addWidget(self._free_gb)

    def _build_condenser_section(self):
        self._cond_gb = QGroupBox("Condenser Type")
        layout = QHBoxLayout(self._cond_gb)

        self._cond_group = QButtonGroup(self)
        rb_air   = QRadioButton("Air Cooled")
        rb_water = QRadioButton("Water Cooled")
        rb_air.setChecked(True)
        self._cond_group.addButton(rb_air,   0)
        self._cond_group.addButton(rb_water, 1)
        layout.addWidget(rb_air)
        layout.addWidget(rb_water)
        layout.addStretch()

        self._main_layout.addWidget(self._cond_gb)

    def _build_expansion_section(self):
        gb = QGroupBox("Expansion Device")
        layout = QHBoxLayout(gb)

        self._exp_group = QButtonGroup(self)
        rb_txv = QRadioButton("TXV")
        rb_cap = QRadioButton("Cap Tube")
        rb_txv.setChecked(True)
        self._exp_group.addButton(rb_txv, 0)
        self._exp_group.addButton(rb_cap, 1)
        layout.addWidget(rb_txv)
        layout.addWidget(rb_cap)
        layout.addStretch()

        self._main_layout.addWidget(gb)

    def _build_optional_section(self):
        gb = QGroupBox("Optional Refrigeration Components")
        layout = QVBoxLayout(gb)

        self._cb_filter_dryer   = QCheckBox("Filter Dryer")
        self._cb_hot_gas_bypass = QCheckBox("Hot Gas Bypass Valve  (for hot gas defrost)")
        layout.addWidget(self._cb_filter_dryer)
        layout.addWidget(self._cb_hot_gas_bypass)

        self._main_layout.addWidget(gb)

    def _build_air_section(self):
        gb = QGroupBox("Air Measurement")
        layout = QVBoxLayout(gb)

        curtain_row = QHBoxLayout()
        curtain_row.addWidget(QLabel("Discharge curtain:"))
        self._curtain_group = QButtonGroup(self)
        rb_single = QRadioButton("Single")
        rb_dual   = QRadioButton("Dual")
        rb_single.setChecked(True)
        self._curtain_group.addButton(rb_single, 0)
        self._curtain_group.addButton(rb_dual,   1)
        curtain_row.addWidget(rb_single)
        curtain_row.addWidget(rb_dual)
        curtain_row.addStretch()
        layout.addLayout(curtain_row)

        note = QLabel("Return air block is always included.\n"
                       "Sensor counts default to 2 per array — adjust via double-click after generation.")
        note.setStyleSheet("color: #555; font-size: 11px;")
        note.setWordWrap(True)
        layout.addWidget(note)

        self._main_layout.addWidget(gb)

    def _build_shelving_section(self):
        gb = QGroupBox("Shelving  (always included)")
        layout = QHBoxLayout(gb)

        layout.addWidget(QLabel("Shelf rows per column:"))
        self._shelf_rows = QSpinBox()
        self._shelf_rows.setRange(3, 7)
        self._shelf_rows.setValue(5)
        self._shelf_rows.setMaximumWidth(70)
        layout.addWidget(self._shelf_rows)
        layout.addStretch()

        self._main_layout.addWidget(gb)

    # =========================================================================
    #  Visibility logic
    # =========================================================================

    def _on_architecture_changed(self):
        arch = self._arch_group.checkedId()   # 0=Mod, 1=NM, 2=Cas, 3=Free
        self._mod_gb.setVisible(arch == 0)
        self._nm_gb.setVisible(arch  == 1)
        self._cas_gb.setVisible(arch == 2)
        self._free_gb.setVisible(arch == 3)
        self._on_location_changed()

    def _on_location_changed(self):
        """Show/hide the Condenser section based on Remote selection."""
        arch = self._arch_group.checkedId()
        if arch == 0:    # Modular
            is_remote = self._mod_loc_group.checkedId() == 1
        elif arch == 1:  # Non-Modular
            is_remote = self._nm_loc_group.checkedId() == 1
        else:
            is_remote = False   # Cassette and Freedom are always SC
        self._cond_gb.setVisible(not is_remote)

    def _on_cassette_case_type_changed(self):
        is_mod = self._cas_case_type_group.checkedId() == 0
        self._cas_mod_widget.setVisible(is_mod)
        self._cas_nm_widget.setVisible(not is_mod)

    # =========================================================================
    #  Result extraction
    # =========================================================================

    def get_config(self) -> dict:
        """Build and return the config dict that diagram_templates.py expects."""
        arch = self._arch_group.checkedId()   # 0=Mod, 1=NM, 2=Cas, 3=Free

        _SIZE_MAP   = {0: '12 ft', 1: '8 ft', 2: '6 ft', 3: '4 ft'}
        _COND_MAP   = {0: 'Air Cooled', 1: 'Water Cooled'}
        _EXP_MAP    = {0: 'TXV', 1: 'Cap Tube'}
        _CURT_MAP   = {0: 'single', 1: 'dual'}

        cfg = {
            # Shared options
            'condenser_type':          _COND_MAP[self._cond_group.checkedId()],
            'expansion_type':          _EXP_MAP[self._exp_group.checkedId()],
            'include_filter_dryer':    self._cb_filter_dryer.isChecked(),
            'include_hot_gas_bypass':  self._cb_hot_gas_bypass.isChecked(),
            'air_curtain_type':        _CURT_MAP[self._curtain_group.checkedId()],
            'shelf_rows':              self._shelf_rows.value(),
        }

        if arch == 0:    # Modular
            is_remote  = self._mod_loc_group.checkedId() == 1
            cfg.update({
                'case_type':           'modular_remote' if is_remote else 'modular_self_contained',
                'case_size':           _SIZE_MAP[self._mod_size_group.checkedId()],
                'circuits_per_module': self._mod_circuits.value(),
            })

        elif arch == 1:  # Non-Modular
            is_remote = self._nm_loc_group.checkedId() == 1
            cfg.update({
                'case_type':           'non_modular_remote' if is_remote else 'non_modular_self_contained',
                'door_count':          self._nm_door_group.checkedId() + 1,
                'circuits_per_module': self._nm_circuits.value(),
            })

        elif arch == 2:  # Cassette
            cas_case_is_mod = self._cas_case_type_group.checkedId() == 0
            cfg.update({
                'case_type':           'cassette',
                'cassette_count':      self._cas_unit_group.checkedId() + 1,
                'circuits_per_module': self._cas_circuits.value(),
                'cassette_case_type':  'modular' if cas_case_is_mod else 'non_modular',
                'cassette_case_size':  _SIZE_MAP[self._cas_size_group.checkedId()],
                'cassette_door_count': self._cas_door_group.checkedId() + 1,
            })

        else:            # Freedom
            cfg.update({
                'case_type':           'freedom',
                'door_count':          1,
                'circuits_per_module': self._free_circuits.value(),
            })

        return cfg

    # =========================================================================
    #  Change-template action
    # =========================================================================

    def _on_change_template_clicked(self):
        """Force-open the file picker for the current config key so the user
        can re-assign which hand-crafted JSON is used as the template."""
        from diagram_template_loader import get_config_key, get_or_pick_template
        config = self.get_config()
        key    = get_config_key(config)
        chosen = get_or_pick_template(key, parent_widget=self, force=True)
        if chosen:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                self,
                "Template Updated",
                f"Template for  '{key}'  is now:\n{chosen}"
            )
