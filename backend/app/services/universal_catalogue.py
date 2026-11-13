"""Whole-body discovery with explicit catalogue/model/clinical boundaries.

Curated examples and existing attributed atlas/lab terms are navigable without a
diagnostic model. Only explicit target associations are evaluated as model links.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from difflib import get_close_matches
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from app.schemas.universal_catalogue import CatalogueBundle
from app.services import universal_terminology

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CATALOGUE_PATH = DATA_DIR / "universal_catalogue.json"
SCHEMA_VERSION = "medtwin.universal-catalogue.v1"
NOTICE = ("Catalogue and source evidence support are not diagnostic capability. Conditions without an eligible "
          "target-specific model remain navigable. All model outputs are research-only; no clinical activation is granted.")


def normalized(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).casefold().replace("tumor", "tumour").replace("hemorrhage", "haemorrhage")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def validate_bundle(payload: dict) -> dict:
    return CatalogueBundle.model_validate(payload).model_dump()


@lru_cache(maxsize=4)
def _load(path: str, size: int, modified: int) -> dict:
    return validate_bundle(_json(Path(path)))


def bundle() -> dict:
    stat = CATALOGUE_PATH.stat()
    return deepcopy(_load(str(CATALOGUE_PATH), stat.st_size, stat.st_mtime_ns))


def _atlas_system(name: str, label: str) -> list[str]:
    if name == "nervous": return ["neurological"]
    if name == "muscular" or name == "insertions": return ["musculoskeletal"]
    if name in {"skeletal", "joints"}: return ["skeletal"]
    if name == "lymphoid": return ["immune-lymphatic"]
    if name == "cardiovascular":
        return ["cardiovascular"] if re.search(r"heart|atrium|ventric|myocard|coronary|cardiac", label, re.I) else ["vascular"]
    if name == "visceral":
        for pattern, system in ((r"lung|bronch|trache|pleur", "respiratory"), (r"kidney|ureter|bladder|urethr", "urinary"),
                                (r"liver|bile|gallbladder", "hepatobiliary"), (r"pancrea", "pancreatic"),
                                (r"uter|ovari|vagin|cervix|fallopi", "female-reproductive"), (r"prostat|testi|peni|seminal", "male-reproductive"),
                                (r"thyroid|pituitar|adrenal|parathyroid", "endocrine"), (r"oesoph|esoph|stomach|intestin|colon|rect|duoden|anal", "gastrointestinal"),
                                (r"eye|retin|optic|orbit", "ophthalmic"), (r"ear|nasal|nose|pharyn|laryn|salivar", "ent")):
            if re.search(pattern, label, re.I): return [system]
    return ["systemic"]


def _atlas_entries() -> tuple[list[dict], str]:
    path = DATA_DIR / "atlas_structures.json"
    payload = _json(path)
    result = []
    for row in payload.get("structures", []):
        label = f"{row['name']} ({row['side']})" if row.get("side") else row["name"]
        result.append({"id": f"atlas:{row['id']}", "label": label, "kind": "structure",
                       "system_ids": _atlas_system(row["system"], row["name"]),
                       "synonyms": [row["name"], *([row["name_la"]] if row.get("name_la") else [])],
                       "parent_id": f"atlas:{row['parent']}" if row.get("parent") else None,
                       "laterality": row.get("side"),
                       "code_mappings": [], "evidence_types": ["REFERENCE_ANATOMY", "DOCUMENT"],
                       "anatomy_links": [{"structure_id": row["id"], "relation": "REFERENCE_ATLAS_TERM"}],
                       "model_targets": [], "source": payload.get("source", "Existing attributed atlas index") + "; attribution: /anatomy/derived/atlas/ATTRIBUTION.md",
                       "source_version": payload.get("schema_version", "NOT_RECORDED"), "licence": "CC BY-SA 4.0; existing attributed index",
                       "review_status": "EXISTING_REFERENCE_TERMINOLOGY",
                       "note": "Generic L1 reference term. Curated system association is schematic, not patient localization or disease mapping."})
    return result, hashlib.sha256(path.read_bytes()).hexdigest()


def _biomarker_entries() -> list[dict]:
    from app.services.terminology import ANALYTES, LOINC_MAPPING_STATUS
    mapping = {"heart": "cardiovascular", "lungs": "respiratory", "brain": "neurological", "nervous": "neurological",
               "liver": "hepatobiliary", "kidneys": "urinary", "pancreas": "pancreatic", "intestines": "gastrointestinal", "skeletal": "skeletal"}
    result = []
    for analyte in ANALYTES:
        codes = [{"system": "http://loinc.org", "version": "CURATED_NOT_RELEASE_VERIFIED", "code": code,
                  "relation": "RELATED", "review_status": "CURATED_UNVERIFIED", "source": "Existing MedTwin analyte mapping; " + LOINC_MAPPING_STATUS}
                 for code in sorted(set(analyte.loinc.values()))]
        result.append({"id": f"biomarker:{analyte.name}", "label": analyte.display, "kind": "biomarker",
                       "system_ids": [mapping.get(analyte.system, "systemic")], "synonyms": [analyte.name.replace("_", " ")],
                       "parent_id": None, "code_mappings": codes, "evidence_types": ["LABORATORY", "DOCUMENT"], "anatomy_links": [],
                       "model_targets": [], "source": "backend/app/services/terminology.py", "source_version": "existing-curated-analytes",
                       "licence": "Existing project terminology; no official LOINC release imported", "review_status": "EXISTING_REFERENCE_TERMINOLOGY",
                       "note": "Explicit source measurement only; missing specimen/unit/reference context stays indeterminate."})
    return result


def _registry_models() -> list[dict]:
    from app.services.model_registry import _load_registry
    return _load_registry()["models"]


def _target_matches(model: dict, target: str) -> bool:
    return normalized(target) in {normalized(str(value)) for value in model.get("supported_classes", [])}


def catalogue_data() -> tuple[dict, list[dict], str]:
    base = bundle()
    atlas, atlas_hash = _atlas_entries()
    # Expanded source terms obey the same reference/cycle/code contract as the
    # authored bundle; a corrupt reference source never becomes public metadata.
    entries = validate_bundle({**base, "entries": base["entries"] + atlas + _biomarker_entries()})["entries"]
    terminology = universal_terminology.status()
    encoded = json.dumps({"catalogue": base, "entries": entries, "atlas_hash": atlas_hash,
                          "official_terminology": {k: terminology.get(k) for k in ("available", "data_sha256", "index_sha256")}}, sort_keys=True, separators=(",", ":")).encode()
    return base, entries, hashlib.sha256(encoded).hexdigest()


def _public_entry(row: dict, models: dict[str, dict]) -> dict:
    result = deepcopy(row)
    candidates = [link["model_id"] for link in row["model_targets"] if link["model_id"] in models
                  and _target_matches(models[link["model_id"]], link["target"])]
    result["model_ids"] = list(dict.fromkeys(candidates))
    result["capability_state"] = "EVIDENCE_SUPPORTED" if row["kind"] in {"organ", "structure", "biomarker", "investigation"} else "CATALOGUE_ONLY"
    result["model_link_semantics"] = "Explicit registered target candidates; use /universal/capabilities for current gates. Not a diagnosis or execution permission."
    result["code_mapping_status"] = "SOURCE_MAPPINGS_RETAINED_UNVERIFIED_WHERE_MARKED" if row["code_mappings"] else "NOT_MAPPED"
    return result


def systems() -> dict:
    base, entries, version = catalogue_data()
    count = Counter(system for row in entries if row["kind"] == "condition" for system in row["system_ids"])
    terminology = universal_terminology.status()
    return {"schema_version": SCHEMA_VERSION, "catalogue_version": base["version"], "data_version": version,
            "systems": [{**row, "condition_count": count[row["id"]],
                         "reference_classification_count": terminology.get("system_counts", {}).get(row["id"], 0),
                         "capability_state": "EVIDENCE_SUPPORTED"} for row in base["systems"]],
            "notice": NOTICE, "official_terminology": terminology}


def search(*, q: str = "", system: str | None = None, kind: str | None = None, limit: int = 50, offset: int = 0) -> dict:
    if not 1 <= limit <= 200 or not 0 <= offset <= 100_000 or len(q) > 200:
        raise ValueError("Catalogue query exceeds bounded pagination/search limits")
    if kind and kind not in {"organ", "condition", "structure", "biomarker", "investigation", "classification"}:
        raise ValueError("Unknown catalogue entry kind")
    base, entries, version = catalogue_data()
    known = {row["id"] for row in base["systems"]}
    if system and system not in known: raise ValueError("Unknown anatomical system")
    query = normalized(q)
    tokens = query.split()
    models = {row["model_id"]: row for row in _registry_models()}
    system_labels = {row["id"]: " ".join([row["label"], *row["synonyms"], *row["organs"]]) for row in base["systems"]}
    candidates = [row for row in entries if (not system or system in row["system_ids"]) and (not kind or row["kind"] == kind)]
    def matches(row):
        # System labels participate so model-free specialties can always be discovered.
        haystack = normalized(" ".join([row["label"], *row["synonyms"], *[system_labels[s] for s in row["system_ids"]],
                                        *[code["code"] for code in row["code_mappings"]]]))
        return all(token in haystack for token in tokens)
    results = [row for row in candidates if matches(row)]
    results.sort(key=lambda row: (normalized(row["label"]) != query, row["kind"] == "structure", row["label"].casefold(), row["id"]))
    suggestions = [] if results or not query else get_close_matches(query, sorted({normalized(row["label"]) for row in candidates}), n=5, cutoff=0.68)
    external = universal_terminology.search(q, system, limit=0) if kind in {None, "classification"} else {"total": 0, "items": [], "resource": universal_terminology.status()}
    # Bounded pagination across three explicit source groups avoids loading all
    # 98k reference entries or suggesting a clinical crosswalk between them.
    direct = [row for row in results if row["kind"] != "structure"]
    structures = [row for row in results if row["kind"] == "structure"]
    items, cursor = [], 0
    for name, group_count in (("curated", len(direct)), ("official", external["total"]), ("atlas", len(structures))):
        start = max(0, offset - cursor)
        if start < group_count and len(items) < limit:
            size = min(limit - len(items), group_count - start)
            if name == "official": items.extend(universal_terminology.search(q, system, limit=size, offset=start)["items"])
            else: items.extend(_public_entry(row, models) for row in (direct if name == "curated" else structures)[start:start + size])
        cursor += group_count
    counts = dict(Counter(row["kind"] for row in results))
    if external["total"]: counts["classification"] = external["total"]
    return {"schema_version": SCHEMA_VERSION, "catalogue_version": base["version"], "data_version": version,
            "items": items, "total": len(results) + external["total"], "limit": limit, "offset": offset,
            "suggestions": suggestions if not external["total"] else [], "counts": counts, "notice": NOTICE,
            "official_terminology": external["resource"],
            "ordering": "Curated concepts, then official classification references (exact code first), then detailed atlas structures; stable within each source group.",
            "terminology_scope": "Curated concepts and attributed atlas/labs plus optional official FY2027 ICD-10-CM reference. Not ICD-11, an exhaustive clinical ontology, a clinical crosswalk or diagnostic AI coverage."}


def detail(identifier: str) -> dict | None:
    _, entries, version = catalogue_data()
    row = next((row for row in entries if row["id"] == identifier), None)
    if row is None:
        external = universal_terminology.detail(identifier)
        return {"schema_version": SCHEMA_VERSION, "data_version": version, "item": external, "notice": NOTICE,
                "official_terminology": universal_terminology.status()} if external else None
    return {"schema_version": SCHEMA_VERSION, "data_version": version,
            "item": _public_entry(row, {m["model_id"]: m for m in _registry_models()}), "notice": NOTICE}


def capabilities(system: str | None = None) -> dict:
    from app.services.model_inference import research_gate
    base, entries, version = catalogue_data()
    if system and system not in {s["id"] for s in base["systems"]}: raise ValueError("Unknown anatomical system")
    linked: dict[str, list[dict]] = {}
    models = {m["model_id"]: m for m in _registry_models()}
    for row in entries:
        if system and system not in row["system_ids"]: continue
        for target in row["model_targets"]:
            model = models.get(target["model_id"])
            if model and _target_matches(model, target["target"]):
                linked.setdefault(model["model_id"], []).append({"concept_id": row["id"], "label": row["label"], "target": target["target"]})
    items = []
    for model_id, targets in linked.items():
        model = models[model_id]
        try:
            gate = research_gate(model)
        except (OSError, ValueError, KeyError) as exc:
            gate = {"allowed": False, "blockers": [f"GATE_UNAVAILABLE_{type(exc).__name__}"]}
        inference = model.get("inference_input", "image_2d" if model.get("research_inference") else None)
        upload_supported = inference in {"image_2d", "ecg_12lead", "volume_nifti", "echo_video", "head_ct_series"}
        items.append({"model_id": model_id, "label": model.get("display_name", model_id), "task": model.get("task"),
                      "registry_state": model.get("status"), "capability_state": "MODEL_AVAILABLE_RESEARCH_ONLY" if gate["allowed"] and upload_supported else "MODEL_BLOCKED",
                      "research_gate": gate, "upload_supported": upload_supported, "inference_input": inference,
                      "supported_modalities": model.get("supported_modalities", []), "targets": targets,
                      "checkpoint_sha256": model.get("artifact_bundle", {}).get("checkpoint_sha256"),
                      "preprocessing_version": model.get("artifact_bundle", {}).get("preprocessing_version"),
                      "evaluation_artifact": model.get("artifact_bundle", {}).get("evaluation_report_path"),
                      "clinical_activation": "CLINICAL_ACTIVATION_NOT_CLEARED", "limitations": model.get("limitations", [])})
    return {"schema_version": "medtwin.universal-capabilities.v1", "data_version": version, "system": system,
            "items": items, "model_count": len(items), "clinical_activation_count": 0, "notice": NOTICE,
            "comparison_semantics": "Organ/condition associations are explicit target links, not interchangeability or clinical diagnostic coverage."}
