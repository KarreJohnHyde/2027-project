# Ownership and handoffs, remaining-gaps pass (14 November 2026)

**What actually happened:** only Claude Code worked in this pass. The Codex desktop app was open on the machine, but Codex wrote no project files during the pass (file timestamps checked before each change to Codex-owned files). So Claude performed both roles in sequence, as the directive allows. **No Codex review of this pass has taken place.** This handoff is not evidence that one did.

## Files changed by Claude in Codex-owned areas (review requested)

| Area | Files |
|---|---|
| Inference | `backend/app/services/model_inference.py`: per-slice head CT series mode; task summaries for tabular and heartbeat models; new input labels |
| Registry | `model_registry/models.json`: haemorrhage model `series_inference`; 9 tabular models |
| Dataset rights | `dataset_registry/release_context.json`, `dataset_registry/tasks.json` (owner's research authorization; new dataset records) |
| Training | `ml_training/tabular.py`, `ml_training/mitbih.py` (new) |
| Preparation and publishing | `scripts/prepare_msd_ct_datasets.py` (`--any-modality`), `scripts/register_msd_ct_dataset.py` (`--modality`, `--approved-on`), `scripts/publish_brain_mri_models.py` (CPU profiles) |

## Claude-owned additions

Evidence and registry display, the remediation scripts (`scripts/remediation_*.py`), the acquisition and registration scripts, the browser test for the native series, and these documents.

## Open handoff for Codex

1. Review the per-slice series path and its real-data parity check (`docs/universal/HANDOFF.md`, 2026-11-14 entry).
2. Review the CPU-trained volumetric runs when queue 3 publishes them.
3. Extend archive-member hashing (RSNA zip, MedMNIST npz) in the integrity audit.
