from __future__ import annotations

import copy
import getpass
import json
import os
import uuid
from datetime import datetime
from typing import List, Optional

from test_request_library import (
    DEFAULT_TARGETS,
    LIBRARY_DIR,
    PART_TYPES,
    compressor_to_rated_inputs,
    request_to_html,
)


FAMILY_RULEBOOK = {
    "insight": {
        "display": "Insight",
        "module_pitch_in": 48,
        "size_question": "modules",
        "size_range": [1, 3],
        "door_style": "french_pair_per_module",
        "open_allowed": True,
        "air_curtains": "dual",
        "shelf_width_in": 48,
        "temp_classes": ["MT"],
    },
    "reach_in": {
        "display": "Reach-in",
        "module_pitch_in": 30,
        "size_question": "doors",
        "size_range": [1, 5],
        "door_style": "one_per_pitch",
        "open_allowed": False,
        "air_curtains": "single",
        "shelf_width_in": 30,
        "temp_classes": ["MT", "LT"],
    },
}


NEW_TOPOLOGY_KEYS = {
    "family",
    "size_count",
    "open_or_doored",
    "temp_class",
    "system",
    "cassette_count",
    "cassette_airflow",
    "circuits",
    "defrost_type",
    "condenser_cooling",
    "shelf_rows",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _user() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


def _safe_name(value: str) -> str:
    clean = "".join(c if c.isalnum() or c in "-_" else "_" for c in value.strip())
    return clean or _new_id("case")


def clean_topology(topology: dict, families: dict | None = None) -> dict:
    """Return only the case-workflow topology schema stored in case.json."""
    topo = copy.deepcopy(topology or {})
    families = families or FAMILY_RULEBOOK
    family = topo.get("family")
    if not family:
        family_text = str(topo.get("case_family", "")).lower()
        if topo.get("mode") == "door" or "reach" in family_text:
            family = "reach_in"
        elif topo:
            family = "insight"
    if family not in families:
        return {k: v for k, v in topo.items() if k in NEW_TOPOLOGY_KEYS}

    rules = families.get(family, {})
    lo, hi = rules.get("size_range", [1, 3])
    size = topo.get("size_count")
    if size is None:
        size = topo.get("num_doors") if family == "reach_in" else topo.get("modules")
    try:
        size = max(int(lo), min(int(hi), int(size or lo)))
    except (TypeError, ValueError):
        size = int(lo)

    system = topo.get("system") or topo.get("system_type") or "shared"
    system = "cassette" if str(system).lower() == "cassette" else "shared"

    open_or_doored = topo.get("open_or_doored") or topo.get("case_type")
    if not rules.get("open_allowed", True):
        open_or_doored = "Doored"
    elif str(open_or_doored).lower().startswith("door"):
        open_or_doored = "Doored"
    else:
        open_or_doored = "Open"

    temp_options = rules.get("temp_classes") or ["MT"]
    temp_class = topo.get("temp_class")
    if temp_class not in temp_options:
        temp_class = temp_options[0]

    defrost = str(topo.get("defrost_type") or "none").lower()
    if defrost not in {"none", "off_time", "electric", "hot_gas", "cool_gas"}:
        defrost = "hot_gas" if topo.get("mode") == "cassette_lt" else "none"

    try:
        circuits = max(1, min(12, int(topo.get("circuits") or topo.get("circuits_per_coil") or 6)))
    except (TypeError, ValueError):
        circuits = 6
    try:
        shelf_rows = max(3, min(8, int(topo.get("shelf_rows") or 5)))
    except (TypeError, ValueError):
        shelf_rows = 5

    cassette_count = topo.get("cassette_count")
    if cassette_count is None:
        cassette_count = topo.get("num_cassettes")
    if system == "cassette":
        try:
            cassette_count = max(1, min(5, int(cassette_count or size)))
        except (TypeError, ValueError):
            cassette_count = size
        cassette_airflow = topo.get("cassette_airflow") or "conventional"
    else:
        cassette_count = None
        cassette_airflow = None

    return {
        "family": family,
        "size_count": size,
        "open_or_doored": open_or_doored,
        "temp_class": temp_class,
        "system": system,
        "cassette_count": cassette_count,
        "cassette_airflow": cassette_airflow,
        "circuits": circuits,
        "defrost_type": defrost,
        "condenser_cooling": topo.get("condenser_cooling") or topo.get("condenser_cooling_new") or "Water",
        "shelf_rows": shelf_rows,
    }


def ensure_old_topology(topology: dict, families: dict | None = None) -> dict:
    """Return a topology dict that old diagram/session helpers can still read."""
    topo = copy.deepcopy(topology or {})
    if "family" not in topo:
        return topo

    families = families or FAMILY_RULEBOOK
    topo = clean_topology(topo, families)
    family = topo.get("family") or "insight"
    rules = families.get(family, {})
    system = topo.get("system", "shared")
    defrost = str(topo.get("defrost_type", "none")).lower()
    size_count = int(topo.get("size_count", 1) or 1)
    circuits = int(topo.get("circuits", 6) or 6)

    if system == "cassette":
        # Legacy modes have only two cassette shapes. Hot/cool gas use the
        # valve-bearing path; electric/off-time/none use the simple path.
        mode = "cassette_lt" if defrost in ("hot_gas", "cool_gas", "hot gas", "cool gas") else "cassette_mt"
    elif family == "reach_in":
        mode = "door"
    else:
        mode = "modular"

    open_or_doored = topo.get("open_or_doored")
    if not open_or_doored:
        open_or_doored = "Doored" if not rules.get("open_allowed", True) else "Open"
    case_type = "Open" if str(open_or_doored).lower().startswith("open") else "Doored"

    legacy = {
        "case_family": rules.get("display", family),
        "system_type": "cassette" if system == "cassette" else "shared",
        "mode": mode,
        "modules": size_count if family != "reach_in" else 1,
        "num_doors": size_count if family == "reach_in" else size_count,
        "num_cassettes": int(topo.get("cassette_count", size_count) or size_count),
        "circuits_per_coil": circuits,
        "condenser_cooling": topo.get("condenser_cooling", "Water"),
        "case_type": case_type,
        "shelf_rows": int(topo.get("shelf_rows", 5) or 5),
        "doored": case_type == "Doored",
        "family": family,
        "size_count": size_count,
        "open_or_doored": open_or_doored,
        "temp_class": topo.get("temp_class") or (rules.get("temp_classes") or ["MT"])[0],
        "system": system,
        "cassette_count": topo.get("cassette_count"),
        "cassette_airflow": topo.get("cassette_airflow", "conventional"),
        "circuits": circuits,
        "defrost_type": topo.get("defrost_type", "none"),
        "condenser_cooling_new": topo.get("condenser_cooling", "Water"),
        "shelf_width_in": rules.get("shelf_width_in", 48 if family == "insight" else 30),
        "air_curtains": rules.get("air_curtains", "dual" if family == "insight" else "single"),
        "door_style": rules.get("door_style", ""),
    }
    return legacy


def topology_one_liner(case: dict, families: dict | None = None) -> str:
    topo = case.get("topology", {}) or {}
    topo = ensure_old_topology(topo, families)
    family = topo.get("family") or ("reach_in" if topo.get("mode") == "door" else "insight")
    rules = (families or FAMILY_RULEBOOK).get(family, {})
    size_label = rules.get("size_question", "modules")
    system = topo.get("system") or topo.get("system_type", "shared")
    return (
        f"{rules.get('display', family)}; {topo.get('size_count') or topo.get('modules') or topo.get('num_doors')} "
        f"{size_label}; {system}; {topo.get('circuits') or topo.get('circuits_per_coil', 6)} circuits; "
        f"{topo.get('condenser_cooling', 'Water')}"
    )


class CaseLibrary:
    def __init__(self, base_dir: str = LIBRARY_DIR):
        self.base = base_dir
        self.cases_dir = os.path.join(self.base, "cases")
        self.family_path = os.path.join(self.base, "case_families.json")
        os.makedirs(self.cases_dir, exist_ok=True)
        self.ensure_family_rulebook()

    @staticmethod
    def _read(path: str, default):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return default
        except Exception as exc:
            print(f"[CASE_LIBRARY] Failed reading {path}: {exc}")
            return default

    @staticmethod
    def _write(path: str, data) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)

    def ensure_family_rulebook(self) -> dict:
        families = self._read(self.family_path, None)
        if not isinstance(families, dict):
            families = copy.deepcopy(FAMILY_RULEBOOK)
            self._write(self.family_path, families)
        else:
            reach = families.setdefault("reach_in", {})
            changed = False
            for key in ("module_pitch_in", "shelf_width_in"):
                if reach.get(key) != 30:
                    reach[key] = 30
                    changed = True
            if changed:
                self._write(self.family_path, families)
        return families

    def families(self) -> dict:
        return self.ensure_family_rulebook()

    def case_dir(self, case_id: str) -> str:
        return os.path.join(self.cases_dir, case_id)

    def case_path(self, case_id: str) -> str:
        return os.path.join(self.case_dir(case_id), "case.json")

    def diagram_path(self, case_id: str) -> str:
        return os.path.join(self.case_dir(case_id), "diagram.json")

    def test_path(self, case_id: str, test_id: str) -> str:
        return os.path.join(self.case_dir(case_id), "tests", f"{test_id}.json")

    def cases(self) -> List[dict]:
        out = []
        if not os.path.isdir(self.cases_dir):
            return out
        for cid in sorted(os.listdir(self.cases_dir)):
            case = self._read(self.case_path(cid), None)
            if case:
                case = self._clean_case_if_needed(case)
                out.append(case)
        return sorted(out, key=lambda c: (c.get("last_used") or "", c.get("model") or ""), reverse=True)

    def get_case(self, case_id: str) -> Optional[dict]:
        case = self._read(self.case_path(case_id), None)
        return self._clean_case_if_needed(case) if case else None

    def _clean_case_if_needed(self, case: dict) -> dict:
        topo = case.get("topology", {}) or {}
        clean = clean_topology(topo, self.families())
        if clean != topo:
            case["topology"] = clean
            self._write(self.case_path(case["id"]), case)
        return case

    def save_case(self, case: dict) -> dict:
        if not case.get("id"):
            case["id"] = _safe_name(case.get("model") or _new_id("case"))
        case.setdefault("created_by", _user())
        case.setdefault("created_at", _now())
        case["updated_at"] = _now()
        case["topology"] = clean_topology(case.get("topology", {}), self.families())
        self._write(self.case_path(case["id"]), case)
        return case

    def save_diagram(self, case_id: str, diagram: dict) -> None:
        self._write(self.diagram_path(case_id), diagram)

    def load_diagram(self, case_id: str) -> dict:
        return self._read(self.diagram_path(case_id), {})

    def tests_for_case(self, case_id: str) -> List[dict]:
        d = os.path.join(self.case_dir(case_id), "tests")
        if not os.path.isdir(d):
            return []
        return [self._read(os.path.join(d, f), None) for f in sorted(os.listdir(d)) if f.endswith(".json")]

    def all_tests(self) -> List[dict]:
        out = []
        for case in self.cases():
            out.extend(t for t in self.tests_for_case(case["id"]) if t)
        return out

    def new_case(self, model: str, topology: dict, parts=None, settings=None, defaults=None, notes: str = "") -> dict:
        cid = _safe_name(model)
        existing = self.get_case(cid)
        if existing:
            cid = _new_id("case")
        return {
            "id": cid,
            "model": model.strip(),
            "notes": notes,
            "topology": clean_topology(topology, self.families()),
            "parts": parts or {},
            "settings": settings or {
                "refrigerant": "R290",
                "charge_oz": None,
                "water_gpm": None,
                "fan_cfm": None,
                "defrost_schedule": "",
                "setpoints": "",
            },
            "default_targets": defaults or [dict(t) for t in DEFAULT_TARGETS],
            "created_by": _user(),
            "created_at": _now(),
            "updated_at": _now(),
            "last_used": None,
        }

    def create_test(self, case: dict, elp_code: str, title: str, objective: str, targets: list) -> dict:
        n = len(self.all_tests()) + 1
        test = {
            "id": _new_id("test"),
            "request_no": f"TR-{datetime.now().year}-{n:03d}",
            "case_id": case["id"],
            "elp_code": elp_code,
            "title": title,
            "objective": objective,
            "targets": targets or copy.deepcopy(case.get("default_targets") or DEFAULT_TARGETS),
            "revisions": [{"rev": "A", "at": _now(), "by": _user(), "note": "Initial release"}],
            "created_by": _user(),
            "created_at": _now(),
        }
        self._write(self.test_path(case["id"], test["id"]), test)
        return test

    def save_test(self, test: dict) -> dict:
        self._write(self.test_path(test["case_id"], test["id"]), test)
        return test

    def mark_used(self, case_id: str) -> None:
        case = self.get_case(case_id)
        if case:
            case["last_used"] = _now()
            self.save_case(case)

def apply_case_to_session(case: dict, diagram: dict, data_manager, emit_signals: bool = True) -> None:
    data_manager.diagram_model = copy.deepcopy(diagram or {})
    if not data_manager.diagram_model:
        from diagram_from_request import generate_case_diagram

        data_manager.diagram_model = generate_case_diagram(case.get("topology", {}), FAMILY_RULEBOOK)
    data_manager.case_id = case.get("id")
    if data_manager.case_id:
        data_manager.diagram_model["_case_id"] = data_manager.case_id
    settings = case.get("settings") or {}
    if settings.get("refrigerant"):
        data_manager.refrigerant = settings.get("refrigerant")
    comp = (case.get("parts") or {}).get("compressor")
    gpm = settings.get("water_gpm")
    if comp:
        data_manager.rated_inputs.update(compressor_to_rated_inputs(comp.get("snapshot", {}), gpm))
    elif gpm:
        data_manager.rated_inputs["gpm_water"] = float(gpm)
    if comp:
        snap = comp.get("snapshot", {})
        disp = snap.get("displacement_in3")
        rpm = snap.get("rated_speed_rpm")
        for component in (data_manager.diagram_model or {}).get("components", {}).values():
            if component.get("type") == "Compressor":
                props = component.setdefault("properties", {})
                if disp:
                    props["displacement_cm3"] = float(disp) * 16.387064
                if rpm:
                    props["speed_rpm"] = float(rpm)
    if emit_signals:
        data_manager.diagram_model_changed.emit()
        data_manager.data_changed.emit()


def test_to_printable_request(test: dict, case: dict) -> dict:
    req = copy.deepcopy(test)
    req["case_model"] = case.get("model", "")
    req["topology"] = ensure_old_topology(case.get("topology", {}), FAMILY_RULEBOOK)
    req["parts"] = copy.deepcopy(case.get("parts") or {})
    req["settings"] = copy.deepcopy(case.get("settings") or {})
    return req


def request_to_case_html(test: dict, case: dict) -> str:
    project_name = case.get("model", "")
    return request_to_html(test_to_printable_request(test, case), project_name)
