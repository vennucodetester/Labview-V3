"""Target scorecard evaluation for case/test acceptance bands."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import pandas as pd


@dataclass
class ScorecardRow:
    target: str
    status: str
    value: float | None
    unit: str
    min_value: float | None
    max_value: float | None
    sources: list[str]
    message: str

    @property
    def target_band(self) -> str:
        lo = _fmt_bound(self.min_value)
        hi = _fmt_bound(self.max_value)
        if self.min_value is None and self.max_value is None:
            return "No acceptance band"
        if self.min_value is None:
            return f"<= {hi} {self.unit}".strip()
        if self.max_value is None:
            return f">= {lo} {self.unit}".strip()
        return f"{lo}-{hi} {self.unit}".strip()

    @property
    def value_text(self) -> str:
        if self.value is None:
            return "No data"
        return f"{self.value:.1f} {self.unit}".strip()


def evaluate_targets(df: pd.DataFrame | None, targets: Iterable[dict] | None) -> list[ScorecardRow]:
    """Return PASS/FAIL/NO DATA/NO LIMIT rows for configured targets."""
    if df is None or df.empty:
        return [
            ScorecardRow(_target_name(t), "NO DATA", None, _target_unit(t),
                         _as_float(t.get("min")), _as_float(t.get("max")), [],
                         "Calculations have not produced rows yet.")
            for t in (targets or [])
        ]

    rows: list[ScorecardRow] = []
    for target in targets or []:
        name = _target_name(target)
        unit = _target_unit(target)
        min_value = _as_float(target.get("min"))
        max_value = _as_float(target.get("max"))
        sources = _candidate_columns(df, name)

        if min_value is None and max_value is None:
            rows.append(ScorecardRow(
                name, "NO LIMIT", None, unit, min_value, max_value, sources,
                "Target is listed for reporting but has no pass/fail band."
            ))
            continue

        value = _aggregate_value(df, sources)
        if value is None:
            rows.append(ScorecardRow(
                name, "NO DATA", None, unit, min_value, max_value, sources,
                "No matching calculated or mapped sensor column was found."
            ))
            continue

        failed_low = min_value is not None and value < min_value
        failed_high = max_value is not None and value > max_value
        status = "FAIL" if failed_low or failed_high else "PASS"
        if failed_low:
            message = f"{name} is below target minimum."
        elif failed_high:
            message = f"{name} is above target maximum."
        else:
            message = f"{name} is inside the acceptance band."
        rows.append(ScorecardRow(name, status, value, unit, min_value, max_value, sources, message))
    return rows


def _candidate_columns(df: pd.DataFrame, target_name: str) -> list[str]:
    columns = list(df.columns)
    normalized = {col: _norm(col) for col in columns}
    name = _norm(target_name)

    if "product" in name and "temp" in name:
        preferred = ["T_prod.avg", "AVG Product Temp", "AVG Product temp", "Average Product Temp"]
        matches = _existing(columns, preferred)
        if matches:
            return matches
        return [c for c, n in normalized.items() if "prod" in n and "temp" in n]

    if "coil" in name and "superheat" in name:
        matches = [c for c in columns if c.startswith("S.H_") and "coil" in c.lower()]
        return matches or _existing(columns, ["S.H_total"])

    if "subcool" in name:
        matches = _existing(columns, ["S.C"])
        matches.extend(c for c in columns if c.startswith("S.C-") or c.startswith("S.C-txv."))
        return list(dict.fromkeys(matches))

    if "capacity" in name:
        return _existing(columns, ["qc", "qc_coils", "Q_evap_btu_hr"])

    if "doe" in name or "energy" in name:
        return [c for c, n in normalized.items() if "kwh" in n or "energy" in n or "doe" in n]

    return [c for c, n in normalized.items() if name and name in n]


def _aggregate_value(df: pd.DataFrame, sources: list[str]) -> float | None:
    values: list[float] = []
    for col in sources:
        if col not in df.columns:
            continue
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if not series.empty:
            values.append(float(series.mean()))
    if not values:
        return None
    value = sum(values) / len(values)
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def _existing(columns: list[str], candidates: list[str]) -> list[str]:
    available = set(columns)
    return [col for col in candidates if col in available]


def _target_name(target: dict) -> str:
    return str((target or {}).get("name") or "Unnamed target")


def _target_unit(target: dict) -> str:
    return str((target or {}).get("unit") or "")


def _as_float(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_bound(value: float | None) -> str:
    if value is None:
        return ""
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.1f}"


def _norm(value: str) -> str:
    return "".join(ch.lower() for ch in str(value) if ch.isalnum())
