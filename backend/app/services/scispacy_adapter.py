"""Secondary biomedical NER with scispaCy, run in the isolated WSL NLP environment.

spaCy's native extensions are blocked by Windows Smart App Control on this host, so
the models run in WSL (scripts/setup_nlp_wsl.sh) through nlp_worker/scispacy_worker.py.
The text stays on this machine. Each model entity is given the same context rules as
the rule extractor (negation, certainty, temporality, experiencer) and is stored as a
separate statement with its own extractor_version; it never replaces a rule statement
and never changes the report label.

Enabled with MEDTWIN_SCISPACY=wsl (default off). Published NER performance of the
models is the publisher's; MedTwin has no annotated clinical corpus to evaluate them.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Optional

from app.services.nlp_processor import _assess, _section_at, _sections, split_sentences

logger = logging.getLogger(__name__)

WORKER = Path(__file__).resolve().parents[2] / "nlp_worker" / "scispacy_worker.py"
DEFAULT_MODELS = ("en_ner_bc5cdr_md",)
LABEL_CATEGORIES = {"DISEASE": "MODEL_DISEASE", "CHEMICAL": "MODEL_CHEMICAL", "ENTITY": "MODEL_ENTITY"}
TIMEOUT_SECONDS = 180


class ScispacyUnavailable(RuntimeError):
    """The NLP environment is disabled, missing or failed."""


def mode() -> str:
    return os.getenv("MEDTWIN_SCISPACY", "off").strip().lower()


def models() -> tuple[str, ...]:
    configured = os.getenv("MEDTWIN_SCISPACY_MODELS", "").strip()
    return tuple(name.strip() for name in configured.split(",") if name.strip()) or DEFAULT_MODELS


def wsl_path(path: Path) -> str:
    drive, rest = path.drive.rstrip(":").lower(), path.as_posix().split(":", 1)[-1]
    return f"/mnt/{drive}{rest}"


def _wsl_command() -> list[str]:
    distro = os.getenv("MEDTWIN_WSL_DISTRO", "Ubuntu")
    python = os.getenv("MEDTWIN_NLP_PYTHON", "~/.medtwin/venv-nlp/bin/python")
    # bash -lc expands "~"; the worker path is quoted for safety.
    return ["wsl.exe", "-d", distro, "--", "bash", "-lc", f"{python} '{wsl_path(WORKER)}'"]


def run_worker(text: str, names: tuple[str, ...]) -> dict[str, Any]:
    try:
        completed = subprocess.run(_wsl_command(), input=json.dumps({"text": text, "models": list(names)}), capture_output=True,
                                   text=True, encoding="utf-8", timeout=TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ScispacyUnavailable(f"scispaCy worker could not run: {type(exc).__name__}") from exc
    if completed.returncode != 0:
        # stderr can quote the input text; log only its last line.
        tail = (completed.stderr.strip().splitlines() or ["no output"])[-1][:200]
        raise ScispacyUnavailable(f"scispaCy worker exited with {completed.returncode}: {tail}")
    return json.loads(completed.stdout)


@lru_cache(maxsize=1)
def probe() -> dict[str, Any]:
    """Runs the worker once on a fixed sentence; reports availability and model versions."""
    if mode() != "wsl":
        return {"available": False, "reason": "DISABLED (set MEDTWIN_SCISPACY=wsl)"}
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
    payload = (runner or run_worker)(text, names or models())
    versions = {model["name"]: extractor_version(model) for model in payload["models"]}
    sections = _sections(text)
    sentences = split_sentences(text)
    statements = []
    for entity in sorted(payload["entities"], key=lambda item: (item["start"], item["end"])):
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
            "entity": entity["text"].lower()[:128], "entity_text": entity["text"][:128], "category": LABEL_CATEGORIES.get(entity["label"], "MODEL_ENTITY"),
            "negation": context["negation"], "certainty": context["certainty"], "temporality": context["temporality"],
            "experiencer": context["experiencer"], "comparison": context["comparison"],
            "cues": [{"type": "MODEL_INFERENCE", "text": f"{entity['model']}:{entity['label']}", "start": None, "end": None}, *context["cues"]],
            "section": section, "anatomical_site": None, "laterality": None, "anatomy_system": None, "atlas_structure_id": None,
            "source_span": sentence[:256], "source_span_start": sentence_start, "source_span_end": sentence_end,
            "entity_start": entity["start"], "entity_end": entity["end"], "extractor_version": versions.get(entity["model"]),
        })
    return statements, payload["models"]
