"""Whole-body source-backed navigation, explicit ancestry and live capability gates."""
from __future__ import annotations
from collections import Counter, defaultdict
from functools import lru_cache
import hashlib
import json
from pathlib import Path

from app.config import PROJECT_ROOT
from app.schemas.universal_structures import StructureNode
from app.services import universal_catalogue as catalogue, icd11_source_adapter

PUBLIC = PROJECT_ROOT / "public"
ATLAS = PUBLIC / "anatomy" / "atlas-index.json"
MANIFEST = PUBLIC / "anatomy" / "manifest.json"
FALLBACK = Path(catalogue.DATA_DIR) / "atlas_structures.json"
NOTICE = "Reference/source hierarchy only. Application system membership is navigation context, not a clinical crosswalk or an anatomical parent. Labels, assets, model targets and patient source associations are distinct; no diagnosis or patient registration is inferred."


def _read(path): return json.loads(path.read_text(encoding="utf-8-sig"))


def _stamp(path):
    try: s = path.stat(); return (str(path), s.st_size, s.st_mtime_ns)
    except OSError: return (str(path), 0, 0)


def _node(identifier, label, kind, source_id, source, systems=(), parent=None, relation="NONE", **kwargs):
    return StructureNode(id=identifier, label=label, kind=kind, source_id=source_id, source=source, system_ids=list(systems),
                         parent_id=parent, parent_relation=relation, review_state=kwargs.pop("review_state", "SOURCE_RETAINED_UNREVIEWED"), **kwargs).model_dump()


@lru_cache(maxsize=3)
def _build(atlas_stamp, manifest_stamp, fallback_stamp, catalogue_version, registry_hash):
    base = catalogue.bundle(); nodes, assets = {}, {}
    models = {m["model_id"]: m for m in catalogue._registry_models()}
    families = {s["id"]: s for s in base["systems"]}
    mapped = defaultdict(set)
    for entry in base["entries"]:
        for target in entry["model_targets"]:
            if target["model_id"] in models and catalogue._target_matches(models[target["model_id"]], target["target"]):
                mapped[target["model_id"]].update(entry["system_ids"])
    for system in base["systems"]:
        row = _node("system:" + system["id"], system["label"], "system", system["id"], "Existing Universal25-family specification", [system["id"]], synonyms=system["synonyms"])
        nodes[row["id"]] = row
    for entry in base["entries"]:
        if entry["kind"] != "organ": continue
        mids = [t["model_id"] for t in entry["model_targets"] if t["model_id"] in models and catalogue._target_matches(models[t["model_id"]], t["target"])]
        row = _node(entry["id"], entry["label"], "organ", entry["id"], entry["source"], entry["system_ids"],
                    parent="system:" + entry["system_ids"][0], relation="APPLICATION_SYSTEM_CONTEXT", model_ids=list(dict.fromkeys(mids)), synonyms=entry["synonyms"])
        nodes[row["id"]] = row
    atlas_available = atlas_stamp[1] > 0
    atlas = _read(ATLAS if atlas_available else FALLBACK) if (atlas_available or fallback_stamp[1]) else {"structures": []}
    chunks = atlas.get("chunks", [])
    for chunk in chunks:
        assets["chunk:" + chunk["id"]] = {"id": "chunk:" + chunk["id"], "label": chunk["id"], "tiers": {t: chunk[t] for t in ("economy", "standard") if t in chunk},
            "licence": {"id": "SOURCE_INDEX_MIXED_DECLARATIONS_REVIEW_REQUIRED", "commercial_use": None},
            "source_licence_declarations": [{"source_id": a["id"], "licence": a.get("license", {})} for a in atlas.get("assets", [])],
            "source": "Existing attributed atlas-index.json; per-chunk commercial rights are not independently established by global source declarations", "review_state": "SOURCE_REFERENCE_NOT_PATIENT_ANATOMY"}
    for item in atlas.get("structures", []):
        asset_ids = ["chunk:" + c["id"] for c in chunks if c["system"] == item["system"] and any(c["mesh_start"] <= mesh < c["mesh_start"] + c["mesh_count"] for mesh in item.get("meshes", []))]
        row = _node("atlas:" + item["id"], item["name"], "atlas_structure", item["id"], "Existing attributed atlas index; /anatomy/derived/atlas/ATTRIBUTION.md",
                    catalogue._atlas_system(item["system"], item["name"]), parent="atlas:" + item["parent"] if item.get("parent") else None,
                    relation="SOURCE_EXPLICIT_PARENT" if item.get("parent") else "NONE", laterality=item.get("side"), laterality_source="atlas.side" if item.get("side") else None,
                    asset_ids=asset_ids, synonyms=[item["name_la"]] if item.get("name_la") else [])
        nodes[row["id"]] = row
    manifest = _read(MANIFEST) if manifest_stamp[1] else {"variants": {}}
    for aid, variant in manifest.get("variants", {}).items():
        systems = [s["id"] for s in base["systems"] if s.get("atlas_system") == variant["system_id"]]
        assets["asset:" + aid] = {"id": "asset:" + aid, "label": variant["label"], "tiers": variant.get("tiers", {}), "licence": variant.get("license", {}),
                                 "source": variant.get("source", {}), "declared_available": variant.get("available", False), "review_state": "EXISTING_MANIFEST_REFERENCE"}
        row = _node("asset:" + aid, variant["label"], "asset", aid, "Existing anatomy manifest", systems, asset_ids=["asset:" + aid])
        nodes[row["id"]] = row
        for component in variant.get("structures", []):
            # Retain only explicit named source components; proposed/inferred
            # labels are not promoted into a new anatomical hierarchy.
            if component.get("label_source") != "SOURCE_NAME": continue
            row = _node(f"asset-structure:{aid}:{component['id']}", component["label"], "asset_structure", component["source_key"], "Existing manifest SOURCE_NAME component",
                        systems, parent="asset:" + aid, relation="SOURCE_ASSET_COMPONENT", asset_ids=["asset:" + aid], review_state=component.get("review_status", "UNREVIEWED"))
            nodes[row["id"]] = row
    for mid, model in models.items():
        if "segmentation" not in model.get("task", "") or not model.get("supported_classes"): continue
        row = _node("model:" + mid, model.get("display_name", mid), "model_task", mid, "Existing model registry task; not an anatomical parent", sorted(mapped[mid]), model_ids=[mid])
        nodes[row["id"]] = row
        for label in model["supported_classes"]:
            identifier = "model-label:" + mid + ":" + hashlib.sha256(str(label).encode()).hexdigest()[:16]
            row = _node(identifier, str(label), "segmentation_label", str(label), "Verbatim registered output label; not an atlas/clinical mapping", sorted(mapped[mid]),
                        parent="model:" + mid, relation="REGISTERED_TASK_CLASS", model_ids=[mid], capability_state="CATALOGUE_ONLY")
            nodes[row["id"]] = row
    children = defaultdict(list)
    for node in nodes.values():
        if node["parent_id"]:
            if node["parent_id"] not in nodes: raise ValueError("Unknown source hierarchy parent")
            children[node["parent_id"]].append(node["id"])
    for node in nodes.values(): node["child_count"] = len(children[node["id"]])
    finished = set()
    for start in nodes:
        seen, current = set(), start
        while current and current not in finished:
            if current in seen: raise ValueError("Source hierarchy parent cycle")
            seen.add(current); current = nodes[current]["parent_id"]
        finished.update(seen)
    return {"nodes": nodes, "children": dict(children), "assets": assets, "families": families,
            "sources": {"atlas_geometry_index_available": atlas_available, "atlas_terms_available": bool(atlas.get("structures")), "manifest_available": bool(manifest_stamp[1]),
                        "atlas_sha256": hashlib.sha256((ATLAS if atlas_available else FALLBACK).read_bytes()).hexdigest() if atlas.get("structures") else None,
                        "notice": "Missing local geometry stays unavailable; fallback terminology does not establish a mesh."}}


def registry():
    base = catalogue.bundle()
    models_hash = hashlib.sha256(json.dumps(catalogue._registry_models(), sort_keys=True).encode()).hexdigest()
    return _build(_stamp(ATLAS), _stamp(MANIFEST), _stamp(FALLBACK), hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest(), models_hash)


def systems():
    data = registry(); counts = Counter(s for n in data["nodes"].values() if n["kind"] != "system" for s in n["system_ids"])
    return {"schema_version": "medtwin.structure-hierarchy.v1", "systems": [{**s, "structure_count": counts[s["id"]]} for s in data["families"].values()],
            "sources": data["sources"], "node_count": len(data["nodes"]), "icd11": icd11_source_adapter.status(), "notice": NOTICE}


def browse(system=None, parent_id=None, q="", limit=50, offset=0):
    if not 1 <= limit <= 200 or not 0 <= offset <= 100000 or len(q) > 200: raise ValueError("Bounded hierarchy query required")
    data = registry(); nodes = data["nodes"]
    if system and system not in data["families"]: raise ValueError("Unknown system")
    if parent_id and parent_id not in nodes: raise KeyError("Unknown parent")
    if q:
        tokens = catalogue.normalized(q).split()
        rows = [n for n in nodes.values() if (not system or system in n["system_ids"]) and all(t in catalogue.normalized(" ".join([n["label"], n["source_id"], *n["synonyms"]])) for t in tokens)]
    elif parent_id and not parent_id.startswith("system:"):
        rows = [nodes[k] for k in data["children"].get(parent_id, [])]
    elif system or parent_id:
        sid = system or parent_id.split(":", 1)[1]
        rows = [n for n in nodes.values() if sid in n["system_ids"] and n["kind"] != "system" and
                (not n["parent_id"] or n["parent_id"].startswith("system:") or sid not in nodes[n["parent_id"]]["system_ids"])]
    else: rows = [n for n in nodes.values() if n["kind"] == "system"]
    rows.sort(key=lambda n: (n["kind"], n["label"].casefold(), n["id"]))
    return {"schema_version": "medtwin.structure-hierarchy.v1", "items": rows[offset:offset + limit], "total": len(rows), "limit": limit, "offset": offset,
            "parent_id": parent_id, "navigation_relation": "APPLICATION_SYSTEM_CONTEXT" if system or (parent_id or "").startswith("system:") else "SOURCE_RECORDED_RELATION",
            "sources": data["sources"], "notice": NOTICE}


def asset_status(asset):
    tiers = []
    for name, tier in asset.get("tiers", {}).items():
        url = tier.get("url", "")
        path = (PUBLIC / url.lstrip("/")).resolve()
        allowed_path = url.startswith("/") and path.is_relative_to(PUBLIC.resolve())
        exists = allowed_path and path.is_file()
        present = bool(exists and (not tier.get("bytes") or path.stat().st_size == tier["bytes"]))
        tiers.append({"tier": name, "url": url if allowed_path else None, "available": present, "declared_sha256": tier.get("sha256"),
                      "integrity": "LOCAL_FILE_PRESENT_SIZE_MATCH_HASH_NOT_REVERIFIED" if present else "LOCAL_RESOURCE_UNAVAILABLE_OR_SIZE_MISMATCH"})
    licence = asset.get("licence", {})
    return {**asset, "tiers": tiers, "local_available": any(t["available"] for t in tiers),
            "commercial_use_declared": licence.get("commercial_use") is True, "clinical_or_patient_geometry": False}


def detail(identifier):
    data = registry(); node = data["nodes"].get(identifier)
    if node is None: return None
    base = catalogue.bundle(); scoped = [e for e in base["entries"] if set(e["system_ids"]) & set(node["system_ids"])]
    all_models = {m["model_id"]: m for m in catalogue._registry_models()}
    from app.services.model_inference import research_gate
    from app.services.model_usage_policy import usage_gate
    capabilities = []
    for mid in node["model_ids"]:
        model = all_models[mid]
        try: gate, rights = research_gate(model), usage_gate(model)
        except (OSError, ValueError, KeyError): gate, rights = {"allowed": False, "blockers": ["CAPABILITY_GATE_UNAVAILABLE"]}, {"allowed": False}
        allowed = gate["allowed"] and rights.get("profile") == "commercial" and rights.get("allowed")
        capabilities.append({"model_id": mid, "task": model.get("task"), "state": model.get("status"), "research_gate": gate, "rights": rights,
                             "capability_state": "MODEL_AVAILABLE_RESEARCH_ONLY" if allowed else "MODEL_BLOCKED",
                             "commercial_context_blocker": None if rights.get("profile") == "commercial" else "COMMERCIAL_PROFILE_NOT_ACTIVE",
                             "clinical_activation": False})
    return {"schema_version": "medtwin.structure-hierarchy.v1", "node": node, "assets": [asset_status(data["assets"][a]) for a in node["asset_ids"]],
            "capabilities": capabilities, "supported_evidence_types": sorted({t for e in scoped for t in e["evidence_types"]}),
            "investigations": [{"id": e["id"], "label": e["label"]} for e in scoped if e["kind"] == "investigation"],
            "concepts": [{"id": e["id"], "label": e["label"], "association": "APPLICATION_SYSTEM_CONTEXT_NOT_STRUCTURE_DIAGNOSIS"} for e in scoped if e["kind"] == "condition"][:40],
            "icd11": icd11_source_adapter.status(), "notice": NOTICE}
