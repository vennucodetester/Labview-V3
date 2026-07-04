from __future__ import annotations

import os

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from case_library import (
    CaseLibrary,
    apply_case_to_session,
    request_to_case_html,
    topology_one_liner,
)
from part_dialogs import NewPartDialog
from test_request_library import DEFAULT_TARGETS, PART_TYPES


class CaseLibraryDialog(QDialog):
    def __init__(self, library: CaseLibrary, parent=None, data_manager=None):
        super().__init__(parent)
        self.lib = library
        self.data_manager = data_manager
        self.selected_case = None
        self.setWindowTitle("Cases")
        self.resize(900, 560)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search cases")
        self.search.textChanged.connect(self.refresh)
        search_row.addWidget(self.search)
        root.addLayout(search_row)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self.open_selected)
        root.addWidget(self.list, 1)

        row = QHBoxLayout()
        self.btn_open = QPushButton("Open Case")
        self.btn_new_case = QPushButton("New Case...")
        self.btn_new_test = QPushButton("New Test...")
        self.btn_export = QPushButton("Open/Export Test...")
        self.btn_open.clicked.connect(self.open_selected)
        self.btn_new_case.clicked.connect(self.new_case)
        self.btn_new_test.clicked.connect(self.new_test)
        self.btn_export.clicked.connect(self.export_test)
        for btn in (self.btn_open, self.btn_new_case, self.btn_new_test, self.btn_export):
            row.addWidget(btn)
        row.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        root.addLayout(row)

    def refresh(self):
        text = self.search.text().strip().lower()
        self.list.clear()
        for case in self.lib.cases():
            hay = " ".join([
                case.get("model", ""),
                topology_one_liner(case, self.lib.families()),
                str(len(self.lib.tests_for_case(case["id"]))),
            ]).lower()
            if text and text not in hay:
                continue
            tests = len(self.lib.tests_for_case(case["id"]))
            label = (
                f"{case.get('model') or case.get('id')}    "
                f"{topology_one_liner(case, self.lib.families())}    "
                f"{tests} test(s)"
            )
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, case["id"])
            self.list.addItem(item)

    def current_case(self):
        item = self.list.currentItem()
        if not item:
            return None
        return self.lib.get_case(item.data(Qt.ItemDataRole.UserRole))

    def open_selected(self, item=None):
        if item is not None and hasattr(item, "data"):
            case = self.lib.get_case(item.data(Qt.ItemDataRole.UserRole))
        else:
            case = self.current_case()
        if not case:
            QMessageBox.information(self, "Cases", "Select a case first.")
            return
        diagram = self.lib.load_diagram(case["id"])
        if not diagram:
            from diagram_from_request import generate_case_diagram

            diagram = generate_case_diagram(case.get("topology", {}), self.lib.families())
            self.lib.save_diagram(case["id"], diagram)
        apply_case_to_session(case, diagram, self.data_manager, emit_signals=False)
        self.lib.mark_used(case["id"])
        self.selected_case = case
        try:
            if self.parent() is not None and hasattr(self.parent(), "tabs"):
                if hasattr(self.parent(), "sensor_panel"):
                    self.parent().sensor_panel.update_ui()
                if hasattr(self.parent(), "diagram_widget"):
                    self.parent().diagram_widget.build_scene_from_model()
                if hasattr(self.parent(), "show_diagram_tab_and_fit"):
                    self.parent().show_diagram_tab_and_fit()
                else:
                    self.parent().tabs.setCurrentWidget(self.parent().diagram_widget)
                    QTimer.singleShot(150, self.parent().diagram_widget.zoom_to_fit)
                self.parent().statusBar().showMessage(f"Case {case.get('model')} loaded", 4000)
        except Exception:
            pass
        self.accept()

    def new_case(self):
        dlg = NewCaseDialog(self.lib, self, self.data_manager)
        if dlg.exec():
            self.refresh()

    def new_test(self):
        case = self.current_case()
        if not case:
            QMessageBox.information(self, "Cases", "Select a case first.")
            return
        dlg = NewTestDialog(self.lib, case, self)
        dlg.exec()
        self.refresh()

    def export_test(self):
        tests = self.lib.all_tests()
        if not tests:
            QMessageBox.information(self, "Cases", "No tests have been saved yet.")
            return
        dlg = TestPickerDialog(self.lib, tests, self)
        dlg.exec()


class NewCaseDialog(QDialog):
    def __init__(self, library: CaseLibrary, parent=None, data_manager=None):
        super().__init__(parent)
        self.lib = library
        self.data_manager = data_manager
        self.setWindowTitle("New Case")
        self.resize(760, 640)
        self._build_ui()
        self._sync_family_rules()
        self._sync_system()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        scroll.setWidget(body)
        content = QVBoxLayout(body)

        identity = QGroupBox("Identity")
        form = QFormLayout(identity)
        self.model = QLineEdit()
        self.notes = QTextEdit()
        self.notes.setMaximumHeight(70)
        form.addRow("Case model:", self.model)
        form.addRow("Notes:", self.notes)
        content.addWidget(identity)

        topo_box = QGroupBox("Topology")
        topo = QFormLayout(topo_box)
        self.family = QComboBox()
        self.family.addItem("Select family", "")
        for key, rules in self.lib.families().items():
            self.family.addItem(rules.get("display", key), key)
        self.family.currentIndexChanged.connect(self._sync_family_rules)
        self.size = QSpinBox()
        self.size.valueChanged.connect(self._sync_progressive_topology)
        self.open_or_doored = QComboBox()
        self.open_or_doored.addItem("Select style", "")
        self.open_or_doored.addItems(["Open", "Doored"])
        self.open_or_doored.currentIndexChanged.connect(self._sync_progressive_topology)
        self.temp_class = QComboBox()
        self.temp_class.currentIndexChanged.connect(self._sync_progressive_topology)
        self.system = QComboBox()
        self.system.addItem("Select system", "")
        self.system.addItem("Shared", "shared")
        self.system.addItem("Cassette", "cassette")
        self.system.currentTextChanged.connect(self._sync_system)
        self.cassette_count = QSpinBox()
        self.cassette_count.setRange(1, 5)
        self.cassette_count.valueChanged.connect(self._update_review)
        self.cassette_airflow = QComboBox()
        self.cassette_airflow.addItems(["conventional", "reverse"])
        self.cassette_airflow.currentIndexChanged.connect(self._update_review)
        self.circuits = QSpinBox()
        self.circuits.setRange(1, 12)
        self.circuits.setValue(6)
        self.circuits.valueChanged.connect(self._update_review)
        self.defrost_type = QComboBox()
        self.defrost_type.addItem("Select defrost", "")
        self.defrost_type.addItems(["none", "off_time", "electric", "hot_gas", "cool_gas"])
        self.defrost_type.currentIndexChanged.connect(self._sync_progressive_topology)
        self.cooling = QComboBox()
        self.cooling.addItem("Select cooling", "")
        self.cooling.addItems(["Water", "Air"])
        self.cooling.currentIndexChanged.connect(self._sync_progressive_topology)
        self.shelf_rows = QSpinBox()
        self.shelf_rows.setRange(3, 8)
        self.shelf_rows.setValue(5)
        self.shelf_rows.valueChanged.connect(self._update_review)
        self.topology_rows = {}
        for key, label, widget in [
            ("family", "Case family:", self.family),
            ("size", "Size:", self.size),
            ("open_or_doored", "Open or doored:", self.open_or_doored),
            ("temp_class", "Temperature class:", self.temp_class),
            ("system", "Refrigeration system:", self.system),
            ("cassette_count", "Cassettes:", self.cassette_count),
            ("cassette_airflow", "Cassette airflow:", self.cassette_airflow),
            ("circuits", "Circuits:", self.circuits),
            ("defrost_type", "Defrost type:", self.defrost_type),
            ("cooling", "Condenser cooling:", self.cooling),
            ("shelf_rows", "Shelf rows:", self.shelf_rows),
        ]:
            self._add_topology_row(topo, key, label, widget)
        content.addWidget(topo_box)

        parts = QGroupBox("Parts")
        pf = QFormLayout(parts)
        self.part_combos = {}
        from test_request_library import TestRequestLibrary

        self.old_lib = TestRequestLibrary()
        for ptype in PART_TYPES:
            cmb = QComboBox()
            cmb.setEditable(True)
            cmb.addItem("")
            cmb.addItems(self.old_lib.catalog_models(ptype))
            self.part_combos[ptype] = cmb
            pf.addRow(ptype.title() + ":", cmb)
        content.addWidget(parts)

        settings = QGroupBox("Settings")
        sf = QFormLayout(settings)
        self.refrigerant = QLineEdit("R290")
        self.charge = QDoubleSpinBox()
        self.charge.setRange(0, 10000)
        self.charge.setSpecialValueText("-")
        self.charge.setDecimals(1)
        self.gpm = QDoubleSpinBox()
        self.gpm.setRange(0, 1000)
        self.gpm.setSpecialValueText("-")
        self.gpm.setDecimals(2)
        self.cfm = QDoubleSpinBox()
        self.cfm.setRange(0, 100000)
        self.cfm.setSpecialValueText("-")
        self.defrost_schedule = QLineEdit()
        self.setpoints = QLineEdit()
        for label, widget in [
            ("Refrigerant:", self.refrigerant),
            ("Charge (oz):", self.charge),
            ("Water GPM:", self.gpm),
            ("Fan CFM:", self.cfm),
            ("Defrost schedule:", self.defrost_schedule),
            ("Setpoints:", self.setpoints),
        ]:
            sf.addRow(label, widget)
        content.addWidget(settings)

        self.review = QLabel()
        self.review.setWordWrap(True)
        content.addWidget(self.review)
        content.addStretch()
        root.addWidget(scroll, 1)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        create = bb.addButton("Create", QDialogButtonBox.ButtonRole.AcceptRole)
        create.clicked.connect(self.create_case)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def _add_topology_row(self, layout, key: str, label: str, widget):
        label_widget = QLabel(label)
        layout.addRow(label_widget, widget)
        self.topology_rows[key] = (label_widget, widget)

    def _set_topology_row_visible(self, key: str, visible: bool):
        row = self.topology_rows.get(key)
        if not row:
            return
        for widget in row:
            widget.setVisible(visible)

    def _sync_family_rules(self):
        key = self.family.currentData()
        if not key:
            for row_key in self.topology_rows:
                self._set_topology_row_visible(row_key, row_key == "family")
            self.review.setText("")
            return
        rules = self.lib.families().get(key, {})
        lo, hi = rules.get("size_range", [1, 3])
        self.size.setRange(int(lo), int(hi))
        self.size.setPrefix("")
        self.size.setSuffix(f" {rules.get('size_question', 'modules')}")
        if not rules.get("open_allowed", True):
            self.open_or_doored.setCurrentText("Doored")
        else:
            self.open_or_doored.setCurrentIndex(0)
        self.temp_class.clear()
        if len(rules.get("temp_classes", ["MT"])) > 1:
            self.temp_class.addItem("Select temperature", "")
        self.temp_class.addItems(rules.get("temp_classes", ["MT"]))
        self.system.setCurrentIndex(0)
        self.defrost_type.setCurrentIndex(0)
        self.cooling.setCurrentIndex(0)
        self._sync_progressive_topology()

    def _sync_system(self):
        self._sync_progressive_topology()

    def _sync_progressive_topology(self):
        key = self.family.currentData()
        rules = self.lib.families().get(key, {}) if key else {}
        for row_key in self.topology_rows:
            self._set_topology_row_visible(row_key, row_key == "family")
        if not key:
            self.review.setText("")
            return

        self._set_topology_row_visible("size", True)
        open_required = bool(rules.get("open_allowed", True))
        temp_required = len(rules.get("temp_classes", ["MT"])) > 1
        if open_required:
            self._set_topology_row_visible("open_or_doored", True)
            if self.open_or_doored.currentIndex() <= 0:
                self._update_review()
                return
        if temp_required:
            self._set_topology_row_visible("temp_class", True)
            if self.temp_class.currentIndex() <= 0:
                self._update_review()
                return

        self._set_topology_row_visible("system", True)
        system = self.system.currentData()
        if not system:
            self._update_review()
            return
        is_cassette = system == "cassette"
        self._set_topology_row_visible("cassette_count", is_cassette)
        self._set_topology_row_visible("cassette_airflow", is_cassette)
        self._set_topology_row_visible("circuits", True)
        self._set_topology_row_visible("defrost_type", True)
        if not self.defrost_type.currentText() or not self.defrost_type.currentData() and self.defrost_type.currentIndex() == 0:
            self._update_review()
            return
        self._set_topology_row_visible("cooling", True)
        if not self.cooling.currentText() or not self.cooling.currentData() and self.cooling.currentIndex() == 0:
            self._update_review()
            return
        self._set_topology_row_visible("shelf_rows", True)
        self._update_review()

    def _update_review(self):
        try:
            if self._topology_complete():
                self.review.setText("Review: " + topology_one_liner({"topology": self._topology()}, self.lib.families()))
            else:
                self.review.setText("")
        except Exception:
            self.review.setText("")

    def _topology_complete(self):
        key = self.family.currentData()
        if not key:
            return False
        rules = self.lib.families().get(key, {})
        if rules.get("open_allowed", True) and self.open_or_doored.currentIndex() <= 0:
            return False
        if len(rules.get("temp_classes", ["MT"])) > 1 and self.temp_class.currentIndex() <= 0:
            return False
        return bool(self.system.currentData() and self.defrost_type.currentText() and self.defrost_type.currentIndex() > 0 and self.cooling.currentText() and self.cooling.currentIndex() > 0)

    def _topology(self):
        family = self.family.currentData()
        rules = self.lib.families().get(family, {})
        system = self.system.currentData()
        open_or_doored = self.open_or_doored.currentText() if rules.get("open_allowed", True) else "Doored"
        temp_class = self.temp_class.currentText() if len(rules.get("temp_classes", ["MT"])) > 1 else (rules.get("temp_classes", ["MT"]) or ["MT"])[0]
        return {
            "family": family,
            "size_count": self.size.value(),
            "open_or_doored": open_or_doored,
            "temp_class": temp_class,
            "system": system,
            "cassette_count": self.cassette_count.value() if system == "cassette" else None,
            "cassette_airflow": self.cassette_airflow.currentText() if system == "cassette" else None,
            "circuits": self.circuits.value(),
            "defrost_type": self.defrost_type.currentText(),
            "condenser_cooling": self.cooling.currentText(),
            "shelf_rows": self.shelf_rows.value(),
        }

    def _parts(self):
        parts = {}
        for ptype, cmb in self.part_combos.items():
            model = cmb.currentText().strip()
            if model and not self.old_lib.find_part(ptype, model):
                dlg = NewPartDialog(ptype, model, self)
                specs = dlg.specs() if dlg.exec() else {}
                self.old_lib.add_part(ptype, model, specs)
            if model:
                request = {"parts": {}}
                self.old_lib.attach_part(request, ptype, model)
                parts[ptype] = request["parts"].get(ptype)
        return parts

    def create_case(self):
        model = self.model.text().strip()
        if not model:
            QMessageBox.warning(self, "New Case", "Enter a case model name.")
            return
        if not self._topology_complete():
            QMessageBox.warning(self, "New Case", "Finish the topology choices.")
            return
        settings = {
            "refrigerant": self.refrigerant.text().strip() or "R290",
            "charge_oz": self.charge.value() or None,
            "water_gpm": self.gpm.value() or None,
            "fan_cfm": self.cfm.value() or None,
            "defrost_schedule": self.defrost_schedule.text().strip(),
            "setpoints": self.setpoints.text().strip(),
        }
        case = self.lib.new_case(
            model,
            self._topology(),
            self._parts(),
            settings,
            [dict(t) for t in DEFAULT_TARGETS],
            self.notes.toPlainText().strip(),
        )
        from diagram_from_request import generate_case_diagram

        diagram = generate_case_diagram(case["topology"], self.lib.families())
        self.lib.save_case(case)
        self.lib.save_diagram(case["id"], diagram)
        if self.data_manager is not None:
            apply_case_to_session(case, diagram, self.data_manager, emit_signals=False)
            try:
                mw = self.parent().parent()
                if hasattr(mw, "diagram_widget"):
                    mw.diagram_widget.build_scene_from_model()
                if hasattr(mw, "show_diagram_tab_and_fit"):
                    mw.show_diagram_tab_and_fit()
                else:
                    mw.tabs.setCurrentWidget(mw.diagram_widget)
                    QTimer.singleShot(150, mw.diagram_widget.zoom_to_fit)
            except Exception:
                pass
        self.accept()


class NewTestDialog(QDialog):
    def __init__(self, library: CaseLibrary, case: dict, parent=None):
        super().__init__(parent)
        self.lib = library
        self.case = case
        self.setWindowTitle(f"New Test - {case.get('model')}")
        self.resize(680, 460)
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.elp = QComboBox()
        self.elp.setEditable(True)
        from test_request_library import TestRequestLibrary

        for code in TestRequestLibrary().elp_codes():
            self.elp.addItem(f"{code['code']} - {code['name']}", code["code"])
        self.title = QLineEdit()
        self.objective = QTextEdit()
        self.objective.setMaximumHeight(90)
        form.addRow("Test type:", self.elp)
        form.addRow("Title:", self.title)
        form.addRow("Objective:", self.objective)
        root.addLayout(form)
        self.targets = TargetTable(case.get("default_targets") or DEFAULT_TARGETS)
        root.addWidget(self.targets)
        row = QHBoxLayout()
        save = QPushButton("Save")
        export = QPushButton("Save + Export printable")
        cancel = QPushButton("Cancel")
        save.clicked.connect(self.save)
        export.clicked.connect(self.save_export)
        cancel.clicked.connect(self.reject)
        row.addWidget(save)
        row.addWidget(export)
        row.addStretch()
        row.addWidget(cancel)
        root.addLayout(row)

    def _payload(self):
        text = self.elp.currentText().strip()
        return {
            "elp_code": text.split(" - ")[0].strip() if text else "",
            "title": self.title.text().strip(),
            "objective": self.objective.toPlainText().strip(),
            "targets": self.targets.rows(),
        }

    def save(self):
        p = self._payload()
        self.lib.create_test(self.case, p["elp_code"], p["title"], p["objective"], p["targets"])
        self.accept()

    def save_export(self):
        p = self._payload()
        test = self.lib.create_test(self.case, p["elp_code"], p["title"], p["objective"], p["targets"])
        html = request_to_case_html(test, self.case)
        out = self.lib.test_path(self.case["id"], test["id"]).replace(".json", ".html")
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)
        try:
            os.startfile(out)
        except Exception:
            pass
        self.accept()


class TestPickerDialog(QDialog):
    def __init__(self, library: CaseLibrary, tests: list, parent=None):
        super().__init__(parent)
        self.lib = library
        self.tests = tests
        self.setWindowTitle("Open/Export Test")
        self.resize(760, 430)
        root = QVBoxLayout(self)
        self.list = QListWidget()
        for test in tests:
            case = self.lib.get_case(test.get("case_id")) or {}
            item = QListWidgetItem(
                f"{test.get('request_no')}    {test.get('elp_code')}    "
                f"{test.get('title') or '(untitled)'}    {case.get('model', '')}"
            )
            item.setData(Qt.ItemDataRole.UserRole, test["id"])
            self.list.addItem(item)
        root.addWidget(self.list)
        row = QHBoxLayout()
        export = QPushButton("Export printable")
        close = QPushButton("Close")
        export.clicked.connect(self.export)
        close.clicked.connect(self.reject)
        row.addWidget(export)
        row.addStretch()
        row.addWidget(close)
        root.addLayout(row)

    def export(self):
        item = self.list.currentItem()
        if not item:
            return
        idx = self.list.row(item)
        test = self.tests[idx]
        case = self.lib.get_case(test.get("case_id")) or {}
        html = request_to_case_html(test, case)
        out = self.lib.test_path(test["case_id"], test["id"]).replace(".json", ".html")
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)
        try:
            os.startfile(out)
        except Exception:
            pass
        QMessageBox.information(self, "Exported", f"Printable test request written to:\n{out}")


class TargetTable(QWidget):
    def __init__(self, targets: list, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Target", "Min", "Max", "Unit"])
        root.addWidget(self.table)
        for target in targets:
            self.add_row(target)

    def add_row(self, target=None):
        target = target or {}
        r = self.table.rowCount()
        self.table.insertRow(r)
        vals = [
            target.get("name", ""),
            "" if target.get("min") is None else str(target.get("min")),
            "" if target.get("max") is None else str(target.get("max")),
            target.get("unit", ""),
        ]
        for c, value in enumerate(vals):
            self.table.setItem(r, c, QTableWidgetItem(value))

    def rows(self):
        out = []
        for r in range(self.table.rowCount()):
            def cell(c):
                item = self.table.item(r, c)
                return item.text().strip() if item else ""

            name = cell(0)
            if not name:
                continue

            def num(c):
                value = cell(c)
                try:
                    return float(value) if value else None
                except ValueError:
                    return None

            out.append({"name": name, "min": num(1), "max": num(2), "unit": cell(3)})
        return out
