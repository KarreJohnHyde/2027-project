# Recovery and release runbook

The application remains a research system. These commands are implemented operational tools, not evidence of a production deployment or clinical authorization. Do not use the workstation research environment as an audited production image.

## Offline backup and staged restore

1. Stop the API, queue workers and all maintenance writers through the actual service manager. The CLI cannot prove that every writer is stopped; `--writers-stopped` is the operator's attestation.
2. Supply the existing raw 256-bit SQLCipher database key through `MEDTWIN_DB_KEY_FILE` (or the existing `MEDTWIN_DB_KEY`), and a **separate** backup key-ring file through `MEDTWIN_BACKUP_KEY_FILE`. Use the key-ring JSON format documented in `backend/app/services/storage_crypto.py`. Do not put keys in source, command arguments, the backup bundle or its destination folder. Retain upload-encryption keys separately too.
3. Run a backup against the actual encrypted database and managed local upload store, using a new destination filename:

```powershell
.\.venv\Scripts\python.exe scripts\recovery_bundle.py backup --database <encrypted-db-path> --uploads <managed-upload-directory> --bundle <new-encrypted-backup-path> --writers-stopped
```

The tool requires encrypted uploads and SQLCipher, checks local database/object references, verifies database integrity and copied bytes, and authenticates the encrypted bundle before publishing it. It refuses incomplete local backups where referenced objects are not present. Remote object-store-only installations need a separate versioned object-store backup procedure. Keys, models, training datasets and deployment configuration are not included.

4. Copy the authenticated encrypted bundle to independently controlled off-host storage with retention and access controls. This transport/retention has not been configured here.
5. Restore into a **new** staging directory, with the separately retained backup and database keys:

```powershell
.\.venv\Scripts\python.exe scripts\recovery_bundle.py restore --bundle <encrypted-backup-path> --destination <new-empty-recovery-directory>
```

The destination must not already exist. Restore authenticates the whole envelope, bounds extraction, rejects unsafe/duplicate archive members, verifies hashes and checks database integrity. It never overwrites or activates the live application.

6. Restore encrypted uploads at the original managed-store mount, or perform and review explicit database path rebasing before activation. The tool does not silently rewrite absolute stored paths. Restore the original upload key-ring through the deployment's secret mechanism.
7. Start an isolated application against the staged copy. Verify authentication, case access, upload decryption, source hashes, queued-job behavior and representative reports. Confirm no worker points at live storage. Record measured recovery time and data-loss interval, then approve an operational cutover through the actual service process. A real off-host drill, recovery objectives and cutover procedure remain outstanding.

## Release configuration

The updated core dependency pins are in `backend/requirements.txt`; the corresponding serverless dependency manifest and transitive lock are `backend/pyproject.toml` and `backend/uv.lock`. CI now audits the resolved core lock. The `.venv-security` environment is a local test overlay, not a redistributable production environment or a locked image.

On a configured Docker host, first validate the candidate configuration with actual separately managed secrets:

```powershell
docker compose -f docker-compose.yml -f docker-compose.hardened.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.hardened.yml build
```

The installed Docker engine now runs. Both patched candidate images built and passed a hardened, isolated production-mode synthetic drill. Authentication, case restoration, actual uploaded-file decryption and frontend API proxying were verified; evidence is `artifacts/audits/docker-drill-1c9c48f757/report.json`. Synthetic OCR and library imports also passed. The [image security review](../security/IMAGE_SECURITY_REVIEW_2026-11-09.md) still records four high backend OS findings and one frontend raw scanner/vendor disagreement. This was local: C: and D: are partitions on disk 0, and an off-host destination has not been configured. Before any release:

- Build on an approved patched runtime, pin the resulting image digest, scan image/OS and optional ML dependencies, and run application/readiness/upload/inference smoke tests with the read-only filesystem and process limits enabled. Provision only reviewed, checksum-bound model artifacts; the base image omits optional research adapters.
- Configure TLS at ingress, secure secret custody/rotation, explicit public frontend/CORS origins and the actual trusted proxy IPs/CIDRs. Do not set `MEDTWIN_TRUSTED_PROXY_IPS=*`. The backend now binds to `127.0.0.1` by default; nginx can still reach it over the private Compose network. Rate limiting remains process-local and needs a shared store before scaling out.
- Keep development seeding and debug off. Ensure durable encrypted database/uploads, required keys and source data access controls; an HTTP health response alone is not a production-readiness or clinical-safety check.
- Complete the off-host restore drill, capacity/timeout/load tests, key-loss recovery, audit retention, incident response and rollback to a tested image/database combination. Define RPO and RTO with the operator; none are claimed from synthetic tests.
- Use `MEDTWIN_USAGE_PROFILE=research` only for permitted research activity. `commercial` refuses unreviewed checkpoints. Review records belong alongside the deployed model registry (`commercial_review.json`) and must name the exact checkpoint, declared use, reviewer and SHA-256-bound rights evidence. Registry/evidence files must be deployment-controlled and read-only to application users. This gate is not a legal opinion and does not replace clinical validation or regulatory assessment.

The optional research workstation includes packages outside the audited deployment lock. The Transformers/RadGraph migration now uses Transformers 5.22.2 and the source-hashed `radgraph 0.1.18+medtwin.tf5.2` build. Six synthetic-report graphs matched the old runtime exactly. The 290-distribution workstation advisory inventory reports zero known vulnerabilities in assessed packages, with four unassessed local-version distributions (custom RadGraph and CUDA Torch/torchaudio/torchvision). This is not an OS, native-binary or custom-code security audit. See `artifacts/audits/dependency-security-tf5-2026-11-09.json`. Production RadGraph remains disabled pending clinical and rights evidence. Do not copy the workstation environment into production. The scikit-learn extension remains blocked by Windows application control and requires an approved compatible build or authorised IT policy decision.

The selected target is commercial clinician decision support in India. Both default Compose usage profiles and the hardening overlay now select `commercial`; the overlay cannot silently inherit a research profile. See the [India review packet](INDIA_COMMERCIAL_RELEASE_REVIEW_2026-11-09.md) for intended-use, regulatory, privacy and exact-checkpoint rights requirements. New commercial volumetric training also needs a separately reviewed data permission record; research owner authorization does not satisfy it. Zero models have clinical or commercial release approval.
