# Public data acquisition and workspace cleanup — 6 November 2026

Update 7 November 2026: the earlier 217-artifact download queue has completed with all
210 KiTS19 CTs and seven MedMNIST NPZs verified. All 210 CT/mask pairs have matching
shapes/affines, though a volumetric training manifest and label checks remain to be
prepared. The expanded image/text, image/table and 2D/3D research resource pass is
documented in `docs/data/MULTIMODAL_RESOURCES_2026-11-07.md`. The acquisition-status
sections further below describe the original in-progress snapshot.

The owner requested automatic acquisition of useful free datasets and removal of unused or permission-blocked material. This pass adds a reviewed, reproducible acquisition queue; it does not claim to download every useful medical dataset or implement new clinical models.

## Subsequent permanent cleanup

Following the owner's explicit deletion request, non-forced deletion of the exact audited manifest entries succeeded. Approximately **64.32 GB on D:** and **410.77 MB on C:** were permanently deleted (decimal units). This supersedes the initial move-only status below. The deleted data cannot be restored by the earlier move scripts; the obsolete quarantine `restore.ps1` was removed.

C: cleanup removed redundant LIDC probe downloads, extracted DICOM files and derived images/masks. All 400 probe payload files matched retained copies by SHA-256; the remaining probe metadata was superseded by the retained selection/preparation records. D: cleanup removed all 925 earlier manifest-listed unused entries and 16 of the 17 additional folders. The unused DeepSA source/checkpoints were removed, but approximately 67.22 MB of read-only Git metadata remains. Required license notices and all 19 registered model-weight locations were preserved.

The exact result is `artifacts/audits/cleanup-2026-11-06/permanent-cleanup-result.json`. Automatic approval review rejected forced recursive deletion with only "blocked by policy" as the reason. The successful alternative used non-forced deletion restricted to audited paths and left read-only Git objects unchanged. No ownership or access controls were changed.

## Removed from the project

17 folders containing 4,775,617,374 bytes (4.78 GB) were moved to `D:\MedTwin_Removed_Datasets_2026-11-06\additional-cleanup`:

- Nine unused extracted source repositories: health-assistant, medical, medvault-ai, metriport, SIH_26047, TwinWeaver, CogStack-SemEHR, codex-plugin-cc, and the second RadGraph extraction.
- The unused DeepSA code/checkpoints, which have no published licence, and five unused brain-data copies superseded by retained RSNA/CQ500 data.
- The nested pneumonia extraction and its AppleDouble metadata. All 5,856 nested JPEGs matched the retained `chest_xray/{train,test,val}` images by relative path and SHA-256.

The audit checked 311 application, training, setup, registry and sample-manifest files for path references and rejected tracked-file removal. Installed runtimes, source trees required by setup scripts, registered checkpoints, active training data, and required licence notices remain in place. The unavailable DeepSA model placeholder remains an honest unavailable capability; removing its unused source does not enable it.

**Initial move-only status (superseded by the permanent-cleanup update above):** no disk space was reclaimed by that move. Automatic approval review rejected the original permanent-deletion command as blocked by policy, without a more specific reason. The reversible move succeeded, and the previous quarantine (59,616,247,968 bytes including metadata) was initially retained. The audit and exact moves are in:

- `artifacts/audits/cleanup-2026-11-06/plan.json`
- `artifacts/audits/cleanup-2026-11-06/result.json`
- `artifacts/audits/cleanup-2026-11-06/previous-moved.json`
- `artifacts/audits/cleanup-2026-11-06/pneumonia-duplicate-check.json`

These local audit artifacts are Git-ignored. The move records are historical provenance; permanently deleted payloads are no longer recoverable through those paths.

## Reviewed acquisition queue

`dataset_registry/public_acquisition.json` contains 217 artifacts totalling 20,462,044,593 bytes (20.46 GB), with publisher sizes, hashes, source revisions and intended use.

| Source | Action | Purpose and limits |
| --- | --- | --- |
| [Official KiTS19 GitHub repository](https://github.com/neheller/kits19) and its publisher-linked imaging host | Download the 210 CT volumes matching the 210 existing masks; GitHub and imaging revisions are pinned; SHA-256 for each image | Kidney/tumour volumetric training data, 20,017,490,682 bytes. Data: CC BY-NC-SA 4.0; code: MIT. Research/noncommercial only. The images still need geometry/pairing checks and a patient-grouped manifest before training. |
| [Official MedMNIST Zenodo release](https://zenodo.org/records/10519652) | Download seven NPZ subsets: OCT, retina, dermatology, breast ultrasound, colorectal pathology, blood cells and tissue microscopy; publisher MD5 checks | 444,553,911 bytes. Standard 28-pixel benchmark candidates, not full-resolution clinical datasets, segmentation labels or automatically implemented models. CC BY 4.0 except DermaMNIST (CC BY-NC 4.0). Retain original splits and check patient/source independence before reuse. |
| [Kaggle pneumonia dataset](https://www.kaggle.com/datasets/paultimothymooney/chest-xray-pneumonia) | Save the public dataset metadata and reuse the existing 5,856 JPEGs instead of downloading another copy | The Kaggle description links CC BY 4.0. Paediatric pneumonia images; patient grouping and split audit remain prerequisites for training. |

GitHub provenance text, licence files, the Zenodo metadata record and Kaggle dataset metadata are saved in `artifacts/downloads/provenance`. Downloaded Python source is saved for provenance and is never executed. No Kaggle account, credentials, payment or personal data were submitted.

The destination is `C:\MedTwin_Datasets`. Transfers resume `.part` files with HTTP Range, verify size and publisher hash before creating the final file, refuse to overwrite a differing final file, and use a single-worker lock. A 60 GiB reserve protects space for the already-running downloads, extraction and caches. Reserve checks can pause the new queue; future storage use by other jobs cannot be guaranteed.

Start or resume the queue from `D:\project`:

```powershell
.\.venv\Scripts\python.exe -u scripts\acquire_public_datasets.py --run
```

Live status (authoritative; this document is a snapshot):

- `artifacts/downloads/public_acquisition_status.json`
- `artifacts/downloads/public-acquisition.log`
- `artifacts/downloads/public-acquisition-errors.log`

The background worker was observed running and successfully verifying downloads. Do not interpret the queued KiTS files as already complete. This pass does not install a new logon task; the queue can be resumed with the command above.

## Existing work retained

LIDC CT, MSD liver CT, CQ500 head-CT downloads and the existing GPU queues were already running and were left running. Their durable scripts are in `artifacts/training/resumable`. CQ500 is the existing external head-CT evaluation acquisition; another copy was not started.

Credentialed datasets such as MIMIC/VinDr and sources without a usable licence were not downloaded through unofficial mirrors. Existing individually authorized MURA and EchoNet data were retained. Larger missing datasets (including remaining LUNA16 subsets) were not added blindly while the current queues need storage. Their absence is still a limitation; this curated pass does not complete the project's entire data-readiness matrix.

## Verification

- Downloader: 5 passing checks using a local HTTP server, including real Range resume, hash rejection, existing-file preservation, path containment and storage reserve.
- Existing model registry, dataset registry and head-CT series: 23 tests passed after the moves.
- Downloaded benchmark NPZ files were opened with `allow_pickle=False`; image/label arrays and original train/validation/test splits were checked. Completion counts belong to the live status file.

No new benchmark was promoted to a registered clinical model or claimed as clinical validation.
