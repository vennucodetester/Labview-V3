from __future__ import annotations

import argparse
import csv
import io
import json
from contextlib import redirect_stdout
from pathlib import Path

from data_manager import DataManager
from case_library import apply_case_to_session
from sensor_canonical import _canonical_from_box_label, normalize_for_match


def _csv_headers(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        try:
            row = next(reader)
        except StopIteration:
            return []
    dm = DataManager()
    names = dm._normalize_column_names(row)
    return [
        str(name).strip()
        for name in names
        if str(name).strip() and not dm._is_ignorable_csv_column(str(name).strip())
    ]


def _grammar_resolve(labels: list[str]) -> tuple[list[dict], list[str]]:
    dm = DataManager()
    aliases = dm._load_alias_db()
    rev_exact = {}
    rev_norm = {}
    for canonical, names in aliases.items():
        for name in names:
            rev_exact[str(name).strip()] = canonical
            rev_norm[normalize_for_match(name)] = canonical

    resolved = []
    unknown = []
    for label in labels:
        parsed = _canonical_from_box_label(label)
        canonical = (parsed[0] if parsed else None) or rev_exact.get(label.strip()) or rev_norm.get(normalize_for_match(label))
        if canonical:
            resolved.append({"csv": label, "canonical": canonical})
        else:
            unknown.append(label)
    return resolved, unknown


def _family_for(label: str) -> str:
    text = normalize_for_match(label)
    if any(token in text for token in ("txvsplit", "split")):
        return "TXV split / shared expansion"
    if "filterdrier" in text:
        return "Filter drier"
    if "fpm" in text or "velocity" in text:
        return "Air velocity"
    if any(token in text for token in ("l1", "l2", "l3", "120v", "volts", "amps", "watts")):
        return "Electrical"
    if text.startswith("ps") or "shelf" in text:
        return "Product simulator"
    if "air" in text:
        return "Air / airflow"
    if "coil" in text or "evap" in text:
        return "Coil / evaporator"
    if "txv" in text or "eev" in text or "distributor" in text:
        return "Expansion / distributor"
    return "Other"


def _scan_case(data_dir: Path, cases_root: Path) -> dict:
    labels = sorted({label for csv_path in data_dir.glob("*.csv") for label in _csv_headers(csv_path)})
    case_dir = cases_root / data_dir.name
    case_path = case_dir / "case.json"
    diagram_path = case_dir / "diagram.json"

    result = {
        "case": data_dir.name,
        "csv_files": len(list(data_dir.glob("*.csv"))),
        "labels": labels,
        "label_count": len(labels),
        "mode": "grammar-only",
        "unknown": [],
        "known_but_no_role": [],
        "known_but_filled": [],
        "mapped": [],
    }
    if not labels:
        return result

    if case_path.exists() and diagram_path.exists():
        dm = DataManager()
        case = json.loads(case_path.read_text(encoding="utf-8"))
        diagram = json.loads(diagram_path.read_text(encoding="utf-8"))
        apply_case_to_session(case, diagram, dm, emit_signals=False)
        with redirect_stdout(io.StringIO()):
            dm.auto_map_csv_to_canonical(labels)
        report = dm.get_auto_map_report()
        result["mode"] = "case+diagram"
        result["unknown"] = report.get("unmapped_csv") or []
        result["known_but_no_role"] = report.get("known_but_no_role") or []
        result["known_but_filled"] = report.get("known_but_filled") or []
        result["mapped"] = sorted((report.get("mapped_columns") or {}).keys())
        return result

    resolved, unknown = _grammar_resolve(labels)
    result["mapped"] = [item["csv"] for item in resolved]
    result["unknown"] = unknown
    return result


def scan_data_folder(data_root: Path | str, cases_root: Path | str, output_path: Path | str | None = None) -> dict:
    data_root = Path(data_root)
    cases_root = Path(cases_root)
    output_path = Path(output_path) if output_path else data_root.parent / "LEXICON_COVERAGE.md"

    cases = [
        _scan_case(path, cases_root)
        for path in sorted(data_root.iterdir())
        if path.is_dir()
    ]
    total_labels = sum(case["label_count"] for case in cases)
    total_unknown = sum(len(case["unknown"]) for case in cases)
    overall = 100.0 if total_labels == 0 else ((total_labels - total_unknown) / total_labels) * 100.0

    lines = [
        "# Lexicon Coverage Report",
        "",
        f"Data root: `{data_root}`",
        f"Cases root: `{cases_root}`",
        "",
        f"Overall grammar coverage: **{overall:.1f}%** ({total_labels - total_unknown}/{total_labels})",
        "",
        "| Case | Mode | CSV files | Unique labels | Unknown | Coverage |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for case in cases:
        count = case["label_count"]
        unknown = len(case["unknown"])
        coverage = 100.0 if count == 0 else ((count - unknown) / count) * 100.0
        lines.append(
            f"| {case['case']} | {case['mode']} | {case['csv_files']} | {count} | {unknown} | {coverage:.1f}% |"
        )

    lines.append("")
    lines.append("## Exceptions")
    any_exception = False
    for case in cases:
        unknown = case["unknown"]
        no_role = case["known_but_no_role"]
        filled = case["known_but_filled"]
        if not unknown and not no_role and not filled:
            continue
        any_exception = True
        lines.append("")
        lines.append(f"### {case['case']}")
        if unknown:
            grouped = {}
            for label in unknown:
                grouped.setdefault(_family_for(label), []).append(label)
            lines.append("")
            lines.append("Unknown labels:")
            for family, labels in sorted(grouped.items()):
                lines.append(f"- {family}: {', '.join(f'`{label}`' for label in labels)}")
        if no_role:
            lines.append("")
            lines.append("Known labels with no slot in this diagram:")
            for item in no_role:
                lines.append(f"- `{item.get('csv')}` -> `{item.get('canonical')}`")
        if filled:
            lines.append("")
            lines.append("Known labels blocked by occupied slots:")
            for item in filled:
                occupied = "; ".join(
                    f"{occ.get('role_key')} occupied by {occ.get('csv') or ''}"
                    for occ in item.get("occupied") or []
                )
                lines.append(f"- `{item.get('csv')}` -> `{item.get('canonical')}` ({occupied})")
    if not any_exception:
        lines.append("")
        lines.append("No unknown, no-slot, or occupied-slot exceptions found.")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "output_path": str(output_path),
        "cases": cases,
        "total_labels": total_labels,
        "total_unknown": total_unknown,
        "overall_coverage": overall,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan CSV headers and report label-lexicon coverage.")
    parser.add_argument("--data", default="DATA", help="Folder containing case CSV subfolders.")
    parser.add_argument("--cases", default="library/cases", help="Folder containing case definitions.")
    parser.add_argument("--out", default="LEXICON_COVERAGE.md", help="Markdown report path.")
    args = parser.parse_args()

    result = scan_data_folder(Path(args.data), Path(args.cases), Path(args.out))
    print(f"Wrote {result['output_path']}")
    print(f"Overall grammar coverage: {result['overall_coverage']:.1f}%")
    print(f"Unknown labels: {result['total_unknown']}")
    return 0 if result["total_unknown"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
