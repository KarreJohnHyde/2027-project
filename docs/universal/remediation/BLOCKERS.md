# Remaining blockers (14 November 2026)

None of these can be solved by writing code. Each one names who must act and the concrete next step. Engineering work that could proceed did proceed; see `REQUIREMENTS.csv`.

| Requirement | Blocker | Owner | Next concrete action |
|---|---|---|---|
| U-014 Real report evaluation | Permitted, independently human-reviewed real report pages: **0** | Project owner | Collect 30–50 de-identified report pages with permission. One person transcribes in the annotation tool; a second, independent person checks every critical field. Then run `scripts/evaluate_independent_reports.py`. |
| U-016 Weak-model improvement | GPU training on hold after fatal hardware errors (13 Nov) | Project owner | Diagnosis on 14 Nov: CUDA works in software (PyTorch 2.14.1+cu130 sees the RTX 5060 Laptop GPU, driver 617.14); no Application Control blocks. The System log shows two fatal WHEA hardware errors (18:56 and 19:23), each with Kernel-Power 41 and a bugcheck, plus one nvlddmkm 153 GPU reset. BIOS F.14 (April 2026), Windows Insider build 26300. Cause is hardware or firmware under load and is unresolved. Next: update the BIOS and NVIDIA driver (vendor sources), consider a non-Insider build, then one bounded GPU run under observation. Experiments are prepared and rights-cleared for research. |
| U-016 (cont.) | The KiTS19 held-out test was exposed to earlier development | Engineering + owner | Any kidney-tumour improvement claim needs a fresh, untouched test cohort. |
| U-017 Patient-to-atlas registration | No independent expert-landmark cohort | Project owner | Obtain a rights-cleared registration cohort with expert landmarks, and independent reviewers. L2/L3 stays disabled until then. |
| U-008 Learned fusion | No genuinely paired same-patient multi-modality cohort with outcomes | Project owner | Obtain one under a data-use agreement. Until then the app reports `LEARNED_FUSION_UNAVAILABLE`. |
| U-009 Disease forecasting | No real longitudinal lab cohort with defined outcomes | Project owner | Credentialed access (e.g. MIMIC-IV, PhysioNet credentialing + DUA) or an approved institutional cohort. |
| U-022 Release | Sensitive objects in the original Git history; no legal, privacy or regulatory review | Project owner | Decide on the history; commission the reviews. Publication stays snapshot-only. |
| U-023 Disaster recovery | No approved off-host backup destination | Project owner | Name an approved destination; then run the recovery drill with fictional data. |
| Rights, all | 46 registry datasets have no known licence; MURA and EchoNet need each user's own Stanford AIMI registration | Project owner | Keep them blocked unless the publisher's terms are found and recorded. |
| Clinical use, all | No independent clinical evaluation or regulatory authorization | Project owner | Out of scope for software. Every output stays research-only. |
| CASE-D detection | Only photographs of the printed film exist | Project owner | Request the original DICOM from the scan centre; the native series path will then run. |
