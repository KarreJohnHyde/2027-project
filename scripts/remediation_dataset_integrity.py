"""Deterministic dataset integrity audit for U-013 (2026-11-14): splits, grouping, cross-split leakage, exact duplicates
and usage rights for every prepared manifest under _derived/datasets.

For each manifest it records split counts, the grouping unit (patient, subject, near-duplicate group or none), groups
whose rows appear in more than one split, and exact byte duplicates across splits (SHA-256, within a byte budget;
anything beyond the budget is reported as DEFERRED, never as clean). Rows that leak are written to quarantine lists:
an evaluation that needs patient independence must exclude them. Source manifests and data are never modified.
Usage rights are copied from dataset_registry/tasks.json and classified by their recorded terms; this classifies,
it does not grant permission.

  python scripts/remediation_dataset_integrity.py [--byte-budget-gb 1.5]  (per manifest)
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DERIVED = ROOT / "_derived" / "datasets"
OUT_DOC = ROOT / "docs" / "universal" / "remediation" / "DATASET_INTEGRITY.json"
OUT_PRIVATE = ROOT / "artifacts" / "remediation-2026-11-14" / "quarantine"
# Prepared-folder name -> task-registry dataset id, where they differ (explicit; no fuzzy matching).
ALIASES = {"isles22-dwi-adc": "isles-2022", "kits19-segmentation": "kits19-labels", "msd-brain-tumour": "msd-task01-brain-tumour",
           "msd-liver": "msd-task03-liver", "acdc-cardiac-segmentation": "acdc-cardiac-mri"}
GROUP_COLUMNS = (("patient_id", "patient"), ("patient", "patient"), ("subject_id", "subject"), ("group_id", "group"))
csv.field_size_limit(10**8)


def rights_by_task() -> dict[str, dict]:
    registry = json.loads((ROOT / "dataset_registry" / "tasks.json").read_text(encoding="utf-8"))
    result = {}
    for dataset in registry["datasets"]:
        licence = dataset.get("license") or {}
        terms = str(licence.get("name") or "").upper()
        non_commercial = any(key in terms for key in ("BY-NC", "NON-COMMERCIAL", "NONCOMMERCIAL", "RESEARCH ONLY", "RESEARCH-ONLY",
                                                      "RESEARCH AND EDUCATIONAL", "RESEARCH USE", "NO REDISTRIBUTION"))
        # Commercial use is recorded only for explicitly permissive licences; anything else needs a human review.
        permissive = any(key in terms for key in ("CC0", "CC BY 4.0", "CC BY 3.0", "CC BY-SA", "ODC ATTRIBUTION", "OPEN DATA COMMONS ATTRIBUTION",
                                                  "NO RESTRICTIONS ON USE"))
        record = {"dataset_id": dataset["id"], "licence": licence.get("name"), "licence_status": licence.get("status"),
                  "training_authorization": licence.get("authorization_status") or "NOT_AUTHORIZED",
                  "authorization_scope": licence.get("authorization_scope"),
                  "usage_class": ("UNKNOWN_LICENCE_BLOCKED" if "NO LICENCE" in terms or not terms else
                                  "NON_COMMERCIAL_RESEARCH_ONLY" if non_commercial else
                                  "COMMERCIAL_USE_PERMITTED_BY_TERMS_WITH_ATTRIBUTION" if permissive else "TERMS_UNCLEAR_REVIEW_REQUIRED"),
                  "redistribution": "NOT_PERMITTED_OR_UNREVIEWED" if "NO REDISTRIBUTION" in terms or non_commercial else "PER_LICENCE_TERMS",
                  "clinical_use": "NOT_APPROVED"}
        for task in dataset.get("tasks") or []:
            result[task["task_id"]] = record
        result.setdefault(dataset["id"], record)
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 22), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_rows(name: str, rows: list[dict], budget: list[int]) -> tuple[dict, list[dict]]:
    columns = set(rows[0]) if rows else set()
    group_column, unit = next(((column, unit) for column, unit in GROUP_COLUMNS if column in columns), (None, "none"))
    splits = Counter(row.get("split", "") for row in rows)
    by_group: dict[str, set] = defaultdict(set)
    if group_column:
        for row in rows:
            by_group[str(row[group_column])].add(row.get("split", ""))
    crossing = sorted(group for group, parts in by_group.items() if len(parts) > 1)
    quarantine = [{"reason": "GROUP_CROSSES_SPLITS", "group": row[group_column], "split": row.get("split"), "entry": row.get("entry") or row.get("case_id") or ""}
                  for row in rows if group_column and str(row[group_column]) in set(crossing) and row.get("split") != "train"]
    hashed, deferred, duplicate_groups = 0, 0, 0
    path_column = next((column for column in ("path", "image_path") if column in columns), None)
    if path_column and rows:
        by_hash: dict[str, set] = defaultdict(set)
        entries: dict[str, list] = defaultdict(list)
        for row in rows:
            path = Path(row[path_column])
            if not path.is_file():
                deferred += 1
                continue
            size = path.stat().st_size
            if budget[0] - size < 0:
                deferred += 1
                continue
            budget[0] -= size
            digest = sha256(path)
            hashed += 1
            by_hash[digest].add(row.get("split", ""))
            entries[digest].append(row)
        for digest, parts in by_hash.items():
            if len(parts) > 1:
                duplicate_groups += 1
                quarantine += [{"reason": "EXACT_DUPLICATE_ACROSS_SPLITS", "group": digest[:16], "split": row.get("split"),
                                "entry": row.get("entry") or ""} for row in entries[digest] if row.get("split") != "train"]
    elif rows:
        deferred = len(rows)
    independence = ("PATIENT_SEPARATION_RECORDED" if unit in ("patient", "subject") else
                    "PATIENT_INDEPENDENCE_UNVERIFIED_GROUPED_BY_CONTENT_ONLY" if unit == "group" else "PATIENT_INDEPENDENCE_UNVERIFIED")
    summary = {"manifest": name, "rows": len(rows), "splits": dict(splits), "group_column": group_column, "group_unit": unit,
               "groups": len(by_group), "groups_crossing_splits": len(crossing), "crossing_group_examples": crossing[:10],
               "exact_hash": {"files_hashed": hashed, "files_deferred_budget_or_unresolved": deferred, "duplicate_sets_across_splits": duplicate_groups,
                              "status": "COMPLETE" if rows and deferred == 0 else "PARTIAL_DEFERRED" if hashed else "NOT_RUN_ARCHIVE_OR_PATHS"},
               "rows_quarantined_for_independent_evaluation": len({(q["split"], q["entry"]) for q in quarantine}),
               "patient_independence": independence}
    return summary, quarantine


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--byte-budget-gb", type=float, default=1.5, help="Exact-hash byte budget per manifest")
    args = parser.parse_args()
    per_manifest = int(args.byte_budget_gb * 1024**3)
    rights = rights_by_task()
    results = []
    OUT_PRIVATE.mkdir(parents=True, exist_ok=True)
    for folder in sorted(path for path in DERIVED.iterdir() if path.is_dir()):
        sources = [(f"{folder.name}/{p.relative_to(folder).as_posix()}", p) for p in sorted(folder.rglob("samples.csv"))]
        manifest = folder / "manifest.json"
        for label, source in sources:
            with source.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            summary, quarantine = audit_rows(label, rows, [per_manifest])
            results.append((folder.name, summary, quarantine))
        if manifest.exists():
            data = json.loads(manifest.read_text(encoding="utf-8"))
            cases = [{"patient_id": str(case.get("patient_id") or case.get("case_id")), "split": case.get("split"),
                      "case_id": str(case.get("case_id") or case.get("patient_id"))} for case in data.get("cases", [])]
            summary, quarantine = audit_rows(f"{folder.name}/manifest.json", cases, [0])
            summary["exact_hash"]["status"] = "NOT_RUN_VOLUMES_HASHED_BY_MANIFEST_BUILDER"
            results.append((folder.name, summary, quarantine))
    report = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tool": "scripts/remediation_dataset_integrity.py",
              "byte_budget_gb": args.byte_budget_gb, "notice": ("Rights are classified from recorded terms and do not grant permission. "
              "Quarantined rows must be excluded from any evaluation that claims patient independence; source manifests are unchanged."),
              "manifests": []}
    for folder, summary, quarantine in results:
        # Exact task or dataset identifiers only; a near name could attach another dataset's licence.
        summary["rights"] = rights.get(ALIASES.get(folder, folder)) or {"usage_class": "NOT_IN_TASK_REGISTRY"}
        if quarantine:
            target = OUT_PRIVATE / (summary["manifest"].replace("/", "__") + ".csv")
            with target.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["reason", "group", "split", "entry"])
                writer.writeheader()
                writer.writerows(quarantine)
            summary["quarantine_list"] = str(target.relative_to(ROOT)).replace("\\", "/")
        report["manifests"].append(summary)
    totals = Counter()
    for summary in report["manifests"]:
        totals["manifests"] += 1
        totals["with_crossing_groups"] += summary["groups_crossing_splits"] > 0
        totals["with_exact_duplicates_across_splits"] += summary["exact_hash"]["duplicate_sets_across_splits"] > 0
        totals["patient_independence_unverified"] += summary["patient_independence"] != "PATIENT_SEPARATION_RECORDED"
        totals["rows_quarantined"] += summary["rows_quarantined_for_independent_evaluation"]
    report["totals"] = dict(totals)
    OUT_DOC.parent.mkdir(parents=True, exist_ok=True)
    OUT_DOC.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["totals"]))
    for summary in report["manifests"]:
        if summary["groups_crossing_splits"] or summary["exact_hash"]["duplicate_sets_across_splits"]:
            print(f"  LEAK {summary['manifest']}: {summary['groups_crossing_splits']} groups cross splits, "
                  f"{summary['exact_hash']['duplicate_sets_across_splits']} exact duplicate sets; {summary['rows_quarantined_for_independent_evaluation']} rows quarantined")
    return 0


if __name__ == "__main__":
    sys.exit(main())
