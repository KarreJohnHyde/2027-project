"""Write docs/universal/remediation/REQUIREMENTS.csv: all 24 rows of docs/universal/requirements.csv with before/after
status, separate engineering, scientific and clinical fields. Only the nine open rows were re-assessed on 2026-11-14;
the other rows are carried over unchanged and say so.

  python scripts/remediation_requirements.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "universal" / "requirements.csv"
OUT = ROOT / "docs" / "universal" / "remediation" / "REQUIREMENTS.csv"

UPDATES = {
    "U-008": ("PARTIAL", "REFERENCE_DATA_MISSING",
              "Evidence graph, concordance/contradiction and missing-modality states work (earlier verified tests). LEARNED_FUSION_UNAVAILABLE: no genuinely paired, same-patient multi-modality cohort with outcomes exists locally; the PTB-XL ECG+demographics comparison shows no improvement (interval includes zero).",
              "Owner: obtain a paired cohort (same patients, matched times, defined outcome) under a data-use agreement."),
    "U-009": ("PARTIAL", "REFERENCE_DATA_MISSING",
              "Observed history, persistence/linear baselines and abstention work on the fictional control. No real longitudinal lab cohort with defined outcomes is available; disease-specific forecasting stays abstained.",
              "Owner: credentialed longitudinal data (e.g. MIMIC-IV via PhysioNet credentialing and DUA) or an institution's approved de-identified cohort."),
    "U-013": ("PARTIAL", "NOT_APPLICABLE",
              "scripts/remediation_dataset_integrity.py audited 39 prepared manifests: ARCADE stenosis (11 groups + 1 exact duplicate) and SYNTAX (2 groups) cross splits, 27 rows quarantined for independent evaluation; no other known leakage within the hashed coverage. 30 manifests cannot verify patient independence (no patient IDs). Exact hashing is complete for 7 manifests and partial or deferred for archive-held sets (RSNA zip, MedMNIST npz). Rights are classified per recorded terms; research purpose set by the owner on 2026-11-14.",
              "Engineering: hash archive members (RSNA, MedMNIST, Kvasir v2 remainder) within a larger budget. Owner: publisher-level patient IDs do not exist for content-grouped sets; "
              "six raw folders stay blocked without recorded publisher terms (RAW_FOLDER_RIGHTS.md: NIAID agreement for TB; LC25000 augmentation groups; LUNA16/LIDC and TB/NLM overlaps). "
              "Tabular audit (TABULAR_AUDIT.json): exact duplicate records between development and test in 4 tables; metrics without them reported."),
    "U-014": ("BLOCKED", "REFERENCE_DATA_MISSING",
              "Annotation and evaluation tooling exist and pass tests. Independently human-reviewed, permitted real full-report pages: 0. Synthetic pages and word crops are not full-report accuracy.",
              "Owner: 30-50 permitted, de-identified real report pages; one human transcriber and a second independent checker."),
    "U-015": ("PARTIAL", "INTERNAL_RESEARCH_ONLY",
              "New exact parity on real data: the app's head CT series path vs the CQ500 evaluator on two CQ500 scans, max |difference| 0.0 on all six labels (CPU float32). Skin parity is device-aware (exact on CUDA; CPU difference declared). The historical Kvasir one-pixel mismatch is unresolved: the original environment archive is absent.",
              "Tabular serving parity (2026-11-14): the serving function re-scores every stored test prediction of all 9 tabular models within the declared 6-decimal storage rounding (max 5e-7); "
              "every reported metric reproduces exactly at full precision. Engineering: parity for the CPU image and signal models once their queues finish. Historical Kvasir environment unavailable."),
    "U-016": ("PARTIAL", "VALIDATION_BLOCKED",
              "Rights blocker lifted for research by the owner's 2026-11-14 decision (11 verified-licence datasets authorized). A controlled GastroVision class-weighting experiment (development-only, test untouched) is queued on CPU. Kidney tumour, stroke, fracture and stenosis experiments need GPU-scale training; the GPU is on hold after three hardware crashes. Original weights unchanged.",
              "Owner: fix the GPU crash cause (BIOS, NVIDIA driver, leave the Insider build) before GPU experiments."),
    "U-017": ("PARTIAL", "REFERENCE_DATA_MISSING",
              "Source-space geometry, refusal of incompatible geometry and synthetic TRE checks exist. No independent expert-landmark, rights-cleared cohort exists, so L2/L3 atlas localisation stays disabled.",
              "Owner: an expert-landmarked registration cohort (e.g. a public challenge set with landmark labels) and independent reviewers."),
    "U-022": ("PARTIAL", "RELEASE_UNAPPROVED",
              "Tree privacy scan clean (1,126 files) on 2026-11-14; GitHub publication only via the history-free snapshot. The original Git history keeps its recorded sensitive objects (publication blocker). Training purpose is research; models on non-commercial data are not for sale. No clinical activation.",
              "Owner: legal, privacy and regulatory review for any release; decision on historical Git objects."),
    "U-023": ("PARTIAL", "NOT_APPLICABLE",
              "Containers, encrypted backups, wrong-key/tamper refusal and a restored backend on separate local storage were verified earlier (see completion report). Off-host disaster recovery is untested.",
              "Owner: an approved off-host backup destination; never real patient records without approval."),
}


def main() -> int:
    with SOURCE.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    out = []
    for row in rows:
        engineering, scientific, evidence, blocker = UPDATES.get(row["id"], (row["status"], "NOT_REASSESSED_IN_THIS_PASS", "", row.get("blocker", "")))
        out.append({"id": row["id"], "feature": row["feature"], "owner": row["owner"], "engineering_before": row["status"],
                    "engineering_after": engineering, "scientific_status": scientific, "clinical_status": "RELEASE_UNAPPROVED",
                    "evidence_2026_11_14": evidence, "remaining_blocker": blocker, "implementation_paths": row.get("implementation_paths", ""),
                    "test_paths": row.get("test_paths", ""), "evidence_paths": row.get("evidence_paths", "")})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(out[0]))
        writer.writeheader()
        writer.writerows(out)
    print(f"{len(out)} rows; re-assessed {sum(row['id'] in UPDATES for row in rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
