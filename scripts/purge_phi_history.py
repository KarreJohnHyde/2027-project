"""Rewrite Git history so no commit contains the embedded patient laboratory reports.

Only one blob is affected: backend/app/services/lab_service.py as committed in the
Phase 1 baseline (blob 0ac0961e79e190da6b2f7eca801ee8bfeeab1667). Every commit that
contains it receives a redacted copy in which the SAMPLE_LAB_REPORTS block is
replaced by an empty dictionary, so historical checkouts still import. All other
content and history is unchanged; commit IDs from the baseline onward change.

Run through scripts/purge_phi_history.ps1, which requires an explicit
authorization phrase, makes a bundle backup first and verifies the result.
Requires git-filter-repo (installed by the wrapper into an isolated venv).
"""

from __future__ import annotations

import argparse
import os
import sys

import git_filter_repo as fr

TARGET_BLOB = b"0ac0961e79e190da6b2f7eca801ee8bfeeab1667"
BLOCK_START = b"# Verified Sample Laboratory Reports"
PLACEHOLDER = (
    b"# [Removed: these embedded laboratory reports contained patient identifiers.\n"
    b"#  See docs/security/PHI_RELEASE_BLOCKER.md.]\n"
    b"SAMPLE_LAB_REPORTS: Dict[str, Dict[str, Any]] = {}\n"
)


def redact(data: bytes) -> bytes:
    lines = data.splitlines(keepends=True)
    start = next(index for index, line in enumerate(lines) if line.startswith(BLOCK_START))
    if not lines[start + 1].startswith(b"SAMPLE_LAB_REPORTS"):
        raise SystemExit("Unexpected blob layout; refusing to rewrite.")
    end = next(index for index in range(start + 2, len(lines)) if lines[index].rstrip(b"\r\n") == b"}")
    return b"".join(lines[:start]) + PLACEHOLDER + b"".join(lines[end + 1:])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True)
    args = parser.parse_args()
    os.chdir(args.repo)
    replaced: list[bytes] = []

    def blob_callback(blob, _metadata):
        if blob.original_id == TARGET_BLOB:
            blob.data = redact(blob.data)
            replaced.append(blob.original_id)

    options = fr.FilteringOptions.parse_args(["--force", "--quiet"], error_on_empty=False)
    fr.RepoFilter(options, blob_callback=blob_callback).run()
    if not replaced:
        print("Target blob not found in history; nothing was rewritten.", file=sys.stderr)
        return 2
    print(f"Redacted {len(replaced)} blob occurrence(s) of {TARGET_BLOB.decode()[:10]}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
