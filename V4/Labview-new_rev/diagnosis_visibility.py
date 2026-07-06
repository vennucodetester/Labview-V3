"""Presentation rules for diagnostic confidence and diagram visibility."""

from __future__ import annotations


TRUSTED_DIAGRAM_PREFIXES = ("SI-", "SCORECARD")
NEUTRAL_CANDIDATE_SEVERITY = "OBSERVATION"


def finding_confidence(finding) -> str:
    scenario_id = str(getattr(finding, "scenario_id", "") or "")
    if any(scenario_id.startswith(prefix) for prefix in TRUSTED_DIAGRAM_PREFIXES):
        return "trusted"
    return "candidate"


def is_candidate_finding(finding) -> bool:
    return (
        finding_confidence(finding) == "candidate"
        and getattr(finding, "severity", "") not in ("OK", "INFO")
    )


def is_diagram_visible_finding(finding) -> bool:
    return (
        finding_confidence(finding) == "trusted"
        and getattr(finding, "severity", "") in ("CRITICAL", "WARNING", "WATCH")
    )


def presentation_severity(finding) -> str:
    if is_candidate_finding(finding):
        return NEUTRAL_CANDIDATE_SEVERITY
    return getattr(finding, "severity", "") or "INFO"


def finding_sort_key(finding) -> tuple:
    severity_rank = {"CRITICAL": 0, "WARNING": 1, "WATCH": 2, "OK": 3, "INFO": 4}
    confidence_rank = {"trusted": 0, "candidate": 1}
    upstream_rank = {
        "System": 0,
        "Refrigerant": 1,
        "Compressor": 2,
        "Condenser": 3,
        "Filter Dryer": 4,
        "Distributor": 5,
        "TXV": 6,
        "CapTube": 6,
        "EEV": 6,
        "Evaporator": 7,
        "Evaporator Coil": 7,
        "Sensors": 8,
        "Sensors / Calculations": 8,
    }
    component = str(getattr(finding, "component", "") or "")
    return (
        severity_rank.get(getattr(finding, "severity", ""), 9),
        confidence_rank.get(finding_confidence(finding), 9),
        upstream_rank.get(component, 9),
        str(getattr(finding, "scenario_id", "") or ""),
    )
