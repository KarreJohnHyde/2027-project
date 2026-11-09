"""medSpaCy context checking and MedCAT concept linking, run in the WSL clinical NLP environment.

Both are secondary to the transparent rule extractor and never change its statements or the report label:
- medSpaCy's ConText and sectionizer re-assess every rule statement's span. Agreement on negation,
  uncertainty, hypothetical, history and family context is recorded in provenance, with each disagreement,
  so a reviewer can see where two independent context algorithms read a sentence differently.
- MedCAT links concepts with a model pack. Each linked mention becomes its own statement (category
  MODEL_CONCEPT, rule context for its sentence, its own extractor version), as scispaCy entities do.
  The default pack is MedCAT's example pack in the project: two concepts ("Kidney Failure", "Failure of
  Kidneys"), never trained, a demonstration of the integration rather than a clinical vocabulary. Real
  linking needs a UMLS or SNOMED CT pack (MEDTWIN_MEDCAT_MODEL_PACK). Packs are pickled: load trusted ones only.

MEDTWIN_CLINICAL_NLP: "auto" (default) runs these wherever ~/.medtwin/venv-clinical exists in WSL
(scripts/setup_clinical_nlp_wsl.sh), "wsl" forces them on, "off" turns them off. Neither tool has been
evaluated on an annotated clinical corpus here; published performance is the publishers'.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable, Optional

from app.services import wsl_runtime
from app.services.scispacy_adapter import entity_statements

WORKER = Path(__file__).resolve().parents[2] / "nlp_worker" / "clinical_nlp_worker.py"
PROJECT = Path(__file__).resolve().parents[3]
EXAMPLE_PACK = PROJECT / "cogstack-nlp-main" / "medcat-service" / "models" / "examples" / "example-medcat-v2-model-pack.zip"
TIMEOUT_SECONDS = 300
# Rule attribute value -> the medSpaCy ConText flag that expresses the same reading.
CONTEXT_PAIRS = (
    ("negation", "NEGATED", "is_negated"),
    ("certainty", "UNCERTAIN", "is_uncertain"),
    ("certainty", "HYPOTHETICAL", "is_hypothetical"),
    ("temporality", "HISTORICAL", "is_historical"),
    ("experiencer", "FAMILY", "is_family"),
)


class ClinicalNlpUnavailable(RuntimeError):
    """The clinical NLP environment is disabled, missing or failed."""


def mode() -> str:
    return os.getenv("MEDTWIN_CLINICAL_NLP", "auto").strip().lower()


def python() -> str:
    return os.getenv("MEDTWIN_CLINICAL_PYTHON", "~/.medtwin/venv-clinical/bin/python")


def enabled() -> bool:
    return wsl_runtime.enabled(mode(), python())


def model_pack() -> Optional[Path]:
    configured = os.getenv("MEDTWIN_MEDCAT_MODEL_PACK", "").strip()
    if configured:
        return Path(configured)
    return EXAMPLE_PACK if EXAMPLE_PACK.exists() else None


def run_worker(text: str, spans: list[dict[str, Any]], pack: Optional[Path]) -> dict[str, Any]:
    request = {"text": text, "spans": spans, "medcat_model_pack": wsl_runtime.wsl_path(pack) if pack else None}
    try:
        completed = subprocess.run(wsl_runtime.command(python(), WORKER), input=json.dumps(request), capture_output=True,
                                   text=True, encoding="utf-8", timeout=TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ClinicalNlpUnavailable(f"clinical NLP worker could not run: {type(exc).__name__}") from exc
    if completed.returncode != 0:
        raise ClinicalNlpUnavailable(f"clinical NLP worker {wsl_runtime.failure_summary(completed.returncode, completed.stderr)}")
    try:
        payload = wsl_runtime.parse_payload(completed.stdout, ("tools", "context", "medcat"))
    except ValueError as exc:  # json.JSONDecodeError is a ValueError
        raise ClinicalNlpUnavailable("clinical NLP worker returned malformed output") from exc
    return payload


def compare_context(rule_statements: list[dict[str, Any]], context: list[dict[str, Any]]) -> dict[str, Any]:
    """Per attribute, how often medSpaCy's ConText reads a rule statement's span the same way."""
    by_id = {item["id"]: item for item in context}
    compared = [(statement, by_id[index]) for index, statement in enumerate(rule_statements) if index in by_id]
    agreement, disagreements = {}, []
    for attribute, value, flag in CONTEXT_PAIRS:
        same = 0
        for statement, assessed in compared:
            rule_says, medspacy_says = statement.get(attribute) == value, assessed[flag]
            if rule_says == medspacy_says:
                same += 1
            elif len(disagreements) < 50:
                disagreements.append({"entity": statement.get("entity_text") or statement.get("entity"), "attribute": f"{attribute}={value}",
                                      "rules": rule_says, "medspacy": medspacy_says,
                                      "medspacy_cues": [modifier["text"] for modifier in assessed["modifiers"]][:5]})
        agreement[f"{attribute}={value}"] = {"agree": same, "of": len(compared)}
    return {"statements_compared": len(compared), "statements_without_offsets": len(rule_statements) - len(compared),
            "agreement": agreement, "disagreements": disagreements}


def analyse(text: str, rule_statements: list[dict[str, Any]],
            runner: Optional[Callable[[str, list[dict[str, Any]], Optional[Path]], dict[str, Any]]] = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Returns (MedCAT concept statements, provenance with the context comparison and the pack used)."""
    from app.services.model_usage_policy import registered_model_usage_gate
    for model_id in ("medcat_adapter", "medspacy_context_adapter"):
        usage = registered_model_usage_gate(model_id)
        if not usage["allowed"]:
            raise ClinicalNlpUnavailable(", ".join(usage["blockers"]))
    spans = [{"id": index, "start": statement["entity_start"], "end": statement["entity_end"]}
             for index, statement in enumerate(rule_statements)
             if isinstance(statement.get("entity_start"), int) and isinstance(statement.get("entity_end"), int)
             and statement["entity_end"] > statement["entity_start"]]
    pack = model_pack()
    payload = (runner or run_worker)(text, spans, pack)
    provenance: dict[str, Any] = {"status": "COMPLETED", "tools": payload["tools"],
                                  "medspacy_context": compare_context(rule_statements, payload["context"]),
                                  "validation_status": "PUBLISHER_REPORTED_ONLY_NOT_EVALUATED_ON_CLINICAL_CORPUS"}
    concepts: list[dict[str, Any]] = []
    medcat = payload.get("medcat")
    if medcat:
        info = medcat["pack"]
        example = pack is not None and pack.resolve() == EXAMPLE_PACK.resolve()
        version = f"medcat:{info.get('model_id') or 'pack'}"[:32]
        entities = [{"start": entity["start"], "end": entity["end"], "text": entity["text"], "category": "MODEL_CONCEPT",
                     "cue": f"medcat:{entity['cui']}:{entity['name']}", "extractor_version": version} for entity in medcat["entities"]]
        concepts = entity_statements(text, entities)
        provenance["medcat"] = {"pack": {**info, "example_pack": example}, "linked_mentions": len(concepts),
                                "vocabulary_note": ("MedCAT example pack: 2 concepts, never trained; a demonstration of the integration, "
                                                    "not a clinical vocabulary") if example else "configured model pack"}
    else:
        provenance["medcat"] = {"status": "NO_MODEL_PACK"}
    return concepts, provenance
