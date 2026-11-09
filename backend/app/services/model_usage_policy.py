"""Separate research execution from deployment-controlled commercial rights review.

A record is evidence of an operator's review, not a legal opinion or clinical
approval. New checkpoints invalidate old reviews. Unknown states fail closed.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from app.config import PROJECT_ROOT, ENVIRONMENT


def usage_gate(model):
    profile = os.getenv("MEDTWIN_USAGE_PROFILE", "commercial" if ENVIRONMENT == "production" else "research").strip().lower()
    result = {"profile": profile, "allowed": False, "blockers": []}
    if profile == "research":
        return {**result, "allowed": True, "notice": "Research profile; source-specific restrictions still apply. No clinical approval implied."}
    if profile != "commercial":
        return {**result, "blockers": ["USAGE_PROFILE_INVALID"]}
    configured = os.getenv("MEDTWIN_COMMERCIAL_REVIEW_PATH", "").strip()
    from app.services.model_registry import REGISTRY_PATH
    path = Path(configured) if configured else REGISTRY_PATH.parent / "commercial_review.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = payload["models"]
        if payload.get("schema_version") != 1 or not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
            raise ValueError("Invalid review schema")
        matching = [item for item in records if item.get("model_id") == model["model_id"]]
        if len(matching) != 1:
            raise ValueError("Missing or duplicate model review")
        review = matching[0]
    except (OSError, ValueError, KeyError, TypeError):
        return {**result, "blockers": ["COMMERCIAL_REVIEW_UNAVAILABLE"]}
    if review.get("checkpoint_sha256") != model.get("artifact_bundle", {}).get("checkpoint_sha256") or not review.get("checkpoint_sha256"):
        result["blockers"].append("COMMERCIAL_REVIEW_CHECKPOINT_MISMATCH")
    for field in ("source_data_rights", "code_rights", "weights_rights", "redistribution_rights"):
        if review.get(field) != "REVIEWED_FOR_DECLARED_COMMERCIAL_USE":
            result["blockers"].append(f"COMMERCIAL_{field.upper()}_NOT_REVIEWED")
    if not review.get("reviewer") or not review.get("reviewed_at") or not review.get("declared_use"):
        result["blockers"].append("COMMERCIAL_REVIEW_IDENTITY_OR_SCOPE_MISSING")
    evidence = review.get("evidence_files")
    if not isinstance(evidence, list) or not evidence:
        result["blockers"].append("COMMERCIAL_RIGHTS_EVIDENCE_MISSING")
    else:
        for record in evidence:
            try:
                source = Path(record["path"])
                source = source if source.is_absolute() else PROJECT_ROOT / source
                if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != record["sha256"]:
                    result["blockers"].append("COMMERCIAL_RIGHTS_EVIDENCE_HASH_MISMATCH")
            except (OSError, KeyError, TypeError):
                result["blockers"].append("COMMERCIAL_RIGHTS_EVIDENCE_INVALID")
    return {**result, "allowed": not result["blockers"], "notice": "Commercial rights record only; clinical validation and regulatory authorization are separate."}


def registered_model_usage_gate(model_id):
    from app.services.model_registry import _load_registry
    model = next((entry for entry in _load_registry()["models"] if entry["model_id"] == model_id), None)
    return usage_gate(model) if model else {"allowed": False, "blockers": ["MODEL_NOT_REGISTERED"]}
