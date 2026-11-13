"""Build a deterministic read-only local index from reviewed official FY2027 files.

Preserves official codes/labels unchanged and keeps original MedTwin conditions
unmapped. No user/case/application DB, model registry or checkpoint is touched.
"""
from __future__ import annotations
import argparse
from collections import Counter
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
from zipfile import ZipFile
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.services.universal_terminology import SCHEMA, NOTICE, normalize

EXPECTED = {
    "codes": "93e3ad6004badf470c55bfe679b748ae88fd9b2b421851e409eec382c7713b9a",
    "tabular": "99b5c2be16ff53eab861cc0be4b1dacba27f687b8ff4bc700679944355037ee0",
}
PREFIX = "https://ftp.cdc.gov/pub/health_statistics/nchs/publications/ICD10CM/2027/"


def broad_systems(code: str, chapter: str) -> list[str]:
    # These are application navigation groups, NEVER official clinical
    # crosswalks or a semantic mapping from the pre-existing 169 examples.
    c = code.replace(".", "")[:3]
    if c in {"K85", "K86"}: return ["pancreatic"]
    if "K70" <= c <= "K87": return ["hepatobiliary"]
    if "K00" <= c <= "K14": return ["oral-dental"]
    if "N60" <= c <= "N65" or c in {"C50", "D05", "D24"}: return ["breast"]
    if "N40" <= c <= "N53": return ["male-reproductive"]
    if "N70" <= c <= "N98": return ["female-reproductive"]
    if "N00" <= c <= "N39": return ["urinary"]
    if "I60" <= c <= "I69": return ["neurological", "vascular"]
    if "I70" <= c <= "I99": return ["vascular"]
    if "D80" <= c <= "D89": return ["immune-lymphatic"]
    if "E70" <= c <= "E90": return ["genetic-metabolic", "endocrine"]
    return {"1": ["infectious"], "2": ["systemic"], "3": ["haematological"], "4": ["endocrine"],
            "5": ["mental-behavioural"], "6": ["neurological"], "7": ["ophthalmic"], "8": ["ent"],
            "9": ["cardiovascular"], "10": ["respiratory"], "11": ["gastrointestinal"], "12": ["dermatological"],
            "13": ["skeletal", "musculoskeletal"], "14": ["urinary"], "15": ["maternal-fetal"],
            "16": ["maternal-fetal"], "17": ["genetic-metabolic"], "22": ["infectious"]}.get(chapter, ["systemic"])


def parse_release(codes_path: Path, tabular_path: Path) -> list[dict]:
    with ZipFile(tabular_path) as archive:
        name = next(n for n in archive.namelist() if "tabular" in n and n.endswith("2027.xml"))
        if archive.getinfo(name).file_size > 100_000_000: raise ValueError("Tabular XML exceeds reviewed bound")
        xml = archive.read(name)
        if b"<!ENTITY" in xml.upper(): raise ValueError("Custom XML entities are not permitted")
        # The standard parser does not resolve external resources. Source ZIP
        # hashes are pinned before this parser is called by the build command.
        tree = ElementTree.fromstring(xml)
    taxonomy = {}
    def visit(node, chapter, chapter_label, parent=None):
        code = node.findtext("name")
        if not code: raise ValueError("Tabular diagnosis has no source code")
        key = code.replace(".", "")
        if key in taxonomy: raise ValueError("Duplicate official tabular code")
        taxonomy[key] = {"code": code, "chapter": chapter, "chapter_label": chapter_label, "parent_code": parent}
        for child in node.findall("diag"): visit(child, chapter, chapter_label, key)
    for chapter in tree.findall("chapter"):
        for node in chapter.findall("section/diag"):
            visit(node, chapter.findtext("name"), chapter.findtext("desc"))
    rows = []
    with ZipFile(codes_path) as archive:
        name = next(n for n in archive.namelist() if n.endswith("icd10cm-order-2027.txt"))
        if archive.getinfo(name).file_size > 50_000_000: raise ValueError("Order file exceeds reviewed bound")
        text = archive.read(name).decode("utf-8-sig")
    seen = set()
    for line in text.splitlines():
        key, valid = line[6:13].strip(), line[14:15]
        if key in seen or not re.fullmatch("[A-Z][0-9A-Z]{2,6}", key) or valid not in {"0", "1"}:
            raise ValueError("Invalid/duplicate official order-file row")
        # The official order file explicitly enumerates seventh-character
        # variants that tabular XML represents via extension instructions.
        # Use that exact supplied code, attaching only its longest existing
        # tabular ancestor for chapter/context; never generate missing codes.
        ancestor = key if key in taxonomy else next((key[:n] for n in range(len(key) - 1, 2, -1) if key[:n] in taxonomy), None)
        if ancestor is None: raise ValueError("Order-file code has no official tabular ancestor")
        seen.add(key)
        meta = taxonomy[ancestor]
        parent = meta["parent_code"] if ancestor == key else ancestor
        rows.append({"id": "icd10cm:fy2027:" + key.lower(), "code": key, "label": line[77:].strip(),
                     "short_label": line[16:76].strip(), "valid_code": int(valid),
                     "parent_id": "icd10cm:fy2027:" + parent.lower() if parent else None,
                     "chapter": meta["chapter"], "chapter_label": meta["chapter_label"],
                     "systems": broad_systems(meta["code"], meta["chapter"])})
    if any(row["parent_id"] and row["parent_id"].rsplit(":", 1)[1].upper() not in seen for row in rows):
        raise ValueError("Official hierarchy has missing order-file parents")
    return rows


def build(codes_path: Path, tabular_path: Path, output: Path) -> dict:
    hashes = {"codes": hashlib.sha256(codes_path.read_bytes()).hexdigest(), "tabular": hashlib.sha256(tabular_path.read_bytes()).hexdigest()}
    if hashes != EXPECTED: raise ValueError("Input release does not match the reviewed official FY2027 source SHA-256; refusing import")
    rows = parse_release(codes_path, tabular_path)
    data_sha = hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    manifest = {"schema_version": SCHEMA, "terminology": "ICD-10-CM", "version": "FY2027",
                "entry_count": len(rows), "valid_code_count": sum(row["valid_code"] for row in rows),
                "header_count": sum(not row["valid_code"] for row in rows), "data_sha256": data_sha,
                "chapter_count": len({row["chapter"] for row in rows}),
                "system_counts": dict(Counter(s for row in rows for s in row["systems"])),
                "effective_start": "2026-10-01", "effective_end": "2027-09-30",
                "commercial_reuse_basis": "Official ICD-10-CM public-domain code set; CDC attribution, unchanged descriptions, no endorsement, source available free",
                "rights_evidence": ["https://stacks.cdc.gov/view/cdc/27312/cdc_27312_DS1.pdf", "https://www.cdc.gov/other/agencymaterials.html"],
                "sources": [{"url": PREFIX + filename, "sha256": hashes[key]} for key, filename in
                            [("codes", "icd10cm-code-descriptions-2027.zip"), ("tabular", "icd10cm-table-and-index-2027.zip")]],
                "system_link_semantics": "BROAD_CHAPTER_OR_CODE_RANGE_CONTEXT_ONLY", "curated_condition_crosswalk": False, "notice": NOTICE}
    if output.exists():
        from app.services.universal_terminology import connect
        with closing(connect(output)) as db:
            previous = json.loads(db.execute("SELECT value FROM metadata WHERE key='manifest'").fetchone()[0])
        if previous == manifest: return {**manifest, "changed": False}
        raise ValueError("Existing generated index differs; choose a new explicit destination for review")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".sqlite3", delete=False) as stream: temporary = Path(stream.name)
    try:
        with closing(sqlite3.connect(temporary)) as db:
            db.executescript("CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL); CREATE TABLE terms(id TEXT PRIMARY KEY,code TEXT UNIQUE,label TEXT,short_label TEXT,valid_code INTEGER,parent_id TEXT,chapter TEXT,chapter_label TEXT,systems TEXT,label_normalized TEXT,search_text TEXT); CREATE TABLE term_systems(term_id TEXT,system_id TEXT,PRIMARY KEY(term_id,system_id)); CREATE INDEX term_system_idx ON term_systems(system_id,term_id); CREATE INDEX term_label_idx ON terms(label COLLATE NOCASE,id);")
            for row in rows:
                db.execute("INSERT INTO terms VALUES(?,?,?,?,?,?,?,?,?,?,?)", [row[k] for k in ("id", "code", "label", "short_label", "valid_code", "parent_id", "chapter", "chapter_label")] +
                           [json.dumps(row["systems"]), normalize(row["label"]), normalize(" ".join([row["label"], row["short_label"], row["code"], row["code"].replace(".", "")]))])
                db.executemany("INSERT INTO term_systems VALUES(?,?)", [(row["id"], system) for system in row["systems"]])
            db.execute("INSERT INTO metadata VALUES('manifest',?)", (json.dumps(manifest, sort_keys=True),))
            db.execute("PRAGMA user_version=1")
            db.commit()
        temporary.replace(output)
    finally: temporary.unlink(missing_ok=True)
    return {**manifest, "changed": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codes", type=Path, required=True); parser.add_argument("--tabular", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.codes, args.tabular, args.output), indent=2))
