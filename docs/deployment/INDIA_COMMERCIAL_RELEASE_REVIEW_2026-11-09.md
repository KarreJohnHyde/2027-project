# India commercial clinician decision support: release review

**Decision: NOT READY FOR CLINICAL OR COMMERCIAL RELEASE.** The owner selected India and commercial clinician decision support on 9 November 2026. This is recorded in `dataset_registry/release_context.json`; it is a development direction, not a regulatory classification or licence grant. No registered model has clinical activation or completed commercial rights clearance.

## Define the first intended use

The first release must identify one organ, test/acquisition protocol, particular finding, exact checkpoint and preprocessing version, target patient population, care setting, intended clinician, clinical action and circumstances for refusal. Specify whether the result informs, drives or makes a decision and how a clinician independently reviews the source evidence. Include exclusions, urgency, failure consequences, reference standard and acceptance thresholds before validation. The current project has not finalised this scope. An all-organ/all-disease claim is unsupported.

CDSCO's 2026 medical-device-software guidance includes AI/ML software and explains that risk classification depends on intended use and the Medical Devices Rules, 2017. Merely naming the product “clinician decision support” does not establish an exemption or a class. The regulatory owner must document applicable classification, manufacturer responsibilities, licensing route and required evidence for the actual function; this document does not assign a class. [CDSCO guidance, sections 6–7 and subsequent licensing/evidence sections](https://cdsco.gov.in/opencms/export/sites/CDSCO_WEB/Pdf-documents/Guidance-document-on-Medical-Device-Software-under-MDR-2017.pdf). The downloaded primary document is retained in `artifacts/audits/india-mdsw-guidance-2026.pdf`.

## Data, code and weights rights

The companion [checkpoint rights backlog](../data/INDIA_COMMERCIAL_RIGHTS_BACKLOG_2026-11-09.csv) is generated from locally declared registry terms. It is an inventory, not a completed independent legal review. Every row needs evidence for source data, annotation, training/derivative use, code, pretrained weights, distribution and customer hosting. A free download or an open-source training library does not establish all those rights. Existing `model_registry/commercial_review.json` records remain `NOT_REVIEWED` and are bound to exact checkpoint hashes.

Adapter entries without a checkpoint hash cannot be cleared merely by reviewing their Python package version. Inventory their actual downloaded weights, tokenizer/vocabulary/configuration and upstream corpora; include indirect assets such as bundled OCR models. Bind the review to those files and the declared task before enabling a commercial path.

| Local source/model family | Current handling | Evidence still needed |
| --- | --- | --- |
| KiTS19, RSNA ICH, CQ500, MURA and Kvasir/Kvasir-SEG with recorded non-commercial or research-only terms | Exclude from the commercial product; preserve previous experiments as research evidence. No new commercial training on these terms. | Separate written permission and reviewed terms, or replacement data and newly developed weights. Do not assume a later rehost relicenses original masks. |
| ACDC, third-party chest/NLP adapters and missing/unclear dataset terms | Hold. Generic research owner authorization is insufficient. | Publisher/data-owner terms and checkpoint/pretraining provenance. |
| Locally declared CC0/CC BY datasets and code/weights with permissive terms | Candidates for review, not cleared assets. | Exact release and attribution, upstream sources, annotation rights, pretrained encoder/weights terms, distribution obligations and any additional agreements. |
| MSD CC BY-SA tasks | Preparation only; commercial and derivative obligations not resolved. | Review source provenance and share-alike/application/distribution obligations for the proposed use. |
| RCC-AID candidate | Downloading and exact CT/mask preparation queued; no training or model publication. | Publisher describes annotations as CC BY 4.0 and original TCIA images/metadata as CC BY 3.0. Preserve both attribution chains and review the actual files and intended use. [Publisher release](https://zenodo.org/records/19630298). |

RCC-AID's current CSV and annotation ZIP contain 142 series from 101 patients, while the publisher prose says 129/91. Preparation uses exact collection + SeriesInstanceUID identities, groups repeated scans by PatientID, checks all source hashes, affine/shape/labels and prevents metadata fields such as PatientName from entering the pairing CSV. The discrepancy is recorded rather than silently changing cohort counts. It remains a candidate cohort requiring curation, rights review and an independent validation source.

Two narrow publisher facts were independently rechecked: [PTB-XL version 1.0.3](https://physionet.org/content/ptb-xl/1.0.3/) states CC BY 4.0 access terms; [TotalSegmentator's maintainer](https://github.com/wasserth/TotalSegmentator) lists the default `total` task under Apache-2.0 and distinguishes separately licensed tasks. These facts do not clear this application's exact checkpoints, pretrained assets, distribution or clinical use. The local skin trainer uses torchvision's ImageNet-pretrained ResNet18 encoder, so the PAD-UFES-20 data licence alone cannot close its upstream weights review. The local detectors use torchvision Faster R-CNN; a YOLO-format label file does not establish use of Ultralytics code or its licence.

The volumetric trainers now require a separately recorded, reviewer-identified and hash-bound commercial-development data review. A research runtime profile cannot override the declared commercial purpose. Other training entry points still need a consistent review before any new commercial experiment; this change is not a universal licence-enforcement claim.

## Privacy and deployment review

DPDP commencement is phased. The official Act commencement notification and final Rules specify immediate, one-year and eighteen-month stages; as of 9 November 2026, it would be inaccurate to state that every substantive provision and rule is already in force. The privacy owner must map the applicable provisions and dates to the proposed launch. [Act commencement notification](https://egazette.gov.in/WriteReadData/2025/267647.pdf), [final Rules, rule 1](https://www.meity.gov.in/static/uploads/2025/11/53450e6e5dc0bfa85ebd78686cadad39.pdf).

The product review still needs a documented processing purpose and lawful basis, clear patient notices and rights/contact processes, processor/hospital agreements, access and retention/deletion controls, incident handling, logging policy, key custody and restoration, plus a documented assessment of hosting, transfers and any child-related workflow. Review applicable requirements at launch; encryption and an upload de-identification checkbox alone do not establish compliance. Keep this development installation restricted to de-identified/synthetic evidence.

Both visible local volumes, C: and D:, are on disk 0. A copy between them is not disk-failure recovery. The tested container drill restores authentication, a case and an encrypted uploaded object using a local synthetic bundle. An off-host destination, independently held keys, retention, recovery objectives and an off-host restore drill are still needed. No real patient backup was created.

The local repository's historical patient-identifier blocker remains documented in [PHI_RELEASE_BLOCKER.md](../security/PHI_RELEASE_BLOCKER.md). A clean working-tree scan does not clear Git history. Do not distribute this repository's Git metadata; publication must follow the existing sanitized snapshot procedure or an expressly authorised remediation. No history rewrite was performed in this work.

## Evidence required before a release decision

1. Clinical/regulatory owner finalises one intended use and documents the India regulatory route and release responsibilities.
2. Rights reviewer closes the exact data/code/weights/redistribution records; replace restricted checkpoints rather than relabelling them.
3. Clinical evaluation uses independently sourced, permitted and representative Indian-site data with patient/site separation, expert reference labels, frozen thresholds, confidence intervals, subgroup results, calibration and explicit unacceptable-failure criteria. Keep the exposed KiTS19 test set out of further model selection.
4. Verify acquisition quality, wrong-organ/protocol rejection, missing data, inference refusal, source links, clinician review, human factors and workflow performance. Viewer/import functionality does not validate pathology diagnosis, EEG interpretation, registration accuracy or forecasting.
5. Close image/OS and runtime vulnerability findings, native-policy approval, deployment load/timeout and rollback tests, off-host recovery, audit retention and incident operations. Dependency advisory scans and synthetic recovery are limited technical evidence.
6. Bind approved evidence, model and dataset versions, configuration and image digests to a controlled release. Establish post-release performance monitoring, change control and revalidation triggers. Nothing in the present evidence authorises clinical use.
