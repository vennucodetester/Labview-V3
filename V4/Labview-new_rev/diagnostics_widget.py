"""
diagnostics_widget.py — Diagnostics Tab UI
===========================================
Renders findings from diagnostics_engine.run_all_diagnostics() as a scrollable
list of expandable cards.  Auto-updates when the Calculations tab emits
filtered_data_ready.

Layout
------
  ┌─ summary bar ────────────────────────────────────────────────────────────┐
  │  ● N CRITICAL  ● N WARNING  ● N WATCH  ✓ N OK   [Filter ▾] [⚙ Thresholds]│
  ├──────────────────────────────────────────────────────────────────────────┤
  │  scrollable list of FindingCard widgets (sorted by severity)             │
  └──────────────────────────────────────────────────────────────────────────┘

Each FindingCard
  ┌─ 🔴 CRITICAL ─── RF-1 · Refrigerant Leak (Trend) ─────────────────────────┐
  │  SH +12°F, SC -8°F over 145 rows — 3/4 leak signals active.              │
  │  [▼ Evidence]                               [▼ Recommendation]            │
  └────────────────────────────────────────────────────────────────────────────┘
  On expand: evidence or recommendation text appears below.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QDialog, QFormLayout, QDoubleSpinBox,
    QDialogButtonBox, QComboBox, QSizePolicy, QGroupBox,
    QSplitter, QListWidget, QListWidgetItem, QLineEdit, QSpinBox, QCheckBox,
    QGridLayout, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PyQt6.QtCore  import Qt, pyqtSlot, pyqtSignal
from PyQt6.QtGui   import QColor, QPalette, QFont

from diagnostics_engine import (
    DiagnosticScenario, Finding, DiagnosticContext,
    SCENARIO_REGISTRY, run_all_diagnostics, get_all_thresholds,
    _SCENARIO_BY_ID, load_custom_scenarios, save_custom_scenarios,
    load_rules_config, save_rules_config,
    _sanitize_colname, CustomScenario,
    SEVERITY_ORDER, COLUMN_DESCRIPTIONS,
)

# ─── NO-WHEEL COMBO FOR RULE EDITOR ───────────────────────────────────────────

class _NoWheelComboBox(QComboBox):
    """Ignore mouse wheel to prevent accidental selection changes while scrolling."""
    def wheelEvent(self, event):
        event.ignore()

# ─── COLOUR PALETTE ────────────────────────────────────────────────────────────

SEVER_COLORS = {
    'CRITICAL': ('#c0392b', '#fdecea'),  # (border/badge, background)
    'WARNING':  ('#e67e22', '#fef6ec'),
    'WATCH':    ('#2980b9', '#eaf4fb'),
    'OK':       ('#27ae60', '#eafaf1'),
    'INFO':     ('#7f8c8d', '#f5f5f5'),
}

SEVER_ICONS = {
    'CRITICAL': '🔴',
    'WARNING':  '🟡',
    'WATCH':    '🔵',
    'OK':       '✅',
    'INFO':     'ℹ️',
}


# ─── FINDING CARD ─────────────────────────────────────────────────────────────

class FindingCard(QFrame):
    """One collapsible card per Finding."""

    locate_requested = pyqtSignal(object)   # emits the Finding → highlight on diagram

    def __init__(self, finding: Finding, parent=None):
        super().__init__(parent)
        self.finding = finding
        self._ev_visible   = False
        self._rec_visible  = False
        self._desc_visible = False
        self._build_ui()

    def _build_ui(self):
        border_col, bg_col = SEVER_COLORS.get(self.finding.severity, ('#888', '#fafafa'))
        icon = SEVER_ICONS.get(self.finding.severity, '')

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            FindingCard {{
                border: 1px solid {border_col};
                border-radius: 4px;
                background: {bg_col};
                margin-bottom: 4px;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(4)

        # ── Header row ───────────────────────────────────────────────────────
        header_row = QHBoxLayout()

        badge = QLabel(f'{icon} {self.finding.severity}')
        badge.setStyleSheet(
            f'color: {border_col}; font-weight: bold; font-size: 11px;'
        )
        badge.setFixedWidth(110)

        id_label = QLabel(f'{self.finding.scenario_id} · {self.finding.label}')
        id_label.setStyleSheet('font-weight: bold; font-size: 12px;')
        id_label.setWordWrap(True)

        trend_tag = QLabel('TREND')
        trend_tag.setStyleSheet(
            'color: #555; font-size: 10px; border: 1px solid #aaa; '
            'border-radius: 3px; padding: 1px 4px;'
        )
        trend_tag.setVisible(self.finding.uses_trend)

        header_row.addWidget(badge)
        header_row.addWidget(id_label, 1)
        header_row.addWidget(trend_tag)
        root.addLayout(header_row)

        # ── Summary ──────────────────────────────────────────────────────────
        summary = QLabel(self.finding.summary)
        summary.setWordWrap(True)
        summary.setStyleSheet('font-size: 11px; color: #333; padding-left: 110px;')
        root.addWidget(summary)

        # ── Expand buttons (only if content exists) ──────────────────────────
        _locatable = self.finding.severity not in ('OK', 'INFO')
        if self.finding.evidence or self.finding.recommendation or _locatable:
            btn_row = QHBoxLayout()
            btn_row.setContentsMargins(108, 0, 0, 0)

            if _locatable:
                self._locate_btn = QPushButton('📍 Show on diagram')
                self._locate_btn.setFlat(True)
                self._locate_btn.setStyleSheet(
                    'color: #8e24aa; font-size: 11px; text-align: left; padding: 0;'
                )
                self._locate_btn.setToolTip(
                    'Switch to the Diagram tab and highlight the affected component')
                self._locate_btn.clicked.connect(
                    lambda: self.locate_requested.emit(self.finding))
                btn_row.addWidget(self._locate_btn)

            if self.finding.evidence:
                self._ev_btn = QPushButton('▶ Evidence')
                self._ev_btn.setFlat(True)
                self._ev_btn.setStyleSheet(
                    'color: #0066cc; font-size: 11px; text-align: left; padding: 0;'
                )
                self._ev_btn.clicked.connect(self._toggle_evidence)
                btn_row.addWidget(self._ev_btn)

            if self.finding.recommendation:
                self._rec_btn = QPushButton('▶ Recommendation')
                self._rec_btn.setFlat(True)
                self._rec_btn.setStyleSheet(
                    'color: #0066cc; font-size: 11px; text-align: left; padding: 0;'
                )
                self._rec_btn.clicked.connect(self._toggle_recommendation)
                btn_row.addWidget(self._rec_btn)

            btn_row.addStretch()
            root.addLayout(btn_row)

        # ── Expandable text panels ────────────────────────────────────────────
        if self.finding.evidence:
            self._ev_panel = QLabel(self.finding.evidence)
            self._ev_panel.setWordWrap(True)
            self._ev_panel.setStyleSheet(
                'font-family: monospace; font-size: 11px; color: #222; '
                'background: rgba(0,0,0,0.04); padding: 6px 8px; '
                'border-radius: 3px; margin-left: 108px;'
            )
            self._ev_panel.setVisible(False)
            root.addWidget(self._ev_panel)

        if self.finding.recommendation:
            self._rec_panel = QLabel(self.finding.recommendation)
            self._rec_panel.setWordWrap(True)
            self._rec_panel.setStyleSheet(
                'font-size: 11px; color: #1a5276; '
                'background: rgba(0,0,102,0.04); padding: 6px 8px; '
                'border-radius: 3px; margin-left: 108px;'
            )
            self._rec_panel.setVisible(False)
            root.addWidget(self._rec_panel)

        # ── What is this fault? (description) ──────────────────────────────────────
        scenario_obj = _SCENARIO_BY_ID.get(self.finding.scenario_id)
        self._desc_text = scenario_obj.DESCRIPTION if scenario_obj and scenario_obj.DESCRIPTION else ''

        if self._desc_text:
            self._desc_btn = QPushButton('▶ What is this fault?')
            self._desc_btn.setStyleSheet(
                'QPushButton{text-align:left;background:#f0e6ff;border:1px solid #c9a0ff;'
                'padding:3px 6px;border-radius:3px;color:#5b00a0;font-size:11px;}'
                'QPushButton:hover{background:#e0ccff;}'
            )
            self._desc_btn.clicked.connect(self._toggle_desc)
            root.addWidget(self._desc_btn)

            self._desc_label = QLabel(self._desc_text)
            self._desc_label.setWordWrap(True)
            self._desc_label.setStyleSheet(
                'background:#f8f0ff;border:1px solid #d9b3ff;padding:6px;'
                'border-radius:3px;font-size:11px;color:#3a0068;'
            )
            self._desc_label.hide()
            root.addWidget(self._desc_label)

    def _toggle_evidence(self):
        self._ev_visible = not self._ev_visible
        self._ev_panel.setVisible(self._ev_visible)
        self._ev_btn.setText(('▼' if self._ev_visible else '▶') + ' Evidence')

    def _toggle_recommendation(self):
        self._rec_visible = not self._rec_visible
        self._rec_panel.setVisible(self._rec_visible)
        self._rec_btn.setText(('▼' if self._rec_visible else '▶') + ' Recommendation')

    def _toggle_desc(self):
        self._desc_visible = not self._desc_visible
        self._desc_label.setVisible(self._desc_visible)
        self._desc_btn.setText(
            ('▼' if self._desc_visible else '▶') + ' What is this fault?'
        )


# ─── THRESHOLD EDITOR DIALOG ──────────────────────────────────────────────────

class ThresholdsDialog(QDialog):
    """
    Editable list of all diagnostic thresholds grouped by scenario.
    Returns updated dict via .get_values().
    """

    def __init__(self, current_thresholds: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle('⚙  Diagnostic Thresholds')
        self.setMinimumWidth(560)
        self.setMinimumHeight(520)
        self._spinboxes: dict[str, QDoubleSpinBox] = {}
        self._build_ui(current_thresholds)

    def _build_ui(self, current: dict):
        outer = QVBoxLayout(self)

        # Scrollable area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        vbox = QVBoxLayout(content)
        vbox.setSpacing(10)

        for scenario in SCENARIO_REGISTRY:
            if not scenario.DEFAULT_THRESHOLDS:
                continue
            grp = QGroupBox(f'{scenario.SCENARIO_ID} · {scenario.LABEL}')
            grp.setStyleSheet('QGroupBox { font-weight: bold; font-size: 11px; }')
            form = QFormLayout(grp)
            form.setSpacing(4)
            for key, default in scenario.DEFAULT_THRESHOLDS.items():
                val = current.get(key, default)
                sb = QDoubleSpinBox()
                sb.setDecimals(3)
                sb.setRange(-9999.0, 9999.0)
                sb.setValue(float(val))
                sb.setSingleStep(0.5)
                self._spinboxes[key] = sb
                # Format key as readable label
                display_key = key.replace('_', ' ').replace('f per', '°F/').replace('row', 'row')
                form.addRow(display_key, sb)
            vbox.addWidget(grp)

        vbox.addStretch()
        content.setLayout(vbox)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.RestoreDefaults
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        btns.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(
            self._reset_defaults
        )
        outer.addWidget(btns)

    def _reset_defaults(self):
        defaults = get_all_thresholds()
        for key, sb in self._spinboxes.items():
            if key in defaults:
                sb.setValue(float(defaults[key]))

    def get_values(self) -> dict:
        return {k: sb.value() for k, sb in self._spinboxes.items()}


# ─── CUSTOM SCENARIOS DIALOG ──────────────────────────────────────────────────

class CustomScenariosDialog(QDialog):
    """
    Dialog for creating, editing, and deleting custom diagnostic scenarios.

    Layout:
      Left panel: list of existing custom scenarios (clickable to select)
      Right panel: edit form for selected scenario
      Bottom: Save, Cancel buttons
    """

    def __init__(self, custom_scenarios_cfg: list, last_df=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Custom Diagnostic Scenarios')
        self.resize(900, 600)
        self._scenarios = [dict(s) for s in custom_scenarios_cfg]  # deep-copy
        self._last_df   = last_df
        self._current_idx = None
        self._build_ui()
        if self._scenarios:
            self._list.setCurrentRow(0)

    # ── UI ──────────────────────────────────────────────────────────────────

    def _build_ui(self):
        from PyQt6.QtWidgets import (
            QSplitter, QListWidget, QListWidgetItem, QFormLayout,
            QLineEdit, QSpinBox, QTextEdit, QScrollArea,
            QDialogButtonBox,
        )
        root = QVBoxLayout(self)

        # ── Splitter: list on left, form on right ───────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        # Left: scenario list
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.addWidget(QLabel('<b>Custom Scenarios</b>'))
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_select)
        left_layout.addWidget(self._list)
        btn_row = QHBoxLayout()
        self._add_btn = QPushButton('+ New')
        self._del_btn = QPushButton('Delete')
        self._del_btn.setEnabled(False)
        self._add_btn.clicked.connect(self._add_scenario)
        self._del_btn.clicked.connect(self._delete_scenario)
        btn_row.addWidget(self._add_btn)
        btn_row.addWidget(self._del_btn)
        left_layout.addLayout(btn_row)
        splitter.addWidget(left)

        # Right: edit form
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 4, 4, 4)
        right_layout.addWidget(QLabel('<b>Edit Scenario</b>'))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_container = QWidget()
        form_layout = QVBoxLayout(form_container)
        scroll.setWidget(form_container)
        right_layout.addWidget(scroll)

        # Basic fields
        basic = QGroupBox('Basic Info')
        fl = QFormLayout(basic)
        self._f_id    = QLineEdit(); fl.addRow('Scenario ID:', self._f_id)
        self._f_label = QLineEdit(); fl.addRow('Label:', self._f_label)
        self._f_comp  = QLineEdit(); self._f_comp.setText('Custom'); fl.addRow('Component:', self._f_comp)
        self._f_desc  = QTextEdit(); self._f_desc.setFixedHeight(60); fl.addRow('Description:', self._f_desc)
        self._f_win   = QSpinBox(); self._f_win.setRange(5, 200); self._f_win.setValue(20); fl.addRow('Window (rows):', self._f_win)
        form_layout.addWidget(basic)

        # Severity levels
        levels_grp = QGroupBox('Severity Levels (evaluated CRITICAL -> WARNING -> WATCH; first True fires)')
        lev_layout = QVBoxLayout(levels_grp)
        self._level_widgets = []
        for sev, color in [('CRITICAL', '#fce4e4'), ('WARNING', '#fef3e2'), ('WATCH', '#e3eeff')]:
            grp = QGroupBox(sev)
            grp.setStyleSheet(f'QGroupBox {{ background:{color}; }}')
            gfl = QFormLayout(grp)
            expr_edit = QLineEdit()
            expr_edit.setPlaceholderText('e.g.  S_H_lh_coil < 0.5 * S_H_rh_coil')
            summary_edit = QLineEdit()
            summary_edit.setPlaceholderText('One-line summary shown on the card when this fires')
            test_btn = QPushButton('Test')
            test_result = QLabel('')
            test_result.setWordWrap(True)
            test_btn.clicked.connect(lambda checked, e=expr_edit, r=test_result: self._test_expr(e, r))
            gfl.addRow('Expression:', expr_edit)
            gfl.addRow('', test_btn)
            gfl.addRow('Test result:', test_result)
            gfl.addRow('Summary text:', summary_edit)
            lev_layout.addWidget(grp)
            self._level_widgets.append({'severity': sev, 'expr': expr_edit, 'summary': summary_edit})
        form_layout.addWidget(levels_grp)

        # Recommendation
        rec_grp = QGroupBox('Recommendation')
        rec_fl = QFormLayout(rec_grp)
        self._f_rec = QTextEdit(); self._f_rec.setFixedHeight(80)
        self._f_rec.setPlaceholderText('Step 1: ...\nStep 2: ...')
        rec_fl.addRow('Steps:', self._f_rec)
        form_layout.addWidget(rec_grp)

        # Variable reference
        from PyQt6.QtWidgets import QListWidget as _LW
        var_grp = QGroupBox('Variable Reference  (column name -> expression variable)')
        var_grp.setCheckable(True)
        var_grp.setChecked(False)
        var_layout = QVBoxLayout(var_grp)
        self._var_table = _LW()
        self._var_table.setFixedHeight(140)
        self._var_search = QLineEdit()
        self._var_search.setPlaceholderText('Search columns...')
        self._var_search.textChanged.connect(self._filter_vars)
        var_layout.addWidget(self._var_search)
        var_layout.addWidget(self._var_table)
        self._populate_var_table('')
        form_layout.addWidget(var_grp)

        splitter.addWidget(right)
        splitter.setSizes([220, 680])

        # Save / Cancel
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        self._refresh_list()
        self._set_form_enabled(False)

    # ── Variable reference ───────────────────────────────────────────────────

    def _populate_var_table(self, filter_text: str = ''):
        self._var_table.clear()
        if self._last_df is None:
            self._var_table.addItem('(Load data first to see available columns)')
            return
        for col in sorted(self._last_df.columns):
            var = _sanitize_colname(col)
            text = f'{var}   <-   {col}'
            if filter_text.lower() in text.lower():
                self._var_table.addItem(text)

    def _filter_vars(self, text: str):
        self._populate_var_table(text)

    # ── Expression tester ────────────────────────────────────────────────────

    def _test_expr(self, expr_edit, result_label):
        import math as _math
        expr = expr_edit.text().strip()
        if not expr:
            result_label.setText('(empty expression)')
            result_label.setStyleSheet('')
            return
        if self._last_df is None:
            result_label.setText('No data loaded — run Calculations first.')
            result_label.setStyleSheet('color: #999;')
            return
        win = self._f_win.value()
        dfw = self._last_df.tail(win)
        ns = {}
        for col in dfw.columns:
            try:
                val = float(dfw[col].mean())
                if val == val:  # not NaN
                    ns[_sanitize_colname(col)] = val
            except Exception:
                pass
        ns.update({'abs': abs, 'min': min, 'max': max, 'round': round,
                   'sqrt': _math.sqrt, 'log': _math.log})
        try:
            result = eval(expr, {"__builtins__": {}}, ns)  # noqa: S307
            if isinstance(result, bool):
                text = f'Result: {"TRUE -> would fire" if result else "FALSE -> would not fire"}'
                color = '#cc0000' if result else '#007700'
            else:
                text = f'Result: {result:.4f}'
                color = '#444'
            result_label.setText(text)
            result_label.setStyleSheet(f'color: {color}; font-weight: bold;')
        except Exception as exc:
            result_label.setText(f'Error: {exc}')
            result_label.setStyleSheet('color: #cc0000;')

    # ── List management ──────────────────────────────────────────────────────

    def _refresh_list(self):
        self._list.clear()
        for s in self._scenarios:
            self._list.addItem(f"{s.get('id', '?')}  --  {s.get('label', '?')}")

    def _on_select(self, idx: int):
        if idx < 0 or idx >= len(self._scenarios):
            self._set_form_enabled(False)
            self._current_idx = None
            return
        self._current_idx = idx
        self._del_btn.setEnabled(True)
        self._set_form_enabled(True)
        cfg = self._scenarios[idx]
        self._f_id.setText(cfg.get('id', ''))
        self._f_label.setText(cfg.get('label', ''))
        self._f_comp.setText(cfg.get('component', 'Custom'))
        self._f_desc.setPlainText(cfg.get('description', ''))
        self._f_win.setValue(cfg.get('window_rows', 20))
        self._f_rec.setPlainText(cfg.get('recommendation', ''))
        levels_map = {lv['severity']: lv for lv in cfg.get('levels', [])}
        for lw in self._level_widgets:
            lv = levels_map.get(lw['severity'], {})
            lw['expr'].setText(lv.get('expression', ''))
            lw['summary'].setText(lv.get('summary', ''))

    def _set_form_enabled(self, enabled: bool):
        for w in [self._f_id, self._f_label, self._f_comp, self._f_win, self._f_desc, self._f_rec]:
            w.setEnabled(enabled)
        for lw in self._level_widgets:
            lw['expr'].setEnabled(enabled)
            lw['summary'].setEnabled(enabled)

    def _add_scenario(self):
        n = len(self._scenarios) + 1
        new_cfg = {
            'id': f'CUSTOM-{n}',
            'label': f'Custom Check {n}',
            'component': 'Custom',
            'description': '',
            'window_rows': 20,
            'levels': [],
            'recommendation': '',
        }
        self._scenarios.append(new_cfg)
        self._refresh_list()
        self._list.setCurrentRow(len(self._scenarios) - 1)

    def _delete_scenario(self):
        if self._current_idx is None:
            return
        from PyQt6.QtWidgets import QMessageBox
        name = self._scenarios[self._current_idx].get('label', '?')
        reply = QMessageBox.question(
            self, 'Delete Scenario', f'Delete "{name}"?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            del self._scenarios[self._current_idx]
            self._refresh_list()
            self._current_idx = None
            self._del_btn.setEnabled(False)
            self._set_form_enabled(False)

    def _commit_current(self):
        """Save form fields back to self._scenarios[_current_idx]."""
        if self._current_idx is None:
            return
        cfg = self._scenarios[self._current_idx]
        cfg['id']          = self._f_id.text().strip() or cfg['id']
        cfg['label']       = self._f_label.text().strip()
        cfg['component']   = self._f_comp.text().strip()
        cfg['description'] = self._f_desc.toPlainText().strip()
        cfg['window_rows'] = self._f_win.value()
        cfg['recommendation'] = self._f_rec.toPlainText().strip()
        levels = []
        for lw in self._level_widgets:
            expr = lw['expr'].text().strip()
            if expr:
                levels.append({
                    'severity':   lw['severity'],
                    'expression': expr,
                    'summary':    lw['summary'].text().strip(),
                })
        cfg['levels'] = levels
        # Refresh list item text
        if self._current_idx < self._list.count():
            self._list.item(self._current_idx).setText(
                f"{cfg.get('id', '?')}  --  {cfg.get('label', '?')}"
            )

    def _on_save(self):
        self._commit_current()
        self.accept()

    def get_scenarios_cfg(self) -> list:
        """Return the updated list of scenario config dicts."""
        return self._scenarios


# ─── CONDITION ROW ────────────────────────────────────────────────────────────

class ConditionRow(QWidget):
    """One condition row: [Column A v] [Function v] [Column B v] [Operator v] [Value] [x]
    Column B is only shown for two-column functions (diff_mean, abs_diff_mean, pressure_ratio).
    """

    changed = pyqtSignal()   # emitted when any field changes
    deleted = pyqtSignal()   # emitted when x clicked

    # Functions that operate on a single column
    ONE_COL_FUNCTIONS = {'mean', 'slope', 'std', 'last', 'pct_above', 'pct_below'}
    # Functions that require two columns (col A and col B)
    TWO_COL_FUNCTIONS = {'diff_mean', 'abs_diff_mean', 'pressure_ratio'}

    FUNCTIONS = [
        'mean', 'slope', 'std', 'last', 'pct_above', 'pct_below',
        'diff_mean', 'abs_diff_mean', 'pressure_ratio',
    ]

    # Human-readable display labels for the function dropdown
    FUNC_LABELS = {
        'mean':           'Mean',
        'slope':          'Slope',
        'std':            'Std Dev',
        'last':           'Last',
        'pct_above':      '% Above',
        'pct_below':      '% Below',
        'diff_mean':      'A \u2212 B (mean)',
        'abs_diff_mean':  '|A \u2212 B| (mean)',
        'pressure_ratio': 'Pressure Ratio',
    }

    OPERATORS = ['>', '<', '>=', '<=', '==', '!=']

    FUNC_TIPS = {
        'mean':           'Average value over window',
        'slope':          'Trend direction (linear regression slope)',
        'std':            'Standard deviation (detects oscillation)',
        'last':           'Most recent single reading',
        'pct_above':      '% of rows above threshold value',
        'pct_below':      '% of rows below threshold value',
        'diff_mean':      'A \u2212 B (mean): mean(col A) \u2212 mean(col B)',
        'abs_diff_mean':  '|A \u2212 B| (mean): abs(mean(col A) \u2212 mean(col B))',
        'pressure_ratio': 'Pressure Ratio: (mean(A)+14.696) / max(mean(B)+14.696, 0.1)',
    }

    def __init__(self, available_columns: list, column='', function='mean', column2='',
                 operator='>', value=0.0, parent=None):
        super().__init__(parent)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(4)

        # Column A dropdown — NOT editable, selection only
        self.col_combo = _NoWheelComboBox()
        self.col_combo.setMinimumWidth(155)
        self.col_combo.addItems(available_columns)
        if column:
            idx = self.col_combo.findText(column)
            if idx >= 0:
                self.col_combo.setCurrentIndex(idx)
        self.col_combo.setToolTip('Column A: data column / thermocouple to read')

        # Function dropdown — shows human-readable labels, stores raw function name as UserRole
        self.func_combo = _NoWheelComboBox()
        self.func_combo.setFixedWidth(135)
        for func in self.FUNCTIONS:
            self.func_combo.addItem(self.FUNC_LABELS.get(func, func), func)
        # Select by internal function name
        for i in range(self.func_combo.count()):
            if self.func_combo.itemData(i) == function:
                self.func_combo.setCurrentIndex(i)
                break
        # Per-item tooltips
        for i in range(self.func_combo.count()):
            fn = self.func_combo.itemData(i)
            self.func_combo.setItemData(i, self.FUNC_TIPS.get(fn, ''), Qt.ItemDataRole.ToolTipRole)
        self.func_combo.setToolTip('Statistical function to apply')

        # Column B dropdown — shown only for two-column functions
        self.col2_combo = _NoWheelComboBox()
        self.col2_combo.setMinimumWidth(155)
        self.col2_combo.addItems(available_columns)
        if column2:
            idx2 = self.col2_combo.findText(column2)
            if idx2 >= 0:
                self.col2_combo.setCurrentIndex(idx2)
        self.col2_combo.setToolTip('Column B: second column for two-column functions')
        # Show/hide based on initial function
        self.col2_combo.setVisible(function in self.TWO_COL_FUNCTIONS)

        # Operator dropdown
        self.op_combo = _NoWheelComboBox()
        self.op_combo.setFixedWidth(52)
        self.op_combo.addItems(self.OPERATORS)
        self.op_combo.setCurrentText(operator)
        self.op_combo.setToolTip('Comparison operator')

        # Value spinbox
        self.val_spin = QDoubleSpinBox()
        self.val_spin.setDecimals(4)
        self.val_spin.setRange(-999999, 999999)
        self.val_spin.setValue(float(value))
        self.val_spin.setFixedWidth(100)
        self.val_spin.setToolTip('Threshold value to compare against')

        # Delete button
        del_btn = QPushButton('x')
        del_btn.setFixedWidth(24)
        del_btn.setToolTip('Remove this condition')
        del_btn.setStyleSheet('color: #c0392b; font-weight: bold; border: none;')
        del_btn.clicked.connect(self.deleted.emit)

        row.addWidget(self.col_combo, 1)
        row.addWidget(self.func_combo)
        row.addWidget(self.col2_combo, 1)
        row.addWidget(self.op_combo)
        row.addWidget(self.val_spin)
        row.addWidget(del_btn)

        # Wire change signals
        self.col_combo.currentTextChanged.connect(lambda: self.changed.emit())
        self.func_combo.currentIndexChanged.connect(self._on_function_changed)
        self.func_combo.currentIndexChanged.connect(lambda: self.changed.emit())
        self.col2_combo.currentTextChanged.connect(lambda: self.changed.emit())
        self.op_combo.currentTextChanged.connect(lambda: self.changed.emit())
        self.val_spin.valueChanged.connect(lambda: self.changed.emit())

    def _on_function_changed(self):
        """Show or hide col2_combo when the function changes."""
        func = self.func_combo.currentData()
        self.col2_combo.setVisible(func in self.TWO_COL_FUNCTIONS)

    def to_dict(self) -> dict:
        func = self.func_combo.currentData() or 'mean'
        d = {
            'column':   self.col_combo.currentText(),
            'function': func,
            'operator': self.op_combo.currentText(),
            'value':    self.val_spin.value(),
        }
        if func in self.TWO_COL_FUNCTIONS:
            d['column2'] = self.col2_combo.currentText()
        return d

    @staticmethod
    def from_dict(d: dict, available_columns: list, parent=None):
        return ConditionRow(
            available_columns=available_columns,
            column=d.get('column', ''),
            function=d.get('function', 'mean'),
            column2=d.get('column2', ''),
            operator=d.get('operator', '>'),
            value=float(d.get('value', 0)),
            parent=parent,
        )


# ─── SEVERITY BLOCK ──────────────────────────────────────────────────────────

class SeverityBlock(QWidget):
    """Visual condition builder for one severity level (CRITICAL/WARNING/WATCH).

    Join modes:
      ALL      → JSON 'and'      (every condition must be true)
      ANY      → JSON 'or'       (at least one condition must be true)
      AT LEAST → JSON 'at_least' (at least min_count conditions must be true)
    """

    changed = pyqtSignal()

    _COLORS = {
        'CRITICAL': '#c0392b',
        'WARNING':  '#e67e22',
        'WATCH':    '#2980b9',
    }

    # Display label ↔ JSON value mappings
    _JOIN_DISPLAY_TO_JSON = {'ALL': 'and', 'ANY': 'or', 'AT LEAST': 'at_least'}
    _JOIN_JSON_TO_DISPLAY = {'and': 'ALL', 'or': 'ANY', 'at_least': 'AT LEAST'}

    def __init__(self, severity: str, available_columns: list,
                 conditions_cfg: dict = None, last_df=None,
                 parent=None):
        super().__init__(parent)
        self._severity = severity
        self._available_columns = available_columns
        self._last_df = last_df
        self._rows: list[ConditionRow] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(2)

        # ── Header ──
        color = self._COLORS.get(severity, '#333')
        hdr = QLabel(f'-- {severity} --')
        hdr.setStyleSheet(f'color: {color}; font-weight: bold; font-size: 11px;')
        layout.addWidget(hdr)

        # ── Rows container ──
        self._rows_container = QVBoxLayout()
        self._rows_container.setSpacing(2)
        layout.addLayout(self._rows_container)

        # ── Footer: Join + [min_count] + Add + Test ──
        foot = QHBoxLayout()
        foot.setSpacing(6)

        join_lbl = QLabel('Join:')
        join_lbl.setStyleSheet('font-size: 10px; color: #666;')

        self.join_combo = _NoWheelComboBox()
        self.join_combo.setFixedWidth(82)
        self.join_combo.addItems(['ALL', 'ANY', 'AT LEAST'])
        self.join_combo.setToolTip(
            'ALL: every condition must be true\n'
            'ANY: at least one condition must be true\n'
            'AT LEAST: specify minimum number of conditions that must be true'
        )

        # AT LEAST count spinner (visible only when AT LEAST is selected)
        self.min_count_spin = QSpinBox()
        self.min_count_spin.setRange(1, 20)
        self.min_count_spin.setValue(1)
        self.min_count_spin.setFixedWidth(44)
        self.min_count_spin.setToolTip('Minimum number of conditions that must be true')

        self.of_label = QLabel('of 0')
        self.of_label.setStyleSheet('font-size: 10px; color: #666;')

        # Initially hidden — only show for AT LEAST
        self.min_count_spin.setVisible(False)
        self.of_label.setVisible(False)

        add_btn = QPushButton('+ Add')
        add_btn.setFixedWidth(55)
        add_btn.setToolTip('Add a new condition row')
        add_btn.clicked.connect(self._add_empty_row)

        self.test_btn = QPushButton('▶ Test')
        self.test_btn.setFixedWidth(55)
        self.test_btn.setToolTip('Test this severity level against the latest data')
        self.test_btn.clicked.connect(self._test)

        foot.addWidget(join_lbl)
        foot.addWidget(self.join_combo)
        foot.addWidget(self.min_count_spin)
        foot.addWidget(self.of_label)
        foot.addWidget(add_btn)
        foot.addStretch()
        foot.addWidget(self.test_btn)
        layout.addLayout(foot)

        # Wire join combo
        self.join_combo.currentTextChanged.connect(self._on_join_changed)
        self.join_combo.currentTextChanged.connect(lambda: self.changed.emit())
        self.min_count_spin.valueChanged.connect(lambda: self.changed.emit())

        # Load initial conditions
        if conditions_cfg:
            join_val = conditions_cfg.get('join', 'and')
            join_display = self._JOIN_JSON_TO_DISPLAY.get(join_val, 'ALL')
            self.join_combo.setCurrentText(join_display)
            if join_val == 'at_least':
                self.min_count_spin.setValue(conditions_cfg.get('min_count', 1))
            for cond in conditions_cfg.get('conditions', []):
                self._add_row(cond)
        self._update_of_label()
        self._on_join_changed(self.join_combo.currentText())

    def _on_join_changed(self, display_text: str):
        """Show/hide AT LEAST spinner based on join mode."""
        is_at_least = (display_text == 'AT LEAST')
        self.min_count_spin.setVisible(is_at_least)
        self.of_label.setVisible(is_at_least)

    def _update_of_label(self):
        self.of_label.setText(f'of {len(self._rows)}')

    def _add_row(self, cond_dict: dict = None):
        row = ConditionRow.from_dict(
            cond_dict or {},
            available_columns=self._available_columns,
            parent=self,
        )
        row.changed.connect(self.changed.emit)
        row.deleted.connect(lambda r=row: self._remove_row(r))
        self._rows.append(row)
        self._rows_container.addWidget(row)
        self._update_of_label()

    def _add_empty_row(self):
        self._add_row({'column': self._available_columns[0] if self._available_columns else '',
                       'function': 'mean', 'operator': '>', 'value': 0})
        self.changed.emit()

    def _remove_row(self, row: ConditionRow):
        self._rows.remove(row)
        self._rows_container.removeWidget(row)
        row.deleteLater()
        self._update_of_label()
        self.changed.emit()

    def to_dict(self) -> dict:
        """Return structured conditions dict for this severity."""
        conditions = [r.to_dict() for r in self._rows]
        if not conditions:
            return {}
        join_display = self.join_combo.currentText()
        join_val = self._JOIN_DISPLAY_TO_JSON.get(join_display, 'and')
        d = {
            'join': join_val,
            'conditions': conditions,
        }
        if join_val == 'at_least':
            d['min_count'] = self.min_count_spin.value()
        return d

    def _test(self):
        """Evaluate this severity's conditions against the last data window."""
        from PyQt6.QtWidgets import QMessageBox
        cfg = self.to_dict()
        if not cfg:
            QMessageBox.information(self, 'Test', f'{self._severity}: No conditions defined.')
            return

        if self._last_df is None or self._last_df.empty:
            QMessageBox.warning(self, 'Test', 'No data loaded — cannot test.')
            return

        try:
            from diagnostics_engine import _conditions_to_expr, _make_expression_namespace
            expr_str = _conditions_to_expr(cfg)
            if not expr_str:
                QMessageBox.information(self, 'Test', 'Empty expression.')
                return

            ns = _make_expression_namespace(self._last_df)
            result = eval(expr_str, {"__builtins__": {}}, ns)  # noqa: S307

            # Build value display (supports one- and two-column functions)
            vals = []
            for cond in cfg.get('conditions', []):
                col  = cond.get('column', '')
                col2 = cond.get('column2', '')
                func = cond.get('function', 'mean')
                fn   = ns.get(func)
                if fn and callable(fn):
                    try:
                        if col2:
                            v = fn(col, col2)
                            vals.append(f'  {func}({col}, {col2}) = {v:.4f}')
                        else:
                            v = fn(col)
                            vals.append(f'  {func}({col}) = {v:.4f}')
                    except Exception:
                        col_display = f'{col}, {col2}' if col2 else col
                        vals.append(f'  {func}({col_display}) = ERROR')

            status = 'FIRES ✓' if result else 'Does NOT fire ✗'
            msg = (f'{self._severity}: {status}\n\n'
                   f'Expression: {expr_str}\n\n'
                   f'Values:\n' + '\n'.join(vals))
            QMessageBox.information(self, f'Test — {self._severity}', msg)
        except Exception as exc:
            QMessageBox.warning(self, 'Test Error', f'Evaluation failed:\n{exc}')


# ─── RULES DIALOG ─────────────────────────────────────────────────────────────

class RulesDialog(QDialog):
    """Unified rules manager — shows ALL diagnostic rules (built-in + custom) in one place."""

    recalc_requested = pyqtSignal(object, object)  # (rules_config dict, custom_cfg list)

    def __init__(self, rules_config: dict, custom_scenarios_cfg: list,
                 last_df=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Diagnostic Rules')
        self.setMinimumSize(980, 640)
        self.resize(1060, 700)

        import copy
        self._rules_config = copy.deepcopy(rules_config or {'version': '1.0', 'scenario_overrides': {}})
        self._custom_cfg   = copy.deepcopy(custom_scenarios_cfg or [])
        self._last_df      = last_df
        self._current_id   = None   # scenario ID currently shown on right

        self._build_ui()
        self._populate_list()

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        # ── Title bar description ──
        desc = QLabel(
            'All diagnostic rules are listed below. '
            'Select a rule to view its description, enable/disable it, '
            'control which system configurations it applies to, and adjust thresholds.'
        )
        desc.setWordWrap(True)
        desc.setStyleSheet('color: #555; font-size: 11px; margin-bottom: 4px;')
        root.addWidget(desc)

        # ── Main split ──
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left: list ──
        left = QWidget()
        lv   = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 4, 0)

        lbl_list = QLabel('Rules')
        lbl_list.setStyleSheet('font-weight: bold; font-size: 12px;')
        lv.addWidget(lbl_list)

        self._list = QListWidget()
        self._list.setMinimumWidth(260)
        self._list.currentItemChanged.connect(self._on_select)
        lv.addWidget(self._list)

        # Add custom rule button
        add_btn = QPushButton('+ Add Custom Rule')
        add_btn.clicked.connect(self._add_custom)
        lv.addWidget(add_btn)

        splitter.addWidget(left)

        # ── Right: detail ──
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        self._right_container = QWidget()
        self._right_layout    = QVBoxLayout(self._right_container)
        self._right_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        right_scroll.setWidget(self._right_container)

        splitter.addWidget(right_scroll)
        splitter.setSizes([280, 720])

        root.addWidget(splitter, 1)

        # ── Footer ──
        foot = QVBoxLayout()

        # Status label (shows feedback after Apply & Preview)
        self._preview_status = QLabel('')
        self._preview_status.setStyleSheet('font-size: 10pt; color: #555; padding: 2px 0;')
        self._preview_status.setVisible(False)
        foot.addWidget(self._preview_status)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._apply_preview_btn = QPushButton('▶  Apply & Preview')
        self._apply_preview_btn.setToolTip(
            'Apply current rule changes and re-run diagnostics without closing this dialog'
        )
        self._apply_preview_btn.setStyleSheet(
            'QPushButton { background: #2980b9; color: white; font-weight: bold;'
            ' padding: 4px 12px; border-radius: 4px; }'
            'QPushButton:hover { background: #3498db; }'
            'QPushButton:disabled { background: #aaa; }'
        )
        self._apply_preview_btn.clicked.connect(self._on_apply_preview)

        cancel_btn = QPushButton('Cancel')
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton('Save All')
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._on_save)

        btn_row.addWidget(self._apply_preview_btn)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        foot.addLayout(btn_row)
        root.addLayout(foot)

    # ── List population ────────────────────────────────────────────────────────

    def _populate_list(self):
        self._list.clear()
        _overrides = self._rules_config.get('rules', self._rules_config.get('scenario_overrides', {}))

        # Group built-in scenarios by component
        _by_comp: dict = {}
        for s in SCENARIO_REGISTRY:
            _by_comp.setdefault(s.COMPONENT, []).append(s)

        for comp, scenarios in _by_comp.items():
            # Component header (non-selectable separator)
            hdr = QListWidgetItem(f'  {comp}')
            hdr.setFlags(Qt.ItemFlag.NoItemFlags)
            hdr.setBackground(QColor('#e8e8e8'))
            font = hdr.font(); font.setBold(True); font.setPointSize(9)
            hdr.setFont(font)
            self._list.addItem(hdr)

            for s in scenarios:
                ovr     = _overrides.get(s.SCENARIO_ID, {})
                enabled = ovr.get('enabled', s.ENABLED)
                dot     = '●' if enabled else '○'
                item    = QListWidgetItem(f'    {dot}  {s.SCENARIO_ID}  {s.LABEL}')
                item.setData(Qt.ItemDataRole.UserRole, ('builtin', s.SCENARIO_ID))
                item.setForeground(QColor('#1a7a1a') if enabled else QColor('#888'))
                self._list.addItem(item)

        # Custom rules section
        if self._custom_cfg:
            hdr2 = QListWidgetItem('  Custom Rules')
            hdr2.setFlags(Qt.ItemFlag.NoItemFlags)
            hdr2.setBackground(QColor('#e8e8e8'))
            font2 = hdr2.font(); font2.setBold(True); font2.setPointSize(9)
            hdr2.setFont(font2)
            self._list.addItem(hdr2)

            for cfg in self._custom_cfg:
                enabled = cfg.get('enabled', True)
                dot     = '●' if enabled else '○'
                item    = QListWidgetItem(f'    {dot}  {cfg.get("id","?")}  {cfg.get("label","")}')
                item.setData(Qt.ItemDataRole.UserRole, ('custom', cfg.get('id')))
                item.setForeground(QColor('#1a7a1a') if enabled else QColor('#888'))
                self._list.addItem(item)

    def _refresh_list_item(self, scenario_id: str, enabled: bool):
        """Update dot colour for a list item without rebuilding the whole list."""
        for i in range(self._list.count()):
            item = self._list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            if data and data[1] == scenario_id:
                dot  = '●' if enabled else '○'
                # Rebuild text keeping same format
                text = item.text()
                # Replace the dot character (first ● or ○)
                for old in ('●', '○'):
                    text = text.replace(old, dot, 1)
                item.setText(text)
                item.setForeground(QColor('#1a7a1a') if enabled else QColor('#888'))
                break

    # ── Selection handler ──────────────────────────────────────────────────────

    def _on_select(self, current, _previous):
        if current is None:
            return
        data = current.data(Qt.ItemDataRole.UserRole)
        if data is None:
            return   # separator row
        kind, sid = data
        self._current_id = sid
        if kind == 'builtin':
            s = _SCENARIO_BY_ID.get(sid)
            if s:
                self._show_builtin(s)
        else:
            cfg = next((c for c in self._custom_cfg if c.get('id') == sid), None)
            if cfg:
                self._show_custom(cfg)

    # ── Built-in detail panel ──────────────────────────────────────────────────

    def _clear_right(self):
        """Remove all widgets and nested layouts from the right panel."""
        def clear_layout(layout):
            while layout.count():
                item = layout.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()
                else:
                    sub = item.layout()
                    if sub:
                        clear_layout(sub)
                        sub.deleteLater()
        clear_layout(self._right_layout)

    def _show_builtin(self, scenario):
        self._clear_right()
        ovr = self._rules_config.get('rules', {}).get(scenario.SCENARIO_ID, {})
        # ALSO check old 'scenario_overrides' format for backward compat
        if not ovr:
            ovr = self._rules_config.get('scenario_overrides', {}).get(scenario.SCENARIO_ID, {})

        # ── Header (keep) ──
        title = QLabel(f'{scenario.SCENARIO_ID} — {scenario.LABEL}')
        title.setStyleSheet('font-size: 14px; font-weight: bold; margin-bottom: 2px;')
        self._right_layout.addWidget(title)

        comp_lbl = QLabel(f'Component: {scenario.COMPONENT}')
        comp_lbl.setStyleSheet('color: #555; font-size: 11px; margin-bottom: 6px;')
        self._right_layout.addWidget(comp_lbl)

        # ── Description (keep) ──
        if scenario.DESCRIPTION:
            desc_box = QLabel(scenario.DESCRIPTION)
            desc_box.setWordWrap(True)
            desc_box.setStyleSheet(
                'background: #f5f5f5; border: 1px solid #ddd; border-radius: 4px;'
                'padding: 8px; font-size: 11px; color: #333; margin-bottom: 8px;'
            )
            self._right_layout.addWidget(desc_box)

        sep1 = QFrame(); sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setStyleSheet('color: #ddd;')
        self._right_layout.addWidget(sep1)

        # ── Conditions section header ──
        cond_header = QHBoxLayout()
        cond_lbl = QLabel('Conditions')
        cond_lbl.setStyleSheet('font-weight: bold; font-size: 12px;')
        cond_header.addWidget(cond_lbl)

        cond_header.addStretch()
        win_lbl = QLabel('Window:')
        win_lbl.setStyleSheet('font-size: 11px; color: #555;')
        win_spin = QSpinBox()
        win_spin.setRange(1, 10000)
        win_spin.setValue(int(ovr.get('window_rows', getattr(scenario, 'DEFAULT_THRESHOLDS', {}).get('trend_window_rows', 20))))
        win_spin.setFixedWidth(70)
        win_spin.setToolTip('Number of recent data rows to analyze')
        win_rows_lbl = QLabel('rows')
        win_rows_lbl.setStyleSheet('font-size: 11px; color: #555;')
        cond_header.addWidget(win_lbl)
        cond_header.addWidget(win_spin)
        cond_header.addWidget(win_rows_lbl)
        self._right_layout.addLayout(cond_header)

        # ── Get available columns from data + computed columns ──
        if self._last_df is not None and not self._last_df.empty:
            available_columns = list(self._last_df.columns)
        else:
            available_columns = []
        # Also include any user-defined computed columns
        for cc_name in self._rules_config.get('computed_columns', {}).keys():
            if cc_name not in available_columns:
                available_columns.append(cc_name)
        available_columns = sorted(available_columns)

        # ── Get current expressions (from rules_config or defaults) ──
        _default_expr = getattr(scenario, 'DEFAULT_EXPRESSIONS', {})
        expressions = ovr.get('expressions', _default_expr)

        # ── Python-only rules (RF-4, HG-1, HG-2): no editable expressions ──
        if not _default_expr and not expressions:
            note = QLabel(
                '⚙  This rule uses advanced calculations (CoolProp / defrost detection)\n'
                'that cannot be expressed as simple column conditions.\n'
                'It runs automatically in Python mode — no visual editor available.\n'
                'Thresholds below still apply and can be adjusted if needed.'
            )
            note.setWordWrap(True)
            note.setStyleSheet(
                'background: #fff8e1; border: 1px solid #f0c040; border-radius: 4px;'
                'padding: 10px; font-size: 11px; color: #555; margin: 6px 0;'
            )
            self._right_layout.addWidget(note)
            # Skip the condition builder — jump straight to Enabled + Applies-to
            sep_skip = QFrame(); sep_skip.setFrameShape(QFrame.Shape.HLine)
            self._right_layout.addWidget(sep_skip)
            # Add enabled + applies-to only and return
            _en_chk_s = QCheckBox('Enabled')
            _en_chk_s.setChecked(ovr.get('enabled', scenario.ENABLED))
            self._right_layout.addWidget(_en_chk_s)
            self._right_layout.addStretch()
            def _commit_simple(*_):
                self._rules_config.setdefault('rules', {})[scenario.SCENARIO_ID] = {
                    'enabled': _en_chk_s.isChecked(),
                    'applies_to': getattr(scenario, 'APPLIES_TO', ['cassette','modular','non-modular']),
                    'window_rows': 20,
                    'expressions': {},
                }
                self._refresh_list_item(scenario.SCENARIO_ID, _en_chk_s.isChecked())
            _en_chk_s.stateChanged.connect(_commit_simple)
            return

        # ── Visual condition builders for each severity ──
        severity_blocks = {}

        # Get last N rows for testing
        _win = int(ovr.get('window_rows', 20))
        _last_window = self._last_df.tail(_win) if self._last_df is not None else None

        for sev in ('CRITICAL', 'WARNING', 'WATCH'):
            sev_cfg = expressions.get(sev, {})
            block = SeverityBlock(
                severity=sev,
                available_columns=available_columns,
                conditions_cfg=sev_cfg,
                last_df=_last_window,
                parent=self._right_container,
            )
            severity_blocks[sev] = block
            self._right_layout.addWidget(block)

        # ── Reset to defaults ──
        reset_btn = QPushButton('Reset to defaults')
        reset_btn.setFixedWidth(150)
        reset_btn.setToolTip('Reset all conditions to the built-in defaults')
        self._right_layout.addWidget(reset_btn)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet('color: #ddd; margin-top: 8px;')
        self._right_layout.addWidget(sep2)

        # ── Enabled toggle ──
        en_row = QHBoxLayout()
        en_chk = QCheckBox('Enabled')
        _current_enabled = ovr.get('enabled', scenario.ENABLED)
        en_chk.setChecked(_current_enabled)
        en_chk.setToolTip('Uncheck to suppress this rule from all diagnostic runs')
        en_row.addWidget(en_chk)
        en_row.addStretch()
        self._right_layout.addLayout(en_row)

        # ── Applies to ──
        at_lbl = QLabel('Applies to:')
        at_lbl.setStyleSheet('font-weight: bold; margin-top: 4px;')
        self._right_layout.addWidget(at_lbl)

        _default_applies = getattr(scenario, 'APPLIES_TO', ['cassette', 'modular', 'non-modular'])
        _current_applies = ovr.get('applies_to', _default_applies)

        at_row = QHBoxLayout()
        chk_cassette   = QCheckBox('Cassette')
        chk_modular    = QCheckBox('Shared -- Modular (2+ modules)')
        chk_nonmodular = QCheckBox('Shared -- Non-modular (1 module)')
        chk_cassette.setChecked('cassette'     in _current_applies)
        chk_modular.setChecked('modular'       in _current_applies)
        chk_nonmodular.setChecked('non-modular' in _current_applies)
        at_row.addWidget(chk_cassette)
        at_row.addWidget(chk_modular)
        at_row.addWidget(chk_nonmodular)
        at_row.addStretch()
        self._right_layout.addLayout(at_row)

        self._right_layout.addStretch()

        # ── Commit closure ──
        def _commit(*_):
            _applies = []
            if chk_cassette.isChecked():   _applies.append('cassette')
            if chk_modular.isChecked():    _applies.append('modular')
            if chk_nonmodular.isChecked(): _applies.append('non-modular')

            _enabled_now = en_chk.isChecked()

            # Build expressions from visual severity blocks
            _expr = {}
            for sev, block in severity_blocks.items():
                d = block.to_dict()
                if d:
                    _expr[sev] = d

            self._rules_config.setdefault('rules', {})[scenario.SCENARIO_ID] = {
                'enabled':     _enabled_now,
                'applies_to':  _applies,
                'window_rows': win_spin.value(),
                'expressions': _expr,
            }
            self._refresh_list_item(scenario.SCENARIO_ID, _enabled_now)

        # Wire all change signals
        en_chk.stateChanged.connect(_commit)
        chk_cassette.stateChanged.connect(_commit)
        chk_modular.stateChanged.connect(_commit)
        chk_nonmodular.stateChanged.connect(_commit)
        win_spin.valueChanged.connect(_commit)
        for block in severity_blocks.values():
            block.changed.connect(_commit)

        # Reset to defaults
        def _reset():
            default_expr = getattr(scenario, 'DEFAULT_EXPRESSIONS', {})
            # Re-show the builtin with defaults
            self._rules_config.get('rules', {}).pop(scenario.SCENARIO_ID, None)
            self._show_builtin(scenario)  # re-render with defaults
        reset_btn.clicked.connect(_reset)

    # ── Custom rule detail panel ───────────────────────────────────────────────

    def _show_custom(self, cfg: dict):
        self._clear_right()

        sid = cfg.get('id', '?')
        title = QLabel(f'{sid} — {cfg.get("label", "")}')
        title.setStyleSheet('font-size: 14px; font-weight: bold; margin-bottom: 6px;')
        self._right_layout.addWidget(title)

        # Re-use the expression editor from CustomScenariosDialog by embedding a mini form
        form = QFormLayout()

        name_edit = QLineEdit(cfg.get('label', ''))
        comp_edit = QLineEdit(cfg.get('component', ''))
        desc_edit = QLineEdit(cfg.get('description', ''))
        win_spin  = QSpinBox()
        win_spin.setRange(1, 10000); win_spin.setValue(cfg.get('window_rows', 20))

        form.addRow('Name:', name_edit)
        form.addRow('Component:', comp_edit)
        form.addRow('Description:', desc_edit)
        form.addRow('Window (rows):', win_spin)

        en_chk = QCheckBox('Enabled')
        en_chk.setChecked(cfg.get('enabled', True))
        form.addRow('', en_chk)

        self._right_layout.addLayout(form)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet('color: #ddd; margin: 6px 0;')
        self._right_layout.addWidget(sep)

        levels_lbl = QLabel('Severity levels (expressions evaluated top-to-bottom; first True fires):')
        levels_lbl.setStyleSheet('font-weight: bold; margin-bottom: 4px;')
        self._right_layout.addWidget(levels_lbl)

        _existing_levels = {lv['severity']: lv['expression'] for lv in cfg.get('levels', [])}
        expr_edits: dict = {}
        for sev, colour in [('CRITICAL', '#c0392b'), ('WARNING', '#e67e22'), ('WATCH', '#2980b9')]:
            lbl2 = QLabel(f'{sev}:')
            lbl2.setStyleSheet(f'color: {colour}; font-weight: bold;')
            expr = QLineEdit(_existing_levels.get(sev, ''))
            expr.setPlaceholderText(f'e.g. S_H_total > 30  (leave blank to skip)')
            expr_edits[sev] = expr
            row2 = QHBoxLayout()
            row2.addWidget(lbl2, 0)
            row2.addWidget(expr, 1)
            self._right_layout.addLayout(row2)

        del_btn = QPushButton('Delete this custom rule')
        del_btn.setStyleSheet('color: #c0392b;')
        self._right_layout.addWidget(del_btn)
        self._right_layout.addStretch()

        def _commit_custom(*_):
            cfg['label']       = name_edit.text().strip() or cfg['label']
            cfg['component']   = comp_edit.text().strip() or cfg.get('component', 'Custom')
            cfg['description'] = desc_edit.text().strip()
            cfg['window_rows'] = win_spin.value()
            cfg['enabled']     = en_chk.isChecked()
            cfg['levels']      = [
                {'severity': sev, 'expression': expr_edits[sev].text().strip()}
                for sev in ('CRITICAL', 'WARNING', 'WATCH')
                if expr_edits[sev].text().strip()
            ]
            self._refresh_list_item(sid, cfg['enabled'])

        name_edit.editingFinished.connect(_commit_custom)
        comp_edit.editingFinished.connect(_commit_custom)
        desc_edit.editingFinished.connect(_commit_custom)
        win_spin.valueChanged.connect(_commit_custom)
        en_chk.stateChanged.connect(_commit_custom)
        for e in expr_edits.values():
            e.editingFinished.connect(_commit_custom)

        def _delete():
            from PyQt6.QtWidgets import QMessageBox
            if QMessageBox.question(self, 'Delete rule',
                    f'Delete custom rule "{cfg.get("label","")}"?',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                ) == QMessageBox.StandardButton.Yes:
                self._custom_cfg = [c for c in self._custom_cfg if c.get('id') != sid]
                self._populate_list()
                self._clear_right()
        del_btn.clicked.connect(_delete)

    # ── Add custom ─────────────────────────────────────────────────────────────

    def _add_custom(self):
        import uuid
        new_id = f'CUSTOM-{str(uuid.uuid4())[:6].upper()}'
        cfg = {
            'id': new_id, 'label': 'New Rule', 'component': 'Custom',
            'description': '', 'enabled': True, 'window_rows': 20,
            'levels': [],
        }
        self._custom_cfg.append(cfg)
        self._populate_list()
        # Select the new item
        for i in range(self._list.count()):
            item = self._list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            if data and data[1] == new_id:
                self._list.setCurrentItem(item)
                break

    # ── Save ───────────────────────────────────────────────────────────────────

    def _on_apply_preview(self):
        """Emit recalc_requested so the parent re-runs diagnostics with current settings."""
        import copy
        self._apply_preview_btn.setEnabled(False)
        self._apply_preview_btn.setText('Running...')
        self.update_preview_status('Running diagnostics…', '#2980b9')
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        self.recalc_requested.emit(
            copy.deepcopy(self._rules_config),
            copy.deepcopy(self._custom_cfg),
        )

    def update_preview_status(self, msg: str, color: str = '#27ae60'):
        """Called by the parent to report back the result of a preview run."""
        self._preview_status.setText(msg)
        self._preview_status.setStyleSheet(
            f'font-size: 10pt; color: {color}; padding: 2px 0; font-style: italic;'
        )
        self._preview_status.setVisible(bool(msg))
        self._apply_preview_btn.setEnabled(True)
        self._apply_preview_btn.setText('▶  Apply & Preview')

    def _on_save(self):
        self.accept()

    def get_results(self):
        """Return (rules_config dict, custom_scenarios_cfg list)."""
        return self._rules_config, self._custom_cfg


# ─── COMPUTED COLUMN EDITOR ───────────────────────────────────────────────────

class ComputedColumnEditor(QDialog):
    """Sub-dialog to create or edit a user-defined computed column."""

    TYPES = ['average', 'max', 'min', 'spread', 'difference', 'sum']
    TYPE_LABELS = {
        'average':    'Average',
        'max':        'Max',
        'min':        'Min',
        'spread':     'Spread  (Max \u2212 Min)',
        'difference': 'Difference  (A \u2212 B)',
        'sum':        'Sum',
    }
    TYPE_TIPS = {
        'average':    'Row-by-row average of all selected source columns',
        'max':        'Row-by-row maximum of all selected source columns',
        'min':        'Row-by-row minimum of all selected source columns',
        'spread':     'Row-by-row Max \u2212 Min of selected source columns',
        'difference': 'First column minus second column (exactly 2 sources required)',
        'sum':        'Row-by-row sum of all selected source columns',
    }

    def __init__(self, existing_name, existing_cfg, data_columns, parent=None):
        super().__init__(parent)
        self.setWindowTitle(
            'Define Computed Column' if not existing_name else f'Edit: {existing_name}'
        )
        self.setMinimumSize(440, 520)
        self.resize(460, 560)
        self._data_columns = sorted(data_columns)
        self._result_name = None
        self._result_cfg  = None
        self._build_ui(existing_name, existing_cfg or {})

    def _build_ui(self, name, cfg):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        form = QFormLayout()
        form.setSpacing(8)

        self._name_edit = QLineEdit(name or '')
        self._name_edit.setPlaceholderText('e.g. SH_avg_coil')
        form.addRow('Name:', self._name_edit)

        self._type_combo = QComboBox()
        for t in self.TYPES:
            self._type_combo.addItem(self.TYPE_LABELS.get(t, t), t)
        # Set current type
        current_type = cfg.get('type', 'average')
        for i in range(self._type_combo.count()):
            if self._type_combo.itemData(i) == current_type:
                self._type_combo.setCurrentIndex(i)
                break
        for i in range(self._type_combo.count()):
            t = self._type_combo.itemData(i)
            self._type_combo.setItemData(i, self.TYPE_TIPS.get(t, ''), Qt.ItemDataRole.ToolTipRole)
        self._type_combo.currentIndexChanged.connect(self._update_type_hint)
        form.addRow('Type:', self._type_combo)

        root.addLayout(form)

        self._type_hint = QLabel('')
        self._type_hint.setStyleSheet('color: #555; font-size: 10px; font-style: italic;')
        self._type_hint.setWordWrap(True)
        root.addWidget(self._type_hint)

        src_lbl = QLabel('Source Columns (select 2 or more):')
        src_lbl.setStyleSheet('font-weight: bold; margin-top: 4px;')
        root.addWidget(src_lbl)

        self._src_filter = QLineEdit()
        self._src_filter.setPlaceholderText('🔍  Filter source columns…')
        self._src_filter.textChanged.connect(self._filter_sources)
        root.addWidget(self._src_filter)

        self._src_list = QListWidget()
        self._src_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        selected_sources = cfg.get('sources', [])
        for col in self._data_columns:
            item = QListWidgetItem(col)
            if col in selected_sources:
                item.setSelected(True)
            self._src_list.addItem(item)
        root.addWidget(self._src_list, 1)

        desc_lbl = QLabel('Description (optional):')
        root.addWidget(desc_lbl)
        self._desc_edit = QLineEdit(cfg.get('description', ''))
        self._desc_edit.setPlaceholderText('e.g. Average of left and right coil superheats')
        root.addWidget(self._desc_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._update_type_hint()

    def _update_type_hint(self):
        t = self._type_combo.currentData()
        self._type_hint.setText(self.TYPE_TIPS.get(t, ''))

    def _filter_sources(self, text):
        text = text.lower()
        for i in range(self._src_list.count()):
            item = self._src_list.item(i)
            item.setHidden(bool(text and text not in item.text().lower()))

    def _on_accept(self):
        from PyQt6.QtWidgets import QMessageBox
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, 'Validation', 'Column name cannot be empty.')
            return
        selected = [
            self._src_list.item(i).text()
            for i in range(self._src_list.count())
            if self._src_list.item(i).isSelected()
        ]
        if len(selected) < 2:
            QMessageBox.warning(self, 'Validation', 'Select at least 2 source columns.')
            return
        ctype = self._type_combo.currentData()
        if ctype == 'difference' and len(selected) != 2:
            QMessageBox.warning(self, 'Validation', '"Difference" type requires exactly 2 source columns.')
            return
        self._result_name = name
        self._result_cfg  = {
            'type':        ctype,
            'sources':     selected,
            'description': self._desc_edit.text().strip(),
        }
        self.accept()

    def get_result(self):
        """Return (name, cfg) if accepted, (None, None) otherwise."""
        return self._result_name, self._result_cfg


# ─── COLUMN MANAGER DIALOG ────────────────────────────────────────────────────

class ColumnManagerDialog(QDialog):
    """Two-section dialog:
    1. Raw Sensor Columns — read-only reference table with descriptions
    2. Computed Columns   — user-created columns that appear in rule dropdowns
    """

    def __init__(self, rules_config: dict, data_columns: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Column Manager')
        self.setMinimumSize(800, 580)
        self.resize(880, 640)

        import copy
        self._rules_config  = copy.deepcopy(rules_config or {})
        self._data_columns  = sorted(data_columns)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # ── Raw Sensor Columns ──────────────────────────────────────────────
        raw_grp = QGroupBox('Raw Sensor Columns  (read-only reference)')
        raw_lay = QVBoxLayout(raw_grp)

        filter_row = QHBoxLayout()
        filter_lbl = QLabel('🔍')
        self._raw_filter = QLineEdit()
        self._raw_filter.setPlaceholderText('Filter columns…')
        self._raw_filter.textChanged.connect(lambda t: self._populate_raw_table(t))
        filter_row.addWidget(filter_lbl)
        filter_row.addWidget(self._raw_filter, 1)
        raw_lay.addLayout(filter_row)

        self._raw_table = QTableWidget()
        self._raw_table.setColumnCount(3)
        self._raw_table.setHorizontalHeaderLabels(['Column Name', 'Description', 'Unit'])
        self._raw_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._raw_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._raw_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._raw_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._raw_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._raw_table.verticalHeader().setVisible(False)
        self._raw_table.setAlternatingRowColors(True)
        self._raw_table.setMinimumHeight(180)
        raw_lay.addWidget(self._raw_table)

        root.addWidget(raw_grp, 2)

        # ── Computed Columns ────────────────────────────────────────────────
        comp_grp = QGroupBox('Computed Columns  (user-defined — available in rule condition dropdowns)')
        comp_lay = QVBoxLayout(comp_grp)

        self._comp_table = QTableWidget()
        self._comp_table.setColumnCount(4)
        self._comp_table.setHorizontalHeaderLabels(['Name', 'Type', 'Source Columns', ''])
        self._comp_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._comp_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._comp_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._comp_table.setColumnWidth(3, 72)
        self._comp_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._comp_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._comp_table.verticalHeader().setVisible(False)
        self._comp_table.setMinimumHeight(120)
        comp_lay.addWidget(self._comp_table)

        add_row = QHBoxLayout()
        add_row.addStretch()
        add_comp_btn = QPushButton('+ Add Computed Column')
        add_comp_btn.setFixedWidth(190)
        add_comp_btn.clicked.connect(self._add_computed)
        add_row.addWidget(add_comp_btn)
        comp_lay.addLayout(add_row)

        root.addWidget(comp_grp, 1)

        # ── Footer ──────────────────────────────────────────────────────────
        foot = QHBoxLayout()
        foot.addStretch()
        close_btn = QPushButton('Close')
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        foot.addWidget(close_btn)
        root.addLayout(foot)

        self._populate_raw_table()
        self._populate_comp_table()

    # ── Raw table ──────────────────────────────────────────────────────────

    def _populate_raw_table(self, filter_text: str = ''):
        # Merge data columns with COLUMN_DESCRIPTIONS
        all_cols = list(self._data_columns)
        for col in COLUMN_DESCRIPTIONS:
            if col not in all_cols:
                all_cols.append(col)
        all_cols = sorted(all_cols)

        ft = filter_text.lower()
        rows = [
            (c, *COLUMN_DESCRIPTIONS.get(c, ('(no description available)', '')))
            for c in all_cols
            if not ft or ft in c.lower()
        ]
        self._raw_table.setRowCount(len(rows))
        for r, (col, desc, unit) in enumerate(rows):
            self._raw_table.setItem(r, 0, QTableWidgetItem(col))
            self._raw_table.setItem(r, 1, QTableWidgetItem(desc))
            self._raw_table.setItem(r, 2, QTableWidgetItem(unit))
        self._raw_table.resizeRowsToContents()

    # ── Computed table ──────────────────────────────────────────────────────

    def _populate_comp_table(self):
        computed = self._rules_config.get('computed_columns', {})
        self._comp_table.setRowCount(len(computed))
        for r, (name, cfg) in enumerate(computed.items()):
            sources_str = ', '.join(cfg.get('sources', []))
            type_label  = ComputedColumnEditor.TYPE_LABELS.get(
                cfg.get('type', ''), cfg.get('type', '').capitalize()
            )
            self._comp_table.setItem(r, 0, QTableWidgetItem(name))
            self._comp_table.setItem(r, 1, QTableWidgetItem(type_label))
            self._comp_table.setItem(r, 2, QTableWidgetItem(sources_str))

            btn_widget = QWidget()
            btn_lay    = QHBoxLayout(btn_widget)
            btn_lay.setContentsMargins(2, 1, 2, 1)
            btn_lay.setSpacing(3)
            edit_btn = QPushButton('✎')
            edit_btn.setFixedWidth(30)
            edit_btn.setToolTip('Edit this computed column')
            del_btn  = QPushButton('✕')
            del_btn.setFixedWidth(30)
            del_btn.setToolTip('Delete this computed column')
            del_btn.setStyleSheet('color: #c0392b;')
            edit_btn.clicked.connect(lambda _, n=name: self._edit_computed(n))
            del_btn.clicked.connect(lambda _, n=name: self._delete_computed(n))
            btn_lay.addWidget(edit_btn)
            btn_lay.addWidget(del_btn)
            btn_lay.addStretch()
            self._comp_table.setCellWidget(r, 3, btn_widget)
        self._comp_table.resizeRowsToContents()

    def _add_computed(self):
        dlg = ComputedColumnEditor(
            existing_name=None,
            existing_cfg=None,
            data_columns=self._data_columns,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name, cfg = dlg.get_result()
            if name:
                self._rules_config.setdefault('computed_columns', {})[name] = cfg
                self._populate_comp_table()

    def _edit_computed(self, name: str):
        cfg = self._rules_config.get('computed_columns', {}).get(name, {})
        dlg = ComputedColumnEditor(
            existing_name=name,
            existing_cfg=cfg,
            data_columns=self._data_columns,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_name, new_cfg = dlg.get_result()
            if new_name:
                computed = self._rules_config.setdefault('computed_columns', {})
                if new_name != name:
                    del computed[name]
                computed[new_name] = new_cfg
                self._populate_comp_table()

    def _delete_computed(self, name: str):
        from PyQt6.QtWidgets import QMessageBox
        if (QMessageBox.question(
                self, 'Delete Computed Column',
                f'Delete computed column "{name}"?\n\nAny rules using it will need to be updated.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            ) == QMessageBox.StandardButton.Yes):
            self._rules_config.get('computed_columns', {}).pop(name, None)
            self._populate_comp_table()

    def get_rules_config(self) -> dict:
        """Return the (possibly modified) rules_config with updated computed_columns."""
        return self._rules_config


# ─── MAIN DIAGNOSTICS WIDGET ──────────────────────────────────────────────────

class DiagnosticsWidget(QWidget):
    """
    Diagnostics tab widget.

    Receives processed_df via on_data_ready() slot (connected to
    CalculationsWidget.filtered_data_ready signal in app.py).
    Runs all diagnostic scenarios and renders expandable finding cards.
    """

    locate_on_diagram = pyqtSignal(object)   # re-emitted from FindingCard

    def __init__(self, data_manager, parent=None):
        super().__init__(parent)
        self.data_manager    = data_manager
        self._findings: list[Finding] = []
        self._user_thresholds: dict   = {}
        self._current_filter          = 'All'
        self._custom_scenarios_cfg: list = []   # raw JSON config dicts
        self._custom_scenarios: list = []        # loaded CustomScenario instances
        try:
            self._custom_scenarios = load_custom_scenarios()
            # Extract cfg for dialog editing
            self._custom_scenarios_cfg = [s._cfg for s in self._custom_scenarios]
        except Exception:
            self._custom_scenarios = []
            self._custom_scenarios_cfg = []
        self._rules_config = load_rules_config()
        self._build_ui()

    # ── UI Construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)

        # ── Top bar ──────────────────────────────────────────────────────────
        top_bar = QHBoxLayout()

        self._title_label = QLabel('🩺  Diagnostics')
        self._title_label.setStyleSheet('font-size: 14px; font-weight: bold;')
        top_bar.addWidget(self._title_label)
        top_bar.addStretch()

        self._filter_combo = QComboBox()
        self._filter_combo.addItems(['All', 'CRITICAL', 'WARNING', 'WATCH', 'OK', 'INFO'])
        self._filter_combo.currentTextChanged.connect(self._apply_filter)
        self._filter_combo.setFixedWidth(110)
        top_bar.addWidget(QLabel('Filter:'))
        top_bar.addWidget(self._filter_combo)

        thr_btn = QPushButton('⚙  Thresholds')
        thr_btn.clicked.connect(self._open_thresholds)
        thr_btn.setFixedWidth(120)
        top_bar.addWidget(thr_btn)

        self._custom_btn = QPushButton('📋 Rules')
        self._custom_btn.setToolTip('View and edit all diagnostic rules — built-in and custom')
        self._custom_btn.clicked.connect(self._open_rules_dialog)
        self._custom_btn.setFixedWidth(100)
        top_bar.addWidget(self._custom_btn)

        self._columns_btn = QPushButton('📖 Columns')
        self._columns_btn.setToolTip(
            'Column Manager: view sensor column descriptions and define computed columns'
        )
        self._columns_btn.clicked.connect(self._open_columns_dialog)
        self._columns_btn.setFixedWidth(110)
        top_bar.addWidget(self._columns_btn)

        root.addLayout(top_bar)

        # ── Summary bar ───────────────────────────────────────────────────────
        self._summary_bar = QLabel('Run Calculations to populate diagnostics.')
        self._summary_bar.setStyleSheet(
            'font-size: 12px; padding: 6px 10px; '
            'background: #f0f0f0; border-radius: 4px; border: 1px solid #ddd;'
        )
        self._summary_bar.setWordWrap(True)
        root.addWidget(self._summary_bar)

        # ── Diagnostics status label (shows while running / on completion) ───
        self._diag_status = QLabel('')
        self._diag_status.setStyleSheet('font-size: 10pt; color: #2980b9; padding: 1px 4px; font-style: italic;')
        self._diag_status.setVisible(False)
        root.addWidget(self._diag_status)

        # ── Scroll area for cards ─────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._cards_container = QWidget()
        self._cards_layout    = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 0, 4, 0)
        self._cards_layout.setSpacing(4)
        self._cards_layout.addStretch()

        scroll.setWidget(self._cards_container)
        root.addWidget(scroll, 1)

    # ── Render cards ──────────────────────────────────────────────────────────

    def _refresh_cards(self):
        """Clear and redraw all cards; apply current filter."""
        # Remove old cards (leave the stretch at end)
        while self._cards_layout.count() > 1:
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        filt = self._current_filter
        visible = [f for f in self._findings
                   if filt == 'All' or f.severity == filt]

        if not visible:
            placeholder = QLabel(
                'No findings to show.' if self._findings
                else 'Run Calculations first to generate diagnostics.'
            )
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet('color: #888; font-size: 13px; padding: 30px;')
            self._cards_layout.insertWidget(0, placeholder)
        else:
            for i, finding in enumerate(visible):
                card = FindingCard(finding)
                card.locate_requested.connect(self.locate_on_diagram.emit)
                self._cards_layout.insertWidget(i, card)

        self._update_summary()

    def _update_summary(self):
        counts = {s: 0 for s in SEVERITY_ORDER}
        for f in self._findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1

        parts = []
        if counts.get('CRITICAL', 0):
            parts.append(f'<span style="color:#c0392b;font-weight:bold;">● {counts["CRITICAL"]} CRITICAL</span>')
        if counts.get('WARNING', 0):
            parts.append(f'<span style="color:#e67e22;font-weight:bold;">● {counts["WARNING"]} WARNING</span>')
        if counts.get('WATCH', 0):
            parts.append(f'<span style="color:#2980b9;">● {counts["WATCH"]} WATCH</span>')
        if counts.get('OK', 0):
            parts.append(f'<span style="color:#27ae60;">✓ {counts["OK"]} OK</span>')
        if counts.get('INFO', 0):
            parts.append(f'<span style="color:#7f8c8d;">ℹ {counts["INFO"]} INFO</span>')

        if parts:
            self._summary_bar.setText('  '.join(parts))
        else:
            self._summary_bar.setText('No findings.')
        self._summary_bar.setTextFormat(Qt.TextFormat.RichText)

    # ── Filter ────────────────────────────────────────────────────────────────

    def _apply_filter(self, text: str):
        self._current_filter = text
        self._refresh_cards()

    # ── Thresholds dialog ─────────────────────────────────────────────────────

    def _open_thresholds(self):
        current = get_all_thresholds(self._user_thresholds)
        dlg = ThresholdsDialog(current, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._user_thresholds = dlg.get_values()
            # If we already have findings data, re-run with new thresholds
            # We need the last df — store it on first receipt
            if hasattr(self, '_last_df') and self._last_df is not None:
                self.on_data_ready(self._last_df)

    # ── Custom scenarios dialog ────────────────────────────────────────────────

    def _open_custom_dialog(self):
        dlg = CustomScenariosDialog(
            custom_scenarios_cfg=self._custom_scenarios_cfg,
            last_df=getattr(self, '_last_df', None),
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._custom_scenarios_cfg = dlg.get_scenarios_cfg()
            # Save to JSON
            save_custom_scenarios(self._custom_scenarios_cfg)
            # Reload scenario instances
            self._custom_scenarios = [CustomScenario(cfg) for cfg in self._custom_scenarios_cfg]
            # Re-run diagnostics if data is available
            if hasattr(self, '_last_df') and self._last_df is not None:
                self.on_data_ready(self._last_df)

    def _open_rules_dialog(self):
        dlg = RulesDialog(
            rules_config=self._rules_config,
            custom_scenarios_cfg=self._custom_scenarios_cfg,
            last_df=getattr(self, '_last_df', None),
            parent=self,
        )
        # Connect live preview: Apply & Preview button inside the dialog
        dlg.recalc_requested.connect(
            lambda rc, cc: self._apply_rules_preview(rc, cc, dlg)
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._rules_config, self._custom_scenarios_cfg = dlg.get_results()
            save_rules_config(self._rules_config)
            save_custom_scenarios(self._custom_scenarios_cfg)
            self._custom_scenarios = [CustomScenario(cfg) for cfg in self._custom_scenarios_cfg]
            if hasattr(self, '_last_df') and self._last_df is not None:
                self.on_data_ready(self._last_df)

    def _apply_rules_preview(self, rules_config: dict, custom_cfg: list, dlg=None):
        """Re-run diagnostics with the given rules config (called from within the Rules dialog)."""
        import copy
        # Apply the incoming config so the main widget is up-to-date
        self._rules_config = copy.deepcopy(rules_config)
        self._custom_scenarios_cfg = copy.deepcopy(custom_cfg)
        self._custom_scenarios = [CustomScenario(cfg) for cfg in self._custom_scenarios_cfg]

        if not hasattr(self, '_last_df') or self._last_df is None:
            if dlg:
                dlg.update_preview_status('⚠  No data — run Calculations first.', '#e67e22')
            return

        try:
            self.on_data_ready(self._last_df)
            n = len(self._findings)
            crit = sum(1 for f in self._findings if f.severity == 'CRITICAL')
            warn = sum(1 for f in self._findings if f.severity == 'WARNING')
            msg = f'✓  Done — {n} findings'
            if crit:
                msg += f'  ({crit} CRITICAL'
                if warn:
                    msg += f', {warn} WARNING'
                msg += ')'
            elif warn:
                msg += f'  ({warn} WARNING)'
            if dlg:
                dlg.update_preview_status(msg, '#27ae60')
        except Exception as exc:
            if dlg:
                dlg.update_preview_status(f'❌  Error: {exc}', '#c0392b')

    def _open_columns_dialog(self):
        """Open the Column Manager dialog — raw sensor column reference + computed columns."""
        last_df   = getattr(self, '_last_df', None)
        data_cols = sorted(last_df.columns.tolist()) if last_df is not None and not last_df.empty else []
        dlg = ColumnManagerDialog(
            rules_config=self._rules_config,
            data_columns=data_cols,
            parent=self,
        )
        dlg.exec()
        # Merge back any computed column changes (user may have added/deleted)
        new_rc = dlg.get_rules_config()
        if new_rc.get('computed_columns') != self._rules_config.get('computed_columns'):
            self._rules_config['computed_columns'] = new_rc.get('computed_columns', {})
            save_rules_config(self._rules_config)
            # Re-run diagnostics so new computed columns take effect
            if last_df is not None:
                self.on_data_ready(last_df)

    def _set_diag_status(self, msg: str, color: str = '#2980b9'):
        """Show a transient status message below the summary bar."""
        from PyQt6.QtWidgets import QApplication
        if msg:
            self._diag_status.setText(msg)
            self._diag_status.setStyleSheet(
                f'font-size: 10pt; color: {color}; padding: 1px 4px; font-style: italic;'
            )
            self._diag_status.setVisible(True)
        else:
            self._diag_status.setVisible(False)
        QApplication.processEvents()

    @pyqtSlot(object)
    def on_data_ready(self, df):  # noqa: F811  (intentional override to cache df)
        """Called automatically when Calculations tab finishes processing."""
        self._last_df = df        # cache so threshold changes can re-run

        self._set_diag_status('Running diagnostics…', '#2980b9')

        try:
            from circuit_semantics import get_all_module_labels
            from calculation_orchestrator import _detect_system_type
            model         = getattr(self.data_manager, 'diagram_model', {}) or {}
            module_labels = get_all_module_labels(model) or ['Left']
            system_type   = _detect_system_type(model)
            rated_inputs  = getattr(self.data_manager, 'rated_inputs', {}) or {}
        except Exception:
            module_labels = ['Left']
            system_type   = 'shared'
            rated_inputs  = {}

        self._findings = run_all_diagnostics(
            df, system_type, module_labels,
            rated_inputs=rated_inputs,
            user_thresholds=self._user_thresholds or None,
            custom_scenarios=self._custom_scenarios,
            rules_config=self._rules_config,
            diagram_model=model,
        )
        n_rows = len(df) if df is not None else 0
        n_mods = len(module_labels)
        unit_word = 'unit' if system_type == 'cassette' else 'module'
        sys_desc  = f'{system_type.capitalize()} {n_mods}-{unit_word}'
        self._title_label.setText(f'🩺  Diagnostics   —   {sys_desc}   |   {n_rows} rows')
        self._refresh_cards()

        crit = sum(1 for f in self._findings if f.severity == 'CRITICAL')
        warn = sum(1 for f in self._findings if f.severity == 'WARNING')
        if crit or warn:
            self._set_diag_status(
                f'✓ Diagnostics complete — {crit} critical, {warn} warning', '#c0392b' if crit else '#e67e22'
            )
        else:
            self._set_diag_status(f'✓ Diagnostics complete — {len(self._findings)} findings', '#27ae60')
