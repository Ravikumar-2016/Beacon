"""
Severity Resolver — Applies consistent severity guidelines across all findings.

Severity levels: CRITICAL, HIGH, MEDIUM, LOW.
Severity depends on IMPACT, not merely whether a detector fired.
"""

from typing import Any

VALID_SEVERITIES = ("critical", "high", "medium", "low")


def resolve_severities(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate and normalize severity for each finding.

    Args:
        findings: List of finding dicts with preliminary severity.

    Returns:
        Findings with validated severity values.
    """
    resolved = []
    for finding in findings:
        sev = finding.get("severity", "medium").lower()
        if sev not in VALID_SEVERITIES:
            sev = "medium"
        finding["severity"] = sev
        resolved.append(finding)

    # Sort by severity: critical > high > medium > low
    severity_order = {s: i for i, s in enumerate(VALID_SEVERITIES)}
    resolved.sort(key=lambda f: severity_order.get(f["severity"], 3))

    return resolved


def severity_rank(severity: str) -> int:
    """Return numeric rank for sorting (lower = more severe)."""
    ranks = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return ranks.get(severity.lower(), 3)
