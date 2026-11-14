# Remediation baseline, 14 November 2026

Recorded by Claude Code (integration reviewer) at the start of the remaining-gaps pass. Every value below was read on this machine on this date.

## Source

| Item | Value |
|---|---|
| Checkout | `D:\project`, branch `feature/medtwin-2-integration` |
| HEAD at baseline | `269b1d59f2d34eae796faa816e51fe2d35975e0d` (local; history is not pushed) |
| GitHub `main` | `6f5f8ea` (history-free snapshot of local `d144212caa`); local commits after it are unpublished |
| Working tree | clean at baseline except files added by this pass |

## Runtime

| Item | Value |
|---|---|
| Python | 3.12.10 (`.venv`) |
| PyTorch | 2.14.1+cu130; MONAI 1.6.1; scikit-learn 1.9.1 |
| Node | 24.22.1 |
| GPU | Present, **on hold**: three fatal hardware errors during GPU training on 13 Nov. Every job in this pass sets `CUDA_VISIBLE_DEVICES=-1`; CUDA reports unavailable under that setting. |
| Windows Application Control | No block observed in this pass; nothing was bypassed. |
| Free disk | C: 35.8 GB, D: 37.4 GB (after downloads) |

## Owner decisions in force

- **Training purpose is `research`** (2026-11-14, `dataset_registry/release_context.json`). The earlier commercial direction (2026-11-09) is kept on record. No licence is removed by this setting.
- **CPU-only training** until the GPU crash cause is fixed.
- **Downloads approved on 2026-11-14:** UCI tables (9), MIT-BIH, NIH malaria cells, Decathlon spleen, prostate, hippocampus and pancreas, HC18, FETAL_PLANES_DB. All come from the original publishers; each file has a SHA-256 and licence-page receipt.

## Data and rights inventory

- Prepared manifests: 39 (`DATASET_INTEGRITY.json`).
- Registry models: 41 (`MODEL_READINESS.csv`): 18 run on uploads, 1 is runnable but blocked as FAILED (kidney tumour), the rest are evaluation evidence only.
- Task registry: 77 dataset records. 46 have no known licence and stay blocked. 11 verified-licence datasets were authorized for research training on 2026-11-14 (`scripts/authorize_research_training.py`).

## Background work at baseline

CPU queues in `artifacts/training/resumable/` (git-ignored; rerun any `.cmd` file to resume after a shutdown):

| Queue | Contents |
|---|---|
| `cpu_queue1.cmd` | Malaria cell classifier, then its applicability reference |
| `cpu_queue2.cmd` | MIT-BIH heartbeat classifier |
| `cpu_queue3.cmd` | FETAL_PLANES_DB classifier; hippocampus, prostate and spleen segmenters; pancreas prepared only |
| `cpu_queue4.cmd` | GastroVision class-weighting experiment (development only) |
