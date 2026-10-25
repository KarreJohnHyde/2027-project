# Local case retention and deletion

Status: `IMPLEMENTED_TESTED` for the local content-addressed upload store. This is a
software erasure workflow, not a legal retention policy or proof of secure media
sanitization.

## Implemented behavior

`DELETE /api/v1/cases/{case_id}` is restricted to the case creator or an
administrator. Before database state changes, every recorded upload path is checked
against the configured `UPLOAD_DIR`; paths outside the direct managed-object root,
symbolic links, directories, and inconsistent metadata stop deletion with HTTP 409.

Case-related database records are removed through the existing relational cascades.
For each content-addressed upload object:

- the object is preserved while any other case still references its stored filename;
- the final reference removes the physical encrypted or plaintext object;
- an already absent object is treated as an idempotent cleanup result; and
- a post-commit filesystem error is recorded and surfaced as HTTP 500 for operator
  follow-up rather than reported as a clean deletion.

The durable `CASE_DELETED` audit event contains only counts and the action type. It
does not contain filenames, paths, hashes, clinical text, or patient identifiers.

## Executed verification

`backend/tests/test_case_retention.py` covers unique-object deletion, shared-object
preservation until the final reference, already-missing objects, refusal of paths
outside the upload root, and refusal of deletion by a delegated case editor.

## Boundaries and remaining policy work

- Case deletion does not rewrite Git history. The independent PHI release blocker in
  `docs/security/PHI_RELEASE_BLOCKER.md` remains open.
- The repository does not define jurisdiction-specific minimum retention periods,
  legal holds, backup expiration, object-store lifecycle rules, or cryptographic/media
  erasure guarantees. Those require an approved production policy and infrastructure.
- Deleted local objects may still exist in host backups, snapshots, filesystem slack,
  logs outside this application, or previously made copies; those systems require
  separate lifecycle controls.
- The SQLite database is not encrypted. Production database selection, backup/restore,
  key management, and tamper-evident audit retention remain release work.
