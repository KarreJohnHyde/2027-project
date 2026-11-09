"""Produce the bounded cleanup plan used for the owner's 2026-11-06 cleanup.

No deletion happens here. Runtime/config/sample-manifest references and tracked files
block removal. Historical documentation references do not imply a runtime dependency.
"""
from pathlib import Path
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/audits/cleanup-2026-11-06"
OUT.mkdir(parents=True, exist_ok=True)
UNUSED_SOURCES = ["health-assistant-main", "medical-main", "medvault-ai-main", "metriport-develop",
                  "SIH_26047-main", "TwinWeaver-main", "CogStack-SemEHR-master", "codex-plugin-cc-main",
                  "radgraph-master (1)"]
UNUSED_BRAIN = ["head_ct", "Head_CT_Hemorrhage", "Brain_CT_Hemorrhage", "Brain_Hemorrhage_Multiclass", "Brain_Data_Organised"]
CANDIDATES = {name: "Unused extracted source repository; no serving, training, setup or manifest dependency." for name in UNUSED_SOURCES}
CANDIDATES.update({name: "Unused brain data copy; no active model or sample-manifest reference; RSNA/CQ500 are retained." for name in UNUSED_BRAIN})
CANDIDATES.update({"External_Repositories/DeepSA": "Unlicensed unused research code/checkpoints; the DeepSA adapter is an unavailable placeholder, not an installed model.",
                   "chest_xray/chest_xray": "5,856 JPEGs matched by relative path and SHA-256 to chest_xray/{train,test,val}; remove the duplicate.",
                   "chest_xray/__MACOSX": "AppleDouble metadata accompanying the duplicate pneumonia extraction; not medical images."})


def inventory(path):
    files = [path] if path.is_file() else list(path.rglob("*"))
    if path.is_symlink() or any(p.is_symlink() or p.is_junction() for p in files):
        raise RuntimeError(f"Refusing a cleanup tree containing filesystem links: {path}")
    regular = [p for p in files if p.is_file()]
    return len(regular), sum(p.stat().st_size for p in regular)


def main():
    protected = []
    for name in ("src", "backend/app", "ml_training", "scripts", "tools", ".vscode", "_derived", "model_registry"):
        base = ROOT / name
        for path in base.rglob("*"):
            if not path.is_file() or any(part in ("node_modules", "__pycache__", ".cache") for part in path.parts):
                continue
            if path.suffix.lower() not in (".py", ".ts", ".tsx", ".js", ".json", ".csv", ".ps1", ".sh", ".cmd", ".pth"):
                continue
            if path.resolve() == Path(__file__).resolve() or path.name == "generate_workspace_inventory.py":
                continue
            protected.append(path)
    references = {}
    for path in protected:
        text = path.read_text(encoding="utf-8", errors="replace").replace("\\\\", "/").replace("\\", "/").lower()
        for name in CANDIDATES:
            # Match paths, not e.g. the head_ct_series function name or DeepSA's placeholder ID.
            needle = name.lower() + "/"
            if needle in text or (ROOT / name).as_posix().lower() in text:
                references.setdefault(name, []).append(path.relative_to(ROOT).as_posix())
    duplicates = json.loads((OUT / "pneumonia-duplicate-check.json").read_text())
    if len(duplicates) != 3 or not all(item["identical_relative_paths_and_sha256"] for item in duplicates):
        raise RuntimeError("Pneumonia duplicate hash check is not complete")
    plan = []
    for name, reason in CANDIDATES.items():
        path = (ROOT / name).resolve()
        path.relative_to(ROOT.resolve())
        if not path.exists():
            continue
        tracked = subprocess.check_output(["git", "ls-files", "--", name], cwd=ROOT, text=True).strip()
        if tracked or references.get(name):
            raise RuntimeError(f"Cannot remove referenced/tracked candidate {name}: {references.get(name)} {tracked[:200]}")
        count, size = inventory(path)
        # Retain small provenance/licence notices for removed source copies.
        if name in UNUSED_SOURCES or name == "External_Repositories/DeepSA":
            for notice in path.rglob("*"):
                if notice.is_file() and notice.name.lower().startswith(("license", "licence", "copying")) and notice.stat().st_size < 100_000:
                    target = OUT / "source-notices" / name / notice.relative_to(path)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(notice.read_bytes())
        plan.append({"path": str(path), "files": count, "bytes": size, "reason": reason})
    old = Path("D:/MedTwin_Removed_Datasets_2026-11-06").resolve()
    if old.exists():
        manifest = json.loads((old / "moved.json").read_text())
        for item in manifest["items"]:
            Path(item["to"]).resolve().relative_to(old)
        (OUT / "previous-moved.json").write_text(json.dumps(manifest, indent=2) + "\n")
        count, size = inventory(old)
        plan.append({"path": str(old), "files": count, "bytes": size,
                     "reason": "Previously removed unlicensed/unused datasets, audited in docs/research/DATASETS_MOVED_OUT_2026-11-06.md; owner now requested removal. Manifest retained."})
    report = {"workspace": str(ROOT), "protected_files_checked": len(protected), "items": plan,
              "total_bytes": sum(item["bytes"] for item in plan), "status": "AUDITED_NOT_YET_REMOVED"}
    (OUT / "plan.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"items": len(plan), "bytes": report["total_bytes"], "protected_files_checked": len(protected)}))


if __name__ == "__main__":
    main()
