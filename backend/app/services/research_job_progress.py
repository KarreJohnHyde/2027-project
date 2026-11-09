"""Read-only allowlisted research-job snapshots. No logs, paths, keys or patient records."""
from datetime import datetime, timezone
import json
import re
from pathlib import Path

from app.config import PROJECT_ROOT

LIVER_PARTIAL = Path("C:/MedTwin_Datasets/Liver_MSD/download/Task03_Liver.tar.part")


def _transfer(path, expected):
    """Known local paths only; received bytes are explicitly not verification."""
    try:
        size = path.stat().st_size
        if 0 <= size <= expected:
            return {"received_bytes": size, "expected_bytes": expected, "verified": False}
    except OSError:
        pass
    return None


def _read(path):
    if not path.is_file() or path.stat().st_size > 8 * 1024**2:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def snapshots(root=PROJECT_ROOT):
    root = Path(root)
    jobs = []
    cohort = _read(root / "artifacts/downloads/cohort_recovery_status.json")
    def state(value):
        return value if isinstance(value, str) and re.fullmatch(r"[A-Z0-9_]{1,100}", value) else "UNKNOWN"
    def timestamp(value):
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).isoformat()
        except ValueError:
            return None
    def count(value):
        return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 10_000_000 else None
    groups = cohort.get("cohorts", {}) if cohort else {}
    if isinstance(groups, dict):
        for name, group in groups.items():
            if name not in {"lidc", "cq500", "liver"} or not isinstance(group, dict):
                continue
            entries = group.get("items", {})
            items = list(entries.values()) if isinstance(entries, dict) else []
            verified = sum(isinstance(v, dict) and v.get("status") in {"VERIFIED_EXISTING", "VERIFIED_RECOVERED_PARTIAL", "DOWNLOADED_ARCHIVE_VERIFIED"} for v in items)
            jobs.append({"id": "acquisition_" + name, "label": {"lidc": "LIDC acquisition", "cq500": "CQ500 acquisition", "liver": "MSD liver acquisition"}[name],
                         "status": state(group.get("status")), "last_event_at": timestamp(cohort.get("updated_at")),
                         "completed": verified, "expected": count(group.get("expected")), "failed": sum(isinstance(v, dict) and v.get("status") == "FAILED" for v in items)})
            if name == "liver":
                jobs[-1]["transfer"] = _transfer(LIVER_PARTIAL, 28_925_891_584)
    for filename, identity, label in [
        ("artifacts/downloads/liver_preparation_status.json", "liver_preparation", "Liver image/mask preparation"),
        ("artifacts/downloads/rcc_aid_status.json", "rcc_acquisition", "RCC-AID acquisition and curation"),
        ("artifacts/downloads/rcc_aid_preparation_status.json", "rcc_preparation", "RCC-AID image/mask preparation"),
        ("artifacts/training/kits19-pipeline-status.json", "kidney_experiment", "KiTS19 completed experiment"),
    ]:
        data = _read(root / filename)
        if data:
            records = data.get("files", {})
            records = records if isinstance(records, dict) else {}
            jobs.append({"id": identity, "label": label, "status": state(data.get("stage", data.get("status"))),
                         "last_event_at": timestamp(data.get("updated_at")), "completed": sum(isinstance(v, dict) and v.get("status") == "VERIFIED" for v in records.values()) if identity == "rcc_acquisition" else None,
                         "expected": 4 if identity == "rcc_acquisition" else None, "failed": None})
            if identity == "rcc_acquisition":
                jobs[-1]["transfer"] = _transfer(root / "MedTwin_Datasets/RCC_AID/download/images.zip.part", 6_635_339_072)
    return {"scope": "Recorded research job events only; no clinical or commercial approval. Counts can await reconciliation after a repaired transfer.",
            "observed_at": datetime.now(timezone.utc).isoformat(), "jobs": jobs,
            "available": bool(jobs), "notice": "Background processes do not automatically restart after a workstation reboot."}
