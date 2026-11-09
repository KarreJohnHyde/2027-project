"""Read-only registry audit; optional private PDF check in disposable OCR storage.

Never opens the application database. Does not train, activate or rewrite models.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--database", type=Path, help="Apply migrations to a disposable SQLite backup; original opened read-only.")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="medtwin-evidence-audit-") as temporary:
        os.environ["UPLOAD_DIR"] = temporary
        for name in ("MEDTWIN_SCISPACY", "MEDTWIN_CLINICAL_NLP", "MEDTWIN_RADGRAPH"):
            os.environ[name] = "off"
        from app.services.model_registry import _load_registry, activation_gate, _resolve_artifact_path
        from app.services.model_inference import research_gate
        from app.services.dataset_registry import load_dataset_task_audit
        models = []
        for model in _load_registry()["models"]:
            bundle = model.get("artifact_bundle") or {}
            models.append({"model_id": model["model_id"], "status": model["status"], "task": model.get("task"),
                           "anatomy": model.get("anatomy"), "supported_modalities": model.get("supported_modalities"),
                           "checkpoint_path": bundle.get("checkpoint_path"),
                           "checkpoint_exists": bool(bundle.get("checkpoint_path") and _resolve_artifact_path(bundle["checkpoint_path"]).is_file()),
                           "preprocessing_version": bundle.get("preprocessing_version"), "dataset_version": bundle.get("dataset_version"),
                           "dataset_license": bundle.get("dataset_license"), "evaluation_report_path": bundle.get("evaluation_report_path"),
                           "research_gate": research_gate(model), "clinical_activation": activation_gate(model)})
        tasks = load_dataset_task_audit()
        result = {"audit_version": "heterogeneous-evidence-v1", "models": models,
                  "model_counts": {"registered": len(models), "research_eligible": sum(m["research_gate"]["allowed"] for m in models),
                                   "clinical_activation_eligible": sum(m["clinical_activation"]["eligible"] for m in models)},
                  "datasets": tasks["datasets"],
                  "dataset_audit_generated_at": tasks.get("generated_at"),
                  "dataset_audit_limitation": "Existing task-level audit loaded; large dataset contents were not re-indexed by this script."}
        result["dataset_counts"] = {"entries": len(tasks["datasets"]),
            "training_eligible_tasks": sum(bool(t.get("training_eligible")) for d in tasks["datasets"] for t in d.get("tasks", [])),
            "validation_ready_tasks": sum(bool(t.get("validation_ready")) for d in tasks["datasets"] for t in d.get("tasks", []))}
        if args.database:
            from sqlalchemy import create_engine
            from app.migrations import run_migrations
            clone = Path(temporary) / "migration-preservation.sqlite"
            original = sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True)
            copied = sqlite3.connect(clone)
            original.backup(copied)
            original.close()
            tables = [r[0] for r in copied.execute("SELECT name FROM sqlite_master WHERE type='table'") if r[0] != "schema_migrations"]

            def quoted(value):
                return '"' + value.replace('"', '""') + '"'

            columns = {t: [r[1] for r in copied.execute(f"PRAGMA table_info({quoted(t)})")] for t in tables}

            def snapshot(connection):
                data = {}
                for table in tables:
                    rows = connection.execute(f"SELECT {','.join(map(quoted, columns[table]))} FROM {quoted(table)}").fetchall()
                    serialized = sorted(json.dumps(row, default=str) for row in rows)
                    data[table] = {"count": len(rows), "sha256": hashlib.sha256('\n'.join(serialized).encode()).hexdigest()}
                return data

            before = snapshot(copied)
            copied.close()
            clone_engine = create_engine(f"sqlite:///{clone.as_posix()}")
            applied = run_migrations(clone_engine)
            assert run_migrations(clone_engine) == [], "Migrations are not idempotent"
            clone_engine.dispose()
            connection = sqlite3.connect(clone)
            try:
                after = snapshot(connection)
            finally:
                connection.close()
            if before != after:
                raise RuntimeError("Existing column contents changed during migration rehearsal")
            result["migration_preservation"] = {"status": "PASSED_ON_DISPOSABLE_COPY", "applied": applied,
                  "tables_checked": len(tables), "existing_rows_and_columns_identical": True, "original_opened_read_only": True,
                  "table_row_counts": {t: d["count"] for t, d in before.items()}}
        if args.pdf:
            import pypdfium2
            from app.services.film_processing import assess_raster
            from app.services.nlp_processor import analyze_clinical_report
            digest = hashlib.sha256(args.pdf.read_bytes()).hexdigest()
            report = analyze_clinical_report(args.pdf, digest)
            labels = Counter((s["entity"], s["negation"], s.get("laterality")) for s in report["statements"])
            doc = pypdfium2.PdfDocument(args.pdf)
            film_pages = []
            for i in range(min(3, len(doc))):
                path = Path(temporary) / f"page-{i + 1}.png"
                doc[i].render(scale=1.5).to_pil().save(path)
                assessment = assess_raster(path)
                film_pages.append({"page": i + 1, "source_type": assessment["source_type"], "candidate_panels": len(assessment["panels"])})
            result["private_pdf_check"] = {"source_sha256": digest, "pages": len(doc),
                    "findings": [{"entity": label[0], "assertion": label[1], "laterality": label[2], "mentions": count} for label, count in labels.items()],
                    "source_pages": sorted({s["source_page"] for s in report["statements"] if s.get("source_page")}),
                    "date_candidates": [{"name": a["name"], "date": a["value_text"], "parse_status": a["parse_status"]}
                                        for a in report["attributes"] if "date" in a["name"]],
                    "film_pages": film_pages,
                    "review_status": "PENDING_HUMAN_REVIEW", "clinical_validation": "NOT_PERFORMED"}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({"models": result["model_counts"], "dataset_entries": len(result["datasets"]),
                          "pdf_checked": bool(args.pdf), "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
