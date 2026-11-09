"""Wait for the acquisition lock, then reconcile failed records using checked archives.

This is a continuation of the existing selected cohorts, not a new download
selection. Previously verified records are retained. It never writes the live
status while another worker owns the lock, or deletes a failed archive.
"""
import json
import msvcrt
import os
import time

import resume_dataset_cohorts as cohort


def main():
    with cohort.STATE.with_suffix(".lock").open("a+b") as lock:
        if cohort.STATE.with_suffix(".lock").stat().st_size == 0:
            lock.write(b"0")
            lock.flush()
        deadline = time.monotonic() + 4 * 3600
        while True:
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise SystemExit("Acquisition still holds the lock after four hours; rerun finalization later")
                time.sleep(10)
        state = json.loads(cohort.STATE.read_text())
        state.update(status="RECONCILING", reconciler_pid=os.getpid())
        for name in ("lidc", "cq500", "liver"):
            expected = list(cohort.cohort_items(name))
            group = state["cohorts"].setdefault(name, {"items": {}})
            group["expected"] = len(expected)
            for item in expected:
                previous = group["items"].get(item["id"], {})
                if previous.get("status") in {"VERIFIED_EXISTING", "DOWNLOADED_ARCHIVE_VERIFIED", "VERIFIED_RECOVERED_PARTIAL"}:
                    continue
                if name == "cq500" and item["id"] == "CQ500-CT-120":
                    audit = cohort.ROOT / "artifacts/audits/cq500-source-invalid-2026-11-09.json"
                    partial = item["target"].with_name(item["target"].name + ".part")
                    if audit.is_file() and partial.is_file():
                        evidence = json.loads(audit.read_text())
                        known = {row["sha256"] for row in evidence.get("copies", [])}
                        if evidence.get("source") == item["url"] and evidence.get("status") == "SOURCE_OBJECT_INVALID_ZIP" and cohort.sha256(partial) in known:
                            group["items"][item["id"]] = {"status": "FAILED", "error": "KNOWN_SOURCE_ARCHIVE_INVALID: byte-identical fresh source copy is unreadable; replacement source required", "audit": str(audit)}
                            continue
                try:
                    result = cohort.acquire(item["url"], item["target"],
                                            None if name == "lidc" else cohort.remote_size(item["url"]),
                                            item.get("expected_images"))
                    group["items"][item["id"]] = {**result, "source": item["url"], "verified_at": cohort.now(),
                                                   "previous_error": previous.get("error")}
                except Exception as exc:
                    group["items"][item["id"]] = {"status": "FAILED", "error": str(exc)}
                state.update(current=f"reconcile/{name}/{item['id']}", updated_at=cohort.now())
                cohort.write_json(cohort.STATE, state)
            group["status"] = "INCOMPLETE" if any(v.get("status") == "FAILED" for v in group["items"].values()) else "COMPLETE_ARCHIVES_VERIFIED"
        state.update(status="COMPLETE_ARCHIVES_VERIFIED" if all(g["status"] == "COMPLETE_ARCHIVES_VERIFIED" for g in state["cohorts"].values()) else "INCOMPLETE",
                     updated_at=cohort.now())
        cohort.write_json(cohort.STATE, state)
        print(json.dumps({"status": state["status"], "cohorts": {n: g["status"] for n, g in state["cohorts"].items()}}), flush=True)
        return int(state["status"] != "COMPLETE_ARCHIVES_VERIFIED")


if __name__ == "__main__":
    raise SystemExit(main())
