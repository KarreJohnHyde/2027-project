// Inventory every anatomy GLB available to MedTwin without modifying it.
//
// Usage: node inspect.mjs [--only <substring>] [--skip-validator]
//
// Writes docs/anatomy/inventory/summary.json plus one detail file per asset.
// Measurements are structural facts about the files; none of them is evidence
// of anatomical accuracy.

import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { getBounds } from "@gltf-transform/core";
import validator from "gltf-validator";
import {
  INVENTORY_DIR,
  PROJECT_ROOT,
  assetIdFor,
  createIO,
  fileSize,
  parseGlbContainer,
  round,
  sha256Bytes,
  sha256File,
  toPosix,
  walkFiles,
} from "./lib.mjs";

const args = process.argv.slice(2);
const onlyFilter = args.includes("--only") ? args[args.indexOf("--only") + 1]?.toLowerCase() : null;
const skipValidator = args.includes("--skip-validator");

const MODE_NAMES = { 0: "POINTS", 1: "LINES", 2: "LINE_LOOP", 3: "LINE_STRIP", 4: "TRIANGLES", 5: "TRIANGLE_STRIP", 6: "TRIANGLE_FAN" };
const TOPOLOGY_VERTEX_CAP = 400_000;
const TOPOLOGY_ASSET_CAP = 3_000_000;

// Anatomical vocabulary used only to summarise which node names look anatomical.
const ANATOMY_TERMS = [
  "atri", "ventric", "valve", "aort", "pulmonary", "coronary", "vena", "cava", "septum", "myocard", "pericard", "artery", "arter", "vein", "venous",
  "lung", "lobe", "bronch", "trachea", "alveol", "pleura", "airway", "larynx", "diaphragm",
  "brain", "cortex", "cerebr", "cerebell", "gyrus", "sulcus", "lobe", "hippocamp", "thalam", "ventricle", "stem", "pons", "medulla", "white_matter", "frontal", "parietal", "temporal", "occipital",
  "liver", "hepat", "portal", "biliar", "gallbladder", "segment",
  "pancrea", "duoden", "spleen",
  "intestin", "colon", "ileum", "jejun", "cecum", "caecum", "rectum", "appendix", "sigmoid", "stomach", "esophag", "oesophag",
  "nerve", "spinal", "plexus", "ganglion", "cord",
  "bone", "skull", "cranium", "rib", "vertebra", "femur", "tibia", "fibula", "humerus", "radius", "ulna", "pelvis", "scapula", "clavicle", "sternum", "patella", "spine", "mandible", "skeleton", "muscle", "tendon",
  "kidney", "renal", "nephron", "glomerul", "tubul", "henle", "bowman", "ureter", "cortex", "pyramid", "calyx", "capsule", "collecting",
  "tumor", "tumour", "carcinoma", "nodule", "lesion",
];

// Exporter-generated names carry no anatomical meaning.
const GENERIC_NAME = /^(object_?\d*|rootnode|root|scene|sketchfab_model|sketchfab_scene|gltf_scenerootnode|defaultmaterial|material(_?\.?\d+)?|mat(_?\.?\d+)?|lambert\d*|phong\d*|blinn\d*|mesh(_?\d+)?|node(_?\d+)?|group\d*|polysurface\d*|pcube\d*|default|untitled.*|.*\.(fbx|obj|3ds|blend|dae|stl)|\(unnamed.*\)|scenecollection|collection(\.\d+)?|geode|cube(\.\d+)?|sphere(\.\d+)?|plane(\.\d+)?|cylinder(\.\d+)?|empty(\.\d+)?|\d+)$/i;

function isGenericName(name) {
  return !name || GENERIC_NAME.test(name.trim());
}

async function discover() {
  const isGlb = (file) => /\.(glb|gltf)$/i.test(file);
  const groups = [
    { source_group: "workspace_root", files: await walkFiles(PROJECT_ROOT, isGlb, { maxDepth: 0 }) },
    { source_group: "public_models", files: await walkFiles(path.join(PROJECT_ROOT, "public", "models"), isGlb, { maxDepth: 0 }) },
    { source_group: "source_folder", files: await walkFiles(path.join(PROJECT_ROOT, "source"), isGlb, { maxDepth: 2 }) },
    { source_group: "anatomy_main_repository", files: await walkFiles(path.join(PROJECT_ROOT, "anatomy-main", "public"), isGlb) },
    {
      source_group: "z_anatomy_atlas_1_2_0_standard",
      files: await walkFiles(path.join(PROJECT_ROOT, "3d-anatomy-atlas-main", "packages", "data", "releases", "1.2.0", "standard"), isGlb),
    },
  ];
  const nonGlbSources = [
    ...(await walkFiles(path.join(PROJECT_ROOT, "heart blender"), (f) => /\.blend$/i.test(f), { maxDepth: 0 })),
    ...(await walkFiles(path.join(PROJECT_ROOT, "source"), (f) => /\.(fbx|3ds|obj|blend)$/i.test(f), { maxDepth: 2 })),
  ];
  return { groups, nonGlbSources };
}

function imageDimensions(bytes, mimeType) {
  try {
    if (mimeType === "image/png" && bytes[0] === 0x89) {
      const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
      return [view.getUint32(16), view.getUint32(20)];
    }
    if (mimeType === "image/jpeg") {
      let offset = 2;
      while (offset < bytes.length) {
        if (bytes[offset] !== 0xff) return null;
        const marker = bytes[offset + 1];
        const length = (bytes[offset + 2] << 8) | bytes[offset + 3];
        if (marker >= 0xc0 && marker <= 0xcf && ![0xc4, 0xc8, 0xcc].includes(marker)) {
          return [(bytes[offset + 7] << 8) | bytes[offset + 8], (bytes[offset + 5] << 8) | bytes[offset + 6]];
        }
        offset += 2 + length;
      }
    }
  } catch {
    return null;
  }
  return null;
}

function primitiveElementCount(primitive) {
  const mode = primitive.getMode();
  const indices = primitive.getIndices();
  const position = primitive.getAttribute("POSITION");
  const count = indices ? indices.getCount() : position ? position.getCount() : 0;
  if (mode === 4) return { triangles: Math.floor(count / 3), points: 0, lines: 0 };
  if (mode === 5 || mode === 6) return { triangles: Math.max(0, count - 2), points: 0, lines: 0 };
  if (mode === 0) return { triangles: 0, points: count, lines: 0 };
  if (mode === 1) return { triangles: 0, points: 0, lines: Math.floor(count / 2) };
  return { triangles: 0, points: 0, lines: Math.max(0, count - 1) };
}

/**
 * Position-welded connectivity: connected components and the fraction of edges
 * used by exactly one triangle (0 means closed/watertight after welding).
 */
function topology(primitive, diagonal) {
  if (primitive.getMode() !== 4) return { status: "NOT_TRIANGLES" };
  const position = primitive.getAttribute("POSITION");
  if (!position) return { status: "NO_POSITION" };
  const vertexCount = position.getCount();
  if (vertexCount > TOPOLOGY_VERTEX_CAP) return { status: "SKIPPED_SIZE", vertex_count: vertexCount };
  const quantum = Math.max(diagonal, 1e-9) * 1e-6;
  const canonical = new Int32Array(vertexCount);
  const keyToId = new Map();
  const element = [0, 0, 0];
  let nonFinite = 0;
  for (let i = 0; i < vertexCount; i++) {
    position.getElement(i, element);
    if (!Number.isFinite(element[0]) || !Number.isFinite(element[1]) || !Number.isFinite(element[2])) nonFinite++;
    const key = `${Math.round(element[0] / quantum)},${Math.round(element[1] / quantum)},${Math.round(element[2] / quantum)}`;
    let id = keyToId.get(key);
    if (id === undefined) {
      id = keyToId.size;
      keyToId.set(key, id);
    }
    canonical[i] = id;
  }
  const parent = new Int32Array(keyToId.size).map((_, index) => index);
  const find = (x) => {
    while (parent[x] !== x) {
      parent[x] = parent[parent[x]];
      x = parent[x];
    }
    return x;
  };
  const union = (a, b) => {
    const ra = find(a);
    const rb = find(b);
    if (ra !== rb) parent[ra] = rb;
  };
  const indices = primitive.getIndices();
  const indexCount = indices ? indices.getCount() : vertexCount;
  const edgeUse = new Map();
  let degenerate = 0;
  for (let t = 0; t + 2 < indexCount; t += 3) {
    const a = canonical[indices ? indices.getScalar(t) : t];
    const b = canonical[indices ? indices.getScalar(t + 1) : t + 1];
    const c = canonical[indices ? indices.getScalar(t + 2) : t + 2];
    if (a === b || b === c || a === c) {
      degenerate++;
      continue;
    }
    union(a, b);
    union(b, c);
    for (const [u, v] of [[a, b], [b, c], [c, a]]) {
      const key = u < v ? u * 4294967296 + v : v * 4294967296 + u;
      edgeUse.set(key, (edgeUse.get(key) ?? 0) + 1);
    }
  }
  const roots = new Set();
  for (let i = 0; i < parent.length; i++) roots.add(find(i));
  let boundary = 0;
  let nonManifold = 0;
  for (const uses of edgeUse.values()) {
    if (uses === 1) boundary++;
    else if (uses > 2) nonManifold++;
  }
  return {
    status: "MEASURED",
    welded_vertex_count: keyToId.size,
    connected_components: roots.size,
    boundary_edge_fraction: round(edgeUse.size ? boundary / edgeUse.size : 0, 5),
    non_manifold_edge_fraction: round(edgeUse.size ? nonManifold / edgeUse.size : 0, 5),
    degenerate_triangles: degenerate,
    non_finite_positions: nonFinite,
  };
}

function boxOf(bounds) {
  const size = bounds.max.map((value, index) => value - bounds.min[index]);
  return {
    min: bounds.min.map((value) => round(value, 6)),
    max: bounds.max.map((value) => round(value, 6)),
    size: size.map((value) => round(value, 6)),
    center: bounds.min.map((value, index) => round((value + bounds.max[index]) / 2, 6)),
    diagonal: round(Math.hypot(...size), 6),
  };
}

function boundsFinite(bounds) {
  return bounds && [...bounds.min, ...bounds.max].every(Number.isFinite) && bounds.max.every((value, index) => value >= bounds.min[index]);
}

async function validate(bytes, name) {
  if (skipValidator) return { status: "SKIPPED" };
  try {
    const report = await validator.validateBytes(bytes, { uri: name, maxIssues: 200, writeTimestamp: false });
    const codes = {};
    for (const message of report.issues.messages) {
      const key = `${["ERROR", "WARNING", "INFO", "HINT"][message.severity] ?? message.severity}:${message.code}`;
      codes[key] = (codes[key] ?? 0) + 1;
    }
    return {
      status: report.issues.numErrors === 0 ? "VALID" : "INVALID",
      validator_version: report.validatorVersion,
      errors: report.issues.numErrors,
      warnings: report.issues.numWarnings,
      infos: report.issues.numInfos,
      hints: report.issues.numHints,
      truncated: report.issues.truncated,
      issue_codes: codes,
      draw_calls: report.info?.drawCallCount ?? null,
      validator_triangle_count: report.info?.totalTriangleCount ?? null,
      validator_vertex_count: report.info?.totalVertexCount ?? null,
    };
  } catch (error) {
    return { status: "VALIDATOR_FAILED", error: String(error?.message ?? error) };
  }
}

async function inspectAsset(io, absolutePath, sourceGroup) {
  const relativePath = toPosix(path.relative(PROJECT_ROOT, absolutePath));
  const started = performance.now();
  const bytes = new Uint8Array(await readFile(absolutePath));
  const container = parseGlbContainer(bytes);
  const json = container.json ?? {};
  const record = {
    asset_id: assetIdFor(relativePath),
    relative_path: relativePath,
    source_group: sourceGroup,
    bytes: bytes.byteLength,
    sha256: sha256Bytes(bytes),
    container: { valid: container.valid, chunks: container.chunks, problems: container.problems },
    gltf: {
      version: json.asset?.version ?? null,
      generator: json.asset?.generator ?? null,
      copyright: json.asset?.copyright ?? null,
      asset_extras: json.asset?.extras ?? null,
      extensions_used: json.extensionsUsed ?? [],
      extensions_required: json.extensionsRequired ?? [],
    },
  };
  record.validation = await validate(bytes, path.basename(absolutePath));

  let document;
  try {
    document = await io.readBinary(bytes);
  } catch (error) {
    record.load = { status: "LOAD_FAILED", error: String(error?.message ?? error) };
    record.inspection_ms = Math.round(performance.now() - started);
    return { summary: record, detail: record };
  }
  const root = document.getRoot();
  const scenes = root.listScenes();
  const scene = root.getDefaultScene() ?? scenes[0] ?? null;
  const sceneBounds = scene ? getBounds(scene) : null;
  const finiteBounds = boundsFinite(sceneBounds);
  const sceneBox = finiteBounds ? boxOf(sceneBounds) : null;
  const diagonal = sceneBox?.diagonal ?? 1;

  // Mesh statistics (unique meshes) and rendered statistics (per node instance).
  const meshStats = new Map();
  let topologyBudget = TOPOLOGY_ASSET_CAP;
  for (const mesh of root.listMeshes()) {
    const stats = { name: mesh.getName() || null, primitives: [], triangles: 0, points: 0, lines: 0, vertices: 0 };
    for (const primitive of mesh.listPrimitives()) {
      const position = primitive.getAttribute("POSITION");
      const counts = primitiveElementCount(primitive);
      const vertexCount = position ? position.getCount() : 0;
      let topo = { status: "SKIPPED_ASSET_BUDGET" };
      if (topologyBudget > 0 && vertexCount <= TOPOLOGY_VERTEX_CAP) {
        topo = topology(primitive, diagonal);
        topologyBudget -= vertexCount;
      } else if (vertexCount > TOPOLOGY_VERTEX_CAP) {
        topo = { status: "SKIPPED_SIZE", vertex_count: vertexCount };
      }
      stats.primitives.push({
        mode: MODE_NAMES[primitive.getMode()] ?? String(primitive.getMode()),
        vertex_count: vertexCount,
        indexed: Boolean(primitive.getIndices()),
        attributes: primitive.listSemantics(),
        has_normals: Boolean(primitive.getAttribute("NORMAL")),
        has_uv: Boolean(primitive.getAttribute("TEXCOORD_0")),
        material: primitive.getMaterial()?.getName() || null,
        morph_targets: primitive.listTargets().length,
        ...counts,
        topology: topo,
      });
      stats.triangles += counts.triangles;
      stats.points += counts.points;
      stats.lines += counts.lines;
      stats.vertices += vertexCount;
    }
    meshStats.set(mesh, stats);
  }

  const nodeRecords = [];
  let renderedTriangles = 0;
  let renderedPoints = 0;
  let largestMeshNode = null;
  function visit(node, depth, parentPath, inheritedName) {
    const name = node.getName() || "(unnamed)";
    const nodePath = parentPath ? `${parentPath}/${name}` : name;
    const mesh = node.getMesh();
    const ownMeaningful = isGenericName(name) ? null : name;
    const materialName = mesh?.listPrimitives()[0]?.getMaterial()?.getName() || null;
    const semanticName = ownMeaningful ?? inheritedName ?? (materialName && !isGenericName(materialName) ? materialName : null);
    let worldBox = null;
    if (mesh) {
      const stats = meshStats.get(mesh);
      renderedTriangles += stats.triangles;
      renderedPoints += stats.points;
      const nodeBounds = getBounds(node);
      if (boundsFinite(nodeBounds)) worldBox = boxOf(nodeBounds);
      if (worldBox && (!largestMeshNode || worldBox.diagonal > largestMeshNode.box.diagonal)) {
        largestMeshNode = { name, box: worldBox };
      }
    }
    nodeRecords.push({
      path: nodePath,
      name,
      semantic_name: semanticName,
      depth,
      mesh: mesh ? mesh.getName() || "(unnamed mesh)" : null,
      material: materialName,
      triangles: mesh ? meshStats.get(mesh).triangles : 0,
      children: node.listChildren().length,
      has_transform: node.getMatrix().some((value, index) => value !== [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1][index]),
      world_bounds: worldBox,
    });
    for (const child of node.listChildren()) visit(child, depth + 1, nodePath, ownMeaningful ?? inheritedName);
  }
  if (scene) for (const child of scene.listChildren()) visit(child, 0, "", null);

  // Heuristic: mesh nodes whose world box lies strictly inside the largest mesh
  // node's box may be internal structures. This is geometry, not anatomy proof.
  let nestedMeshNodes = 0;
  if (largestMeshNode) {
    const outer = largestMeshNode.box;
    const margin = outer.size.map((value) => value * 0.02);
    for (const node of nodeRecords) {
      if (!node.world_bounds || node.name === largestMeshNode.name) continue;
      const inner = node.world_bounds;
      const inside = inner.min.every((value, axis) => value >= outer.min[axis] + margin[axis]) && inner.max.every((value, axis) => value <= outer.max[axis] - margin[axis]);
      if (inside) nestedMeshNodes++;
    }
  }

  const meshNodeNames = nodeRecords.filter((node) => node.mesh).map((node) => node.semantic_name ?? node.name);
  const anatomicalNames = meshNodeNames.filter((name) => {
    const lower = name.toLowerCase();
    return ANATOMY_TERMS.some((term) => lower.includes(term));
  });

  const materials = root.listMaterials().map((material) => ({
    name: material.getName() || null,
    alpha_mode: material.getAlphaMode(),
    alpha_cutoff: material.getAlphaMode() === "MASK" ? material.getAlphaCutoff() : null,
    base_color_alpha: round(material.getBaseColorFactor()[3], 4),
    double_sided: material.getDoubleSided(),
    textures: {
      base_color: Boolean(material.getBaseColorTexture()),
      normal: Boolean(material.getNormalTexture()),
      metallic_roughness: Boolean(material.getMetallicRoughnessTexture()),
      occlusion: Boolean(material.getOcclusionTexture()),
      emissive: Boolean(material.getEmissiveTexture()),
    },
    extensions: material.listExtensions().map((extension) => extension.extensionName),
  }));

  const textures = root.listTextures().map((texture) => {
    const image = texture.getImage();
    const mimeType = texture.getMimeType();
    let size = null;
    try {
      size = texture.getSize();
    } catch {
      size = null;
    }
    return {
      name: texture.getName() || texture.getURI() || null,
      mime_type: mimeType,
      bytes: image ? image.byteLength : 0,
      dimensions: size ?? (image ? imageDimensions(image, mimeType) : null),
    };
  });

  const primitiveList = [...meshStats.values()].flatMap((stats) => stats.primitives);
  const measuredTopology = primitiveList.map((primitive) => primitive.topology).filter((topo) => topo.status === "MEASURED");
  const sizeSorted = sceneBox ? [...sceneBox.size].sort((a, b) => b - a) : null;
  const tallestAxis = sceneBox ? ["x", "y", "z"][sceneBox.size.indexOf(Math.max(...sceneBox.size))] : null;
  const maxTextureEdge = textures.reduce((max, texture) => Math.max(max, ...(texture.dimensions ?? [0])), 0);

  const summary = {
    ...record,
    load: { status: "LOADED" },
    counts: {
      scenes: scenes.length,
      nodes: root.listNodes().length,
      mesh_nodes: meshNodeNames.length,
      meshes: root.listMeshes().length,
      primitives: primitiveList.length,
      materials: materials.length,
      textures: textures.length,
      animations: root.listAnimations().length,
      skins: root.listSkins().length,
      cameras: root.listCameras().length,
    },
    geometry: {
      unique_triangles: [...meshStats.values()].reduce((sum, stats) => sum + stats.triangles, 0),
      rendered_triangles: renderedTriangles,
      unique_vertices: [...meshStats.values()].reduce((sum, stats) => sum + stats.vertices, 0),
      points: renderedPoints,
      primitive_modes: [...new Set(primitiveList.map((primitive) => primitive.mode))],
      primitives_without_normals: primitiveList.filter((primitive) => !primitive.has_normals && primitive.mode === "TRIANGLES").length,
      primitives_without_uv: primitiveList.filter((primitive) => !primitive.has_uv).length,
      unindexed_primitives: primitiveList.filter((primitive) => !primitive.indexed).length,
      morph_target_primitives: primitiveList.filter((primitive) => primitive.morph_targets > 0).length,
      topology_measured_primitives: measuredTopology.length,
      topology_skipped_primitives: primitiveList.length - measuredTopology.length,
      connected_components_measured: measuredTopology.reduce((sum, topo) => sum + topo.connected_components, 0),
      closed_measured_primitives: measuredTopology.filter((topo) => topo.boundary_edge_fraction === 0).length,
      max_boundary_edge_fraction: measuredTopology.reduce((max, topo) => Math.max(max, topo.boundary_edge_fraction), 0),
      degenerate_triangles_measured: measuredTopology.reduce((sum, topo) => sum + topo.degenerate_triangles, 0),
      non_finite_positions_measured: measuredTopology.reduce((sum, topo) => sum + topo.non_finite_positions, 0),
    },
    spatial: {
      scene_bounds: sceneBox,
      bounds_finite: finiteBounds,
      tallest_axis: tallestAxis,
      aspect_ratio: sizeSorted && sizeSorted[2] > 0 ? round(sizeSorted[0] / sizeSorted[2], 3) : null,
      root_transform_present: nodeRecords.some((node) => node.depth === 0 && node.has_transform),
      nested_mesh_nodes_inside_largest: nestedMeshNodes,
      largest_mesh_node: largestMeshNode?.name ?? null,
      unit_note: "glTF declares metres; source authoring units are not verifiable from the file.",
    },
    materials_summary: {
      blend: materials.filter((material) => material.alpha_mode === "BLEND").length,
      mask: materials.filter((material) => material.alpha_mode === "MASK").length,
      transmission: materials.filter((material) => material.extensions.includes("KHR_materials_transmission")).length,
      unlit: materials.filter((material) => material.extensions.includes("KHR_materials_unlit")).length,
      double_sided: materials.filter((material) => material.double_sided).length,
      names: materials.map((material) => material.name).slice(0, 60),
    },
    textures_summary: {
      count: textures.length,
      total_bytes: textures.reduce((sum, texture) => sum + texture.bytes, 0),
      max_edge_px: maxTextureEdge,
      mime_types: [...new Set(textures.map((texture) => texture.mime_type))],
    },
    naming: {
      mesh_node_names_sample: meshNodeNames.slice(0, 80),
      anatomically_named_mesh_nodes: anatomicalNames.length,
      anatomical_names_sample: [...new Set(anatomicalNames)].slice(0, 80),
    },
    inspection_ms: Math.round(performance.now() - started),
  };
  const detail = { ...summary, nodes: nodeRecords, meshes: [...meshStats.values()], materials, textures };
  return { summary, detail };
}

async function main() {
  const io = await createIO();
  const { groups, nonGlbSources } = await discover();
  await mkdir(INVENTORY_DIR, { recursive: true });
  const summaries = [];
  const tasks = groups.flatMap((group) => group.files.map((file) => ({ file, group: group.source_group })));
  const selected = onlyFilter ? tasks.filter((task) => task.file.toLowerCase().includes(onlyFilter)) : tasks;
  let index = 0;
  for (const task of selected) {
    index++;
    const label = toPosix(path.relative(PROJECT_ROOT, task.file));
    process.stdout.write(`[${index}/${selected.length}] ${label} ... `);
    try {
      const { summary, detail } = await inspectAsset(io, task.file, task.group);
      await writeFile(path.join(INVENTORY_DIR, `${summary.asset_id}.json`), JSON.stringify(detail, null, 2));
      summaries.push(summary);
      console.log(`${summary.load?.status} ${summary.validation?.status} tris=${summary.geometry?.rendered_triangles ?? "?"} ${summary.inspection_ms}ms`);
    } catch (error) {
      console.log(`FAILED ${error.message}`);
      summaries.push({ asset_id: assetIdFor(label), relative_path: label, source_group: task.group, load: { status: "INSPECTION_FAILED", error: String(error.message) } });
    }
  }

  const sourceFiles = [];
  for (const file of nonGlbSources) {
    const bytes = await fileSize(file);
    sourceFiles.push({
      relative_path: toPosix(path.relative(PROJECT_ROOT, file)),
      format: path.extname(file).slice(1).toLowerCase(),
      bytes,
      sha256: await sha256File(file),
      parsed: false,
      note: "Authoring source retained unchanged; not parsed by the GLB inventory.",
    });
  }

  if (onlyFilter) {
    console.log(`Filtered run (${onlyFilter}); summary.json not rewritten.`);
    return;
  }
  const output = {
    schema_version: "medtwin-anatomy-inventory-1.0.0",
    generated_at_utc: new Date().toISOString(),
    generator: "tools/asset-pipeline/inspect.mjs",
    scope_notice:
      "Structural file inspection only. Counts, bounds, validator results and topology metrics do not establish anatomical accuracy, licensing, or patient relevance.",
    totals: {
      glb_assets: summaries.length,
      loaded: summaries.filter((item) => item.load?.status === "LOADED").length,
      validator_valid: summaries.filter((item) => item.validation?.status === "VALID").length,
      bytes: summaries.reduce((sum, item) => sum + (item.bytes ?? 0), 0),
    },
    assets: summaries,
    authoring_sources: sourceFiles,
  };
  await writeFile(path.join(INVENTORY_DIR, "summary.json"), JSON.stringify(output, null, 2));
  console.log(`Wrote ${summaries.length} asset records and ${sourceFiles.length} authoring-source records.`);
}

await main();
