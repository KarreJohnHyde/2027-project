"""Run unchanged local MedTwin OCR on externally labelled images, keeping text private.

Real prescription-word recognition and synthetic full-page document OCR are
reported separately. Neither establishes real laboratory-field extraction.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import csv
import hashlib
import io
import importlib.util
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys
import time
import unicodedata
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.ocr import ocr_images, engine_version
from app.services.ocr_evaluation import _edit_distance
from PIL import Image


def runtime_identity() -> dict:
    package = importlib.util.find_spec("rapidocr_onnxruntime")
    directory = Path(package.origin).parent / "models"
    models = []
    for path in sorted(directory.glob("*.onnx")):
        models.append({"file": path.name, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return {"python": platform.python_version(), "rapidocr": version("rapidocr-onnxruntime"),
            "onnxruntime": version("onnxruntime"), "pillow": version("Pillow"),
            "bundled_model_files": models, "model_selection": "Existing MedTwin default RapidOCR constructor; no replacement weights or learned benchmark tuning",
            "ocr_source_sha256": hashlib.sha256((ROOT / "backend/app/services/ocr.py").read_bytes()).hexdigest()}


def normalise(text: str) -> str:
    # Layout/case-insensitive transcript metric; no spelling/clinical repair.
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def score(gold: str, predicted: str) -> dict:
    gold, predicted = normalise(gold), normalise(predicted)
    if not gold: raise ValueError("Blank source reference is not scoreable")
    char_edits = _edit_distance(gold, predicted)
    words = gold.split()
    word_edits = _edit_distance(words, predicted.split())
    return {"character_edits": char_edits, "reference_characters": len(gold),
            "word_edits": word_edits, "reference_words": len(words),
            "cer": char_edits / len(gold), "wer": word_edits / len(words), "exact": gold == predicted,
            "empty_prediction": not predicted}


def aggregate(rows: list[dict]) -> dict:
    counts = {key: sum(row[key] for row in rows) for key in ("character_edits", "reference_characters", "word_edits", "reference_words")}
    return {"n": len(rows), **counts,
            "cer_micro": counts["character_edits"] / counts["reference_characters"] if counts["reference_characters"] else None,
            "wer_micro": counts["word_edits"] / counts["reference_words"] if counts["reference_words"] else None,
            "exact_match_fraction": sum(row["exact"] for row in rows) / len(rows) if rows else None,
            "empty_predictions": sum(row["empty_prediction"] for row in rows)}


def rxhand_rows(archive: ZipFile) -> list[dict]:
    labels_path = "Test_Labels.csv"
    rows = []
    for row in csv.DictReader(io.StringIO(archive.read(labels_path).decode("utf-8-sig"))):
        if row.get("Text", "").strip():
            rows.append({"image": "Test_Set/" + row["Images"], "gold": row["Text"],
                         "id": "rxhand-test-" + Path(row["Images"]).stem, "subset": "real_prescription_words", "split": "upstream_testing"})
    return rows


def exact_split_audit(archive: ZipFile) -> dict:
    hashes = {}
    for split, folder in (("train", "Train_Set/"), ("test", "Test_Set/")):
        hashes[split] = {hashlib.sha256(archive.read(name)).hexdigest() for name in archive.namelist()
                         if name.startswith(folder) and name.lower().endswith((".jpg", ".png"))}
    return {"method": "Exact SHA-256 of original image bytes", "train_unique_hashes": len(hashes["train"]),
            "test_unique_hashes": len(hashes["test"]), "cross_split_exact_duplicates": len(hashes["train"] & hashes["test"]),
            "patient_writer_or_source_prescription_independence": "NOT_VERIFIED"}


def clinocr_rows(archive: ZipFile, per_subset: int) -> list[dict]:
    names = archive.namelist()
    lookup = next(n for n in names if n.endswith("oneshot_lookup.csv"))
    rows, selected = [], Counter()
    # Choose the first held-out eval of each template before adding another
    # sample. This is predetermined coverage selection, never error selection.
    records = [r for r in csv.DictReader(io.StringIO(archive.read(lookup).decode("utf-8-sig"))) if r["role"] == "eval"]
    records.sort(key=lambda r: (r["subset"], int(r["sample"]), int(r["template"])))
    for record in records:
        subset = record["subset"]
        if selected[subset] >= per_subset: continue
        stem = f"template_{record['template']}_sample_{record['sample']}_"
        image = next(n for n in names if f"/scans/{subset}/" in n and Path(n).name.startswith(stem))
        gold_path = image.replace("/scans/", "/ground_truth/").rsplit(".", 1)[0] + ".txt"
        rows.append({"image": image, "gold": archive.read(gold_path).decode("utf-8-sig"),
                     "id": "clinocr-" + subset + "-t" + record["template"] + "-s" + record["sample"],
                     "subset": subset, "split": "upstream_eval_not_exemplar"})
        selected[subset] += 1
    return rows


def run(archive_path: Path, dataset: str, per_subset: int) -> dict:
    if dataset not in {"clinocr", "rxhandbd"}:
        raise ValueError("Only reviewed commercially eligible corpora may execute; education-only prescription data are excluded")
    source_hash = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    expected = {"clinocr": "ce1d231138050abf7f458ba5e6bd75c6ee2f3832b72f22296843da4c5ba45457",
                "rxhandbd": "25d31c7bc1ceab4b3707d5e6d2205e518cadbd75d2f99efe1492a1aee5ef1951"}
    if source_hash != expected[dataset]:
        raise ValueError("Archive differs from the reviewed MIT dataset release; source/rights review is required")
    start = time.monotonic()
    with ZipFile(archive_path) as archive:
        rows = rxhand_rows(archive) if dataset == "rxhandbd" else clinocr_rows(archive, per_subset)
        split_audit = exact_split_audit(archive) if dataset == "rxhandbd" else {"exemplars_excluded": True, "cross_artifact_template_dependence": "PRESENT_BY_DESIGN"}
        # Existing source bytes are never rewritten, resized or augmented here.
        images, identities = [], []
        for row in rows:
            content = archive.read(row["image"])
            image = Image.open(io.BytesIO(content)); image.load()
            images.append(image)
            identities.append(hashlib.sha256(content).hexdigest())
        outputs = ocr_images(images)
        scored = []
        for row, output, image_hash in zip(rows, outputs, identities, strict=True):
            scored.append({"id": row["id"], "subset": row["subset"], "split": row["split"],
                           "source_image_sha256": image_hash, "reference_text_sha256": hashlib.sha256(row["gold"].encode()).hexdigest(),
                           "prediction_text_sha256": hashlib.sha256(output.text.encode()).hexdigest(),
                           "rotation_degrees": output.rotation_degrees, "ocr_line_count": output.line_count,
                           "mean_line_confidence": output.mean_confidence, **score(row["gold"], output.text)})
    by_subset = {subset: aggregate([r for r in scored if r["subset"] == subset]) for subset in sorted({r["subset"] for r in scored})}
    real = dataset == "rxhandbd"
    return {"schema_version": "medtwin.external-ocr-benchmark.v1", "executed_at": datetime.now(timezone.utc).isoformat(),
            "dataset": dataset, "data_nature": "REAL_PRESCRIPTION_WORD_CROPS" if real else "SYNTHETIC_CLINICAL_PAGES_HUMAN_AUDITED",
            "reference_provenance": "Independent publisher-supplied Test_Labels.csv for physical prescription crops; individual annotation/reviewer method is not specified by the publisher" if real else "Publisher programmatically extracted Word text then manually audited; clinical content is synthetic",
            "licence_scope": "MIT per primary Zenodo dataset record18478741 (DOI10.5281/zenodo.18478741); retain attribution and notice" if real else "MIT; preserve upstream licence",
            "split_audit": split_audit,
            "archive_sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(), "archive_bytes": archive_path.stat().st_size,
            "engine": engine_version(), "python": platform.python_version(),
            "engine_artifacts": runtime_identity(),
            "ocr_source_sha256": hashlib.sha256((ROOT / "backend/app/services/ocr.py").read_bytes()).hexdigest(),
            "preprocessing": "Existing MedTwin ocr_images unchanged; no fitting, new weights, dictionary correction or benchmark-driven tuning",
            "metric_normalisation": "Unicode NFC, casefold, whitespace collapse; edit distance / reference length, rates may exceed one",
            "selection": "Entire upstream Testing split" if real else f"Upstream eval only, first {per_subset} per subset sorted by sample then template; all exemplars excluded",
            "aggregate": aggregate(scored), "by_subset": by_subset, "per_item": scored,
            "elapsed_seconds": time.monotonic() - start,
            "full_real_clinical_report_validation": False,
            "limitations": ["No full-page real lab row/value/unit/date/reference-interval ground truth was supplied by this word corpus.",
                            "Patient/writer/source-prescription independence is not verified by word-level splits.",
                            "Source word labels are reference text, not verification of medication, dose, dispensing safety or a patient finding.",
                            "No extracted text, patient details, images or labels are published in this result; hashes and aggregate errors only.",
                            "This is new OCR execution, not new clinical validation or author-baseline reproduction."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--dataset", choices=["clinocr", "rxhandbd"], required=True)
    parser.add_argument("--per-subset", type=int, default=8)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.per_subset <= 56: parser.error("per-subset must be between 1 and 56")
    result = run(args.archive, args.dataset, args.per_subset)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "data_nature": result["data_nature"], "aggregate": result["aggregate"], "elapsed_seconds": result["elapsed_seconds"]}))


if __name__ == "__main__": main()
