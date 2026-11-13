"""Create a local history-free code snapshot; never publish or alter Git history."""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import hashlib
import json
import shutil
import subprocess
import sys
import privacy_scan

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/completion-2026-11-13/release"
TEXT = {".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".css", ".html", ".json", ".yaml", ".yml", ".toml", ".md", ".txt", ".ps1", ".sh", ".sql", ".ini", ".cfg", ".conf", ".example"}
DENY = {".git", ".cache", ".venv", "artifacts", "database", "uploads", "data", "node_modules", "dist", "_derived", "_imports"}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = ROOT / ".cache/completion-release" / f"source-{stamp}"
    destination.mkdir(parents=True, exist_ok=False)
    inventory = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT).decode().split("\0")
    allow = json.loads((ROOT / "scripts/privacy_allowlist.json").read_text(encoding="utf-8"))["entries"]
    scan = privacy_scan.Report(allowlist={entry["key"]: entry for entry in allow})
    files = []
    for name in sorted(set(inventory)):
        if not name: continue
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts: raise ValueError("Unexpected source path traversal")
        if (ROOT / relative).is_symlink(): continue
        source = (ROOT / relative).resolve()
        if not source.is_relative_to(ROOT) or not source.is_file(): continue
        if source.relative_to(ROOT).parts[0] in DENY: continue
        if relative.parts[0] in DENY or relative.as_posix().startswith(("public/models/", "public/anatomy/derived/")): continue
        if source.suffix.lower() not in TEXT and source.name not in {".gitignore", ".dockerignore", ".gitattributes", "Dockerfile.frontend", "Dockerfile"}: continue
        if source.stat().st_size > 16 * 1024 * 1024: raise ValueError("Unexpected oversized code/reference file; manual source scope review required")
        raw = source.read_bytes()
        content = privacy_scan.decode(raw)
        if content is None: raise ValueError("Binary source found in text snapshot scope")
        privacy_scan.scan_text(content, "snapshot", relative.as_posix(), scan)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        files.append({"path": relative.as_posix(), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
    manifest = {"schema_version": "medtwin.history-free-source-snapshot.v1", "created_at": stamp,
                "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "uncommitted_source_included": True, "scope": "LOCAL_TEXT_SOURCE_AND_REFERENCE_METADATA_ONLY_NOT_DEPLOYMENT_OR_CLINICAL_RELEASE",
                "excluded": ["Git objects/history", "patient records/uploads", "credentials/keys", "weights/datasets", "raw/derived anatomy binaries", "private attachments"],
                "published": False, "files": files}
    (destination / "SOURCE_SNAPSHOT_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    findings = [{"path": item.location, "category": item.category, "line": item.line} for item in scan.findings]
    proof = {"status": "VERIFIED_HISTORY_FREE_LOCAL_SOURCE" if not findings else "BLOCKED_PRIVACY_FINDINGS", "snapshot_directory": str(destination), "file_count": len(files),
             "git_metadata_present": any(p.name == ".git" for p in destination.rglob(".git")), "privacy_findings": findings, "allowlisted_synthetic_counts": dict(scan.allowlisted),
             "manifest_sha256": hashlib.sha256((destination / "SOURCE_SNAPSHOT_MANIFEST.json").read_bytes()).hexdigest(), "published": False,
             "original_history_changed": False, "clinical_or_commercial_release_approval": False}
    (OUT / "source-snapshot.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": proof["status"], "file_count": len(files), "privacy_findings": len(findings), "git_metadata_present": proof["git_metadata_present"]}))
    if findings or proof["git_metadata_present"]: raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, default=OUT)
    arguments = parser.parse_args()
    OUT = arguments.output_directory.resolve()
    if not OUT.is_relative_to((ROOT / "artifacts").resolve()): raise ValueError("Snapshot proof must stay in the explicit artifacts directory")
    main()
