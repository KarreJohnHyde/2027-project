// Join the curated catalog, automated inventory, verified derivatives and the
// atlas release into the manifests consumed by the Anatomy Studio and backend.
//
// Outputs
//   public/anatomy/manifest.json        systems, variants, structures, provenance
//   public/anatomy/atlas-index.json     compact structure index for picking
//   backend/app/data/atlas_structures.json  names for anatomical-site normalisation

import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { ATLAS_SELECTIONS, CURATION, EXCLUDED, HYBRID_LAYERS, SYSTEMS, classifyLicense } from "./catalog.mjs";
import { INVENTORY_DIR, MANIFEST_PATH, PROJECT_ROOT, assetIdFor, round, sha256Bytes } from "./lib.mjs";

const ATLAS_RELEASE = path.join(PROJECT_ROOT, "3d-anatomy-atlas-main", "packages", "data", "releases", "1.2.0");
const ATLAS_INDEX_PATH = path.join(PROJECT_ROOT, "public", "anatomy", "atlas-index.json");
const BACKEND_ATLAS_PATH = path.join(PROJECT_ROOT, "backend", "app", "data", "atlas_structures.json");
const DERIVATIVES_PATH = path.join(PROJECT_ROOT, "docs", "anatomy", "derivatives.json");

const GENERIC = /^(object_?\d*|rootnode|root|scene|sketchfab_model|defaultmaterial|defaultmat|material_?\d*|mat(\.\d+)?|lambert\d*|mesh_?\d*|node_?\d*|geode|scene_-_root|\(unnamed.*\)|.*\.(fbx|obj|stl|blend|gles)|subtool-.*|\d+)$/i;

function readJson(file) {
  return readFile(file, "utf8").then(JSON.parse);
}

function humanize(raw) {
  return raw
    .replace(/^Maya_\d+:/, "")
    .replace(/[_]+/g, " ")
    .replace(/\s*\.\d+$/, "")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^\w/, (character) => character.toUpperCase());
}

function parentOf(nodePath) {
  const segments = nodePath.split("/");
  return segments.length >= 2 ? segments[segments.length - 2] : null;
}

function groupKey(node, groupBy) {
  if (groupBy === "material") return node.material ?? node.semantic_name ?? node.name;
  if (groupBy === "parent") {
    const parent = parentOf(node.path);
    return parent && !GENERIC.test(parent) ? parent : node.semantic_name ?? node.name;
  }
  return node.name;
}

function resolveLabel(variant, key, index) {
  const exact = variant.labels?.[key];
  if (exact) return { ...exact };
  for (const pattern of variant.label_patterns ?? []) {
    if (pattern.match.test(key)) return { label: pattern.label, label_source: pattern.label_source };
  }
  if (key && !GENERIC.test(key) && (variant.humanize_material || variant.group_by !== "node")) {
    return { label: humanize(key), label_source: "SOURCE_NAME" };
  }
  return { label: `Unlabelled segment ${index + 1}`, label_source: "NONE" };
}

function buildStructures(variant, detail) {
  const groups = new Map();
  for (const node of detail.nodes.filter((item) => item.mesh)) {
    const key = groupKey(node, variant.group_by ?? "node");
    if (!groups.has(key)) groups.set(key, { key, nodes: [], triangles: 0, boxes: [] });
    const group = groups.get(key);
    group.nodes.push(node.name);
    group.triangles += node.triangles;
    if (node.world_bounds) group.boxes.push(node.world_bounds);
  }
  return [...groups.values()].map((group, index) => {
    const label = resolveLabel(variant, group.key, index);
    return {
      id: `s${index + 1}`,
      source_key: group.key,
      label: label.label,
      label_source: label.label_source,
      note: label.note ?? null,
      review_status: label.label_source === "NONE" ? "NOT_APPLICABLE" : CURATION.review_status,
      nodes: group.nodes,
      triangles: group.triangles,
    };
  });
}

function viewTypes(variant, summary, structures) {
  const geometry = summary.geometry ?? {};
  const isPoints = (geometry.primitive_modes ?? []).every((mode) => mode === "POINTS");
  const types = isPoints ? ["POINTS"] : ["EXTERIOR", "TRANSPARENT", "SECTION"];
  if (!isPoints && (variant.role === "INTERIOR" || (structures.length > 1 && (summary.spatial?.nested_mesh_nodes_inside_largest ?? 0) > 0))) {
    types.push("INTERIOR");
  }
  if (structures.length > 1) types.push("LAYERED");
  if (variant.role === "CROSS_SECTION") types.push("AUTHORED_CROSS_SECTION");
  return types;
}

function tierRecords(derived) {
  const tiers = {};
  for (const [tier, value] of Object.entries(derived?.tiers ?? {})) {
    if (!value.passed) continue;
    tiers[tier] = {
      url: value.url,
      bytes: value.bytes,
      sha256: value.sha256,
      triangles: value.after.rendered_triangles,
      points: value.after.points,
      triangle_ratio_vs_source: value.triangle_ratio,
      bounds_relative_deviation: value.checks.bounds_relative_deviation,
      geometry_changed: value.geometry_changed,
      transforms: value.transforms,
    };
  }
  return tiers;
}

function unionBox(boxes) {
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (const box of boxes) {
    for (let axis = 0; axis < 3; axis++) {
      min[axis] = Math.min(min[axis], box.min[axis]);
      max[axis] = Math.max(max[axis], box.max[axis]);
    }
  }
  return { min, max, size: max.map((value, axis) => value - min[axis]) };
}

/**
 * Compare an asset's extents with the matching atlas system. When both the
 * minimum and maximum of an axis are displaced in the same direction, the
 * mean displacement is an estimated translation; the half-difference is the
 * residual that a translation cannot explain. Millimetres throughout.
 */
function frameAlignment(assetBox, referenceBox) {
  const axes = [0, 1, 2].map((axis) => {
    const minShift = referenceBox.min[axis] - assetBox.min[axis];
    const maxShift = referenceBox.max[axis] - assetBox.max[axis];
    return { offset: (minShift + maxShift) / 2, residual: Math.abs(minShift - maxShift) / 2, before: Math.max(Math.abs(minShift), Math.abs(maxShift)) };
  });
  const translation = axes.map((axis) => (Math.abs(axis.offset) > 0.002 ? axis.offset : 0));
  const corrected = translation.some((value) => value !== 0);
  return {
    method: "AXIS_ALIGNED_BOUNDING_BOX_EXTENT_COMPARISON",
    extent_difference_before_mm: axes.map((axis) => round(axis.before * 1000, 1)),
    translation_m: translation.map((value) => round(value, 6)),
    residual_after_translation_mm: axes.map((axis) => round(axis.residual * 1000, 1)),
    status: corrected ? "BBOX_TRANSLATION_ALIGNED" : "SOURCE_FRAME_SHARED",
    caveat: "Estimated from bounding-box extents of a whole system; this is not landmark-based registration and does not verify internal correspondence.",
  };
}

/** Uniform scale + translation that fits an unregistered asset's box to the atlas stature. */
function bboxFitTransform(assetBox, referenceBox) {
  const scale = referenceBox.size[1] / assetBox.size[1];
  const translation = [
    (referenceBox.min[0] + referenceBox.max[0]) / 2 - ((assetBox.min[0] + assetBox.max[0]) / 2) * scale,
    referenceBox.min[1] - assetBox.min[1] * scale,
    (referenceBox.min[2] + referenceBox.max[2]) / 2 - ((assetBox.min[2] + assetBox.max[2]) / 2) * scale,
  ];
  const residual = [0, 2].map((axis) => Math.abs(assetBox.size[axis] * scale - referenceBox.size[axis]) * 1000);
  return {
    method: "UNIFORM_SCALE_TO_STATURE_AND_CENTRE",
    scale: round(scale, 8),
    translation: translation.map((value) => round(value, 6)),
    residual_width_mm: round(residual[0], 1),
    residual_depth_mm: round(residual[1], 1),
    status: "UNREGISTERED_BBOX_SCALED",
    caveat: "Scale and position are fitted to overall height only. Internal correspondence with the atlas body is not established.",
  };
}

async function buildAtlas() {
  const manifest = await readJson(path.join(ATLAS_RELEASE, "manifest.json"));
  const english = (await readJson(path.join(ATLAS_RELEASE, "names", "en.json"))).entries;
  const latin = (await readJson(path.join(ATLAS_RELEASE, "names", "la.json"))).entries;
  const derivatives = await readJson(DERIVATIVES_PATH);
  const fileByKey = new Map(derivatives.atlas.files.map((file) => [`${file.chunk}:${file.quality}`, file]));
  const structures = manifest.structures.map((structure) => ({
    id: structure.id,
    parent: structure.parent,
    system: structure.system,
    kind: structure.kind,
    side: structure.side ?? null,
    meshes: structure.meshes ?? [],
    name: english[structure.id]?.name ?? structure.id,
    name_la: latin[structure.id]?.name ?? null,
    review: structure.review?.status ?? "unreviewed",
  }));
  const chunks = manifest.chunks.map((chunk) => ({
    id: chunk.id,
    system: chunk.system,
    mesh_start: chunk.meshStart,
    mesh_count: chunk.meshCount,
    standard: { url: fileByKey.get(`${chunk.id}:standard`).url, bytes: chunk.files.standard.bytes, sha256: chunk.files.standard.sha256, triangles: chunk.files.standard.triangles },
    economy: { url: fileByKey.get(`${chunk.id}:economy`).url, bytes: chunk.files.economy.bytes, sha256: chunk.files.economy.sha256, triangles: chunk.files.economy.triangles },
  }));
  return {
    index: {
      schema_version: "medtwin-atlas-index-1.0.0",
      release: { version: manifest.version, channel: manifest.channel, content_hash: manifest.contentHash, generated_at: manifest.generatedAt },
      coordinates: manifest.coordinates,
      bounds: manifest.bounds,
      notices: { review: manifest.notices.review.en, data: manifest.notices.data.en },
      palette: manifest.materials.map((material) => material.color),
      palette_kinds: manifest.materials.map((material) => material.kind),
      issues: manifest.issues.map((issue) => ({ id: issue.id, kind: issue.kind, text: issue.text.en, status: issue.status })),
      assets: manifest.assets.map((asset) => ({ id: asset.id, title: asset.title, authors: asset.authors, license: asset.license, source: asset.source })),
      systems: manifest.systems.map((system) => system.id),
      chunks,
      structures,
    },
    manifest,
  };
}

function atlasStructuresUnder(index, groups, { systems = [], exclude = [] } = {}) {
  const byId = new Map(index.structures.map((structure) => [structure.id, structure]));
  const ancestors = (structure) => {
    const chain = [];
    let current = structure;
    while (current) {
      chain.push(current.id);
      current = current.parent ? byId.get(current.parent) : null;
    }
    return chain;
  };
  return index.structures.filter((structure) => {
    if (structure.kind !== "structure") return false;
    const chain = ancestors(structure);
    if (exclude.some((group) => chain.includes(group))) return false;
    return systems.includes(structure.system) || groups.some((group) => chain.includes(group));
  });
}

function chunksFor(index, structures) {
  const meshes = new Set(structures.flatMap((structure) => structure.meshes));
  return index.chunks.filter((chunk) => [...meshes].some((mesh) => mesh >= chunk.mesh_start && mesh < chunk.mesh_start + chunk.mesh_count)).map((chunk) => chunk.id);
}

async function main() {
  const inventory = await readJson(path.join(INVENTORY_DIR, "summary.json"));
  const derivatives = await readJson(DERIVATIVES_PATH);
  const { index: atlasIndex } = await buildAtlas();
  const summaryById = new Map(inventory.assets.map((asset) => [asset.asset_id, asset]));
  const atlasBox = { min: atlasIndex.bounds.min, max: atlasIndex.bounds.max, size: atlasIndex.bounds.max.map((value, axis) => value - atlasIndex.bounds.min[axis]) };
  const atlasLicence = { id: "CC-BY-SA-4.0", class: "SHARE_ALIKE", commercial_use: true, share_alike: true, redistribution: "ATTRIBUTION_SHARE_ALIKE" };

  // Reference boxes for frame concordance, from the atlas chunk inventory.
  const atlasChunkSummaries = inventory.assets.filter((asset) => asset.source_group === "z_anatomy_atlas_1_2_0_standard");
  const systemBox = (system) => unionBox(atlasChunkSummaries.filter((asset) => asset.relative_path.includes(`/standard/${system}/`)).map((asset) => asset.spatial.scene_bounds));

  const variants = {};
  const systems = [];
  for (const system of SYSTEMS) {
    const variantIds = [];
    for (const variant of system.variants) {
      const assetId = assetIdFor(variant.source);
      const summary = summaryById.get(assetId);
      if (!summary) throw new Error(`No inventory record for ${variant.source}`);
      const detail = await readJson(path.join(INVENTORY_DIR, `${assetId}.json`));
      const extras = summary.gltf.asset_extras ?? {};
      const structures = buildStructures(variant, detail);
      const tiers = tierRecords(derivatives.variants[variant.id]);
      const record = {
        id: variant.id,
        system_id: system.id,
        kind: "STANDALONE_ASSET",
        label: variant.label,
        role: variant.role,
        view_types: viewTypes(variant, summary, structures),
        available: Boolean(tiers.standard),
        default_tier: tiers.preview && tiers.standard.bytes > 40 * 2 ** 20 ? "preview" : "standard",
        tiers,
        source: {
          relative_path: summary.relative_path,
          sha256: summary.sha256,
          bytes: summary.bytes,
          title: extras.title ?? null,
          author: extras.author ?? null,
          source_url: extras.source ?? null,
          license_text: extras.license ?? null,
          generator: summary.gltf.generator,
          validator: { status: summary.validation.status, errors: summary.validation.errors, issue_codes: summary.validation.issue_codes },
        },
        license: classifyLicense(extras.license),
        statistics: {
          triangles: summary.geometry.rendered_triangles,
          points: summary.geometry.points,
          vertices: summary.geometry.unique_vertices,
          nodes: summary.counts.nodes,
          mesh_nodes: summary.counts.mesh_nodes,
          materials: summary.counts.materials,
          textures: summary.counts.textures,
          animations: summary.counts.animations,
          skins: summary.counts.skins,
          closed_primitives_measured: `${summary.geometry.closed_measured_primitives}/${summary.geometry.topology_measured_primitives}`,
          bounds_size: summary.spatial.scene_bounds?.size ?? null,
          blend_materials: summary.materials_summary.blend,
        },
        structures,
        group_by: variant.group_by ?? "node",
        labelled_structures: structures.filter((structure) => structure.label_source !== "NONE").length,
        frame: variant.frame ?? "INDEPENDENT_ASSET_FRAME",
        registration: { status: "NOT_PATIENT_REGISTERED", representation_level: "L1_GENERIC_REFERENCE" },
        notes: variant.notes ?? [],
        repairs:
          summary.validation.errors > 0 && tiers.standard
            ? [`Source validator errors (${Object.keys(summary.validation.issue_codes).filter((code) => code.startsWith("ERROR")).join(", ")}) are absent from the derivative after buffer repacking; geometry is unchanged.`]
            : [],
      };
      if (variant.frame === "Z_ANATOMY_ADULT_MALE") {
        const reference = variant.id.includes("neurology") ? systemBox("nervous") : systemBox("cardiovascular");
        const alignment = frameAlignment(summary.spatial.scene_bounds, reference);
        record.registration = {
          status: alignment.status,
          representation_level: "L1_GENERIC_REFERENCE",
          reference_frame: "Z-Anatomy adult male atlas 1.2.0 (+Y up, +Z front, metres, origin between heels)",
          alignment,
        };
      }
      variants[variant.id] = record;
      variantIds.push(variant.id);
    }

    if (system.atlas) {
      const selection = ATLAS_SELECTIONS[system.id];
      const selected = atlasStructuresUnder(atlasIndex, selection.groups, {});
      const id = `atlas-${system.id}`;
      variants[id] = {
        id,
        system_id: system.id,
        kind: "ATLAS_REFERENCE",
        label: `${system.label} — structure-labelled atlas reference`,
        role: "ATLAS_IN_BODY_REFERENCE",
        view_types: ["EXTERIOR", "TRANSPARENT", "SECTION", "INTERIOR", "LAYERED"],
        available: true,
        default_tier: "standard",
        atlas: { chunks: chunksFor(atlasIndex, selected), groups: selection.groups, structure_count: selected.length },
        source: {
          relative_path: "3d-anatomy-atlas-main/packages/data/releases/1.2.0",
          title: "Svitylo 3D Anatomy Atlas data 1.2.0 (Z-Anatomy, BodyParts3D-derived)",
          author: "Z-Anatomy; The Database Center for Life Science (BodyParts3D); see ATTRIBUTION.md",
          source_url: "https://github.com/Z-Anatomy/Models-of-human-anatomy",
          license_text: "CC BY-SA 4.0 (kidneys CC BY 4.0, Human Reference Atlas)",
          content_hash: atlasIndex.release.content_hash,
        },
        license: atlasLicence,
        statistics: { structures: selected.length },
        labelled_structures: selected.length,
        frame: "Z_ANATOMY_ADULT_MALE",
        registration: { status: "SOURCE_FRAME_SHARED", representation_level: "L1_GENERIC_REFERENCE" },
        notes: ["Every atlas structure carries the release's own review status ('unreviewed' throughout 1.2.0)."],
      };
      variantIds.push(id);
    }

    let hybrid = null;
    if (system.hybrid) {
      const layers = HYBRID_LAYERS.map((layer) => {
        const selected = atlasStructuresUnder(atlasIndex, layer.atlas_groups ?? [], { systems: layer.atlas_systems ?? [], exclude: layer.exclude_groups ?? [] });
        return { ...layer, kind: "ATLAS_LAYER", chunks: chunksFor(atlasIndex, selected), structure_count: selected.length, registration: "SOURCE_FRAME_SHARED" };
      });
      for (const [layerId, label, variantId] of [
        ["angiology-detailed", "Vascular — detailed Z-Anatomy layer", "hybrid-angiology-zanatomy"],
        ["neurology-detailed", "Nervous — detailed Z-Anatomy layer", "nervous-zanatomy-neurology"],
      ]) {
        const alignment = variants[variantId].registration.alignment;
        layers.push({ id: layerId, label, kind: "ASSET_LAYER", variant_id: variantId, default_on: false, registration: alignment.status, translation_m: alignment.translation_m, alignment });
      }
      const comparison = system.unregistered_comparison.map((variantId) => {
        const summary = summaryById.get(assetIdFor(SYSTEMS.flatMap((item) => item.variants).find((variant) => variant.id === variantId).source));
        return {
          id: `${variantId}-comparison`,
          label: `${variants[variantId].label} — unregistered comparison`,
          kind: "UNREGISTERED_COMPARISON",
          variant_id: variantId,
          default_on: false,
          registration: "UNREGISTERED_BBOX_SCALED",
          transform: bboxFitTransform(summary.spatial.scene_bounds, atlasBox),
        };
      });
      hybrid = {
        frame: atlasIndex.coordinates,
        body_bounds: atlasIndex.bounds,
        layers: [...layers, ...comparison],
        review_workflow: "Unregistered comparison layers can be reviewed in the studio; a review records the transform, metrics and reviewer decision.",
      };
    }

    systems.push({
      id: system.id,
      order: system.order,
      label: system.label,
      specialty: system.specialty,
      summary: system.summary,
      variants: variantIds,
      default_variant: variantIds.find((id) => variants[id].available) ?? variantIds[0],
      hybrid,
      limitations: system.limitations,
    });
  }

  const allTierBytes = Object.values(variants).flatMap((variant) => Object.values(variant.tiers ?? {}).map((tier) => tier.bytes));
  const manifest = {
    schema_version: "medtwin-anatomy-manifest-1.0.0",
    generated_at_utc: new Date().toISOString(),
    generator: "tools/asset-pipeline/build-manifest.mjs",
    curation: CURATION,
    representation_level: "L1_GENERIC_REFERENCE",
    notice:
      "All anatomy here is generic educational reference geometry. None of it is the patient's anatomy, and no finding is spatially registered to it.",
    mapping_categories: {
      SPATIALLY_REGISTERED: "Image-derived finding placed through validated registration. Not available: no registration is validated.",
      VERIFIED_ANATOMICAL_REGION: "A clinician-confirmed report statement naming a region that maps to a labelled atlas structure.",
      SCHEMATIC_ORGAN_ASSOCIATION: "Evidence associated with an organ by its documented text or analyte; the highlight is organ-level and schematic.",
      UNSUPPORTED_MAPPING: "Evidence with no defensible anatomical association.",
    },
    atlas_index_url: "/anatomy/atlas-index.json",
    atlas_attribution_url: "/anatomy/derived/atlas/ATTRIBUTION.md",
    totals: {
      systems: systems.length,
      variants: Object.keys(variants).length,
      available_variants: Object.values(variants).filter((variant) => variant.available).length,
      derived_bytes: allTierBytes.reduce((sum, bytes) => sum + bytes, 0),
      atlas_structures: atlasIndex.structures.filter((structure) => structure.kind === "structure").length,
    },
    systems,
    variants,
    excluded: EXCLUDED,
  };

  await mkdir(path.dirname(MANIFEST_PATH), { recursive: true });
  await writeFile(MANIFEST_PATH, JSON.stringify(manifest, null, 2));
  const atlasText = JSON.stringify(atlasIndex);
  await writeFile(ATLAS_INDEX_PATH, atlasText);
  await mkdir(path.dirname(BACKEND_ATLAS_PATH), { recursive: true });
  await writeFile(
    BACKEND_ATLAS_PATH,
    JSON.stringify({
      schema_version: "medtwin-atlas-structures-1.0.0",
      source: "Svitylo 3D Anatomy Atlas data 1.2.0 (Z-Anatomy terms, CC BY-SA 4.0)",
      atlas_index_sha256: sha256Bytes(Buffer.from(atlasText)),
      structures: atlasIndex.structures.map(({ id, parent, system, kind, side, name, name_la }) => ({ id, parent, system, kind, side, name, name_la })),
    }),
  );
  console.log(
    `manifest: ${systems.length} systems, ${manifest.totals.variants} variants (${manifest.totals.available_variants} available), ` +
      `${(manifest.totals.derived_bytes / 2 ** 20).toFixed(1)} MB derived; atlas index ${(atlasText.length / 2 ** 20).toFixed(2)} MB`,
  );
}

await main();
