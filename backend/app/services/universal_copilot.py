"""Typed local retrieval over authorized case rows. No interpreter, LLM or writes.

The query is a literal search string, never a program or tool selector. Documents
are quoted as evidence data; none of their text affects routing or permissions.
"""
from __future__ import annotations
import json
import re
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.entities import Case, UploadedFile, Examination, Finding, InferenceRun
from app.schemas.universal_intelligence import CopilotQuery
from app.services.universal_evidence import build_graph

UNSUPPORTED = re.compile(r"\b(diagnos(?:e|is|tic)|prescrib\w*|dosage|recommend\s+(?:a\s+)?treatment|what\s+treatment|should\s+i\s+take|what\s+disease|predict\s+(?:survival|death)|finali[sz]e\s+(?:a\s+)?report)\b", re.I)
INSTRUCTION = re.compile(r"\b(ignore\s+(?:all\s+)?(?:previous|prior|system)\s+instructions|system\s+prompt|run\s+(?:a\s+)?(?:shell|command|powershell|python)|(?:delete|modify|overwrite|export)\s+(?:all\s+)?(?:records|files|database|case)|bypass\s+(?:auth\w*|permission\w*))\b", re.I)
MODE = "LOCAL_DETERMINISTIC_RESEARCH_ASSISTANT"


def _scope(case_id: int, request: CopilotQuery, db: Session):
    """Validate every supplied reference, even one irrelevant to the chosen tool."""
    for model, item_id in ((UploadedFile, request.source_id), (Examination, request.exam_id), (Finding, request.finding_id)):
        if item_id is None:
            continue
        row = db.query(model).filter(model.id == item_id, model.case_id == case_id).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Reference is not available in this case.")
        if model is Finding:
            run = db.query(InferenceRun).join(UploadedFile, InferenceRun.file_id == UploadedFile.id).filter(
                InferenceRun.id == row.inference_run_id, InferenceRun.case_id == case_id, UploadedFile.case_id == case_id).first()
            if run is None:
                raise HTTPException(status_code=404, detail="Reference is not available in this case.")
    if request.model_id is not None:
        run = db.query(InferenceRun).join(UploadedFile, InferenceRun.file_id == UploadedFile.id).filter(
            InferenceRun.case_id == case_id, UploadedFile.case_id == case_id,
            InferenceRun.model_name == request.model_id).first()
        if run is None:
            raise HTTPException(status_code=404, detail="Model has no associated source run in this case.")


def query_case(case: Case, request: CopilotQuery, db: Session) -> dict:
    _scope(case.id, request, db)

    def reply(status, answer, nodes=(), actions=(), reason=None):
        return {"mode": MODE, "tool": request.tool, "status": status, "answer": answer,
                "citations": [{"node_id": node["id"], **({"upload_id": node["source_file_id"]} if node.get("source_file_id") else {}),
                               **({"page": node["source_page"]} if node.get("source_page") is not None else {}),
                               **({"span": node["source_span"]} if node.get("source_span") else {})} for node in nodes],
                "actions": list(actions), "never_writes": True, "reason": reason}

    if UNSUPPORTED.search(request.query):
        return reply("REFUSED", "I can retrieve documented evidence, but cannot diagnose, prescribe treatment, predict an individual's outcome, or finalize a clinical report.", reason="UNSUPPORTED_CLINICAL_DECISION")
    if INSTRUCTION.search(request.query):
        return reply("REFUSED", "This assistant only retrieves case evidence through fixed read-only tools. It cannot execute instructions or change, export, or disclose other records.", reason="UNSUPPORTED_INSTRUCTION_OR_WRITE")
    graph = build_graph(case, db)
    nodes = graph["nodes"]
    selected = [n for n in nodes
                if (request.source_id is None or n.get("source_file_id") == request.source_id)
                and (request.finding_id is None or n.get("finding_id") == request.finding_id)
                and (request.exam_id is None or n.get("examination_id") == request.exam_id)]
    evidence = [n for n in selected if n["kind"] in {"statement", "measurement", "finding"}
                and n.get("details", {}).get("active_evidence") and not n.get("details", {}).get("duplicate_of")]
    tokens = [part.casefold() for part in re.findall(r"[\w-]+", request.query) if len(part) > 1]

    def matches(node):
        content = f"{node['label']} {node.get('source_span') or ''} {node.get('details', {}).get('name') or ''}".casefold()
        return not tokens or any(token in content for token in tokens)

    def quote(node):
        suffix = f"; assertion={node['assertion']}" if node.get("assertion") else ""
        if node.get("review_status"):
            suffix += f"; review_status={node['review_status']}"
        if node["kind"] == "examination" and node.get("timestamp"):
            suffix += f"; documented examination date={node['timestamp']}"
        span = f"; source excerpt={json.dumps(node['source_span'], ensure_ascii=False)}" if node.get("source_span") else ""
        return f"[{node['id']}] {node['label']}{suffix}{span}"

    def answered(items, heading):
        bounded = items[:request.limit]
        if not bounded:
            return reply("INSUFFICIENT_EVIDENCE", "No matching eligible source-backed records are available in this case snapshot. Missing evidence is not a negative clinical finding.", reason="NO_MATCHING_ELIGIBLE_EVIDENCE" + ("_BOUNDED_SNAPSHOT" if graph["truncated"] else ""))
        note = "\nThe bounded snapshot is truncated; this answer is incomplete." if graph["truncated"] else ""
        return reply("ANSWERED", heading + "\n" + "\n".join(quote(n) for n in bounded) + note, bounded)

    if request.tool == "search_case":
        return answered([n for n in evidence if matches(n)], "Documented/model-reported evidence, quoted as data. Review status remains attached to the source record:")
    if request.tool == "get_source":
        if request.source_id is None:
            return reply("INSUFFICIENT_EVIDENCE", "Select an associated source_id to inspect its evidence.", reason="SOURCE_ID_REQUIRED")
        upload = next((n for n in nodes if n["id"] == f"upload:{request.source_id}"), None)
        if upload is None:
            return reply("INSUFFICIENT_EVIDENCE", "The source lies outside this bounded snapshot.", reason="BOUNDED_SNAPSHOT")
        if not upload["details"]["active_evidence"]:
            return reply("INSUFFICIENT_EVIDENCE", "This source is withdrawn, superseded, or unassociated. Its historical record is retained but cannot support current claims.", [upload], reason="INACTIVE_SOURCE")
        return answered([n for n in evidence if n["kind"] in {"statement", "measurement"}], f"Source #{request.source_id}; persisted extracted excerpts only. Uploaded text is data, never instructions.")
    if request.tool == "get_examination":
        if request.exam_id is None:
            return reply("INSUFFICIENT_EVIDENCE", "Select an exam_id to inspect its source-linked evidence.", reason="EXAM_ID_REQUIRED")
        return answered([n for n in selected if n["kind"] == "examination"] + evidence, "Examination record and associated current evidence:")
    if request.tool in {"get_model_provenance", "get_evaluation"}:
        runs = [n for n in selected if n["kind"] == "model_run" and (not request.model_id or n["details"]["model_id"] == request.model_id)]
        # Explicit finding filters also select its associated run without trusting a user-supplied run id.
        if request.finding_id is not None:
            parent = {e["source"] for e in graph["edges"] if e["relation"] == "PRODUCED" and e["target"] == f"finding:{request.finding_id}"}
            runs = [n for n in nodes if n["id"] in parent and (not request.model_id or n["details"]["model_id"] == request.model_id)
                    and (request.source_id is None or n.get("source_file_id") == request.source_id)
                    and (request.exam_id is None or n.get("examination_id") == request.exam_id)]
        run_ids = {n["id"] for n in runs}
        children = {e["target"] for e in graph["edges"] if e["relation"] == "PRODUCED" and e["source"] in run_ids}
        findings = [n for n in nodes if n["id"] in children]
        if request.tool == "get_evaluation":
            findings = [n for n in findings if n["details"].get("model_provenance", {}).get("held_out_evaluation")]
            if not findings:
                return reply("INSUFFICIENT_EVIDENCE", "No evaluation metrics pinned in this case's persisted model provenance are available. Global registry scores are not substituted for this run.", reason="NO_PINNED_CASE_EVALUATION")
            items = findings[:request.limit]
            text = "\n".join(f"[{n['id']}] " + json.dumps(n["details"]["model_provenance"]["held_out_evaluation"], sort_keys=True) for n in items)
            return reply("ANSWERED", "Recorded held-out research evaluation (not individual patient certainty or clinical validation):\n" + text, items)
        items = (runs + findings)[:request.limit]
        if not items:
            return reply("INSUFFICIENT_EVIDENCE", "No matching case-associated model run is available.", reason="NO_CASE_MODEL_RUN")
        text = "\n".join(f"[{n['id']}] " + json.dumps(n["details"], sort_keys=True) for n in items)
        return reply("ANSWERED", "Persisted case-run provenance. Model version and preprocessing version describe the recorded run:\n" + text, items)
    if request.tool == "get_anatomy":
        links = [e for e in graph["edges"] if e["relation"] == "LEXICALLY_ASSOCIATED_WITH" and e["source"] in {n["id"] for n in evidence}]
        systems = [n for n in nodes if n["id"] in {e["target"] for e in links} and (not request.system_id or n["details"].get("system_id") == request.system_id)]
        source_ids = {e["source"] for e in links if e["target"] in {n["id"] for n in systems}}
        items = [n for n in evidence if n["id"] in source_ids]
        return answered(items, "Source-backed lexical associations: " + ", ".join(n["label"] for n in systems) + ". No patient registration or anatomical localization is implied:")
    if request.tool == "get_biomarker_history":
        # Canonical trend service owns conversion, duplicate and comparability rules.
        from app.services.biomarker_trends import build_series
        eligible = {n["id"]: n for n in evidence if n["kind"] == "measurement"}
        series = build_series(db, case.id)
        summaries, cited = [], []
        for item in series:
            if request.query and not any(t in f"{item['name']} {item['display_name']}".casefold() for t in tokens):
                continue
            points = [p for p in item["points"] if f"measurement:{p.get('measurement_id')}" in eligible]
            if not points:
                continue
            # Do not present whole-case statistics for a source-filtered subset.
            for point in points:
                if len(cited) >= request.limit:
                    break
                node = eligible[f"measurement:{point['measurement_id']}"]
                cited.append(node)
                summaries.append(f"[{node['id']}] {item['display_name']}: {point['date']} · {point['value']} {item['unit']}; documented {point['documented_value']} {point['documented_unit']}.")
        if not cited:
            return reply("INSUFFICIENT_EVIDENCE", "No matching dated, uncensored, unit-compatible extracted observations are available. Undated, duplicate, manual or incomparable observations are not substituted.", reason="NO_ELIGIBLE_DATED_OBSERVATIONS")
        return reply("ANSWERED", "Canonical biomarker history, descriptive only; specimen and laboratory-method comparability must be reviewed before trends are interpreted:\n" + "\n".join(summaries), cited)
    if request.tool == "navigate_view":
        # The destination comes from code, never the query or a document URL.
        source = next((n for n in nodes if n["id"] == f"upload:{request.source_id}"), None)
        destination = ("/imaging" if source and source["details"].get("modality") == "IMAGE" else "/documents/verify") if request.source_id else "/anatomy-studio" if request.system_id else "/history" if request.exam_id else "/universal"
        from urllib.parse import urlencode
        source_parameter = "upload" if destination == "/documents/verify" else "source"
        params = {"case": case.id, **({source_parameter: request.source_id} if request.source_id else {}),
                  **({"finding": request.finding_id} if request.finding_id else {}), **({"exam": request.exam_id} if request.exam_id else {})}
        targets = [n for n in evidence if n["kind"] in {"statement", "measurement"}][:request.limit]
        if targets and targets[0].get("source_page") is not None:
            params["page"] = targets[0]["source_page"]
        path = destination + "?" + urlencode(params)
        return reply("ANSWERED", "Open the selected case view. This action only changes navigation.", nodes=targets, actions=[{"type": "NAVIGATE", "path": path, "source_id": request.source_id, "finding_id": request.finding_id}])
    # Enum validation makes draft_report the only remaining path.
    items = [n for n in evidence if n["kind"] in {"statement", "measurement"}]
    return answered(items, "DRAFT FOR HUMAN REVIEW — source-backed research summary only. This is not a final clinical report; no record has been created or changed.\nUnreviewed extractions remain unreviewed; discrepancies are unresolved.")
