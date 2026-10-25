# Anatomy asset report

Generated data: `public/anatomy/manifest.json` (served to the viewer), `docs/anatomy/derivatives.json` (derivative verification), `docs/anatomy/inventory/` (per-source inspection), `public/anatomy/atlas-index.json`.

Every model here is **generic reference anatomy** (`L1_GENERIC_REFERENCE`). None is the patient's anatomy. A finding is drawn on a model only as a schematic organ association or as a clinician-confirmed atlas region; spatially registered lesion display is `REGISTRATION_UNAVAILABLE`.

## Coverage

| System | Variants | | System | Variants |
| --- | ---: | --- | --- | ---: |
| Heart | 4 | | Intestines | 2 |
| Lungs | 7 | | Nervous system | 2 |
| Brain | 7 | | Skeletal system | 3 |
| Liver | 4 | | Hybrid full body | 1 |
| Pancreas | 3 | | Kidneys and nephrons | 10 |

That is 43 variants: 34 standalone assets and 9 atlas views. 25 variants have labelled structures. The Z-Anatomy atlas contributes 3,898 named structures. The hybrid full body has 14 atlas layers (skeleton, joints, muscles, vascular, nervous, heart, lungs, brain, liver, pancreas, intestines, kidneys, lymphoid, skin), 2 detailed asset layers (angiology, neurology) and 2 unregistered comparison models.

## Spatial frame

| Status | Variants | Meaning |
| --- | ---: | --- |
| `SOURCE_FRAME_SHARED` | 9 | Atlas chunks exported in one coordinate frame. |
| `BBOX_TRANSLATION_ALIGNED` | 2 | Z-Anatomy asset layers were offset by about 50 mm. They are aligned to the atlas by a measured bounding-box translation and await clinician review in the studio. |
| `NOT_PATIENT_REGISTERED` | 32 | Standalone assets, shown in their own frame. |

The two comparison models (skeleton, écorché) are placed by bounding-box scale and translation and are labelled `UNREGISTERED_COMPARISON`.

## Licences

| Class | Variants | Consequence |
| --- | ---: | --- |
| Attribution | 24 | Credit required. |
| Share-alike | 13 | Derivatives must use the same licence. |
| Non-commercial | 4 | `heart-external-newey`, `lungs-airways-umcg`, `lungs-transparent-alebogino`, `kidney-cowley`. Not usable in a commercial product. |
| Restricted (Sketchfab Standard) | 2 | `brain-hologram-oxterium`, `nephron-structure-arloopa`. Redistribution is limited; check before publishing screenshots or derivatives. |

Licences and attribution come from each file's embedded `asset.extras` metadata. Nine source files are excluded: 3 duplicate formats, 2 unattributed re-exports, 2 duplicate re-exports, 1 with an unknown licence and 1 superseded.

## Derivatives and fidelity

Originals are read-only; derivatives never replace them (`public/models/`, `source/` and the atlas release are untouched).

- **Standard tier:** triangle count identical to the source, bounds deviation ≤ 1e-4 of the diagonal, mesh names preserved. The worst observed deviation is 6.45e-6 (`kidney-payoman`). Changes: deduplication, pruning, WebP textures, quantisation (positions and normals left unquantised on skinned meshes) and meshopt compression.
- **Preview tier:** generated only above 600,000 triangles (7 variants) and labelled reduced-detail in the viewer. It keeps 25–36% of the triangles. The worst bounds deviation is 1.3e-3 (`nephron-iqcenter`). A tier that fails its gate is not published: the `lungs-transparent-alebogino` preview (`pulmones_con_transparencia.glb`) failed at 2.9% deviation, so that variant offers the standard tier only.
- **Size:** 801,430,980 bytes (764.3 MiB) of derivatives in `public/anatomy/derived/`. That folder is git-ignored and must be regenerated after a clean clone.

## Regenerating

```powershell
cd tools/asset-pipeline
npm ci
node inspect.mjs          # inventory and gltf-validator reports -> docs/anatomy/inventory/
node optimize.mjs         # derivatives -> public/anatomy/derived/, verification -> docs/anatomy/derivatives.json
node build-manifest.mjs   # public/anatomy/manifest.json, atlas-index.json, backend/app/data/atlas_structures.json
```

Without `public/anatomy/derived/`, the studio shows each variant's load failure and still renders the panels, evidence and provenance.
