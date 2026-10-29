"""OCR engine comparison on synthetic laboratory and imaging report pages.

Renders seeded synthetic report pages (invented values, no patient data) in several fonts,
degrades them like a phone photograph and a low-resolution fax, reads every page with each
available OCR engine configuration and scores:

- character and word error rate against the rendered text (order-sensitive: a table read
  column by column scores worse, as it extracts worse);
- laboratory values recovered end to end: (analyte, value) pairs that MedTwin's extractor
  finds in the OCR text, against the pairs it finds in the rendered text itself (so the
  extractor's own misses are not charged to OCR);
- negations kept: negated report statements still found negated after OCR;
- seconds per page.

Engines: RapidOCR as MedTwin runs it (no per-box angle classifier, detection threshold 0.3,
rows de-skewed), RapidOCR with the angle classifier, RapidOCR at the engine's default
detection threshold, the OCR engine built into Windows 10/11 (Windows.Media.Ocr, through
benchmarks/windows_ocr.ps1) and Tesseract when its binary is installed. An engine that is
not available here is reported NOT_INSTALLED, not scored.

Synthetic pages are not real clinical photographs: the scores rank engines and settings for
this pipeline; they are not an accuracy claim for any real document. Hand-transcribed real
pages can be scored privately with --gold-dir (pairs of <name>.png and <name>.gold.txt); those
results go to --private-out and never to benchmarks/results.

  .venv\\Scripts\\python.exe benchmarks\\ocr_benchmark.py [--pages-per-condition 4] [--seed 20261029]
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import random
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402

from app.services import ocr  # noqa: E402
from app.services.nlp_processor import extract_clinical_statements, extract_numeric_measurements  # noqa: E402

PAGE_SIZE = (2480, 3508)  # A4 at 300 DPI, the resolution MedTwin renders PDF pages at
FONTS = ["arial.ttf", "times.ttf", "calibri.ttf", "verdana.ttf", "tahoma.ttf", "cour.ttf"]
# Printed name, unit, plausible low/high for the invented value, decimals, printed interval.
ANALYTES = [
    ("Haemoglobin", "g/dL", 9.0, 16.5, 1, "12.0 - 15.0"),
    ("Total WBC Count", "cells/cumm", 3500, 12000, 0, "4000 - 11000"),
    ("Haematocrit (PCV)", "%", 32, 50, 1, "36.0 - 46.0"),
    ("MCV", "fL", 75, 100, 1, "83.0 - 101.0"),
    ("Serum Creatinine", "mg/dL", 0.6, 1.8, 2, "0.55 - 1.02"),
    ("Blood Urea", "mg/dL", 15, 60, 0, "15 - 40"),
    ("Fasting Blood Sugar", "mg/dL", 70, 180, 0, "70 - 110"),
    ("HbA1c", "%", 5.0, 9.5, 1, "4.0 - 6.0"),
    ("Total Cholesterol", "mg/dL", 140, 260, 0, "0 - 200"),
    ("HDL Cholesterol", "mg/dL", 30, 70, 0, "40 - 60"),
    ("LDL Cholesterol", "mg/dL", 60, 180, 0, "0 - 100"),
    ("Triglycerides", "mg/dL", 70, 300, 0, "60 - 150"),
    ("SGPT (ALT)", "U/L", 10, 90, 0, "0 - 35"),
    ("SGOT (AST)", "U/L", 10, 80, 0, "0 - 35"),
    ("Alkaline Phosphatase", "U/L", 40, 160, 0, "40 - 129"),
    ("Total Bilirubin", "mg/dL", 0.3, 2.2, 2, "0.30 - 1.20"),
    ("Albumin", "g/dL", 3.0, 5.0, 1, "3.5 - 5.2"),
    ("TSH", "mIU/L", 0.4, 8.0, 2, "0.35 - 4.94"),
    ("Serum Sodium", "mmol/L", 128, 146, 0, "136 - 145"),
    ("Serum Potassium", "mmol/L", 3.2, 5.6, 1, "3.5 - 5.1"),
]
FINDINGS = [
    "No pleural effusion.", "No focal consolidation is seen.", "Mild hepatomegaly is noted.", "Gall bladder calculus is seen.",
    "No hydronephrosis.", "Grade I fatty liver.", "No pneumothorax.", "Few subcentimetric mediastinal lymph nodes.",
    "No ascites.", "Cardiac size is within normal limits.",
]
CONDITIONS = {
    "clean_scan": "Rendered page as a flatbed scan at 300 DPI.",
    "phone_photo": "Rotated 1-3 degrees, slight blur, uneven lighting, sensor noise and JPEG quality 40.",
    "low_resolution": "Downsampled to about 100 DPI and enlarged again, as a fax or a low-resolution scan.",
}


def font(name: str, size: int):
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        return ImageFont.load_default(size=size)


def render_page(rng: random.Random, number: int) -> tuple[Image.Image, list[str]]:
    """One synthetic report page and its text lines in reading order."""
    image = Image.new("RGB", PAGE_SIZE, "white")
    draw = ImageDraw.Draw(image)
    face = FONTS[number % len(FONTS)]
    body, title = font(face, 40), font(face, 52)
    lines: list[str] = []
    y = 180

    def write(text: str, x: int, row_y: int, which=body) -> None:
        draw.text((x, row_y), text, fill=(20, 20, 20), font=which)

    heading = "SYNTHETIC LABORATORY REPORT - SOFTWARE TEST FIXTURE"
    write(heading, 160, y, title)
    lines.append(heading)
    y += 130
    columns = (160, 1100, 1450, 1850)
    header = ("Test Name", "Result", "Units", "Reference Range")
    for x, text in zip(columns, header):
        write(text, x, y)
    lines.append(" ".join(header))
    y += 90
    for name, unit, low, high, decimals, interval in rng.sample(ANALYTES, 14):
        value = f"{rng.uniform(low, high):.{decimals}f}"
        for x, text in zip(columns, (name, value, unit, interval)):
            write(text, x, y)
        lines.append(f"{name} {value} {unit} {interval}")
        y += 82
    if number % 2 == 0:
        y += 70
        write("IMPRESSION:", 160, y)
        lines.append("IMPRESSION:")
        y += 82
        for sentence in rng.sample(FINDINGS, 4):
            write(sentence, 160, y)
            lines.append(sentence)
            y += 82
    return image, lines


def degrade(image: Image.Image, condition: str, rng: random.Random) -> Image.Image:
    if condition == "clean_scan":
        return image
    if condition == "low_resolution":
        small = image.resize((image.width // 3, image.height // 3), Image.Resampling.BILINEAR)
        return small.resize(image.size, Image.Resampling.BILINEAR)
    photo = image.rotate(rng.uniform(1.0, 3.0) * rng.choice((-1, 1)), resample=Image.Resampling.BICUBIC, expand=False, fillcolor="white")
    photo = photo.filter(ImageFilter.GaussianBlur(1.1))
    array = np.asarray(photo).astype(np.float32)
    shade = np.linspace(0.72, 1.0, array.shape[1], dtype=np.float32)[None, :, None]
    noise = np.random.default_rng(rng.randrange(1 << 30)).normal(0.0, 7.0, array.shape).astype(np.float32)
    photo = Image.fromarray(np.clip(array * shade + noise, 0, 255).astype(np.uint8))
    buffer = tempfile.SpooledTemporaryFile()
    photo.save(buffer, format="JPEG", quality=40)
    buffer.seek(0)
    return Image.open(buffer).convert("RGB")


# --------------------------------------------------------------------------- engines

def _rapidocr_raw(use_cls: bool, box_thresh: float) -> Callable[[list[Image.Image]], list[tuple[str, float]]]:
    def read(images):
        results = []
        for image in images:
            started = time.perf_counter()
            detections, _ = ocr._engine()(np.asarray(image.convert("RGB")), use_cls=use_cls, box_thresh=box_thresh)
            text = ocr.page_text(ocr._reading_order(detections or []))
            results.append((text, time.perf_counter() - started))
        return results
    return read


def _rapidocr_medtwin(images):
    results = []
    for image in images:
        started = time.perf_counter()
        text = ocr.ocr_image(image).text
        results.append((text, time.perf_counter() - started))
    return results


def _windows_ocr(images):
    with tempfile.TemporaryDirectory() as folder:
        paths = []
        for index, image in enumerate(images):
            path = Path(folder) / f"page-{index}.png"
            image.save(path)
            paths.append(str(path))
        output = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "benchmarks" / "windows_ocr.ps1"), *paths],
            capture_output=True, encoding="utf-8", errors="replace", timeout=1800, check=True,
        ).stdout
    # PowerShell 5.1 leaves some control characters a recogniser emits unescaped.
    records = {record["path"]: record for record in (json.loads(line, strict=False) for line in output.splitlines() if line.strip().startswith("{"))}
    results = []
    for path in paths:
        # Windows returns a table's columns as separate lines; group its word boxes into rows
        # with MedTwin's own row grouping so the engines are compared on recognition.
        words = [([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], word["text"], 1.0)
                 for word in records[path]["words"] for x0, y0, x1, y1 in [word["box"]]]
        results.append((ocr.page_text(ocr._reading_order(words)), records[path]["seconds"]))
    return results


def _tesseract(images):
    results = []
    with tempfile.TemporaryDirectory() as folder:
        for index, image in enumerate(images):
            path = Path(folder) / f"page-{index}.png"
            image.save(path)
            started = time.perf_counter()
            text = subprocess.run(["tesseract", str(path), "stdout", "--psm", "6"], capture_output=True, text=True, timeout=600, check=True).stdout
            results.append((text, time.perf_counter() - started))
    return results


def engines() -> list[dict]:
    windows = platform.system() == "Windows" and shutil.which("powershell") is not None
    return [
        {"id": "rapidocr_medtwin", "label": "RapidOCR as MedTwin runs it", "read": _rapidocr_medtwin, "available": ocr.ocr_available(),
         "description": "PP-OCRv4 (rapidocr-onnxruntime), no per-box angle classifier, detection box threshold 0.3, de-skewed rows, upside-down retry."},
        {"id": "rapidocr_angle_classifier", "label": "RapidOCR + angle classifier", "read": _rapidocr_raw(True, ocr.DETECTION_BOX_THRESHOLD),
         "available": ocr.ocr_available(), "description": "As above with the per-box 180-degree classifier (MedTwin's earlier setting)."},
        {"id": "rapidocr_default_threshold", "label": "RapidOCR, default threshold", "read": _rapidocr_raw(False, 0.5),
         "available": ocr.ocr_available(), "description": "Engine default detection box threshold 0.5."},
        {"id": "windows_ocr", "label": "Windows OCR", "read": _windows_ocr, "available": windows,
         "description": "Windows.Media.Ocr built into Windows 10/11, user-profile language; its word boxes are grouped into rows by MedTwin's row grouping."},
        {"id": "tesseract", "label": "Tesseract", "read": _tesseract, "available": shutil.which("tesseract") is not None,
         "description": "Tesseract command-line OCR, page segmentation mode 6."},
    ]


# --------------------------------------------------------------------------- scoring

def edit_distance(left, right) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for row, a in enumerate(left, 1):
        current = [row]
        for column, b in enumerate(right, 1):
            current.append(min(previous[column] + 1, current[column - 1] + 1, previous[column - 1] + (a != b)))
        previous = current
    return previous[-1]


def normalised(text: str) -> str:
    return " ".join(text.split())


def lab_pairs(text: str) -> set[tuple[str, float]]:
    return {(item["name"], round(float(item["value"]), 4)) for item in extract_numeric_measurements(text)}


def negated(text: str) -> set[str]:
    return {item["entity"] for item in extract_clinical_statements(text) if item["negation"] == "NEGATED"}


def score(gold_text: str, read_text: str) -> dict:
    gold, read = normalised(gold_text), normalised(read_text)
    gold_pairs, read_pairs = lab_pairs(gold_text), lab_pairs(read_text)
    gold_negated, read_negated = negated(gold_text), negated(read_text)
    return {
        "char_edits": edit_distance(gold, read), "chars": len(gold),
        "word_edits": edit_distance(gold.split(), read.split()), "words": len(gold.split()),
        "lab_gold": len(gold_pairs), "lab_found": len(gold_pairs & read_pairs), "lab_read": len(read_pairs),
        "negated_gold": len(gold_negated), "negated_kept": len(gold_negated & read_negated),
    }


def summarise(scores: list[dict], seconds: list[float]) -> dict:
    total = {key: sum(item[key] for item in scores) for key in scores[0]}

    def ratio(numerator, denominator):
        return round(numerator / denominator, 4) if denominator else None

    return {
        "pages": len(scores),
        "cer": ratio(total["char_edits"], total["chars"]),
        "wer": ratio(total["word_edits"], total["words"]),
        "lab_value_recall": ratio(total["lab_found"], total["lab_gold"]),
        "lab_value_precision": ratio(total["lab_found"], total["lab_read"]),
        "negations_kept": ratio(total["negated_kept"], total["negated_gold"]),
        "lab_pairs_scored": total["lab_gold"],
        "seconds_per_page_median": round(statistics.median(seconds), 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pages-per-condition", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20261029)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "benchmarks" / "results")
    parser.add_argument("--gold-dir", type=Path, help="private hand-transcribed pages (<name>.png + <name>.gold.txt)")
    parser.add_argument("--private-out", type=Path, help="where private --gold-dir results are written (never the repository)")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    corpus: dict[str, list[tuple[Image.Image, str]]] = {}
    for condition in CONDITIONS:
        pages = []
        for number in range(args.pages_per_condition):
            image, lines = render_page(rng, number)
            pages.append((degrade(image, condition, rng), "\n".join(lines)))
        corpus[condition] = pages
    ceiling = [score(text, text) for pages in corpus.values() for _image, text in pages]

    results, listed = [], []
    for engine in engines():
        listed.append({key: engine[key] for key in ("id", "label", "description")} | {"status": "COMPLETED" if engine["available"] else "NOT_INSTALLED"})
        if not engine["available"]:
            continue
        print(f"reading with {engine['id']}", flush=True)
        engine["read"]([corpus["clean_scan"][0][0]])  # untimed warm-up: model loading is not page latency
        for condition, pages in corpus.items():
            readings = engine["read"]([image for image, _text in pages])
            scores = [score(text, read) for (_image, text), (read, _seconds) in zip(pages, readings)]
            results.append({"engine": engine["id"], "condition": condition, **summarise(scores, [seconds for _read, seconds in readings])})

    if args.gold_dir:
        if not args.private_out or ROOT in args.private_out.resolve().parents:
            sys.exit("--gold-dir needs --private-out outside the repository.")
        private = []
        for gold in sorted(args.gold_dir.glob("*.gold.txt")):
            image = Image.open(gold.with_name(gold.name.replace(".gold.txt", ".png"))).convert("RGB")
            for engine in (item for item in engines() if item["available"]):
                read, seconds = engine["read"]([image])[0]
                private.append({"page": gold.stem, "engine": engine["id"], **summarise([score(gold.read_text(encoding="utf-8"), read)], [seconds])})
        args.private_out.write_text(json.dumps(private, indent=2), encoding="utf-8")

    from importlib.metadata import version

    payload = {
        "schema_version": "medtwin-ocr-benchmark-1.0.0",
        "benchmark_kind": "ocr_engine_comparison",
        "status": "completed",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": args.seed,
        "corpus": {
            "kind": "SYNTHETIC_RENDERED_PAGES", "pages_per_condition": args.pages_per_condition, "page_size_px": PAGE_SIZE,
            "fonts": FONTS, "conditions": CONDITIONS, "lab_rows_per_page": 14,
            "extractor_ceiling": summarise(ceiling, [0.0]) | {"note": "Scores of the extractor on the rendered text itself; OCR scores are relative to it."},
        },
        "engines": listed,
        "results": results,
        "environment": {
            "python": platform.python_version(), "platform": platform.platform(), "cpu_count": os.cpu_count(),
            "rapidocr_onnxruntime": version("rapidocr-onnxruntime"), "onnxruntime": version("onnxruntime"),
            "medtwin_ocr_workers": ocr.OCR_WORKERS, "medtwin_threads_per_engine": ocr.OCR_THREADS_PER_ENGINE,
        },
        "limitations": [
            "Synthetic pages with invented values in system fonts; real photographed reports (curled paper, stamps, handwriting, glare) are harder.",
            "Character and word error rates depend on reading order; a table read column by column scores worse.",
            "Laboratory-value recall is end to end through MedTwin's extractor and counts only pairs the extractor finds in the rendered text.",
            "Timings are single-page latencies on this machine, not throughput.",
        ],
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    target = args.out_dir / f"ocr-benchmark-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {target}")
    for row in results:
        print(f"{row['engine']:28} {row['condition']:15} CER {row['cer']}  WER {row['wer']}  lab recall {row['lab_value_recall']}  "
              f"negations {row['negations_kept']}  {row['seconds_per_page_median']} s/page")


if __name__ == "__main__":
    main()
