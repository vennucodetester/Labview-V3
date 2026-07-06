"""Phase 2a arithmetic verification harness for diagnostic trust.

Runs the app calculation pipeline on available DATA/* CSVs, then recomputes
core thermodynamic columns independently from the processed P/T columns.
This is intentionally headless and repeatable.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

try:
    import CoolProp.CoolProp as CP
except Exception:  # pragma: no cover - harness reports this cleanly at runtime
    CP = None


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "DATA"
CASES_DIR = ROOT / "library" / "cases"


@dataclass
class CheckResult:
    case_id: str
    csv_path: str
    rows: int
    checked: int
    failures: list[str]
    skipped: list[str]

    @property
    def ok(self) -> bool:
        return not self.failures


def _psig_to_pa(psig: float) -> float:
    return (float(psig) + 14.696) * 6894.76


def _f_to_k(temp_f: float) -> float:
    return (float(temp_f) - 32.0) * 5.0 / 9.0 + 273.15


def _k_to_f(temp_k: float) -> float:
    return (float(temp_k) - 273.15) * 9.0 / 5.0 + 32.0


def _close(a, b, abs_tol=0.08, rel_tol=0.0008) -> bool:
    if pd.isna(a) or pd.isna(b):
        return True
    return abs(float(a) - float(b)) <= max(abs_tol, rel_tol * max(abs(float(a)), abs(float(b)), 1.0))


def _assert_series(name: str, actual: pd.Series, expected: pd.Series, failures: list[str], checked: list[int], abs_tol=0.08):
    mask = actual.notna() & expected.notna()
    if not mask.any():
        return
    checked[0] += int(mask.sum())
    delta = (actual[mask].astype(float) - expected[mask].astype(float)).abs()
    bad = delta > abs_tol
    if bad.any():
        worst_idx = delta.idxmax()
        failures.append(
            f"{name}: {int(bad.sum())}/{int(mask.sum())} mismatch(es), "
            f"worst row {worst_idx} delta={delta.loc[worst_idx]:.4g}, "
            f"actual={actual.loc[worst_idx]:.4g}, expected={expected.loc[worst_idx]:.4g}"
        )


def _independent_check(processed: pd.DataFrame, refrigerant: str = "R290") -> tuple[int, list[str], list[str]]:
    if CP is None:
        return 0, ["CoolProp is not available"], []
    failures: list[str] = []
    skipped: list[str] = []
    checked = [0]

    def has(*cols):
        return all(c in processed.columns for c in cols)

    def sat_from_pressure(col: str, quality: int):
        return processed[col].apply(lambda p: _k_to_f(CP.PropsSI("T", "P", _psig_to_pa(p), "Q", quality, refrigerant)) if pd.notna(p) else math.nan)

    if has("P_suction"):
        t_sat_suc = sat_from_pressure("P_suction", 1)
        if "T_sat.comp.in" in processed:
            _assert_series("T_sat.comp.in", processed["T_sat.comp.in"], t_sat_suc, failures, checked)
        if has("T_2b", "S.H_total"):
            _assert_series("S.H_total", processed["S.H_total"], processed["T_2b"] - t_sat_suc, failures, checked)
        for ab in ("lh", "ctr", "rh"):
            t_col = {"lh": "T_2a-LH", "ctr": "T_2a-CTR", "rh": "T_2a-RH"}[ab]
            sh_col = f"S.H_{ab} coil"
            if has(t_col, sh_col):
                _assert_series(sh_col, processed[sh_col], processed[t_col] - t_sat_suc, failures, checked)
    else:
        skipped.append("shared suction pressure columns not present")

    if has("P_disch"):
        t_sat_cond = sat_from_pressure("P_disch", 0)
        if "T_sat.cond" in processed:
            _assert_series("T_sat.cond", processed["T_sat.cond"], t_sat_cond, failures, checked)
        if has("T_4a", "S.C"):
            _assert_series("S.C", processed["S.C"], t_sat_cond - processed["T_4a"], failures, checked)
        for ab in ("lh", "ctr", "rh"):
            t_col = f"T_4b-{ab}"
            sc_col = f"S.C-txv.{ab}"
            if has(t_col, sc_col):
                _assert_series(sc_col, processed[sc_col], t_sat_cond - processed[t_col], failures, checked)
    else:
        skipped.append("shared discharge pressure columns not present")

    # Independent enthalpy recomputation for the hidden P-h columns.
    if has("P_suction"):
        p_suc_pa = processed["P_suction"].apply(lambda p: _psig_to_pa(p) if pd.notna(p) else math.nan)
        enthalpy_specs = [
            ("h_2b", "T_2b", p_suc_pa),
            ("h_2a_LH", "T_2a-LH", p_suc_pa),
            ("h_2a_CTR", "T_2a-CTR", p_suc_pa),
            ("h_2a_RH", "T_2a-RH", p_suc_pa),
        ]
        for out_col, t_col, pressure_series in enthalpy_specs:
            if has(out_col, t_col):
                expected = pd.Series([
                    CP.PropsSI("H", "T", _f_to_k(t), "P", p, refrigerant) / 1000.0
                    if pd.notna(t) and pd.notna(p) else math.nan
                    for t, p in zip(processed[t_col], pressure_series)
                ], index=processed.index)
                _assert_series(out_col, processed[out_col], expected, failures, checked, abs_tol=0.12)

    if has("P_disch"):
        p_cond_pa = processed["P_disch"].apply(lambda p: _psig_to_pa(p) if pd.notna(p) else math.nan)
        enthalpy_specs = [
            ("h_3a", "T_3a", p_cond_pa),
            ("h_4a", "T_4a", p_cond_pa),
            ("h_4b_LH", "T_4b-lh", p_cond_pa),
            ("h_4b_CTR", "T_4b-ctr", p_cond_pa),
            ("h_4b_RH", "T_4b-rh", p_cond_pa),
        ]
        for out_col, t_col, pressure_series in enthalpy_specs:
            if has(out_col, t_col):
                expected = pd.Series([
                    CP.PropsSI("H", "T", _f_to_k(t), "P", p, refrigerant) / 1000.0
                    if pd.notna(t) and pd.notna(p) else math.nan
                    for t, p in zip(processed[t_col], pressure_series)
                ], index=processed.index)
                _assert_series(out_col, processed[out_col], expected, failures, checked, abs_tol=0.12)

    return checked[0], failures, skipped


def _load_case_data_manager(case_id: str, csv_path: Path):
    from data_manager import DataManager

    diagram_path = CASES_DIR / case_id / "diagram.json"
    if not diagram_path.exists():
        return None, f"missing diagram for {case_id}"
    dm = DataManager()
    with open(diagram_path, "r", encoding="utf-8") as fh:
        dm.diagram_model = json.load(fh)
    case_path = CASES_DIR / case_id / "case.json"
    if case_path.exists():
        with open(case_path, "r", encoding="utf-8") as fh:
            case = json.load(fh)
        dm.case_id = case_id
        dm.refrigerant = (case.get("settings") or {}).get("refrigerant") or dm.refrigerant
        water_gpm = (case.get("settings") or {}).get("water_gpm")
        if water_gpm:
            dm.rated_inputs["gpm_water"] = water_gpm
    dm.load_csv(str(csv_path))
    return dm, None


def run_case_csv(case_id: str, csv_path: Path, max_rows: int | None = 300) -> CheckResult:
    from calculation_orchestrator import run_batch_processing

    dm, err = _load_case_data_manager(case_id, csv_path)
    if err:
        return CheckResult(case_id, str(csv_path), 0, 0, [], [err])
    input_df = dm.get_filtered_data()
    if max_rows and len(input_df) > max_rows:
        input_df = input_df.head(max_rows).copy()
    processed = run_batch_processing(dm, input_df)
    real_errors = []
    if "error" in processed.columns:
        real_errors = [str(v) for v in processed["error"].dropna().tolist() if str(v).strip()]
    if real_errors:
        return CheckResult(case_id, str(csv_path), len(input_df), 0, real_errors[:3], [])
    checked, failures, skipped = _independent_check(processed, getattr(dm, "refrigerant", "R290") or "R290")
    return CheckResult(case_id, str(csv_path), len(processed), checked, failures, skipped)


def discover_pairs() -> list[tuple[str, Path]]:
    pairs = []
    for csv_path in sorted(DATA_DIR.glob("*/*.csv")):
        pairs.append((csv_path.parent.name, csv_path))
    return pairs


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 2a arithmetic verification.")
    parser.add_argument("--case", dest="case_id", help="Only run one case id")
    parser.add_argument("--csv", dest="csv_path", help="Only run one CSV path")
    parser.add_argument("--max-rows", type=int, default=300,
                        help="Rows per CSV to verify; use 0 for all rows")
    args = parser.parse_args(argv)

    if args.csv_path:
        csv_path = Path(args.csv_path)
        pairs = [(args.case_id or csv_path.parent.name, csv_path)]
    else:
        pairs = discover_pairs()
        if args.case_id:
            pairs = [(case_id, path) for case_id, path in pairs if case_id == args.case_id]

    max_rows = None if args.max_rows == 0 else args.max_rows
    results = [run_case_csv(case_id, path, max_rows=max_rows) for case_id, path in pairs]
    failures = 0
    for result in results:
        status = "OK" if result.ok else "FAIL"
        print(f"{status} {result.case_id} {Path(result.csv_path).name} rows={result.rows} checked={result.checked}")
        for item in result.skipped:
            print(f"  SKIP {item}")
        for item in result.failures:
            failures += 1
            print(f"  FAIL {item}")
    print(f"ARITHMETIC_HARNESS_SUMMARY cases={len(results)} failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
