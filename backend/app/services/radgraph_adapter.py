"""RadGraph-XL observations and their anatomy on imaging-report pages, as secondary statements.

RadGraph (Stanford AIMI; MIT code and weights from huggingface.co/StanfordAIMI/RRG_scorers, downloaded with the
owner's approval into artifacts/third_party/radgraph) labels observations as definitely present, definitely
absent or uncertain and links them to anatomy (located_at), modifiers (modify) and other observations
(suggestive_of). It was trained on radiology reports (chest X-ray and, for the XL model, CT and MRI reports), so
it runs only on sentences of pages the page classifier types as imaging reports.

Each observation becomes its own statement (category MODEL_RADGRAPH_OBSERVATION): RadGraph's own presence label
gives negation and certainty, its located_at anatomy fills anatomical_site, and the rule extractor's context
supplies temporality and experiencer, which RadGraph does not model. Statements never replace rule statements.
MEDTWIN_RADGRAPH: "auto" (default) runs it when the package and the model are installed, "on" requires them,
"off" turns it off. Published performance is the publisher's; MedTwin has no annotated corpus to evaluate it.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Callable, Optional

from app.config import PROJECT_ROOT, ENVIRONMENT
from app.services.nlp_processor import _assess, _section_at, _sections, split_sentences

MODEL_TYPE = "radgraph-xl"
CACHE = PROJECT_ROOT / "artifacts" / "third_party" / "radgraph"
IMAGING = "IMAGING_REPORT"
PRESENCE = {"definitely present": ("AFFIRMED", "CERTAIN"), "definitely absent": ("NEGATED", "CERTAIN"), "uncertain": ("AFFIRMED", "UNCERTAIN")}


class RadGraphUnavailable(RuntimeError):
    """RadGraph or its model is not installed, or it failed."""


def mode() -> str:
    return os.getenv("MEDTWIN_RADGRAPH", "auto").strip().lower()


def installed() -> bool:
    try:
        import radgraph  # noqa: F401
    except ImportError:
        return False
    model_dir = CACHE / MODEL_TYPE
    return model_dir.is_dir() and any(model_dir.iterdir())


def enabled() -> bool:
    setting = mode()
    if ENVIRONMENT == "production":
        # Report an explicit unavailable reason without importing the legacy stack.
        return setting != "off"
    return setting == "on" or (setting == "auto" and installed())


@lru_cache(maxsize=1)
def _model():
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    if not installed():
        raise RadGraphUnavailable("RadGraph or the radgraph-xl model is not installed (artifacts/third_party/radgraph).")
    from radgraph import RadGraph

    return RadGraph(model_type=MODEL_TYPE, model_cache_dir=str(CACHE))


def run_model(sentences: list[str]) -> dict[str, Any]:
    """RadGraph's graphs keyed "0", "1", ... in the order of the sentences given."""
    if ENVIRONMENT == "production":
        raise RadGraphUnavailable("RADGRAPH_NOT_APPROVED_FOR_PRODUCTION: the dependency migration does not establish clinical validation or commercial rights for this adapter.")
    from app.services.model_inference import _inference_lock
    from app.services.model_usage_policy import registered_model_usage_gate

    usage = registered_model_usage_gate("radgraph_adapter")
    if not usage["allowed"]:
        raise RadGraphUnavailable(", ".join(usage["blockers"]))

    try:
        with _inference_lock:  # one model on the GPU at a time
            return _model()(sentences)
    except RadGraphUnavailable:
        raise
    except Exception as exc:  # the third-party stack raises many types; none may break report analysis
        raise RadGraphUnavailable(f"RadGraph failed: {type(exc).__name__}") from exc


def imaging_sentences(text: str, page_starts: list[int], page_meta: list[dict[str, Any]]) -> list[tuple[int, int]]:
    """Sentence bounds that start on a page typed as an imaging report."""
    ends = [*page_starts[1:], len(text) + 1]
    imaging = [(start, end) for start, end, meta in zip(page_starts, ends, page_meta)
               if (meta.get("document_type") or {}).get("document_type") == IMAGING]
    return [(start, end) for start, end in split_sentences(text)
            if any(low <= start < high for low, high in imaging) and text[start:end].strip()]


def _token_spans(sentence: str, tokens: list[str]) -> Optional[list[tuple[int, int]]]:
    """RadGraph-XL tokens are pieces of the text in order (wordpunct, some punctuation runs split further);
    find each one after the previous. None if a token is not in the text (the graph is then skipped)."""
    spans, cursor = [], 0
    for token in tokens:
        found = sentence.find(token, cursor)
        if found < 0:
            return None
        spans.append((found, found + len(token)))
        cursor = found + len(token)
    return spans


def observation_statements(text: str, page_starts: list[int], page_meta: list[dict[str, Any]],
                           runner: Optional[Callable[[list[str]], dict[str, Any]]] = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    bounds = imaging_sentences(text, page_starts, page_meta)
    if not bounds:
        return [], {"status": "NOT_APPLICABLE", "reason": "No page of this document is typed as an imaging report."}
    graphs = (runner or run_model)([text[start:end] for start, end in bounds])
    sections = _sections(text)
    statements, relations = [], 0
    for index, (start, end) in enumerate(bounds):
        graph = graphs.get(str(index))
        sentence = text[start:end]
        # graph["text"] is RadGraph's own token sequence, the one its start_ix/end_ix index into.
        spans = _token_spans(sentence, graph["text"].split()) if graph else None
        if not graph or spans is None:
            continue
        entities = graph["entities"]
        for entity in entities.values():
            kind, _, presence = entity["label"].partition("::")
            if kind != "Observation" or presence not in PRESENCE or entity["end_ix"] >= len(spans):
                continue
            local_start, local_end = spans[entity["start_ix"]][0], spans[entity["end_ix"]][1]
            sites = [entities[target]["tokens"] for relation, target in entity["relations"] if relation == "located_at" and target in entities]
            relations += len(entity["relations"])
            negation, certainty = PRESENCE[presence]
            section = _section_at(sections, start)
            context = _assess(sentence, local_start, local_end, section)
            statements.append({
                "entity": sentence[local_start:local_end].lower()[:128], "entity_text": sentence[local_start:local_end][:128],
                "category": "MODEL_RADGRAPH_OBSERVATION", "negation": negation, "certainty": certainty,
                "temporality": context["temporality"], "experiencer": context["experiencer"], "comparison": context["comparison"],
                "cues": [{"type": "MODEL_INFERENCE", "text": f"{MODEL_TYPE}:{entity['label']}"[:128], "start": None, "end": None},
                         *[{"type": "MODEL_RELATION", "text": f"{relation}:{entities[target]['tokens']}"[:128], "start": None, "end": None}
                           for relation, target in entity["relations"] if target in entities]],
                "section": section, "anatomical_site": "; ".join(sites)[:128] or None, "laterality": None, "anatomy_system": None,
                "atlas_structure_id": None, "source_span": sentence[:256], "source_span_start": start, "source_span_end": end,
                "entity_start": start + local_start, "entity_end": start + local_end, "extractor_version": f"radgraph:{MODEL_TYPE}:tf5.2"[:32],
            })
    return statements, {"status": "COMPLETED", "model": MODEL_TYPE, "sentences": len(bounds), "observations": len(statements),
                        "relations": relations, "validation_status": "PUBLISHER_REPORTED_ONLY_NOT_EVALUATED_ON_CLINICAL_CORPUS"}
