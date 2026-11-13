# Canonical architecture and evidence lineage

```mermaid
flowchart LR
  UI[React Case Command Center / Model Arena] --> API[Existing FastAPI /api/v1]
  API --> Auth[Existing cookie session and case authorization]
  API --> Registry[Versioned catalogue and actual model registry]
  API --> DB[(Existing case / examination / source / review database)]
  API --> Queue[Durable job queue]
  Queue --> Worker[Existing CPU / GPU worker]
  Worker --> Readers[Document / DICOM / native volume / ECG adapters]
  Readers --> Gates[Quality + modality + geometry + rights + checkpoint gates]
  Gates --> Output[Source-grid prediction or explicit refusal]
  Output --> DB
  DB --> Graph[Bounded evidence projection]
  Graph --> Copilot[Typed read-only local retrieval]
  Graph --> UI
  Registry --> Arena[Saved report binding + actual labelled cohort checks]
  Arena --> UI
  API --> PNG[Bounded source PNG slice rendering]
  PNG --> MPR[Shared voxel crosshairs + three planes + source 3D]
  MPR --> UI
```

```mermaid
flowchart TD
  Source[Immutable source bytes and SHA-256] --> Examination[Case and examination association]
  Source --> Parse[Versioned extraction / preprocessing]
  Parse --> Observation[Source span/page/box or source-grid model mask]
  Observation --> Review[Append-only human review]
  Review --> Decision[Independent correction approval]
  Decision --> Effective[Derived effective evidence; original retained]
  Effective --> History[Unit-aware dated comparison]
  Effective --> EvidenceGraph[Stable-ID graph and possible conflicts]
  EvidenceGraph --> Citation[Exact source citation]
  Citation --> Snapshot[Explicit research snapshot export + byte hash]
  Observation --> NativeMesh[Actual predicted mask-derived mesh]
  Atlas[Generic reference atlas] -. L1 association only .-> EvidenceGraph
  NativeMesh -. no validated atlas transform .-> Registration[REGISTRATION_UNAVAILABLE]
```

The graph is a reproducible projection of current persisted evidence, not a second clinical database or a causal disease model. It retains inactive/superseded evidence as history, excludes it from current claims, and bounds nodes/edges/reviews. All graph, source, copilot and spatial routes independently authorize case access. Catalogue data and saved public research evaluations contain no private-case evidence.

The viewer reuses existing decoders, PNG render endpoints, Three.js, mask editor and surfaces. This avoids installing a second DICOM engine without an established need. Source voxel planes are labelled as such, particularly for oblique inputs; they are not resampled patient-anatomical planes. Four-dimensional channel volumes are refused by this viewer, while their independently validated model adapter can run. No arbitrary channel flattening is introduced.
