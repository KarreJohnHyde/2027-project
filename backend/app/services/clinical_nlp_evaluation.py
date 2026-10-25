"""Strict, corpus-agnostic evaluation for clinical NLP entity spans.

The evaluator consumes two independently supplied JSON artifacts: an adjudicated
gold artifact and a prediction artifact. It does not create labels, infer missing
context, or claim that an uploaded corpus is clinically representative. Exact and
overlap matching are label-aware and one-to-one; assertion, negation and temporality
are scored separately on the matched entities.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from bisect import bisect_left
import hashlib
import json
import re
from typing import Any, Callable, Iterable

from app.services.evaluation_metrics import EvaluationInputError


SCHEMA_VERSION = "medtwin.clinical-nlp-spans.v1"
MAX_DOCUMENTS = 10_000
MAX_SPANS = 100_000
MAX_PER_DOCUMENT_ROWS = 1_000
MAX_MATCH_EDGES = 2_000_000
MAX_MATCH_COMPARISONS = 5_000_000
MAX_LABELS = 1_000
_DOCUMENT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_NORMALIZED_TOKEN = re.compile(r"[A-Z][A-Z0-9_:-]{0,63}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_CONTEXT_FIELDS = ("assertion", "negation", "temporality")
_CONTEXT_VALUES = {
    "assertion": {"CERTAIN", "UNCERTAIN", "HYPOTHETICAL"},
    "negation": {"AFFIRMED", "NEGATED"},
    "temporality": {"CURRENT", "HISTORICAL"},
}


@dataclass(frozen=True)
class Document:
    document_id: str
    character_count: int
    document_sha256: str


@dataclass(frozen=True)
class EntitySpan:
    document_id: str
    start: int
    end: int
    label: str
    assertion: str
    negation: str
    temporality: str
    code_system: str | None
    concept_id: str | None

    @property
    def identity(self) -> tuple[str, int, int, str]:
        return (self.document_id, self.start, self.end, self.label)


@dataclass(frozen=True)
class SpanArtifact:
    role: str
    documents: tuple[Document, ...]
    spans: tuple[EntitySpan, ...]


def _strict_keys(value: dict[str, Any], required: set[str], optional: set[str], location: str) -> None:
    missing = sorted(required - value.keys())
    unexpected = sorted(value.keys() - required - optional)
    if missing:
        raise EvaluationInputError(f"{location} is missing required field(s): {', '.join(missing)}.")
    if unexpected:
        raise EvaluationInputError(f"{location} has unexpected field(s): {', '.join(unexpected)}.")


def _normalized_token(value: Any, field: str, location: str) -> str:
    if not isinstance(value, str) or not _NORMALIZED_TOKEN.fullmatch(value):
        raise EvaluationInputError(
            f"{location}.{field} must be a normalized uppercase token (A-Z, 0-9, underscore, colon or hyphen)."
        )
    return value


def _context_value(value: Any, field: str, location: str) -> str:
    normalized = _normalized_token(value, field, location)
    if normalized not in _CONTEXT_VALUES[field]:
        accepted = ", ".join(sorted(_CONTEXT_VALUES[field]))
        raise EvaluationInputError(f"{location}.{field} must be one of: {accepted}.")
    return normalized


def _parse_json(content: bytes, expected_role: str) -> SpanArtifact:
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise EvaluationInputError(f"The {expected_role} artifact must be UTF-8 JSON.") from exc
    try:
        payload = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise EvaluationInputError(f"The {expected_role} artifact is not valid JSON: {exc.msg}.") from exc
    if not isinstance(payload, dict):
        raise EvaluationInputError(f"The {expected_role} artifact root must be an object.")
    _strict_keys(payload, {"schema_version", "artifact_role", "documents", "spans"}, set(), f"{expected_role} artifact")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise EvaluationInputError(f"The {expected_role} artifact schema_version must be '{SCHEMA_VERSION}'.")
    if payload["artifact_role"] != expected_role:
        raise EvaluationInputError(f"The {expected_role} upload must declare artifact_role '{expected_role}'.")
    if not isinstance(payload["documents"], list):
        raise EvaluationInputError(f"{expected_role} artifact.documents must be an array.")
    if not isinstance(payload["spans"], list):
        raise EvaluationInputError(f"{expected_role} artifact.spans must be an array.")
    if len(payload["documents"]) > MAX_DOCUMENTS:
        raise EvaluationInputError(f"At most {MAX_DOCUMENTS} documents are accepted per artifact.")
    if len(payload["spans"]) > MAX_SPANS:
        raise EvaluationInputError(f"At most {MAX_SPANS} spans are accepted per artifact.")

    documents: list[Document] = []
    document_by_id: dict[str, Document] = {}
    for index, raw in enumerate(payload["documents"]):
        location = f"{expected_role} artifact.documents[{index}]"
        if not isinstance(raw, dict):
            raise EvaluationInputError(f"{location} must be an object.")
        _strict_keys(raw, {"document_id", "character_count", "document_sha256"}, set(), location)
        document_id = raw["document_id"]
        if not isinstance(document_id, str) or not _DOCUMENT_ID.fullmatch(document_id):
            raise EvaluationInputError(
                f"{location}.document_id must be a pseudonymous 1-128 character identifier using letters, digits, dot, underscore, colon or hyphen."
            )
        character_count = raw["character_count"]
        if type(character_count) is not int or character_count < 0:
            raise EvaluationInputError(f"{location}.character_count must be a non-negative integer.")
        document_sha256 = raw["document_sha256"]
        if not isinstance(document_sha256, str) or not _SHA256.fullmatch(document_sha256):
            raise EvaluationInputError(f"{location}.document_sha256 must be a lowercase SHA-256 hex digest.")
        if document_id in document_by_id:
            raise EvaluationInputError(f"Duplicate document_id '{document_id}' in the {expected_role} artifact.")
        document = Document(document_id, character_count, document_sha256)
        documents.append(document)
        document_by_id[document_id] = document

    spans: list[EntitySpan] = []
    identities: set[tuple[str, int, int, str]] = set()
    for index, raw in enumerate(payload["spans"]):
        location = f"{expected_role} artifact.spans[{index}]"
        if not isinstance(raw, dict):
            raise EvaluationInputError(f"{location} must be an object.")
        required = {"document_id", "start", "end", "label", "assertion", "negation", "temporality"}
        _strict_keys(raw, required, {"code_system", "concept_id"}, location)
        document_id = raw["document_id"]
        if not isinstance(document_id, str) or document_id not in document_by_id:
            raise EvaluationInputError(f"{location}.document_id must reference a document declared in the same artifact.")
        start, end = raw["start"], raw["end"]
        if type(start) is not int or type(end) is not int:
            raise EvaluationInputError(f"{location}.start and .end must be integers.")
        if start < 0 or end <= start:
            raise EvaluationInputError(f"{location} must satisfy 0 <= start < end.")
        if end > document_by_id[document_id].character_count:
            raise EvaluationInputError(f"{location}.end exceeds the declared document character_count.")
        has_code_system = "code_system" in raw
        has_concept_id = "concept_id" in raw
        if has_code_system != has_concept_id:
            raise EvaluationInputError(f"{location}.code_system and .concept_id must be supplied together.")
        code_system = _normalized_token(raw["code_system"], "code_system", location) if has_code_system else None
        concept_id = raw.get("concept_id")
        if concept_id is not None and (
            not isinstance(concept_id, str) or not _DOCUMENT_ID.fullmatch(concept_id)
        ):
            raise EvaluationInputError(
                f"{location}.concept_id must be a normalized 1-128 character code using letters, digits, dot, underscore, colon or hyphen."
            )
        span = EntitySpan(
            document_id=document_id,
            start=start,
            end=end,
            label=_normalized_token(raw["label"], "label", location),
            assertion=_context_value(raw["assertion"], "assertion", location),
            negation=_context_value(raw["negation"], "negation", location),
            temporality=_context_value(raw["temporality"], "temporality", location),
            code_system=code_system,
            concept_id=concept_id,
        )
        if span.identity in identities:
            raise EvaluationInputError(
                f"Duplicate entity span in the {expected_role} artifact at {document_id}:{start}-{end} with label {span.label}."
            )
        identities.add(span.identity)
        spans.append(span)

    if len({span.label for span in spans}) > MAX_LABELS:
        raise EvaluationInputError(f"At most {MAX_LABELS} distinct normalized labels are accepted per artifact.")

    return SpanArtifact(expected_role, tuple(documents), tuple(spans))


def _verify_matching_manifests(gold: SpanArtifact, predictions: SpanArtifact) -> None:
    gold_manifest = {item.document_id: (item.character_count, item.document_sha256) for item in gold.documents}
    predicted_manifest = {item.document_id: (item.character_count, item.document_sha256) for item in predictions.documents}
    if gold_manifest != predicted_manifest:
        raise EvaluationInputError(
            "Gold and prediction document manifests must contain the same document IDs, character counts and document hashes."
        )


def _overlap_length(left: EntitySpan, right: EntitySpan) -> int:
    if left.document_id != right.document_id:
        return 0
    return max(0, min(left.end, right.end) - max(left.start, right.start))


def _maximum_matching(
    gold: list[EntitySpan],
    predictions: list[EntitySpan],
    compatible: Callable[[EntitySpan, EntitySpan], bool],
) -> list[tuple[int, int]]:
    """Maximum-cardinality bipartite match with deterministic, overlap-first edges."""
    prediction_order = sorted(
        range(len(predictions)), key=lambda index: (predictions[index].start, predictions[index].end, index)
    )
    prediction_starts = [predictions[index].start for index in prediction_order]
    adjacency: list[list[int]] = []
    edge_count = 0
    for gold_span in gold:
        # Only predictions that start before the gold end can overlap. The
        # compatibility predicate applies the remaining end/label checks.
        possible = prediction_order[: bisect_left(prediction_starts, gold_span.end)]
        candidates = [index for index in possible if compatible(gold_span, predictions[index])]
        edge_count += len(candidates)
        if edge_count > MAX_MATCH_EDGES:
            raise EvaluationInputError(
                "The artifacts contain more than 2,000,000 candidate span overlaps; split the evaluation by a fixed document partition."
            )
        candidates.sort(
            key=lambda index: (
                -_overlap_length(gold_span, predictions[index]),
                abs(gold_span.start - predictions[index].start) + abs(gold_span.end - predictions[index].end),
                predictions[index].start,
                predictions[index].end,
                predictions[index].label,
                index,
            )
        )
        adjacency.append(candidates)

    gold_to_prediction = [-1] * len(gold)
    prediction_to_gold = [-1] * len(predictions)
    for root in range(len(gold)):
        if gold_to_prediction[root] != -1:
            continue
        stack = [root]
        visited_gold = {root}
        visited_predictions: set[int] = set()
        parent_prediction: dict[int, int] = {}
        free_prediction = -1
        while stack and free_prediction == -1:
            gold_index = stack.pop()
            for prediction_index in adjacency[gold_index]:
                if prediction_index in visited_predictions:
                    continue
                visited_predictions.add(prediction_index)
                parent_prediction[prediction_index] = gold_index
                matched_gold = prediction_to_gold[prediction_index]
                if matched_gold == -1:
                    free_prediction = prediction_index
                    break
                if matched_gold not in visited_gold:
                    visited_gold.add(matched_gold)
                    stack.append(matched_gold)
        if free_prediction == -1:
            continue
        prediction_index = free_prediction
        while prediction_index != -1:
            gold_index = parent_prediction[prediction_index]
            previous_prediction = gold_to_prediction[gold_index]
            gold_to_prediction[gold_index] = prediction_index
            prediction_to_gold[prediction_index] = gold_index
            prediction_index = previous_prediction
    return [(gold_index, prediction_index) for gold_index, prediction_index in enumerate(gold_to_prediction) if prediction_index != -1]


def _exact_matches(gold: list[EntitySpan], predictions: list[EntitySpan]) -> list[tuple[int, int]]:
    predicted_by_identity = {span.identity: index for index, span in enumerate(predictions)}
    return [(index, predicted_by_identity[span.identity]) for index, span in enumerate(gold) if span.identity in predicted_by_identity]


def _grouped_overlap_matches(
    gold: list[EntitySpan], predictions: list[EntitySpan], label_aware: bool
) -> list[tuple[int, int]]:
    gold_groups: dict[tuple[str, ...], list[int]] = defaultdict(list)
    prediction_groups: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for index, span in enumerate(gold):
        key = (span.document_id, span.label) if label_aware else (span.document_id,)
        gold_groups[key].append(index)
    for index, span in enumerate(predictions):
        key = (span.document_id, span.label) if label_aware else (span.document_id,)
        prediction_groups[key].append(index)

    matches: list[tuple[int, int]] = []
    comparison_count = 0
    for key in sorted(gold_groups.keys() & prediction_groups.keys()):
        gold_indexes = gold_groups[key]
        prediction_indexes = prediction_groups[key]
        comparison_count += len(gold_indexes) * len(prediction_indexes)
        if comparison_count > MAX_MATCH_COMPARISONS:
            raise EvaluationInputError(
                "The artifacts require more than 5,000,000 candidate span comparisons; split the evaluation by a fixed document partition."
            )
        local_gold = [gold[index] for index in gold_indexes]
        local_predictions = [predictions[index] for index in prediction_indexes]
        local_matches = _maximum_matching(
            local_gold,
            local_predictions,
            lambda left, right: _overlap_length(left, right) > 0,
        )
        matches.extend((gold_indexes[left], prediction_indexes[right]) for left, right in local_matches)
    return sorted(matches)


def _overlap_matches(gold: list[EntitySpan], predictions: list[EntitySpan], label_aware: bool = True) -> list[tuple[int, int]]:
    return _grouped_overlap_matches(gold, predictions, label_aware)


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def _score(matches: int, gold_count: int, predicted_count: int) -> dict[str, int | float | None]:
    false_positive = predicted_count - matches
    false_negative = gold_count - matches
    return {
        "tp": matches,
        "fp": false_positive,
        "fn": false_negative,
        "precision": _ratio(matches, matches + false_positive),
        "recall": _ratio(matches, matches + false_negative),
        "f1": _ratio(2 * matches, 2 * matches + false_positive + false_negative),
    }


def _context_summary(
    gold: list[EntitySpan], predictions: list[EntitySpan], matches: Iterable[tuple[int, int]], field: str
) -> dict[str, Any]:
    pairs = [(getattr(gold[left], field), getattr(predictions[right], field)) for left, right in matches]
    confusion = Counter(pairs)
    correct = sum(count for (reference, predicted), count in confusion.items() if reference == predicted)
    return {
        "evaluated": len(pairs),
        "correct": correct,
        "errors": len(pairs) - correct,
        "accuracy": _ratio(correct, len(pairs)),
        "confusion": [
            {"gold": reference, "predicted": predicted, "count": count}
            for (reference, predicted), count in sorted(confusion.items())
        ],
    }


def _context_block(
    gold: list[EntitySpan], predictions: list[EntitySpan], matches: list[tuple[int, int]]
) -> dict[str, Any]:
    return {field: _context_summary(gold, predictions, matches, field) for field in _CONTEXT_FIELDS}


def _concept_link_summary(
    gold: list[EntitySpan], predictions: list[EntitySpan], matches: Iterable[tuple[int, int]]
) -> dict[str, Any]:
    annotated = [
        (gold[left], predictions[right])
        for left, right in matches
        if gold[left].code_system is not None and gold[left].concept_id is not None
    ]
    correct = 0
    missing = 0
    wrong = 0
    confusion: Counter[tuple[str, str]] = Counter()
    for reference, predicted in annotated:
        gold_code = f"{reference.code_system}:{reference.concept_id}"
        if predicted.code_system is None or predicted.concept_id is None:
            predicted_code = "__MISSING__"
            missing += 1
        else:
            predicted_code = f"{predicted.code_system}:{predicted.concept_id}"
            if predicted_code == gold_code:
                correct += 1
            else:
                wrong += 1
        confusion[(gold_code, predicted_code)] += 1
    return {
        "evaluated": len(annotated),
        "correct": correct,
        "missing": missing,
        "wrong": wrong,
        "errors": missing + wrong,
        "accuracy": _ratio(correct, len(annotated)),
        "confusion": [
            {"gold": reference, "predicted": predicted, "count": count}
            for (reference, predicted), count in sorted(confusion.items())
        ],
    }


def _per_label(
    gold: list[EntitySpan],
    predictions: list[EntitySpan],
    exact: list[tuple[int, int]],
    overlap: list[tuple[int, int]],
) -> list[dict[str, Any]]:
    gold_by_label: dict[str, set[int]] = defaultdict(set)
    predictions_by_label: dict[str, set[int]] = defaultdict(set)
    exact_by_label: dict[str, list[tuple[int, int]]] = defaultdict(list)
    overlap_by_label: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for index, span in enumerate(gold):
        gold_by_label[span.label].add(index)
    for index, span in enumerate(predictions):
        predictions_by_label[span.label].add(index)
    for pair in exact:
        exact_by_label[gold[pair[0]].label].append(pair)
    for pair in overlap:
        overlap_by_label[gold[pair[0]].label].append(pair)

    rows: list[dict[str, Any]] = []
    for label in sorted(gold_by_label.keys() | predictions_by_label.keys()):
        gold_indexes = gold_by_label[label]
        predicted_indexes = predictions_by_label[label]
        exact_matches = exact_by_label[label]
        overlap_matches = overlap_by_label[label]
        rows.append(
            {
                "label": label,
                "gold_count": len(gold_indexes),
                "predicted_count": len(predicted_indexes),
                "exact_span": _score(len(exact_matches), len(gold_indexes), len(predicted_indexes)),
                "overlap": _score(len(overlap_matches), len(gold_indexes), len(predicted_indexes)),
                "context_errors": {
                    "exact_span": {
                        field: _context_summary(gold, predictions, exact_matches, field)["errors"]
                        for field in _CONTEXT_FIELDS
                    },
                    "overlap": {
                        field: _context_summary(gold, predictions, overlap_matches, field)["errors"]
                        for field in _CONTEXT_FIELDS
                    },
                },
                "concept_link_errors": {
                    "exact_span": _concept_link_summary(gold, predictions, exact_matches)["errors"],
                    "overlap": _concept_link_summary(gold, predictions, overlap_matches)["errors"],
                },
            }
        )
    return rows


def _label_confusion(
    gold: list[EntitySpan], predictions: list[EntitySpan]
) -> tuple[list[dict[str, Any]], list[tuple[int, int]]]:
    matches = _overlap_matches(gold, predictions, label_aware=False)
    paired_gold = {left for left, _ in matches}
    paired_predictions = {right for _, right in matches}
    confusion = Counter((gold[left].label, predictions[right].label) for left, right in matches)
    confusion.update((gold[index].label, "__MISSING__") for index in range(len(gold)) if index not in paired_gold)
    confusion.update(("__SPURIOUS__", predictions[index].label) for index in range(len(predictions)) if index not in paired_predictions)
    rows = [
        {"gold": reference, "predicted": predicted, "count": count}
        for (reference, predicted), count in sorted(confusion.items())
    ]
    return rows, matches


def _per_document(
    documents: tuple[Document, ...],
    gold: list[EntitySpan],
    predictions: list[EntitySpan],
    exact: list[tuple[int, int]],
    overlap: list[tuple[int, int]],
) -> tuple[list[dict[str, Any]], bool]:
    rows: list[dict[str, Any]] = []
    gold_by_document: dict[str, set[int]] = defaultdict(set)
    predicted_by_document: dict[str, set[int]] = defaultdict(set)
    exact_by_document: dict[str, list[tuple[int, int]]] = defaultdict(list)
    overlap_by_document: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for index, span in enumerate(gold):
        gold_by_document[span.document_id].add(index)
    for index, span in enumerate(predictions):
        predicted_by_document[span.document_id].add(index)
    for pair in exact:
        exact_by_document[gold[pair[0]].document_id].append(pair)
    for pair in overlap:
        overlap_by_document[gold[pair[0]].document_id].append(pair)
    for document in documents[:MAX_PER_DOCUMENT_ROWS]:
        gold_indexes = gold_by_document[document.document_id]
        predicted_indexes = predicted_by_document[document.document_id]
        document_exact = exact_by_document[document.document_id]
        document_overlap = overlap_by_document[document.document_id]
        rows.append(
            {
                # Never persist uploader-supplied identifiers in an evaluation
                # result; the digest preserves sample-level provenance without
                # copying a potentially identifying token into the shared run log.
                "document_id_sha256": hashlib.sha256(document.document_id.encode("utf-8")).hexdigest(),
                "character_count": document.character_count,
                "document_sha256": document.document_sha256,
                "gold_spans": len(gold_indexes),
                "predicted_spans": len(predicted_indexes),
                "exact_span": _score(len(document_exact), len(gold_indexes), len(predicted_indexes)),
                "overlap": _score(len(document_overlap), len(gold_indexes), len(predicted_indexes)),
            }
        )
    return rows, len(documents) > MAX_PER_DOCUMENT_ROWS


def _manifest_digest(documents: tuple[Document, ...]) -> str:
    serialized = json.dumps(
        [
            {
                "document_id": document.document_id,
                "character_count": document.character_count,
                "document_sha256": document.document_sha256,
            }
            for document in sorted(documents, key=lambda item: item.document_id)
        ],
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def evaluate_clinical_nlp(gold_content: bytes, prediction_content: bytes) -> dict[str, Any]:
    """Evaluate normalized clinical entity spans without manufacturing a corpus or claim."""
    gold_artifact = _parse_json(gold_content, "gold")
    prediction_artifact = _parse_json(prediction_content, "prediction")
    _verify_matching_manifests(gold_artifact, prediction_artifact)

    def order(span: EntitySpan) -> tuple[Any, ...]:
        return (
            span.document_id,
            span.start,
            span.end,
            span.label,
            span.assertion,
            span.negation,
            span.temporality,
            span.code_system or "",
            span.concept_id or "",
        )
    # Canonical ordering makes ambiguous one-to-one overlap pairings stable
    # across semantically identical JSON files with different array order.
    gold = sorted(gold_artifact.spans, key=order)
    predictions = sorted(prediction_artifact.spans, key=order)
    exact = _exact_matches(gold, predictions)
    overlap = _overlap_matches(gold, predictions)
    label_confusion, geometry_matches = _label_confusion(gold, predictions)
    exact_score = _score(len(exact), len(gold), len(predictions))
    overlap_score = _score(len(overlap), len(gold), len(predictions))
    documents, documents_truncated = _per_document(
        gold_artifact.documents, gold, predictions, exact, overlap
    )
    exact_context = _context_block(gold, predictions, exact)
    overlap_context = _context_block(gold, predictions, overlap)
    exact_concepts = _concept_link_summary(gold, predictions, exact)
    overlap_concepts = _concept_link_summary(gold, predictions, overlap)
    boundary_mismatches = sum(
        1
        for left, right in overlap
        if (gold[left].start, gold[left].end) != (predictions[right].start, predictions[right].end)
    )
    label_mismatches = sum(1 for left, right in geometry_matches if gold[left].label != predictions[right].label)

    return {
        "task_type": "clinical_nlp",
        "n": len(gold_artifact.documents),
        "n_groups": len(gold_artifact.documents),
        "gold_span_count": len(gold),
        "predicted_span_count": len(predictions),
        "metrics": {
            "exact_span_precision": exact_score["precision"],
            "exact_span_recall": exact_score["recall"],
            "exact_span_f1": exact_score["f1"],
            "overlap_precision": overlap_score["precision"],
            "overlap_recall": overlap_score["recall"],
            "overlap_f1": overlap_score["f1"],
            "exact_concept_link_accuracy": exact_concepts["accuracy"],
            "overlap_concept_link_accuracy": overlap_concepts["accuracy"],
        },
        "exact_span": exact_score,
        "overlap": overlap_score,
        "matching_protocol": {
            "exact_span": "Same document_id, normalized label, start and exclusive end; context fields are evaluated separately.",
            "overlap": "Intersecting ranges receive a deterministic maximum-cardinality one-to-one match within document_id and normalized label; context and concept fields are evaluated separately.",
            "offset_convention": "Zero-based Unicode code-point offsets with an exclusive end.",
        },
        "per_label": _per_label(gold, predictions, exact, overlap),
        "label_confusion": label_confusion,
        "context_confusion": {"exact_span": exact_context, "overlap": overlap_context},
        "concept_linking": {"exact_span": exact_concepts, "overlap": overlap_concepts},
        "error_counts": {
            "exact_missing": exact_score["fn"],
            "exact_spurious": exact_score["fp"],
            "overlap_missing": overlap_score["fn"],
            "overlap_spurious": overlap_score["fp"],
            "boundary_mismatches_on_label_matched_overlaps": boundary_mismatches,
            "label_mismatches_on_geometric_overlaps": label_mismatches,
            "exact_context_errors": {field: exact_context[field]["errors"] for field in _CONTEXT_FIELDS},
            "overlap_context_errors": {field: overlap_context[field]["errors"] for field in _CONTEXT_FIELDS},
            "exact_concept_link_errors": exact_concepts["errors"],
            "overlap_concept_link_errors": overlap_concepts["errors"],
        },
        "documents": documents,
        "documents_truncated": documents_truncated,
        "provenance": {
            "schema_version": SCHEMA_VERSION,
            "document_manifest_sha256": _manifest_digest(gold_artifact.documents),
            "document_count": len(gold_artifact.documents),
            "gold_span_count": len(gold),
            "predicted_span_count": len(predictions),
            "gold_artifact_role": gold_artifact.role,
            "prediction_artifact_role": prediction_artifact.role,
            "document_manifests_identical": True,
        },
        "assumptions": [
            "Gold labels were independently annotated and lawfully supplied by the uploader; MedTwin does not verify adjudication quality.",
            "Offsets refer to the same immutable, de-identified document text represented by the matching document manifest.",
            "Metrics describe only the supplied artifacts and are not clinical-validation evidence without a valid held-out evaluation context.",
        ],
    }
