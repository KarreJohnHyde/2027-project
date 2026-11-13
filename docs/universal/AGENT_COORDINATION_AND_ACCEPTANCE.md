# Ownership, interfaces and acceptance

The implementation uses the canonical FastAPI API, React application and existing storage/authorization boundaries. Work was divided by assigned files; original data and weights were not replaced. No destructive database migration was introduced by this finalization.

| Role | Assigned responsibility | Interface / deliverable | Actual execution |
| --- | --- | --- | --- |
| Codex integration owner | Canonical router mounting, dashboard placement, container resource wiring, verification and clean-history GitHub publication | `/api/v1`, `UniversalWorkspacePage`, backend Dockerfile, aggregate evidence and publication audit | Executed |
| Codex imaging/evidence task | Measured-readiness service and UI; privacy of optional private evaluation results | `GET /universal/research/readiness`, strict response schema, `ResearchReadinessPanel` | Executed; assigned modules and tests |
| Codex evaluation task | Full-report reference validation, local prediction/evaluation bridge, source/permission/denominator checks | `scripts/evaluate_independent_reports.py`, `medtwin.independent-report-evaluation.v1` | Executed; tooling and controlled tests, no real-data accuracy claim |
| Codex CI task | Published commit CI inspection without changing tests to hide failures | Exact GitHub run/job metadata, browser result and skipped-fixture explanation | Executed |
| External Claude reviewer | Independent source review of contracts, refusal coverage, evaluation leakage and publication scope | Review the same committed source; report findings without editing implementation-owner files | Handoff prepared; no Claude execution or approval is claimed |
| Human data/reference owners | De-identification, actual processing permission, independent transcription and critical-field review | Source-bound inventory, finalized annotation bundle and permission evidence | Required external evidence; model outputs do not fill this role |

Phases and acceptance:

1. **Audit inputs:** distinguish raw medical sources, application exports, manuscripts, archives and installers. Preserve originals. Project instructions and executables are not annotation data.
2. **Validate references:** bind every complete document/page to actual source bytes and declared rendering profile. Reject missing review, modified labels, incomplete coverage, reused output-as-gold and absent commercial scope before prediction.
3. **Execute locally:** use the existing local OCR and rule extraction. No external/NC NLP fallback, model download, training or automatic reference generation occurs.
4. **Report measurements:** separate OCR error, lab field precision/recall, critical field mismatches, NLP given human text and end-to-end source-region results. Missing evidence is unavailable rather than zero accuracy.
5. **Show evidence in the app:** public engineering evidence has explicit source hashes and recorded scope; live model gates and cohort binding are separate. Private report metrics require an administrator. No raw report text, path, per-document hash or reviewer identity enters the global API response.
6. **Verify and publish:** run the integrated suites, frontend checks, actual API/browser controls and source/privacy checks. Publish only reviewed source/metadata through the separate clean-history checkout. Never include patient uploads, keys, downloaded datasets or new weights.

Claude review handoff: inspect these contracts and the tests on the published commit, run the documented verification commands, and check that no result is silently promoted to independent or clinical validation. Do not send private source documents to another service, generate gold labels, finalize human review, change rights gates or activate a model.

Acceptance is tracked separately for software behavior and scientific evidence. Successful tests establish the stated engineering controls; independently annotated full real-report accuracy remains unverified until appropriate reference artifacts pass the input gate and an actual evaluation completes.
