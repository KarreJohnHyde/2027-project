# PHI release blocker: patient identifiers in Git history

**Status: OPEN — RELEASE AND SHARING BLOCKED pending the repository owner's authorization to sanitize history.**
This document is deliberately redacted: it contains no names, ages, report numbers or other identifiers.

## Current release decision (revalidated 2026-10-24)

- `python scripts/privacy_scan.py --history` still exits 1. The previously documented
  PHI-bearing blob remains reachable from both local branches; the purge has not run.
- `git remote`, `refs/remotes`, tags, and stashes are empty. This is useful local
  containment evidence, but it neither removes the PHI nor proves that no other copy
  exists.
- Do not push, publish, upload, attach, archive for transfer, or otherwise share this
  repository, a clone, a bundle, or any copy containing its Git metadata. The
  repository release gate remains blocked until the authorized purge and clean
  post-purge history scan are complete.

## What happened

The Phase 1 workspace, committed as found, embedded two laboratory reports in `backend/app/services/lab_service.py` (`SAMPLE_LAB_REPORTS`). They identified two real patients and included name, age, sex, hospital/laboratory, report numbers and collection times. The block was never referenced by code. It was removed from the working tree on 2026-10-24 (commit `3aee888`), but it remains in earlier commits.

## Extent (verified 2026-10-24 with `scripts/privacy_scan.py`, values withheld)

| Location | Finding |
| --- | --- |
| Git object database | Exactly **one blob**, `0ac0961e79e190da6b2f7eca801ee8bfeeab1667` (`backend/app/services/lab_service.py`). It contains 2 report identifiers, 2 patient names and 2 ages. |
| Commits containing it | `bfb7988` (baseline, branch `main`) and `ba7eb13` (`feature/medtwin-2-integration`). Later commits do not contain it. |
| Refs reaching it | `refs/heads/main`, `refs/heads/feature/medtwin-2-integration`, plus local reflogs. Of 5 reachable commits, 2 contain the sensitive blob and 3 contain the cleaned version. There are no tags, stashes, configured remotes or remote-tracking refs. That is local evidence only; it cannot prove the repository was never copied or shared. |
| Working tree, untracked files, compiled `.pyc` caches | None. The tracked-and-untracked release scan is clean; 8 reviewed synthetic test-fixture lines are allowlisted in `scripts/privacy_allowlist.json`. |
| Development database (`backend/medtwin.db`) | `lab_reports` has 0 rows; the reports were never stored. No patient-identifier pattern was found in any text column. |
| Git LFS / higher-risk binary paths | 22 tracked LFS paths (14 JPG, 4 GLB, 2 PNG, 1 DOCX and 1 PDF). They have not had a formal clinical DLP review; binary absence of PHI is therefore not asserted. |
| Local Claude Code transcript | `C:\Users\johnn\.claude\projects\d--project\480f2f70-391a-48d3-934a-3da9e1a5362f.jsonl` contains the identifiers. An earlier session printed the affected lines while investigating. This file is outside the repository. Delete it, or restrict access to it, at your discretion. |
| Credentials | No provider API keys, private-key blocks, JWTs or literal bearer tokens were found. One local/service database URI uses placeholder-like credentials, and two Markdown code examples contain secret-like literals; these require manual review and rotation if ever reused. |

An unreachable blob (an older line-ending variant of `backend/tests/test_new_features.py`) contains only test passwords; garbage collection during the purge removes it.

## Controls in place now

- **Push guard:** `scripts/install_git_guards.ps1` installed `.git/hooks/pre-push`. It runs the history scan and blocks every push while any finding remains (verified: exit code 1).
- **Release scan:** `python scripts/privacy_scan.py --tree --paths dist` must exit 0 before any build artifact leaves the machine. It is also run by `scripts/verify.ps1` and by `backend/tests/test_release_privacy.py`.
- **Training exclusion:** these reports must never be used as data. They are excluded from every dataset registry and task.

## Purge procedure (not executed)

The strongest option for this five-commit, no-remote repository is a new sanitized
canonical repository created from an allowlisted current snapshot, after the privacy
owner decides whether incident evidence must be retained. If history must be preserved,
`scripts/purge_phi_history.ps1` performs a controlled rewrite. It runs only with the
exact authorization phrase, an explicit pre-existing encrypted/access-controlled backup
directory, and `-SecureBackupApproved`:

1. Refuses to run with uncommitted tracked changes. Warns about remotes; it never pushes.
2. Writes a verified `git bundle` only to the privacy-owner-approved secure backup directory (the bundle still contains the sensitive history). It refuses repository and temporary directories and never creates an ordinary default backup.
3. Installs `git-filter-repo==2.47.0` into an isolated venv. It then replaces that single blob in every commit with a redacted copy, in which `SAMPLE_LAB_REPORTS` becomes an empty dictionary so old checkouts still import; nothing else changes.
4. Expires all reflogs, garbage-collects unreachable objects and runs `git fsck --full`.
5. Re-scans every object; the script fails unless the scan is clean.

**Drill result (2026-10-24, on a disposable clone):** 1 blob occurrence redacted; 4 commits rewritten with new IDs; post-purge scan clean; the redacted baseline still defines the module. The clone and its backup were deleted afterwards.

**Consequences you should accept before authorizing:**
- Every commit ID from the baseline onward changes. Docs citing `bfb7988`, `ba7eb13`, `3aee888` and `2c90050` need updating; `.git/filter-repo/commit-map` gives the mapping.
- Any other clone, copy, backup or zip of this repository still holds the data and must be deleted.
- Delete the pre-purge bundle once you are satisfied.
- Rewriting cannot recall copies that have already left this machine. As far as can be determined, none have: there is no remote.

## Closing the blocker

After an authorized purge: run `python scripts/privacy_scan.py --history`, which must exit 0. Then delete the backup bundle and other copies, update the commit IDs cited in the docs, and set the status here to CLOSED with the date.
