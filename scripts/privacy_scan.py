"""Privacy and secret scanner that never prints what it finds.

Reports categories, counts and locations (object, path, line) for patient
identifiers and credentials. Matched values are never written to stdout or to
the report; distinct values are only counted.

Scopes:
    --history   every blob in the Git object database (reachable or not),
                commit messages, and the refs/commits that reach each blob
    --tree      tracked files plus untracked, non-ignored files
    --paths P   arbitrary directories or files (e.g. dist/, a Docker context)
    --sqlite DB text columns of a SQLite database

Exit code 1 when any patient-identifier or credential finding remains, so the
release check can gate on it. Usage:
    python scripts/privacy_scan.py --history --tree --report logs/privacy/scan.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_BLOB_BYTES = 8 * 1024 * 1024

# Patient-identifier patterns. Structural, so the scanner needs no copy of the
# identifiers it is looking for.
PATIENT_PATTERNS: dict[str, re.Pattern[str]] = {
    "PATIENT_NAME_FIELD": re.compile(r"""["']?patient_?name["']?\s*[:=]\s*["'][^"'\n]{2,}["']""", re.IGNORECASE),
    "PATIENT_AGE_FIELD": re.compile(r"""["']?patient_?age["']?\s*[:=]\s*["'][^"'\n]+["']""", re.IGNORECASE),
    "HONORIFIC_NAME": re.compile(r"\b(?:Mr|Mrs|Ms|Miss)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+"),
    "LAB_REPORT_ID": re.compile(r"\b[A-Z0-9]{2,}-LAB-\d{4}-\d{3,}\b"),
    "RECORD_NUMBER": re.compile(r"\b(?:MRN|UHID|Patient\s*ID|Lab\s*No)\s*[:#.]\s*[A-Z0-9-]{4,}", re.IGNORECASE),
    "DATE_OF_BIRTH": re.compile(r"\b(?:DOB|Date\s+of\s+Birth)\s*[:-]\s*\d", re.IGNORECASE),
    "NATIONAL_ID_LIKE": re.compile(r"(?<!\d)\d{4}\s\d{4}\s\d{4}(?!\d)"),
    # A bare 10-digit number is usually a byte count or ID; require a prefix or a contact keyword.
    "PHONE_IN": re.compile(r"(?:\+91[\s-]?[6-9]\d{4}[\s-]?\d{5}\b|(?i:phone|mobile|tel|contact|whatsapp)\W{1,6}(?:\+?\d[\d\s-]{8,14}\d))"),
    "EMAIL": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
}
SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "PRIVATE_KEY": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "AWS_ACCESS_KEY": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GITHUB_TOKEN": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "API_KEY_SK": re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{24,}\b"),
    "SLACK_TOKEN": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    "JWT": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    "HARDCODED_SECRET": re.compile(r"""(?i)\b(?:secret|password|passwd|api[_-]?key|access[_-]?token)\b["']?\s*[:=]\s*["'][^"'\s]{12,}["']"""),
}
# Addresses and placeholders that are not personal data: RFC 2606/6761 reserved
# names (.invalid, .test, .example, .localhost, example.*), test.* hosts and
# service addresses.
EMAIL_ALLOW = re.compile(
    r"@(?:[a-z0-9.-]+\.(?:invalid|test|example|localhost)|example\.[a-z.]+|test\.[a-z0-9.-]+|anthropic\.com|users\.noreply\.github\.com|localhost)$|^noreply@|^git@",
    re.IGNORECASE,
)
SECRET_ALLOW = re.compile(r"test-only|replace-with|change-me|changeme|placeholder|example|dummy|verification-only|compose-validation|your[_-]", re.IGNORECASE)
TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".json", ".md", ".txt", ".csv", ".tsv", ".yaml", ".yml", ".toml", ".ini", ".cfg",
                 ".html", ".css", ".xml", ".sql", ".ps1", ".sh", ".bat", ".env", ".example", ".conf", ".rst", ".ipynb", ""}


@dataclass
class Finding:
    scope: str
    location: str
    line: int
    category: str
    kind: str  # PATIENT or SECRET
    context: str  # safe description: the key before the match, or an email's domain


def safe_context(line: str, match: re.Match[str], category: str) -> str:
    """Describe a match without revealing it: the identifier preceding it on the line."""
    if category == "EMAIL":
        return "domain=" + match.group(0).rsplit("@", 1)[-1].lower()
    before = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", line[: match.start()])
    key = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", match.group(0).split(":")[0].split("=")[0]) if category in {"PATIENT_NAME_FIELD", "PATIENT_AGE_FIELD", "HARDCODED_SECRET"} else []
    return "key=" + (key[0] if key else before[-1] if before else "<start>")


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    distinct_values: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    notes: list[str] = field(default_factory=list)
    scanned: Counter = field(default_factory=Counter)
    allowlist: dict[str, dict] = field(default_factory=dict)
    allowlisted: Counter = field(default_factory=Counter)


def line_key(location: str, line: str) -> str:
    """Allowlist key: file path (normalised) plus a hash of the exact line, so any edit re-flags it."""
    path = location.split(":", 2)[-1] if location.startswith("blob:") else location
    digest = hashlib.sha256(line.rstrip("\r\n").encode("utf-8")).hexdigest()
    return f"{path.replace(chr(92), '/')}#{digest}"


def scan_text(text: str, scope: str, location: str, report: Report) -> None:
    for number, line in enumerate(text.splitlines(), start=1):
        for kind, patterns in (("PATIENT", PATIENT_PATTERNS), ("SECRET", SECRET_PATTERNS)):
            for category, pattern in patterns.items():
                for match in pattern.finditer(line):
                    value = match.group(0)
                    if category == "EMAIL" and EMAIL_ALLOW.search(value):
                        continue
                    if kind == "SECRET" and SECRET_ALLOW.search(value):
                        continue
                    entry = report.allowlist.get(line_key(location, line))
                    if entry and category in entry.get("categories", []):
                        report.allowlisted[category] += 1
                        continue
                    report.findings.append(Finding(scope, location, number, category, kind, safe_context(line, match, category)))
                    report.distinct_values[category].add(value)


def decode(data: bytes) -> str | None:
    if b"\x00" in data[:8192]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def docx_text(data: bytes) -> str | None:
    import io
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            xml = archive.read("word/document.xml").decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, KeyError):
        return None
    return re.sub(r"<[^>]+>", " ", xml)


def git(*args: str, input_bytes: bytes | None = None) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), *args], input=input_bytes, capture_output=True, check=True).stdout


def scan_history(report: Report) -> dict:
    objects = [line.split() for line in git("cat-file", "--batch-all-objects", "--batch-check").decode().splitlines()]
    blobs = {sha: int(size) for sha, kind, size in objects if kind == "blob"}
    reachable: dict[str, set[str]] = defaultdict(set)
    for line in git("rev-list", "--all", "--objects").decode("utf-8", errors="replace").splitlines():
        sha, _, path = line.partition(" ")
        if sha in blobs and path:
            reachable[sha].add(path)
    commits = git("rev-list", "--all").decode().split()
    blob_commits: dict[str, set[str]] = defaultdict(set)
    for commit in commits:
        for entry in git("ls-tree", "-r", commit).decode("utf-8", errors="replace").splitlines():
            meta, _, _path = entry.partition("\t")
            parts = meta.split()
            if len(parts) == 3 and parts[1] == "blob":
                blob_commits[parts[2]].add(commit[:10])
    flagged: dict[str, Counter] = {}
    batch = git("cat-file", "--batch", input_bytes="\n".join(blobs).encode() + b"\n")
    offset = 0
    while offset < len(batch):
        header_end = batch.index(b"\n", offset)
        sha, _kind, size = batch[offset:header_end].decode().split()
        size = int(size)
        data = batch[header_end + 1: header_end + 1 + size]
        offset = header_end + 1 + size + 1
        report.scanned["blobs"] += 1
        if size > MAX_BLOB_BYTES:
            report.notes.append(f"blob {sha[:10]} ({size} bytes) skipped: larger than {MAX_BLOB_BYTES} bytes")
            continue
        text = decode(data)
        if text is None:
            report.scanned["binary_blobs_skipped"] += 1
            continue
        before = len(report.findings)
        paths = sorted(reachable.get(sha, {"<unreachable>"}))
        scan_text(text, "history", f"blob:{sha[:10]}:{paths[0]}", report)
        if len(report.findings) > before:
            flagged[sha] = Counter(f.category for f in report.findings[before:])
    for line in git("log", "--all", "--format=%H%x00%B%x01").decode("utf-8", errors="replace").split("\x01"):
        if "\x00" in line:
            commit, _, message = line.partition("\x00")
            report.scanned["commit_messages"] += 1
            scan_text(message, "history", f"commit-message:{commit.strip()[:10]}", report)
    refs = {}
    for line in git("for-each-ref", "--format=%(refname) %(objectname)").decode().splitlines():
        name, sha = line.split()
        refs[name] = sha[:10]
    reflog = git("reflog", "--all", "--format=%h %gd").decode().splitlines()
    exposure = []
    for sha, counts in flagged.items():
        reaching = sorted(blob_commits.get(sha, set()))
        reaching_refs = sorted(name for name, tip in refs.items() if tip in reaching or any(
            subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", commit, tip], capture_output=True).returncode == 0
            for commit in reaching))
        exposure.append({"blob": sha[:10], "paths": sorted(reachable.get(sha, {"<unreachable>"})), "categories": dict(counts),
                         "commits": reaching, "refs": reaching_refs, "reachable": sha in reachable})
    lfs_dir = ROOT / ".git" / "lfs" / "objects"
    lfs_files = [path for path in lfs_dir.rglob("*") if path.is_file()] if lfs_dir.exists() else []
    for path in lfs_files:
        data = path.read_bytes()
        text = docx_text(data) if data[:2] == b"PK" else None
        if text is not None:
            report.scanned["lfs_docx"] += 1
            scan_text(text, "history-lfs", f"lfs:{path.name[:10]}", report)
        else:
            report.scanned["lfs_binary_not_scanned"] += 1
    return {"objects": len(objects), "blobs": len(blobs), "commits": len(commits), "refs": refs, "reflog_entries": len(reflog), "flagged_blobs": exposure}


def tracked_and_untracked() -> list[Path]:
    listed = git("ls-files", "-z", "--cached", "--others", "--exclude-standard").decode("utf-8", errors="replace").split("\x00")
    return [ROOT / name for name in listed if name]


def scan_files(paths: list[Path], scope: str, report: Report) -> None:
    for path in paths:
        if not path.is_file() or path.stat().st_size > MAX_BLOB_BYTES:
            continue
        if path.suffix.lower() == ".docx":
            text = docx_text(path.read_bytes())
        elif path.suffix.lower() in TEXT_SUFFIXES or path.name.startswith(".env"):
            text = decode(path.read_bytes())
        else:
            continue
        if text is None:
            continue
        report.scanned[f"{scope}_files"] += 1
        try:
            location = str(path.relative_to(ROOT))
        except ValueError:
            location = str(path)
        scan_text(text, scope, location, report)


def scan_sqlite(database: Path, report: Report) -> dict:
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    summary = {}
    try:
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables:
            columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]
            counts = {"rows": connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]}
            for column in columns:
                if re.search(r"patient_?(name|ref)|^name$|email|phone|address|dob|birth", column, re.IGNORECASE):
                    counts[f"non_empty:{column}"] = connection.execute(f'SELECT COUNT(*) FROM "{table}" WHERE "{column}" IS NOT NULL AND TRIM(CAST("{column}" AS TEXT)) != ""').fetchone()[0]
                for (value,) in connection.execute(f'SELECT "{column}" FROM "{table}" WHERE typeof("{column}") = \'text\''):
                    scan_text(value, "sqlite", f"{database.name}:{table}.{column}", report)
            summary[table] = counts
    finally:
        connection.close()
    report.scanned["sqlite_tables"] += len(summary)
    return summary


def main() -> int:
    global ROOT
    parser = argparse.ArgumentParser(description="Privacy scan that reports locations, never values.")
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--tree", action="store_true")
    parser.add_argument("--paths", nargs="*", default=[])
    parser.add_argument("--sqlite", nargs="*", default=[])
    parser.add_argument("--report", help="Write a JSON report (locations and counts only).")
    parser.add_argument("--explain", action="store_true", help="Also print each finding's line number and safe context (never the value).")
    parser.add_argument("--allowlist", default=str(ROOT / "scripts" / "privacy_allowlist.json"),
                        help="Reviewed synthetic-fixture lines (path + line hash). Use '' to disable.")
    parser.add_argument("--print-keys", action="store_true", help="Print allowlist keys (path#line-hash) for current findings, for review.")
    parser.add_argument("--repo", help="Repository to scan (defaults to the one containing this script).")
    args = parser.parse_args()
    if args.repo:
        ROOT = Path(args.repo).resolve()

    report = Report()
    if args.allowlist and Path(args.allowlist).exists():
        entries = json.loads(Path(args.allowlist).read_text(encoding="utf-8"))["entries"]
        report.allowlist = {entry["key"]: entry for entry in entries}
    output: dict = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "values_redacted": True}
    if args.history:
        output["history"] = scan_history(report)
    if args.tree:
        scan_files(tracked_and_untracked(), "tree", report)
    for target in args.paths:
        root = Path(target).resolve()
        scan_files([root] if root.is_file() else [path for path in root.rglob("*") if path.is_file()], "paths", report)
    if args.sqlite:
        output["sqlite"] = {database: scan_sqlite(Path(database).resolve(), report) for database in args.sqlite}

    by_location: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for finding in report.findings:
        by_location[(finding.scope, finding.location)][finding.category] += 1
    output["scanned"] = dict(report.scanned)
    output["allowlisted_by_category"] = dict(report.allowlisted)
    output["distinct_values_by_category"] = {category: len(values) for category, values in report.distinct_values.items()}
    output["locations"] = [{"scope": scope, "location": location, "categories": dict(counts)} for (scope, location), counts in sorted(by_location.items())]
    output["notes"] = report.notes

    print(f"scanned: {dict(report.scanned)}")
    print(f"allowlisted synthetic fixtures by category: {dict(report.allowlisted) or 'none'}")
    print(f"distinct values by category (values withheld): {output['distinct_values_by_category'] or 'none'}")
    for entry in output["locations"]:
        print(f"  [{entry['scope']}] {entry['location']}: {entry['categories']}")
    if args.explain:
        for finding in report.findings:
            print(f"    {finding.scope} {finding.location}:{finding.line} {finding.category} {finding.context}")
    if args.print_keys:
        texts: dict[str, list[str]] = {}
        for finding in report.findings:
            if finding.scope != "tree":
                continue
            lines = texts.setdefault(finding.location, (ROOT / finding.location).read_text(encoding="utf-8", errors="replace").splitlines())
            print(f"    key {line_key(finding.location, lines[finding.line - 1])} {finding.category} {finding.context}")
    for blob in output.get("history", {}).get("flagged_blobs", []):
        print(f"  history exposure: blob {blob['blob']} paths={blob['paths']} commits={blob['commits']} refs={blob['refs']} reachable={blob['reachable']}")
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
        print(f"report: {target}")
    return 1 if report.findings else 0


if __name__ == "__main__":
    sys.exit(main())
