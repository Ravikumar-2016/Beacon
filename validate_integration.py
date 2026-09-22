#!/usr/bin/env python3
r"""
Stage 6 Integration Verification -- Agent -> Entrypoint Contract

This is deliberately separate from validate_orchestrator.py (Stage 5, frozen).
Stage 5 verified orchestrate.py's internal logic via Python-level imports.
Stage 6 verifies the actual external contract an agent relies on: running
orchestrate.py as a subprocess, using the package's own .venv interpreter
(not whatever `python` happens to resolve to on PATH), from an arbitrary
working directory, and inspecting only its process-level outputs
(exit code, stdout, stderr, filesystem side effects).

Run with the project .venv:
    .venv\Scripts\python.exe validate_integration.py [--skip-live]
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import subprocess
import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.join(ROOT, "brand-ai-readiness-audit")
# .venv lives at the dev root, one level above the marketplace root, so the
# marketplace root itself stays free of dev-only artifacts for submission.
VENV_PYTHON = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
SKILLS_DIR = os.path.join(PKG_ROOT, "skills")
ORCHESTRATE_PATH = os.path.join(SKILLS_DIR, "audit-orchestrator", "scripts", "orchestrate.py")
REPORT_BUILDER_PATH = os.path.join(SKILLS_DIR, "audit-orchestrator", "scripts", "report_builder.py")
MARKETPLACE_JSON_PATH = os.path.join(PKG_ROOT, "marketplace.json")

SKILL_DIR_NAMES = ["audit-orchestrator", "crawl-render-audit", "freshness-corroboration", "engagement-audit"]

# Test/validation harnesses legitimately use synthetic domains for fixtures;
# only PRODUCTION skill scripts are scanned for hardcoded real-world domains.
_SUSPECT_DOMAINS = [
    "example.com", "docs.python.org", "nginx.org", "ycombinator.com",
    "vuejs.org", "vue.js",
]


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _list_tmp_artifacts() -> set[str]:
    """Snapshot any leftover dynamic-loading temp files across all skill
    scripts/ directories (the pattern used by orchestrate.py and every
    validate_*.py harness: `_<namespace>_..._tmp.py`)."""
    found = set()
    for skill_dir in SKILL_DIR_NAMES:
        scripts_dir = os.path.join(SKILLS_DIR, skill_dir, "scripts")
        if not os.path.isdir(scripts_dir):
            continue
        for fname in os.listdir(scripts_dir):
            if fname.startswith("_") and "tmp" in fname:
                found.add(os.path.join(scripts_dir, fname))
    return found


def _docstring_line_ranges(tree: ast.AST) -> list[tuple[int, int]]:
    """Line ranges (inclusive) of every module/class/function docstring."""
    ranges: list[tuple[int, int]] = []

    def _add_if_docstring(node) -> None:
        body = getattr(node, "body", None)
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            expr = body[0]
            ranges.append((expr.lineno, getattr(expr, "end_lineno", expr.lineno)))

    _add_if_docstring(tree)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            _add_if_docstring(node)
    return ranges


def _domain_is_only_in_comment_or_docstring(source: str, domain: str) -> bool:
    """True if every line mentioning `domain` is either a `#` comment line or
    falls within an actual docstring's line range — as opposed to a string
    literal used in executable logic (e.g. a URL passed to a request or
    compared in a conditional)."""
    lines = source.splitlines()
    comment_lines = {i for i, line in enumerate(lines, start=1) if line.strip().startswith("#")}
    hit_lines = {i for i, line in enumerate(lines, start=1) if domain in line.lower()}
    if not hit_lines:
        return True

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False

    doc_ranges = _docstring_line_ranges(tree)

    def _in_docstring(i: int) -> bool:
        return any(start <= i <= end for start, end in doc_ranges)

    return all(i in comment_lines or _in_docstring(i) for i in hit_lines)


def _check(results, label, condition, detail=""):
    results.append((label, condition))
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    return condition


# ---------------------------------------------------------------------------
# Part 1: real subprocess invocation of orchestrate.py
# ---------------------------------------------------------------------------

def run_subprocess_integration_test(site_url: str):
    results = []
    print("\n" + "=" * 72)
    print("SUBPROCESS INTEGRATION TEST (actual agent-facing invocation)")
    print(f"Interpreter: {VENV_PYTHON}")
    print(f"Script:      {ORCHESTRATE_PATH}")
    print(f"Site:        {site_url}")
    print("=" * 72)

    _check(results, "Package .venv interpreter exists", os.path.isfile(VENV_PYTHON), VENV_PYTHON)
    _check(results, "orchestrate.py exists at expected path", os.path.isfile(ORCHESTRATE_PATH), ORCHESTRATE_PATH)

    before_tmp = _list_tmp_artifacts()

    proc = subprocess.run(
        [VENV_PYTHON, ORCHESTRATE_PATH, site_url],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,  # deliberately the repo root, NOT the skill's own directory
        timeout=120,
    )

    after_tmp = _list_tmp_artifacts()

    _check(results, "Exit code is 0", proc.returncode == 0, f"returncode={proc.returncode}, stderr={proc.stderr[:500]}")
    _check(results, "stderr is empty", proc.stderr.strip() == "", repr(proc.stderr[:500]))

    report = None
    try:
        report = json.loads(proc.stdout)
        stdout_is_json = True
    except json.JSONDecodeError as exc:
        stdout_is_json = False
        print(f"    JSON parse error: {exc}")
    _check(results, "stdout parses as JSON (and nothing else is mixed in)", stdout_is_json)

    if report is not None:
        report_builder = _load_module(REPORT_BUILDER_PATH, "vi_report_builder")
        schema_errors = report_builder.validate_report(report)
        _check(results, "Report conforms to the required public schema", schema_errors == [], str(schema_errors))
        _check(results, "audited_at is ISO-8601 parseable", _is_iso8601(report.get("audited_at", "")))
        print(f"    findings: {report.get('summary', {}).get('total_findings', '?')}")
        for f in report.get("findings", []):
            print(f"      [{f['severity'].upper()}] {f['id']}: {f['title']}")

    _check(results, "No new temporary artifacts left behind after the run",
           after_tmp == before_tmp, f"before={before_tmp}, after={after_tmp}")

    return results, report


def _is_iso8601(value: str) -> bool:
    from datetime import datetime
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except (ValueError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# Part 2: README's own six-item validation checklist
# ---------------------------------------------------------------------------

def run_readme_checklist():
    results = []
    print("\n" + "=" * 72)
    print("README VALIDATION CHECKLIST (six items, from brand-ai-readiness-audit/README.md)")
    print("=" * 72)

    # 1. marketplace.json is valid JSON, exactly 4 skills, exactly 1 entrypoint.
    try:
        with open(MARKETPLACE_JSON_PATH, encoding="utf-8") as f:
            marketplace = json.load(f)
        skills = marketplace.get("skills", [])
        entrypoints = [s for s in skills if s.get("entrypoint") is True]
        ok = len(skills) == 4 and len(entrypoints) == 1
        detail = f"{len(skills)} skill(s), {len(entrypoints)} entrypoint(s)"
    except Exception as exc:
        ok, detail = False, str(exc)
    _check(results, "1. marketplace.json is valid JSON with exactly 4 skills and 1 entrypoint", ok, detail)

    # 2 & 3. Each skill directory has a valid SKILL.md with name/description
    #        frontmatter, and name matches the directory name.
    frontmatter_ok = True
    name_match_ok = True
    detail_lines = []
    for skill_dir in SKILL_DIR_NAMES:
        skill_md_path = os.path.join(SKILLS_DIR, skill_dir, "SKILL.md")
        if not os.path.isfile(skill_md_path):
            frontmatter_ok = False
            detail_lines.append(f"{skill_dir}: SKILL.md missing")
            continue
        with open(skill_md_path, encoding="utf-8") as f:
            content = f.read()
        if not content.startswith("---"):
            frontmatter_ok = False
            detail_lines.append(f"{skill_dir}: no frontmatter block")
            continue
        end = content.find("---", 3)
        frontmatter = content[3:end] if end != -1 else ""
        has_name = "\nname:" in ("\n" + frontmatter)
        has_description = "\ndescription:" in ("\n" + frontmatter)
        if not (has_name and has_description):
            frontmatter_ok = False
            detail_lines.append(f"{skill_dir}: missing name/description in frontmatter")
        name_line = next((l for l in frontmatter.splitlines() if l.strip().startswith("name:")), "")
        declared_name = name_line.split("name:", 1)[-1].strip()
        if declared_name != skill_dir:
            name_match_ok = False
            detail_lines.append(f"{skill_dir}: SKILL.md name='{declared_name}' != directory name")

    _check(results, "2. Each skill directory has a valid SKILL.md with name/description frontmatter",
           frontmatter_ok, "; ".join(detail_lines))
    _check(results, "3. Skill name (frontmatter) matches its directory name",
           name_match_ok, "; ".join(detail_lines))

    # 4. Scripts import/compile without obvious errors.
    compile_errors = []
    for skill_dir in SKILL_DIR_NAMES:
        scripts_dir = os.path.join(SKILLS_DIR, skill_dir, "scripts")
        if not os.path.isdir(scripts_dir):
            continue
        for fname in sorted(os.listdir(scripts_dir)):
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(scripts_dir, fname)
            try:
                # utf-8-sig transparently strips a leading BOM if present
                # (several existing, already-signed-off files have one) —
                # matches how Python's own import machinery reads source,
                # so this doesn't flag files that already load and run fine.
                with open(fpath, encoding="utf-8-sig") as f:
                    source = f.read()
                compile(source, fpath, "exec")
            except SyntaxError as exc:
                compile_errors.append(f"{skill_dir}/{fname}: {exc}")
    _check(results, "4. All scripts compile without syntax errors", not compile_errors, "; ".join(compile_errors))

    # 5. No hardcoded target websites in PRODUCTION skill scripts.
    # Mentions inside comments or docstrings (e.g. a docstring illustrating
    # URL-normalization behavior) are illustrative documentation, not
    # behavioral special-casing, and are excluded — this distinction was
    # already reviewed and accepted during the Stage 2 sign-off for the
    # specific cases this exclusion covers.
    hardcoded_hits = []
    for skill_dir in SKILL_DIR_NAMES:
        scripts_dir = os.path.join(SKILLS_DIR, skill_dir, "scripts")
        if not os.path.isdir(scripts_dir):
            continue
        for fname in sorted(os.listdir(scripts_dir)):
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(scripts_dir, fname)
            with open(fpath, encoding="utf-8-sig") as f:
                source = f.read()
            for domain in _SUSPECT_DOMAINS:
                if domain in source.lower() and not _domain_is_only_in_comment_or_docstring(source, domain):
                    hardcoded_hits.append(f"{skill_dir}/{fname}: contains '{domain}' outside a comment/docstring")
    _check(results, "5. No hardcoded target websites in production skill scripts (outside comments/docstrings)",
           not hardcoded_hits, "; ".join(hardcoded_hits))

    return results


def print_summary(subprocess_results, readme_results):
    all_results = subprocess_results + readme_results
    n_pass = sum(1 for _, ok in all_results if ok)
    n_total = len(all_results)
    print("\n" + "=" * 72)
    print("STAGE 6 OVERALL RESULT")
    print("=" * 72)
    print(f"Checks passed: {n_pass}/{n_total}")
    return n_pass, n_total


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-live", action="store_true")
    parser.add_argument("--site", default="https://example.com/")
    args = parser.parse_args()

    print("=" * 72)
    print("Brand AI Readiness -- Stage 6 Integration Verification")
    print(f"Python (this script): {sys.version.split()[0]}  |  CWD: {os.getcwd()}")
    print("=" * 72)

    readme_results = run_readme_checklist()

    subprocess_results = []
    report = None
    if not args.skip_live:
        subprocess_results, report = run_subprocess_integration_test(args.site)
        # 6. Final report follows the required schema — reuses the live
        # subprocess result above rather than re-running the audit.
        if report is not None:
            report_builder = _load_module(REPORT_BUILDER_PATH, "vi_report_builder_2")
            schema_errors = report_builder.validate_report(report)
            _check(readme_results, "6. Final report follows the required schema (live-site check)",
                   schema_errors == [], str(schema_errors))
        else:
            _check(readme_results, "6. Final report follows the required schema (live-site check)",
                   False, "no report produced")

    n_pass, n_total = print_summary(subprocess_results, readme_results)
    if n_pass != n_total:
        sys.exit(1)
