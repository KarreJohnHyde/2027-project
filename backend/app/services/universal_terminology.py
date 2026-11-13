"""Optional read-only official ICD-10-CM index; never a diagnostic crosswalk.

An absent deployment mount is explicit. All original curated concepts keep their
own mapping review state. Official code/label identity is exact; application
chapter/system links are broad navigational context only.
"""
from __future__ import annotations
from functools import lru_cache
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import unicodedata

from app.config import PROJECT_ROOT

DEFAULT_PATH = PROJECT_ROOT / "data" / "external" / "icd10cm-fy2027" / "catalogue.sqlite3"
DB_PATH = Path(os.getenv("MEDTWIN_TERMINOLOGY_DB", str(DEFAULT_PATH)))
SCHEMA = "medtwin.official-terminology.v1"
SOURCE_URL = "https://www.cdc.gov/nchs/icd/icd-10-cm/files.html"
NOTICE = ("Source: CDC/NCHS FY2027 ICD-10-CM, available at no charge from CDC. No CDC/HHS/US Government endorsement is implied. "
          "Official descriptions/codes are unchanged. ICD-10-CM is not ICD-11; application system links are broad reference context, "
          "not exact anatomy, diagnosis, a mapping of the original curated conditions, model eligibility or billing advice.")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).casefold().replace("tumor", "tumour").replace("hemorrhage", "haemorrhage")
    return re.sub("[^a-z0-9]+", " ", text).strip()


def connect(path: Path | None = None):
    path = (path or DB_PATH).resolve()
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)
    connection.row_factory = sqlite3.Row
    return connection


@lru_cache(maxsize=4)
def _metadata(path: str, size: int, mtime: int) -> dict:
    with closing(connect(Path(path))) as db:
        value = json.loads(db.execute("SELECT value FROM metadata WHERE key='manifest'").fetchone()[0])
        if value.get("schema_version") != SCHEMA: raise ValueError("Unknown terminology index schema")
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok": raise ValueError("Terminology index integrity check failed")
        if db.execute("SELECT COUNT(*) FROM terms").fetchone()[0] != value.get("entry_count"):
            raise ValueError("Terminology index entry count mismatch")
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""): digest.update(block)
    value = {**value, "index_sha256": digest.hexdigest()}
    return value


def status() -> dict:
    try:
        stat = DB_PATH.stat()
        metadata = _metadata(str(DB_PATH), stat.st_size, stat.st_mtime_ns)
        return {"available": True, "state": "OFFICIAL_REFERENCE_INDEX_AVAILABLE", **metadata, "notice": NOTICE}
    except (OSError, ValueError, sqlite3.Error, TypeError, AttributeError, IndexError, KeyError):
        return {"available": False, "state": "OFFICIAL_REFERENCE_INDEX_UNAVAILABLE", "schema_version": SCHEMA,
                "entry_count": 0, "system_counts": {}, "data_sha256": None,
                "reason": "Configured read-only terminology index is absent, unreadable, invalid or not mounted. Core curated catalogue remains available.",
                "setup": "Build with scripts/build_official_terminology.py; mount the generated index read-only and set MEDTWIN_TERMINOLOGY_DB.", "notice": NOTICE}


def _where(q: str, system: str | None) -> tuple[str, list[str]]:
    clauses, parameters = [], []
    for token in normalize(q).split():
        clauses.append("search_text LIKE ?")
        parameters.append("%" + token + "%")
    if system:
        clauses.append("EXISTS(SELECT 1 FROM term_systems s WHERE s.term_id=terms.id AND s.system_id=?)")
        parameters.append(system)
    return " AND ".join(clauses) or "1=1", parameters


def search(q: str, system: str | None, *, limit: int, offset: int = 0) -> dict:
    if not 0 <= limit <= 200 or not 0 <= offset <= 100_000: raise ValueError("Terminology query exceeds bounds")
    resource = status()
    if not resource["available"]: return {"total": 0, "items": [], "resource": resource}
    clause, parameters = _where(q, system)
    with closing(connect()) as db:
        total = db.execute("SELECT COUNT(*) FROM terms WHERE " + clause, parameters).fetchone()[0]
        rows = db.execute("SELECT * FROM terms WHERE " + clause + " ORDER BY CASE WHEN code=? COLLATE NOCASE THEN 0 WHEN label_normalized=? THEN 1 ELSE 2 END,label COLLATE NOCASE,id LIMIT ? OFFSET ?",
                          [*parameters, normalize(q).replace(" ", "").upper(), normalize(q), limit, offset]).fetchall()
    return {"total": total, "items": [public_entry(dict(row)) for row in rows], "resource": resource}


def detail(identifier: str) -> dict | None:
    if not identifier.startswith("icd10cm:fy2027:") or not status()["available"]: return None
    with closing(connect()) as db:
        row = db.execute("SELECT * FROM terms WHERE id=?", (identifier,)).fetchone()
    return public_entry(dict(row)) if row else None


def public_entry(row: dict) -> dict:
    code = row["code"]
    dotted = code[:3] + "." + code[3:] if len(code) > 3 else code
    return {"id": row["id"], "label": row["label"], "kind": "classification", "system_ids": json.loads(row["systems"]),
            "synonyms": list(dict.fromkeys([row["short_label"], code, dotted])),
            "parent_id": row["parent_id"], "laterality": None,
            "code_mappings": [{"system": "ICD-10-CM", "version": "FY2027", "code": code, "relation": "EXACT",
                               "review_status": "VERIFIED_SOURCE_MAPPING", "source": SOURCE_URL}],
            "evidence_types": ["CLINICIAN_REPORT", "DOCUMENT"], "anatomy_links": [], "model_targets": [],
            "source": "CDC/NCHS official FY2027 code-description order file and tabular XML; " + SOURCE_URL,
            "source_version": "FY2027 (2026-10-01 to 2027-09-30)",
            "licence": "Public-domain ICD-10-CM reference; CDC attribution and no-endorsement notice retained",
            "review_status": "EXISTING_REFERENCE_TERMINOLOGY", "note": NOTICE,
            "classification": {"system": "ICD-10-CM", "version": "FY2027", "code": code,
                               "valid_for_reporting_in_source": bool(row["valid_code"]),
                               "chapter": row["chapter"], "chapter_label": row["chapter_label"],
                               "system_link_semantics": "BROAD_CHAPTER_OR_CODE_RANGE_CONTEXT_ONLY",
                               "curated_condition_crosswalk": False},
            "capability_state": "CATALOGUE_ONLY", "model_ids": [],
            "model_link_semantics": "No model link is inferred from a code, code range, chapter, term similarity or anatomical family.",
            "code_mapping_status": "VERIFIED_SOURCE_SELF_CODE_NOT_CLINICAL_CROSSWALK"}
