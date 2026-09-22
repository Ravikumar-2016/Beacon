"""
Report Builder — Assembles the final structured audit report.

Produces a JSON report conforming to the required Adobe schema:
- site, audited_at, summary (counts by severity), findings list.
- Each finding: id, title, severity, evidence, suggested_action.
"""

import json
from datetime import datetime, timezone
from typing import Any


def build_report(domain: str, findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the final audit report.

    Args:
        domain: The audited website domain.
        findings: Deduplicated, severity-resolved findings.

    Returns:
        Complete audit report dictionary.
    """
    # Assign sequential IDs
    for i, finding in enumerate(findings, start=1):
        finding["id"] = f"F-{i:03d}"

    # Count by severity
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for finding in findings:
        sev = finding.get("severity", "medium")
        if sev in counts:
            counts[sev] += 1

    report = {
        "site": domain,
        "audited_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": {
            "total_findings": len(findings),
            "critical": counts["critical"],
            "high": counts["high"],
            "medium": counts["medium"],
        },
        "findings": [_format_finding(f) for f in findings],
    }

    return report


def _format_finding(finding: dict[str, Any]) -> dict[str, Any]:
    """Format a finding into the required output schema."""
    return {
        "id": finding.get("id", "F-000"),
        "title": finding.get("title", "Untitled finding"),
        "severity": finding.get("severity", "medium"),
        "evidence": finding.get("evidence", "No evidence provided."),
        "suggested_action": {
            "summary": finding.get("suggested_action", {}).get(
                "summary", "Review and address this finding."
            ),
            "priority": finding.get("suggested_action", {}).get(
                "priority", finding.get("severity", "medium")
            ),
        },
    }


def validate_report(report: dict[str, Any]) -> list[str]:
    """Validate report against required schema. Returns list of errors."""
    errors = []

    for field in ("site", "audited_at", "summary", "findings"):
        if field not in report:
            errors.append(f"Missing required field: {field}")

    summary = report.get("summary", {})
    for field in ("total_findings", "critical", "high", "medium"):
        if field not in summary:
            errors.append(f"Missing summary field: {field}")

    for i, finding in enumerate(report.get("findings", [])):
        for field in ("id", "title", "severity", "evidence", "suggested_action"):
            if field not in finding:
                errors.append(f"Finding {i}: missing field: {field}")
        action = finding.get("suggested_action", {})
        for field in ("summary", "priority"):
            if field not in action:
                errors.append(f"Finding {i}: suggested_action missing: {field}")

    return errors


def to_json(report: dict[str, Any], indent: int = 2) -> str:
    """Serialize report to JSON string."""
    return json.dumps(report, indent=indent, ensure_ascii=False)
