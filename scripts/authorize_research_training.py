"""Record the owner's non-commercial research training authorization in dataset_registry/tasks.json.

Owner decision 2026-11-14 (dataset_registry/release_context.json: training_purpose "research"). Only datasets whose
licence source is already verified (license.status == "VERIFIED", with a named licence and a source) and that have no
authorization yet are changed. Datasets without a known licence stay blocked, and existing authorizations are left as
they are. The authorization never widens the licence: its scope is non-commercial research under the recorded terms.

Dry run by default; --apply writes the registry (same formatting and line endings).

  .venv\\Scripts\\python.exe scripts\\authorize_research_training.py [--apply]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "dataset_registry" / "tasks.json"
DECISION = {"authorization_status": "VERIFIED", "authorization_scope": "NON_COMMERCIAL_RESEARCH_UNDER_RECORDED_TERMS",
            "authorized_by": "project owner (chat instruction)", "authorized_on": "2026-11-14"}


def eligible(licence: dict) -> bool:
    return (licence.get("status") == "VERIFIED" and bool(licence.get("name")) and bool(licence.get("source"))
            and not licence.get("authorization_status") and "no licence" not in str(licence.get("name")).lower())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    raw = REGISTRY.read_bytes()
    crlf = b"\r\n" in raw[:4096]
    text = raw.decode("utf-8")
    registry = json.loads(text)
    render = lambda value: json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    if render(registry).replace("\n", "\r\n" if crlf else "\n") != text:
        print("The registry does not round-trip with this formatting; refusing to rewrite it.")
        return 1
    changed = []
    for item in registry["datasets"]:
        licence = item.get("license") or {}
        if eligible(licence):
            licence.update(DECISION, authorization_reason=(
                f"Owner authorized non-commercial research training on 2026-11-14 under the recorded terms: {licence['name']}"))
            changed.append((item["id"], licence["name"]))
    for dataset_id, name in changed:
        print(f"{'AUTHORIZE' if args.apply else 'would authorize'} {dataset_id}: {name[:90]}")
    blocked = [item["id"] for item in registry["datasets"] if not (item.get("license") or {}).get("authorization_status")]
    print(f"{len(changed)} authorized; {len(blocked)} remain blocked without a known licence.")
    if args.apply and changed:
        REGISTRY.write_bytes(render(registry).replace("\n", "\r\n" if crlf else "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
