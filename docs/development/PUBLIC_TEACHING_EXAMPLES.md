# Public teaching examples

`/examples` is a public, read-only teaching library. The entry page and workspace navigation link to it. It renders without authentication, backend requests, a visitor account or database writes. Each case has an authored source packet, attributed findings, an illustrative timeline, evidence differences, fictional measurements where useful, future comparison questions, capability limits and a JSON download.

Alex, Maya and Sam are **fictional teaching adaptations**, not anonymized copies of identifiable reports. Their names, clinical details, measurements and timelines are invented. The examples preserve general learning themes from report workflows without publishing original medical records, exact values, dates, ages, institutions, identifiers, source filenames, source hashes, OCR or images. They carry no ground-truth, clinical validation or model-performance claim. Static authored text is explicitly distinguished from model inference. No diagnostic model is run by this page.

The public content is deliberately maintained in `src/data/publicCaseExamples.ts`; it must never be automatically populated from the private-reference store. The source repository is public, so these fictional fixtures are public there as well as in the app. Owner-specific records, source previews and OCR continue to use the existing protected API and encrypted local storage. Their access rules and guest-demo generation are unchanged.

General educational explanations link to NIDDK's A1C page and the National Kidney Foundation's CKD criteria. These sources support the limited explanatory statements; they do not validate the fictional records or an individual clinical decision.

Browser checks cover anonymous access with the entire backend blocked, source navigation, three-case selection, deep links, mobile overflow, explicit fictional/export labels, exclusion of private-store fields from exports, and the sign-in guard on private references.
