# Encryption at rest — design and executed tests

Current reconciliation (2026-10-29): uploaded-file encryption and optional whole-database
SQLCipher encryption are implemented. Actual database protection depends on runtime
configuration; plain SQLite is not encrypted merely because the feature exists.
See `backend/app/database.py`, `scripts/encrypt_database.py` and the
[current audit](../verification/COMPLETENESS_AUDIT_2026-10-29.md).

The remaining sections are the earlier uploaded-file test/design snapshot. Their
"Not covered" statements are historical, not a current claim that SQLCipher is absent.
Key rotation, backup/restore drills and production key custody still need verification.

## What is encrypted

Every file stored through `app.services.upload_store.store()` (all upload paths) when
`MEDTWIN_STORAGE_ENCRYPTION` is `auto` with a key configured, or `required`.

| Property | Implementation (`backend/app/services/storage_crypto.py`) |
| --- | --- |
| Cipher | AES-256-GCM (`cryptography` 50.0.2), chunked 1 MiB records |
| Construction | STREAM-style: nonce = 7-byte random prefix ‖ 32-bit counter ‖ last-chunk flag; the file header (magic `MTENC\x01`, key id, prefix, chunk size, plaintext size) is authenticated as AAD of every chunk |
| Integrity | Any modified, truncated, reordered, appended or re-keyed chunk fails authentication (`StorageCryptoError`) |
| Keys | Key ring from `MEDTWIN_STORAGE_KEY_FILE` (JSON `{"keys": {...}, "active": ...}`) and/or `MEDTWIN_STORAGE_KEYS`; key id = first 8 bytes of SHA-256(key); new files use the active key, older files stay readable while their key is in the ring; `scripts/storage_keys.py rotate` moves them to the active key |
| Writes | Encrypt to a temporary file, then atomic `os.replace` |
| Readers | `upload_store.stream()` for downloads; `upload_store.materialize()` for libraries that need a path (pydicom, nibabel, SimpleITK, OCR, research models) decrypts into a private per-call directory under `UPLOAD_DIR/.work`, keeps the original suffix, and deletes it when the block exits; leftovers older than 1 h are purged at startup |
| Fail-closed | `required` mode without a key refuses uploads with 503 and readiness reports `storage_encryption.ready = false` |

Keys must live outside the repository. `scripts/dev.ps1 -Mode qa` generates a QA key in
its scratch directory; production key provisioning is an operator task. Both the backend
and optional worker services in `docker-compose.yml` default
`MEDTWIN_STORAGE_ENCRYPTION` to `required`, so a Compose deployment without a supplied
storage key may start for diagnostics but fails closed before accepting an upload.

## Executed tests

`backend/tests/test_storage_encryption.py` — 10 test functions, 15 cases, all passing
(last run 2026-10-24: `15 passed in 5.14s`; also part of the full backend suite).

| Test | Verifies |
| --- | --- |
| `test_round_trip_preserves_every_byte` (6 sizes: 0, 1, chunk−1, chunk, chunk+1, 3·chunk+5) | Byte-exact round trip; exact ciphertext size (header + data + one 16-byte tag per chunk) |
| `test_any_modification_truncation_or_reordering_is_rejected` | A flipped byte in the body, the header size field, the header nonce prefix or the final tag; truncation by 20 bytes; one appended byte; and swapping two equal-length chunks are all rejected |
| `test_unknown_key_and_missing_configuration_are_typed` | Decrypting with a ring that lacks the file's key, and encrypting with an empty ring, both raise `StorageKeyError` |
| `test_rotation_keeps_old_files_readable_and_writes_with_the_new_key` | Rotation: files written before rotation still decrypt; new files carry the new key id |
| `test_reencrypt_in_place_handles_legacy_and_rotated_files` | `reencrypt_in_place` encrypts a legacy plaintext file and re-encrypts a file under the old key; both end under the active key with byte-identical plaintext, no partial files remain, and an empty key ring refuses before writing |
| `test_storage_keys_cli_is_a_dry_run_unless_applied` | `scripts/storage_keys.py rotate` changes nothing without `--apply`; with it, every stored file ends under the active key and the `.work` area is untouched |
| `test_plaintext_copies_exist_only_inside_the_block` | `plaintext_path` keeps the original name/suffix (`.nii.gz`) and removes the plaintext on exit |
| `test_uploads_are_encrypted_on_disk_and_every_reader_still_works` | Through the API: the stored file is ciphertext (a marker string is absent on disk), and analysis, text extraction and download still work |
| `test_encrypted_dicom_still_renders` | DICOM rendering reads an encrypted upload |
| `test_required_mode_without_a_key_refuses_to_store` | `required` without a key → upload 503, readiness not ready |

Browser evidence: the isolated QA stack runs with `MEDTWIN_STORAGE_ENCRYPTION=required`;
uploads, document extraction and research-model runs in the browser walkthrough
(`docs/anatomy/BROWSER_WALKTHROUGH.md`) all operate on encrypted files.

## Not covered (documented gaps)

- **Database encryption**: case metadata, extracted statements and measurements in
  SQLite are plaintext. Options: SQLCipher, or PostgreSQL with encrypted storage. Not started.
- **Migration has not been run on the development upload store.** The tool exists
  (`scripts/storage_keys.py status | encrypt-legacy | rotate`, dry run unless `--apply`;
  each rewrite streams plaintext into new ciphertext and verifies the SHA-256 before an
  atomic replace), but encrypting the existing development uploads is an operator
  decision: run `status` first, keep the key file backed up outside the repository.
- **Key management service / HSM**: keys come from a file or environment variable.
- **Backups** of the upload directory inherit encryption; database backups do not.
