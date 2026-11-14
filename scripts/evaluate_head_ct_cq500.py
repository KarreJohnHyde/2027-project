"""External evaluation of the head-CT haemorrhage models on CQ500 (real DICOM, three radiologists' reads).

CQ500 (qure.ai; CC BY-NC-SA 4.0; downloaded with the owner's approval on 2026-11-06) is used for evaluation only.
For each scan, the plain soft-tissue axial series is chosen (no bone kernel; slice thickness nearest 5 mm, then the
most slices), assembled with app.services.dicom_series and put through the serving path:

- single-slice model (brain_ct_rsna_ich_classifier): every slice windowed with the model's declared DICOM window,
  checked against its applicability reference; only slices inside it are classified;
- neighbouring-slice model (brain_ct_rsna_ich_25d_classifier), when registered: model_inference.run_head_ct_series,
  which refuses a series with more than half of its slices outside the reference.

Scan-level score per label: the highest probability over the analysed slices (as in the RSNA study-level evaluation).
Reference: a label is present when at least two of the three readers marked it. AUROC with a bootstrap over scans;
sensitivity and specificity at the thresholds chosen on the RSNA validation patients. Refused scans are reported, not
scored. Prints and writes summary numbers only.

    python scripts/evaluate_head_ct_cq500.py --cq500 C:/MedTwin_Datasets/CQ500 [--limit N]
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import hashlib
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from app.services import dicom_series, image_ood, model_inference as mi  # noqa: E402
from app.services.evaluation_metrics import _auroc  # noqa: E402
from ml_training.common import bootstrap_ci  # noqa: E402

LABELS = {"ICH": "any intracranial haemorrhage", "IPH": "intraparenchymal", "IVH": "intraventricular", "SDH": "subdural",
          "EDH": "epidural", "SAH": "subarachnoid"}
MODELS = ("brain_ct_rsna_ich_classifier", "brain_ct_rsna_ich_25d_classifier")


def reference(reads_csv: Path) -> dict[str, dict[str, int]]:
    with reads_csv.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {row["name"]: {label: int(sum(int(row[f"R{reader}:{label}"]) for reader in (1, 2, 3)) >= 2) for label in LABELS} for row in rows}


def choose_series(archive: zipfile.ZipFile) -> tuple[list[str], dict]:
    import pydicom

    series: dict[str, dict] = {}
    for name in archive.namelist():
        if name.endswith("/"):
            continue
        try:
            header = pydicom.dcmread(io.BytesIO(archive.read(name)), stop_before_pixels=True)
        except Exception:
            continue
        uid = str(header.get("SeriesInstanceUID", ""))
        entry = series.setdefault(uid, {"members": [], "description": str(header.get("SeriesDescription", "")),
                                        "thickness": float(header.get("SliceThickness") or 0), "kernel": str(header.get("ConvolutionKernel", ""))})
        entry["members"].append(name)
    candidates = [item for item in series.values() if "BONE" not in item["description"].upper() and "BONE" not in item["kernel"].upper()
                  and len(item["members"]) >= 10]
    if not candidates:
        return [], {"status": "NO_SOFT_TISSUE_SERIES", "series": len(series)}
    best = min(candidates, key=lambda item: (abs(item["thickness"] - 5.0), -len(item["members"])))
    return best["members"], {"status": "CHOSEN", "series": len(series), "slices": len(best["members"]), "thickness_mm": best["thickness"]}


def single_slice_scan(model: dict, prepared, network, payload, device, reference_set: dict) -> dict:
    window = model["dicom_window"]
    grey = np.asarray(mi.series_slice_images(prepared.hounsfield, window))[..., 1]  # the middle channel is the slice itself
    scores, analysed = [], 0
    for plane in grey:
        image = Image.fromarray(plane, mode="L").convert("RGB")
        features = mi.image_features(network, payload, device, image)
        value = mi._combined_score(reference_set, image_ood.stage_scores(reference_set, [stage[None] for stage in features])[0])
        if value > reference_set["threshold"]:
            continue
        analysed += 1
        labels = mi.classify_multilabel(network, payload, device, image)["labels"]
        scores.append([label["probability"] for label in labels])
    total = len(grey)
    if analysed * 2 < total:
        return {"status": "REFUSED", "analysed": analysed, "slices": total}
    return {"status": "SCORED", "analysed": analysed, "slices": total, "max": np.max(np.asarray(scores), axis=0).tolist()}


def series_scan(model: dict, prepared) -> dict:
    try:
        output = mi.run_head_ct_series(model, prepared)
    except mi.InferenceNotPermitted:
        return {"status": "REFUSED"}
    analysed = [item for item in output["slices"] if item["status"] == "ANALYSED"]
    names = [label["label"] for label in analysed[0]["labels"]]
    maxima = np.max(np.asarray([[label["probability"] for label in item["labels"]] for item in analysed]), axis=0)
    return {"status": "SCORED", "analysed": len(analysed), "slices": len(output["slices"]), "max": maxima.tolist(), "names": names}


def metrics(rows: list[dict], truth: dict, names: list[str], thresholds: dict[str, float]) -> dict:
    scored = [row for row in rows if row["status"] == "SCORED"]
    result = {"scans": len(rows), "scored": len(scored), "refused": sum(row["status"] == "REFUSED" for row in rows), "per_label": {}}
    for label, name in LABELS.items():
        index = names.index(name)
        y = np.array([truth[row["scan"]][label] for row in scored])
        p = np.array([row["max"][index] for row in scored])
        if len(set(y)) < 2:
            result["per_label"][label] = {"positives": int(y.sum()), "auroc": None}
            continue
        guess = p >= thresholds[name]
        result["per_label"][label] = {
            "positives": int(y.sum()), "negatives": int((1 - y).sum()), "auroc": _auroc(y, p),
            "auroc_ci95": bootstrap_ci(lambda idx: _auroc(y[idx], p[idx]), len(y), None, rounds=1000, unit="scan"),
            "sensitivity_at_rsna_threshold": float(guess[y == 1].mean()), "specificity_at_rsna_threshold": float(1 - guess[y == 0].mean())}
    return result


def source_defects(folder) -> dict:
    """Scans whose public source archive is documented as defective by cq500_repair_zip.py records (*.zip.repaired.json)."""
    if folder is None or not Path(folder).is_dir():
        return {}
    defects = {}
    for record_path in Path(folder).glob("*.zip.repaired.json"):
        record = json.loads(record_path.read_text(encoding="utf-8"))
        defects[record_path.name[: -len(".zip.repaired.json")]] = {
            "reason": record["source"]["problem"], "source_sha256": record["source"]["sha256"],
            "entries_recovered": record["entries_recovered"], "local_headers_found": record["local_headers_found"],
            "series": [{"description": item["description"], "slices": item["slices"],
                        "missing_inside_range": len(item["missing_inside_range"])} for item in record["series"]],
        }
    return defects


def cohort_scope(truth, archives, limit, defects=None):
    present = {path.stem for path in archives}
    missing = sorted(set(truth) - present)
    documented = {scan: (defects or {})[scan] for scan in missing if scan in (defects or {})}
    unexplained = [scan for scan in missing if scan not in documented]
    if unexplained and not limit:
        raise ValueError(f"Full external evaluation refused: {len(unexplained)} referenced CQ500 scan archives are missing "
                         "without a documented source defect")
    if limit:
        scope = "PILOT_SUBSET_NOT_FULL_COHORT"
    elif documented:
        # Every other referenced scan is evaluated; the excluded ones are named with the evidence that their public
        # source copy cannot be read completely, so the result is never mistaken for the complete cohort.
        scope = "FULL_REFERENCED_COHORT_EXCEPT_DOCUMENTED_SOURCE_DEFECTS"
    else:
        scope = "FULL_REFERENCED_COHORT"
    return {"expected_reference_scans": len(truth), "present_archives": len(present),
            "missing_reference_scans": missing, "excluded_source_defects": documented, "scope": scope,
            "clinical_validation": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cq500", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--output", type=Path, help="Optional explicit result path, including for pilot subsets")
    parser.add_argument("--source-defects", type=Path,
                        help="Folder of cq500_repair_zip.py records (default: <cq500>/zips-partial). A referenced scan missing "
                             "from zips/ is excluded only when a record documents that its public source copy is defective.")
    args = parser.parse_args()
    truth = reference(args.cq500 / "reads.csv")
    zips = sorted((args.cq500 / "zips").glob("CQ500-CT-*.zip"), key=lambda path: int(path.stem.rsplit("-", 1)[1]))
    try:
        scope = cohort_scope(truth, zips, args.limit, source_defects(args.source_defects or args.cq500 / "zips-partial"))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if args.limit:
        zips = zips[: args.limit]
    available = {model_id: mi.get_model(model_id) for model_id in MODELS
                 if any(model["model_id"] == model_id for model in mi._load_registry()["models"])}
    loaded = {model_id: (mi.load_model(model), mi.ood_reference(model)) for model_id, model in available.items() if mi.research_gate(model)["allowed"]}
    if not loaded:
        raise SystemExit("No eligible head-CT research checkpoint is available for evaluation")
    rows: dict[str, list[dict]] = {model_id: [] for model_id in loaded}
    selection = {"chosen": 0, "no_series": 0, "not_assembled": 0, "not_axial": 0}
    for number, path in enumerate(zips, 1):
        scan = path.stem
        if scan not in truth:
            continue
        with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory() as work:
            members, chosen = choose_series(archive)
            if not members:
                selection["no_series"] += 1
                continue
            files = []
            for index, member in enumerate(members):
                target = Path(work) / f"{index:04d}.dcm"
                target.write_bytes(archive.read(member))
                files.append(target)
            report = dicom_series.assemble_series(files, load_pixels=True)
        if report.get("status") != "ASSEMBLED":
            selection["not_assembled"] += 1
            continue
        report["ordered_upload_ids"] = list(range(report["shape_slices_rows_columns"][0]))
        try:
            prepared = mi.prepare_head_ct_series(available[MODELS[0]], report)
        except mi.InferenceNotPermitted:
            selection["not_axial"] += 1
            continue
        selection["chosen"] += 1
        for model_id, ((network, payload, device), reference_set) in loaded.items():
            outcome = (single_slice_scan(available[model_id], prepared, network, payload, device, reference_set)
                       if available[model_id].get("inference_input") != "head_ct_series" else series_scan(available[model_id], prepared))
            rows[model_id].append({"scan": scan, **outcome})
        if number % 25 == 0:
            print(f"{number}/{len(zips)}", flush=True)
    summary = {"dataset": "CQ500 (qure.ai), CC BY-NC-SA 4.0, evaluation only", "reference": "label present when at least 2 of 3 readers marked it",
               "series_selection": selection, "models": {}, "cohort": scope,
               "reference_csv_sha256": hashlib.sha256((args.cq500 / "reads.csv").read_bytes()).hexdigest(),
               "requested_limit": args.limit, "selected_scan_ids": [path.stem for path in zips],
               "checkpoint_sha256": {key: model["artifact_bundle"]["checkpoint_sha256"] for key, model in available.items()},
               "threshold_policy": "Frozen internal RSNA thresholds; not selected or recalibrated on CQ500",
               "metric_population": "Scored scans only; refused scans are reported separately and must not be treated as normal."}
    for model_id, model_rows in rows.items():
        model = available[model_id]
        network, payload, device = loaded[model_id][0]
        names = list(payload["classes"])
        thresholds = {names[i]: float(payload["thresholds"][key]) for i, key in enumerate(payload["label_keys"])}
        summary["models"][model_id] = metrics(model_rows, truth, names, thresholds)
        summary["models"][model_id]["median_analysed_slice_fraction"] = float(np.median([row["analysed"] / row["slices"] for row in model_rows if "slices" in row])) if model_rows else None
    print(json.dumps(summary, indent=1, default=float))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, indent=2, default=float) + "\n", encoding="utf-8")
    if not args.limit:
        target = ROOT / "docs" / "validation" / "models" / "head_ct_cq500_external.json"
        target.write_text(json.dumps(summary, indent=2, default=float) + "\n", encoding="utf-8")
        print(f"written {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
