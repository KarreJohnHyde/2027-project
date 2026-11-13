"""Stage an allowlisted source snapshot in a separate clean GitHub-history worktree.

Never copies this workspace's Git objects, data, keys, model weights or binary assets.
Commit and push remain explicit subsequent operations after scans and verification.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DENIED = {".git", ".cache", ".venv", "data", "artifacts", "uploads", "database", "node_modules", "dist", "_imports", "_derived"}


def git(directory, *arguments):
    return subprocess.check_output(["git", "-C", str(directory), *arguments], text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    destination = args.worktree.resolve(strict=True)
    boundary = (ROOT / ".cache/publication").resolve()
    if destination == boundary or not destination.is_relative_to(boundary): raise ValueError("Publication worktree must be a child of the explicit ignored publication directory")
    common = Path(git(destination, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
    if common == (ROOT / ".git").resolve() or common.is_relative_to((ROOT / ".git").resolve()): raise ValueError("Refusing the original workspace Git history")
    remote = git(destination, "remote", "get-url", "origin").removesuffix(".git")
    if remote != "https://github.com/KarreJohnHyde/2027-project": raise ValueError("Unexpected publication destination")
    if git(destination, "rev-parse", "HEAD") != args.expected_head or git(destination, "rev-parse", "origin/main") != args.expected_head: raise ValueError("Publication base changed; inspect before retrying")
    if git(destination, "status", "--porcelain"): raise ValueError("Publication worktree must be clean before snapshot preparation")
    snapshot = args.snapshot.resolve(strict=True)
    if not snapshot.is_relative_to((ROOT / ".cache/completion-release").resolve()): raise ValueError("Only a locally audited source snapshot is accepted")
    manifest = json.loads((snapshot / "SOURCE_SNAPSHOT_MANIFEST.json").read_text(encoding="utf-8"))
    if manifest.get("published") is not False: raise ValueError("Unexpected source snapshot schema")
    files = []
    for entry in manifest["files"]:
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts or relative.parts[0] in DENIED: raise ValueError("Unsafe source path")
        if relative.name.startswith(".env") and relative.name != ".env.example": raise ValueError("Secret environment file refused")
        origin, live, target = snapshot / relative, ROOT / relative, destination / relative
        if origin.is_symlink() or live.is_symlink() or target.is_symlink(): raise ValueError("Source symlink refused")
        if not target.resolve().is_relative_to(destination): raise ValueError("Publication path escaped through an existing directory")
        raw = origin.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != entry["sha256"] or hashlib.sha256(live.read_bytes()).hexdigest() != digest: raise ValueError(f"Source changed since audited snapshot: {relative}")
        files.append((relative, origin, target))
    for relative, origin, target in files:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, target)
    # Owner LICENSE and all previously reviewed binaries remain in the clean base.
    paths = ROOT / ".cache/publication/stage-paths.bin"
    paths.write_bytes(b"\0".join(str(relative).replace("\\", "/").encode() for relative, _, _ in files) + b"\0")
    subprocess.run(["git", "-C", str(destination), "add", f"--pathspec-from-file={paths}", "--pathspec-file-nul"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(destination), "diff", "--cached", "--check"], check=True)
    changed = git(destination, "diff", "--cached", "--name-only").splitlines()
    report = {"status": "STAGED_FOR_REVIEW_NOT_PUBLISHED", "publication_base": args.expected_head, "source_snapshot_manifest_sha256": hashlib.sha256((snapshot / "SOURCE_SNAPSHOT_MANIFEST.json").read_bytes()).hexdigest(), "source_files": len(files), "staged_files": changed, "original_git_history_copied": False, "new_binary_assets_copied": False, "weights_data_keys_copied": False, "owner_license_preserved": (destination / "LICENSE").is_file(), "published": False}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "source_files": len(files), "changed_files": len(changed)}))


if __name__ == "__main__": main()
