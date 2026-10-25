# MedTwin L1 anatomical reference attribution

## Curated selectable assets

The following assets are copied without modification from
`3d-anatomy-atlas-main/packages/data/releases/1.2.0/economy`:

- `cardiovascular/arterial_system.glb` → `medtwin_l1_heart.glb`
- `visceral/endocrine_glands--respiratory_system.glb` → `medtwin_l1_respiratory.glb`
- `nervous/brain.glb` → `medtwin_l1_brain.glb`
- `visceral/digestive_system.glb` → `medtwin_l1_digestive.glb`

Exact hashes, byte sizes, served paths and system mappings are recorded in
`registry.json`.

The release attributes its underlying anatomy primarily to “Z-Anatomy — The
libre 3D atlas of anatomy,” including BodyParts3D-derived material, and records
it under CC BY-SA 4.0. The brain chunk additionally includes Brain for Blender
material under CC BY-SA 3.0, with adaptations distributed under CC BY-SA 4.0.
The pinned Z-Anatomy source revision is
`e38ea5e6c7e22d229a975f3fde563a5aca52099e`.

Upstream transformations include conversion to +Y-up metre coordinates,
simplification into atlas quality levels, grouping, quantisation and
`EXT_meshopt_compression`.

The upstream 1.2.0 release labels its model and provenance audits as `pending`.
MedTwin therefore presents every asset as a traceable, generic Level-1 research
reference. None is a patient-specific reconstruction, registered clinical
anatomy, or evidence of diagnostic localization.
