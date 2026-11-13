"""Actual OCR parity/source-box smoke on previously used development word crops.

This is functional parity on public words pasted into a synthetic blank canvas,
not a new accuracy benchmark or an independent real report evaluation.
"""
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import sys
from zipfile import ZipFile

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services import upright_word_ocr as helper, ocr
from experiment_ocr_word_preprocessing import predict, ARCHIVE_SHA


def run(archive_path: Path, plan_path: Path) -> dict:
    source = archive_path.read_bytes()
    if hashlib.sha256(source).hexdigest() != ARCHIVE_SHA: raise ValueError("Source differs from reviewed MIT resource")
    plan = json.loads(plan_path.read_text())
    runtime = helper.capability()
    if not runtime["available"]: raise ValueError("Evaluated helper runtime unavailable")
    rows = []
    with ZipFile(io.BytesIO(source)) as archive:
        for entry in plan["development"][:16]:
            data = archive.read("Train_Set/" + entry["id"] + ".jpg")
            if hashlib.sha256(data).hexdigest() != entry["image_sha256"]: raise ValueError("Development source hash mismatch")
            crop = Image.open(io.BytesIO(data)); crop.load()
            reference = ocr._executor().submit(predict, ("upright", crop)).result()
            origin = (73, 109)
            canvas = Image.new("RGB", (1200, 1600), "white"); canvas.paste(crop, origin)
            result = helper.recognise(canvas, [origin[0], origin[1], origin[0] + crop.width, origin[1] + crop.height],
                                     source={"kind": "PUBLIC_WORD_CROP_ON_SYNTHETIC_CANVAS_FOR_PARITY_ONLY", "source_image_sha256": entry["image_sha256"]},
                                     upright_attested=True, single_word_attested=True, latin_text_attested=True)
            available = result["status"] == "AVAILABLE"
            row = {"id": entry["id"], "image_sha256": entry["image_sha256"], "status": result["status"], "code": result["code"],
                   "text_parity_on_available": result["text_proposal"] == reference["text"] if available else None}
            if available:
                row["source_box_translation_exact"] = result["source_word_bbox_xyxy"] == [v + origin[i % 2] for i, v in enumerate(result["crop_word_bbox_xyxy"])]
                row["synthetic_canvas_origin_xy"] = list(origin)
            rows.append(row)
    return {"schema_version": "medtwin.upright-word-helper-parity.v1", "purpose": "Actual unchanged-engine parity and source-box translation only, no new accuracy claim",
            "n": len(rows), "statuses": dict(Counter(r["status"] for r in rows)),
            "available_text_parity_all": all(r["text_parity_on_available"] for r in rows if r["status"] == "AVAILABLE"),
            "available_translation_all": all(r["source_box_translation_exact"] for r in rows if r["status"] == "AVAILABLE"),
            "per_item": rows, "runtime": runtime,
            "helper_code_sha256": hashlib.sha256(Path(helper.__file__).read_bytes()).hexdigest(),
            "original_exposed_test_or_reserved_holdout_reused_for_selection": False,
            "clinical_validation": False, "images_or_raw_text_published": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True); parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); result = run(args.archive, args.plan)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("n", "statuses", "available_text_parity_all", "available_translation_all")}))
