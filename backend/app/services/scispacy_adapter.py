"""Secondary biomedical NER with scispaCy, run in the isolated WSL NLP environment.

spaCy's native extensions are blocked by Windows Smart App Control on this host, so
the models run in WSL (scripts/setup_nlp_wsl.sh) through nlp_worker/scispacy_worker.py.
The text stays on this machine. Each model entity is given the same context rules as
the rule extractor (negation, certainty, temporality, experiencer) and is stored as a
separate statement with its own extractor_version; it never replaces a rule statement
and never changes the report label.

MEDTWIN_SCISPACY: "auto" (default) runs it wherever the WSL environment exists, "wsl" forces
it on, "off" turns it off. Published NER performance of the models is the publisher's;
MedTwin has no annotated clinical corpus to evaluate them.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Optional

from app.services import wsl_runtime
from app.services.nlp_processor import _assess, _section_at, _sections, split_sentences

logger = logging.getLogger(__name__)

WORKER = Path(__file__).resolve().parents[2] / "nlp_worker" / "scispacy_worker.py"
DEFAULT_MODELS = ("en_ner_bc5cdr_md",)
LABEL_CATEGORIES = {"DISEASE": "MODEL_DISEASE", "CHEMICAL": "MODEL_CHEMICAL", "ENTITY": "MODEL_ENTITY"}
TIMEOUT_SECONDS = 180


class ScispacyUnavailable(RuntimeError):
    """The NLP environment is disabled, missing or failed."""


def mode() -> str:
    return os.getenv("MEDTWIN_SCISPACY", "auto").strip().lower()


def python() -> str:
    return os.getenv("MEDTWIN_NLP_PYTHON", "~/.medtwin/venv-nlp/bin/python")


def enabled() -> bool:
    return wsl_runtime.enabled(mode(), python())


def models() -> tuple[str, ...]:
    configured = os.getenv("MEDTWIN_SCISPACY_MODELS", "").strip()
    return tuple(name.strip() for name in configured.split(",") if name.strip()) or DEFAULT_MODELS


def run_worker(text: str, names: tuple[str, ...]) -> dict[str, Any]:
    try:
        completed = subprocess.run(wsl_runtime.command(python(), WORKER), input=json.dumps({"text": text, "models": list(names)}), capture_output=True,
                                   text=True, encoding="utf-8", timeout=TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ScispacyUnavailable(f"scispaCy worker could not run: {type(exc).__name__}") from exc
    if completed.returncode != 0:
        raise ScispacyUnavailable(f"scispaCy worker {wsl_runtime.failure_summary(completed.returncode, completed.stderr)}")
    try:
        payload = wsl_runtime.parse_payload(completed.stdout, ("models", "entities"))
    except ValueError as exc:  # json.JSONDecodeError is a ValueError
        raise ScispacyUnavailable("scispaCy worker returned malformed output") from exc
    return payload


@lru_cache(maxsize=1)
def probe() -> dict[str, Any]:
    """Runs the worker once on a fixed sentence; reports availability and model versions."""
    if not enabled():
        return {"available": False, "reason": "DISABLED (MEDTWIN_SCISPACY is off, or its WSL environment is missing)"}
    try:
        payload = run_worker("No evidence of pneumonia.", models())
    except ScispacyUnavailable as exc:
        return {"available": False, "reason": str(exc)}
    return {"available": True, "models": payload["models"]}


def extractor_version(model: dict[str, Any]) -> str:
    return f"scispacy:{model['name']}-{model['version']}"[:32]


def model_statements(text: str, runner: Optional[Callable[[str, tuple[str, ...]], dict[str, Any]]] = None,
                     names: Optional[tuple[str, ...]] = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Statements for model entities, with rule-based context; returns (statements, model metadata)."""
    from app.services.model_usage_policy import registered_model_usage_gate
    usage = registered_model_usage_gate("scispacy_adapter")
    if not usage["allowed"]:
        raise ScispacyUnavailable(", ".join(usage["blockers"]))
    payload = (runner or run_worker)(text, names or models())
    versions = {model["name"]: extractor_version(model) for model in payload["models"]}
    entities = [{**entity, "category": LABEL_CATEGORIES.get(entity["label"], "MODEL_ENTITY"), "cue": f"{entity['model']}:{entity['label']}",
                 "extractor_version": versions.get(entity["model"])} for entity in payload["entities"]]
    return entity_statements(text, entities), payload["models"]


def entity_statements(text: str, entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One statement per model entity ({start, end, text, category, cue, extractor_version}), given the
    rule extractor's context for its sentence. Entities whose offsets do not quote the text are dropped."""
    sections = _sections(text)
    sentences = split_sentences(text)
    statements = []
    for entity in sorted(entities, key=lambda item: (item["start"], item["end"])):
        bounds = next(((start, end) for start, end in sentences if start <= entity["start"] and entity["end"] <= end), None)
        if bounds is None or text[entity["start"]:entity["end"]] != entity["text"]:
            continue  # entity offsets must point at the same characters in the stored text
        sentence_start, sentence_end = bounds
        sentence = text[sentence_start:sentence_end]
        section = _section_at(sections, sentence_start)
        context = _assess(sentence, entity["start"] - sentence_start, entity["end"] - sentence_start, section)
        context.pop("clause")
        for cue in context["cues"]:
            if cue["start"] is not None:
                cue["start"] += sentence_start
                cue["end"] += sentence_start
        statements.append({
            "entity": entity["text"].lower()[:128], "entity_text": entity["text"][:128], "category": entity["category"],
            "negation": context["negation"], "certainty": context["certainty"], "temporality": context["temporality"],
            "experiencer": context["experiencer"], "comparison": context["comparison"],
            "cues": [{"type": "MODEL_INFERENCE", "text": entity["cue"][:128], "start": None, "end": None}, *context["cues"]],
            "section": section, "anatomical_site": None, "laterality": None, "anatomy_system": None, "atlas_structure_id": None,
            "source_span": sentence[:256], "source_span_start": sentence_start, "source_span_end": sentence_end,
            "entity_start": entity["start"], "entity_end": entity["end"], "extractor_version": entity["extractor_version"],
        })
    return statements
