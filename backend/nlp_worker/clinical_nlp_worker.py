"""medSpaCy context and MedCAT concept linking, run inside the WSL clinical NLP environment (venv-clinical).

Reads {"text": str, "spans": [{"id", "start", "end"}], "medcat_model_pack": str | null} as JSON on stdin and
writes {"tools": {...}, "context": [...], "medcat": {...}} to stdout. It performs no network access (MedCAT's
update check is switched off) and keeps nothing except MedCAT's unpacked copy of the model pack.

- medSpaCy: PyRuSH sentences, then ConText and the sectionizer on exactly the spans the caller found, so its
  negation, uncertainty, history and family assessments can be compared with the caller's own.
- MedCAT: concepts linked by the given model pack, with the pack's own description of its vocabulary.
Kept free of MedTwin imports: this environment has medSpaCy and MedCAT, not the backend stack.
"""

import json
import os
import shutil
import sys
from pathlib import Path

os.environ["MEDCAT_DISABLE_VERSION_CHECK"] = "true"
PACK_CACHE = Path.home() / ".medtwin" / "medcat-packs"
CONTEXT_FLAGS = ("is_negated", "is_uncertain", "is_historical", "is_hypothetical", "is_family")


def layers(spans):
    """Groups (id, token_start, token_end) spans so no two in a layer share a token: a spaCy Doc cannot hold
    overlapping entities, and two character spans can expand to the same token (OCR-glued words)."""
    out = []
    for span in sorted(spans, key=lambda item: (item[1], -item[2])):
        for layer in out:
            if all(span[2] <= other[1] or span[1] >= other[2] for other in layer):
                layer.append(span)
                break
        else:
            out.append([span])
    return out


def medspacy_context(text, spans):
    import medspacy
    from spacy.tokens import Span

    nlp = medspacy.load(medspacy_enable=["medspacy_pyrush", "medspacy_context", "medspacy_sectionizer"])
    base = nlp.get_pipe("medspacy_pyrush")(nlp.make_doc(text))
    token_spans = []
    for span in spans:
        entity = base.char_span(span["start"], span["end"], label="TARGET", alignment_mode="expand")
        if entity is not None and len(entity):
            token_spans.append((span["id"], entity.start, entity.end))
    results = []
    for layer in layers(token_spans):
        doc = nlp.get_pipe("medspacy_pyrush")(nlp.make_doc(text))  # tokenisation is deterministic: same token indices
        doc.ents = [Span(doc, start, end, label="TARGET") for _, start, end in layer]
        for name in ("medspacy_context", "medspacy_sectionizer"):
            doc = nlp.get_pipe(name)(doc)
        by_tokens = {(ent.start, ent.end): ent for ent in doc.ents}
        for span_id, start, end in layer:
            ent = by_tokens[(start, end)]
            modifiers = [{"category": modifier.category, "text": doc[modifier.modifier_span[0]:modifier.modifier_span[1]].text}
                         for modifier in ent._.modifiers]
            results.append({"id": span_id, **{flag: bool(getattr(ent._, flag)) for flag in CONTEXT_FLAGS},
                            "section": ent._.section_category, "modifiers": modifiers})
    return results, {"name": "medspacy", "version": medspacy.__version__, "pipes": nlp.pipe_names}


def medcat_entities(text, pack):
    import medcat
    from medcat.cat import CAT

    source = Path(pack)
    PACK_CACHE.mkdir(parents=True, exist_ok=True)
    local = PACK_CACHE / source.name
    if not local.exists() or local.stat().st_size != source.stat().st_size:
        shutil.copyfile(source, local)  # MedCAT unpacks next to the zip; keep that out of the project tree
    cat = CAT.load_model_pack(str(local))
    card = cat.get_model_card(as_dict=True)
    stats = card.get("Basic CDB Stats", {})
    entities = []
    for entity in cat.get_entities(text)["entities"].values():
        entities.append({"cui": str(entity.get("cui")), "name": entity.get("pretty_name"), "start": int(entity["start"]),
                         "end": int(entity["end"]), "text": entity.get("source_value"),
                         "similarity": entity.get("context_similarity", entity.get("acc")), "types": entity.get("type_ids", [])})
    pack_info = {"file": source.name, "model_id": card.get("Model ID"), "source_ontology": card.get("Source Ontology"),
                 "concepts": stats.get("Number of concepts"), "names": stats.get("Number of names"),
                 "concepts_trained": stats.get("Number of concepts that received training"), "medcat_version": card.get("MedCAT Version")}
    return entities, pack_info, {"name": "medcat", "version": medcat.__version__}


def main() -> int:
    # PyRuSH logs every token at DEBUG through loguru; report text must not reach any log.
    from loguru import logger

    logger.remove()
    logger.add(sys.stderr, level="ERROR")
    request = json.load(sys.stdin)
    text = request["text"]
    tools = {}
    context, context_tool = medspacy_context(text, request.get("spans", []))
    tools["medspacy"] = context_tool
    medcat_result = None
    if request.get("medcat_model_pack"):
        entities, pack_info, medcat_tool = medcat_entities(text, request["medcat_model_pack"])
        tools["medcat"] = medcat_tool
        medcat_result = {"pack": pack_info, "entities": entities}
    json.dump({"tools": tools, "context": context, "medcat": medcat_result}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
