"""Register an extracted Medical Segmentation Decathlon CT task in dataset_registry/tasks.json.

The licence is the one the task's own dataset.json declares (MSD: CC BY-SA 4.0); the download was approved by the
repository owner on 2026-11-06. The archive's SHA-256 is recorded so the trained model's provenance names exactly the
data it came from. Other records are kept unchanged.

    python scripts/register_msd_ct_dataset.py --archive <Task07_Pancreas.tar> --task-dir <extracted Task07_Pancreas> \
        --dataset-id msd-task07-pancreas --task-id msd-pancreas-tumour-segmentation --system pancreas \
        --target "pancreas and pancreatic tumour" --title "Medical Segmentation Decathlon Task07 Pancreas"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--task-dir", type=Path, required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--system", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--identity", default="")
    parser.add_argument("--modality", default="CT", help="Registry modality (CT for the CT tasks; MRI for prostate and hippocampus)")
    parser.add_argument("--approved-on", default="2026-11-06", help="Date the repository owner approved this download")
    args = parser.parse_args()
    meta = json.loads((args.task_dir / "dataset.json").read_text(encoding="utf-8"))
    licence = str(meta.get("licence") or meta.get("license") or "").strip()
    if "CC-BY-SA" not in licence.upper().replace(" ", "-"):
        raise SystemExit(f"dataset.json declares licence {licence!r}; expected the MSD CC BY-SA 4.0 licence.")
    images = [path for path in (args.task_dir / "imagesTr").glob("*.nii.gz") if not path.name.startswith("._")]
    record = {
        "id": args.dataset_id, "archive": args.archive.name, "title": args.title, "modality": args.modality, "system": args.system,
        "identity": args.identity or f"{len(images)} labelled training {args.modality} volumes (imagesTr/labelsTr); unlabelled test volumes unused; labels {meta.get('labels')}",
        "labels": "NIFTI_VOLUMES_WITH_MASKS", "official_splits": False, "patient_ids": "CASE_NUMBERS_ONLY",
        "source_archive": str(args.archive.resolve()).replace("\\", "/"), "source_sha256": sha256(args.archive),
        "files": sum(1 for _ in args.task_dir.rglob("*") if _.is_file() and not _.name.startswith("._")), "location": str(args.task_dir.resolve().parent).replace("\\", "/"),
        "license": {
            "status": "PUBLISHED_LICENCE_IN_ARCHIVE", "authorization_status": "VERIFIED",
            "authorization_reason": f"The archive's dataset.json declares \"licence\": \"{licence}\" ({meta.get('release') or 'MSD release'}). CC BY-SA 4.0 permits "
                                    "training and evaluation with attribution; adapted datasets must be shared alike. Trained weights are not distributed.",
            "authorized_by": f"published licence (CC BY-SA 4.0); download approved by the repository owner on {args.approved_on}",
            "authorized_on": args.approved_on, "authorization_scope": "local research training and evaluation; images and masks are not committed or redistributed",
            "name": "CC BY-SA 4.0 (Medical Segmentation Decathlon)", "source": f"{args.task_dir.name}/dataset.json inside the archive", "verified_on": args.approved_on,
            "citation": "Antonelli M, Reinke A, Bakas S, et al. The Medical Segmentation Decathlon. Nature Communications 13:4128 (2022); "
                        "Simpson AL, Antonelli M, Bakas S, et al. arXiv:1902.09063 (2019).",
        },
        "privacy": "PUBLISHER_DE_IDENTIFIED (case numbers only)", "exact_duplicate_overlap": {}, "notes": [],
        "tasks": [{"task_id": args.task_id, "type": "SEGMENTATION_VOLUMES", "target": args.target, "flags": ["TASK_SUPPORTED_BY_LABELS"],
                   "training_eligible": True, "trainer": f"python -m ml_training.volumetric_multichannel train --intensity {'ct' if args.modality == 'CT' else 'mr'}",
                   "manifest_builder": "python scripts/prepare_msd_ct_datasets.py; python -m ml_training.volumetric_manifest pairs",
                   "validation_ready": True, "readiness": "READY_FOR_TRAINING"}],
    }
    path = ROOT / "dataset_registry" / "tasks.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    previous = next((item for item in registry["datasets"] if item["id"] == args.dataset_id), None)
    if previous and previous.get("source_sha256") == record["source_sha256"]:
        review = previous.get("license", {}).get("commercial_development_review")
        if review:
            record["license"]["commercial_development_review"] = review
    registry["datasets"] = [item for item in registry["datasets"] if item["id"] != args.dataset_id] + [record]
    # Technical preparation and the declared training purpose are separate.
    # Reuse the trainer's live evidence gate, including commercial scope.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from ml_training.volumetric_manifest import enforce_training_license, LicenseAuthorizationError
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    try:
        gate = enforce_training_license({"dataset_id": args.dataset_id}, temporary)
        record["tasks"][0]["training_purpose"] = gate["training_purpose"]
    except LicenseAuthorizationError as exc:
        record["tasks"][0].update(training_eligible=False, readiness="RIGHTS_REVIEW_REQUIRED_FOR_DECLARED_PURPOSE",
                                  training_blocker=str(exc), commercial_development_eligible=False)
    temporary.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    print(json.dumps({"dataset_id": args.dataset_id, "images": len(images), "sha256": record["source_sha256"][:16]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
