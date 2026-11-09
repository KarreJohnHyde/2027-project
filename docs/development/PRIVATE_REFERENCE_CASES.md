# Private reference cases

The authenticated `/private-references` screen provides precomputed, source-linked case reports, original-page previews, local OCR, dated observations, reported measurements, unresolved differences and input-specific model abstentions. The overview and navigation link to it without needing a shared case selection.

These packets are **owner-only even when shared workspace mode is enabled**, including against other administrators. They are not ordinary shared cases, public demo seeds, clinical ground truth, training data or clinician-reviewed findings. Other workspaces do not gain access by selecting a case or receiving a case membership.

Originals, previews, OCR and reports use the existing authenticated AES-256-GCM file format. Default storage is `%LOCALAPPDATA%/MedTwin/private-references`, with a separate key at `%LOCALAPPDATA%/MedTwin/private-reference.key`. Both must remain outside Git and public assets. Protect this directory and its key with operating-system permissions. Copying or backing up ciphertext requires preserving the key separately; this implementation is not an off-host recovery drill.

The source database stores no medical reference payload. Account binding includes ID, username and creation timestamp to prevent reassignment after ID reuse. Routes authenticate the current owner, reject traversal/symlinks, return no-store headers and authenticate ciphertext before returning sources. `DELETE /api/v1/private-references/{id}` erases that owner's encrypted packet. Original user files elsewhere are unaffected.

Import with the approved runtime:

```powershell
.venv\Scripts\python.exe scripts/import_private_references.py --owner-username <exact-login> --manifest <private-manifest.json>
```

The manifest schema is described in the importer. Keep actual definitions and case contents private, never in source or fixtures. Imports refuse duplicate revision keys, unlinked observations and claims of completed model predictions. All source bytes receive SHA-256 verification; all previews and originals are authenticated after encryption. OCR runs locally, with engine/version recorded. Selected-page transcription is explicitly separate from OCR and clinical review. Failed imports remove their incomplete packet; previously imported revisions remain intact.

No clinical diagnostic model or forecast is run by this importer. Photographs of CT films are not DICOM volumes; an ECG photo is not a digital waveform. Source-reported EF and laboratory values are not model predictions. There is no automatic transplant of these records into the shared prediction pipeline, training manifests, clinical reviews or demographic attestations. New supported capabilities still require organ, test, target, validated model/version and independent evaluation.

Synthetic tests cover encryption, original/preview access, cross-owner and administrator isolation, no-cache responses, source integrity failure, import rollback, owner binding, unsupported prediction claims and scoped erasure. Review and validate any clinical content independently before intended clinical use.
