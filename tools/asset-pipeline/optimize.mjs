// Generate browser-ready derivatives from the immutable original GLBs.
//
// Usage: node optimize.mjs [--only <variant-id-substring>] [--force]
//
// Tiers
//   standard  Same triangles as the original. Lossless repack, 16-bit position
//             quantisation (KHR_mesh_quantization), meshopt buffer compression,
//             textures re-encoded as WebP with a 2048 px ceiling.
//   preview   Only for assets above PREVIEW_TRIANGLE_THRESHOLD. Adds meshopt
//             simplification bounded by a relative error, and 1024 px textures.
//             Always labelled as reduced detail.
//
// Each output is re-read, re-validated, and compared with the original's
// world-space bounds and triangle count. Results go to docs/anatomy/derivatives.json.

import { copyFile, mkdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { getBounds, PropertyType } from "@gltf-transform/core";
import { EXTMeshoptCompression, KHRMaterialsPBRSpecularGlossiness } from "@gltf-transform/extensions";
import { dedup, metalRough, prune, quantize, reorder, simplify, textureCompress, weld } from "@gltf-transform/functions";
import validator from "gltf-validator";
import { MeshoptEncoder, MeshoptSimplifier } from "meshoptimizer";
import sharp from "sharp";
import { CURATION, SYSTEMS } from "./catalog.mjs";
import { DERIVED_DIR, PROJECT_ROOT, createIO, round, sha256Bytes, toPosix } from "./lib.mjs";

const args = process.argv.slice(2);
const onlyFilter = args.includes("--only") ? args[args.indexOf("--only") + 1] : null;
const force = args.includes("--force");
const REPORT_PATH = path.join(PROJECT_ROOT, "docs", "anatomy", "derivatives.json");
const ATLAS_RELEASE = path.join(PROJECT_ROOT, "3d-anatomy-atlas-main", "packages", "data", "releases", "1.2.0");
const PREVIEW_TRIANGLE_THRESHOLD = 600_000;

const STANDARD = { maxTexture: 2048, colorQuality: 90, positionBits: 16, normalBits: 12, texcoordBits: 14 };
const PREVIEW = { maxTexture: 1024, colorQuality: 80, ratio: 0.25, error: 0.002 };

function countTriangles(document) {
  let triangles = 0;
  let points = 0;
  for (const mesh of document.getRoot().listMeshes()) {
    for (const primitive of mesh.listPrimitives()) {
      const indices = primitive.getIndices();
      const count = indices ? indices.getCount() : primitive.getAttribute("POSITION")?.getCount() ?? 0;
      const mode = primitive.getMode();
      if (mode === 4) triangles += Math.floor(count / 3);
      else if (mode === 5 || mode === 6) triangles += Math.max(0, count - 2);
      else if (mode === 0) points += count;
    }
  }
  // Count per node instance, matching what the renderer draws.
  let rendered = 0;
  for (const node of document.getRoot().listNodes()) {
    const mesh = node.getMesh();
    if (!mesh) continue;
    for (const primitive of mesh.listPrimitives()) {
      const indices = primitive.getIndices();
      const count = indices ? indices.getCount() : primitive.getAttribute("POSITION")?.getCount() ?? 0;
      if (primitive.getMode() === 4) rendered += Math.floor(count / 3);
    }
  }
  return { unique_triangles: triangles, rendered_triangles: rendered, points };
}

function sceneBounds(document) {
  const scene = document.getRoot().getDefaultScene() ?? document.getRoot().listScenes()[0];
  const bounds = getBounds(scene);
  const size = bounds.max.map((value, index) => value - bounds.min[index]);
  return { min: bounds.min, max: bounds.max, diagonal: Math.hypot(...size) };
}

function meshNodeNames(document) {
  return document
    .getRoot()
    .listNodes()
    .filter((node) => node.getMesh())
    .map((node) => node.getName());
}

function texturesSummary(document) {
  return document
    .getRoot()
    .listTextures()
    .map((texture) => ({ mime_type: texture.getMimeType(), bytes: texture.getImage()?.byteLength ?? 0, size: safeSize(texture) }));
}

function safeSize(texture) {
  try {
    return texture.getSize();
  } catch {
    return null;
  }
}

async function validateBytes(bytes, name) {
  const report = await validator.validateBytes(bytes, { uri: name, maxIssues: 100, writeTimestamp: false });
  const errors = report.issues.messages.filter((message) => message.severity === 0).map((message) => message.code);
  return { errors: report.issues.numErrors, warnings: report.issues.numWarnings, error_codes: [...new Set(errors)] };
}

async function buildTier(io, sourceBytes, tier) {
  const document = await io.readBinary(sourceBytes);
  const transforms = [];
  const root = document.getRoot();
  const hasSpecGloss = root.listMaterials().some((material) => material.getExtension("KHR_materials_pbrSpecularGlossiness"));

  // Materials are intentionally excluded from dedup: identical-looking materials
  // carry distinct anatomical names that the studio uses as structure labels.
  await document.transform(
    dedup({ propertyTypes: [PropertyType.ACCESSOR, PropertyType.TEXTURE] }),
    prune({ keepLeaves: true, keepAttributes: true, keepIndices: true }),
  );
  transforms.push("dedup(accessors, textures)", "prune(unused resources; empty hierarchy nodes kept)");
  const skinned = root.listSkins().length > 0;

  if (hasSpecGloss) {
    await document.transform(metalRough());
    transforms.push("metalRough(): KHR_materials_pbrSpecularGlossiness converted to metallic-roughness (three.js dropped spec-gloss support)");
    for (const extension of root.listExtensionsUsed()) {
      if (extension.extensionName === KHRMaterialsPBRSpecularGlossiness.EXTENSION_NAME) extension.dispose();
    }
  }

  if (tier === "preview") {
    await document.transform(weld(), simplify({ simplifier: MeshoptSimplifier, ratio: PREVIEW.ratio, error: PREVIEW.error, lockBorder: true }));
    transforms.push(`weld(exact)`, `simplify(meshoptimizer, target_ratio=${PREVIEW.ratio}, max_error=${PREVIEW.error} of mesh radius, lockBorder)`);
  }

  if (root.listTextures().length > 0) {
    const maxTexture = tier === "preview" ? PREVIEW.maxTexture : STANDARD.maxTexture;
    const quality = tier === "preview" ? PREVIEW.colorQuality : STANDARD.colorQuality;
    await document.transform(
      textureCompress({ encoder: sharp, targetFormat: "webp", resize: [maxTexture, maxTexture], slots: /^(?!normalTexture$).*/, quality }),
      textureCompress({ encoder: sharp, targetFormat: "webp", resize: [maxTexture, maxTexture], slots: /^normalTexture$/, lossless: tier === "standard", quality: 92 }),
    );
    transforms.push(
      `textureCompress(webp, max ${maxTexture}px, colour/data quality ${quality})`,
      `textureCompress(webp, max ${maxTexture}px, normal maps ${tier === "standard" ? "lossless" : "quality 92"})`,
    );
  }

  // Quantising a skinned mesh rewrites its inverse bind matrices; skinned
  // positions and normals therefore stay in float so the bind pose is untouched.
  await document.transform(
    reorder({ encoder: MeshoptEncoder, target: "size" }),
    quantize({
      pattern: skinned ? /^(TEXCOORD|COLOR)_/ : /.*/,
      quantizePosition: STANDARD.positionBits,
      quantizeNormal: STANDARD.normalBits,
      quantizeTexcoord: STANDARD.texcoordBits,
      quantizeColor: 8,
      quantizeGeneric: 16,
      quantizationVolume: "mesh",
      cleanup: false,
    }),
  );
  transforms.push(
    "reorder(meshopt vertex/index order; triangles unchanged)",
    skinned
      ? `quantize(texcoord ${STANDARD.texcoordBits} bit only; skinned mesh positions/normals kept in float)`
      : `quantize(position ${STANDARD.positionBits} bit, normal ${STANDARD.normalBits} bit, texcoord ${STANDARD.texcoordBits} bit, per-mesh volume)`,
  );
  document.createExtension(EXTMeshoptCompression).setRequired(true).setEncoderOptions({ method: EXTMeshoptCompression.EncoderMethod.QUANTIZE });
  transforms.push("EXT_meshopt_compression(buffer compression, lossless over quantised data)");
  document.getRoot().getAsset().generator = "MedTwin asset pipeline (gltf-transform 4.5.1)";
  document.getRoot().getAsset().extras = {
    ...(document.getRoot().getAsset().extras ?? {}),
    medtwin_derivative: { tier, curated_on: CURATION.curated_on, original_is_authoritative: true },
  };

  const bytes = await io.writeBinary(document);
  return { bytes, transforms };
}

async function verify(io, originalDocument, derivedBytes, tier) {
  const derived = await io.readBinary(derivedBytes);
  const before = countTriangles(originalDocument);
  const after = countTriangles(derived);
  const b0 = sceneBounds(originalDocument);
  const b1 = sceneBounds(derived);
  const deviation = Math.max(...b0.min.map((value, axis) => Math.abs(value - b1.min[axis])), ...b0.max.map((value, axis) => Math.abs(value - b1.max[axis])));
  const relativeDeviation = b0.diagonal > 0 ? deviation / b0.diagonal : null;
  const originalNames = new Set(meshNodeNames(originalDocument));
  const derivedNames = new Set(meshNodeNames(derived));
  const missingNames = [...originalNames].filter((name) => !derivedNames.has(name));
  const triangleRatio = before.rendered_triangles > 0 ? after.rendered_triangles / before.rendered_triangles : null;
  const checks = {
    triangles_identical: before.rendered_triangles === after.rendered_triangles && before.points === after.points,
    bounds_relative_deviation: round(relativeDeviation, 8),
    bounds_within_tolerance: relativeDeviation !== null && relativeDeviation <= (tier === "standard" ? 1e-4 : 5e-3),
    mesh_node_names_preserved: missingNames.length === 0,
    missing_mesh_node_names: missingNames.slice(0, 20),
  };
  const passed =
    checks.bounds_within_tolerance && checks.mesh_node_names_preserved && (tier === "preview" ? true : checks.triangles_identical);
  return { passed, before, after, triangle_ratio: round(triangleRatio, 4), checks, textures: texturesSummary(derived) };
}

async function deriveVariant(io, variant, previous) {
  const sourcePath = path.join(PROJECT_ROOT, variant.source);
  const sourceBytes = new Uint8Array(await readFile(sourcePath));
  const sourceSha = sha256Bytes(sourceBytes);
  const prior = previous?.variants?.[variant.id];
  if (!force && prior?.source_sha256 === sourceSha && prior.tiers?.standard?.passed) {
    return { ...prior, reused: true };
  }
  const originalDocument = await io.readBinary(sourceBytes);
  const sourceTriangles = countTriangles(originalDocument);
  const record = {
    variant_id: variant.id,
    source: toPosix(variant.source),
    source_sha256: sourceSha,
    source_bytes: sourceBytes.byteLength,
    source_validation: await validateBytes(sourceBytes, path.basename(sourcePath)),
    tiers: {},
  };
  const tiers = ["standard"];
  if (sourceTriangles.rendered_triangles > PREVIEW_TRIANGLE_THRESHOLD) tiers.push("preview");
  for (const tier of tiers) {
    const started = performance.now();
    const { bytes, transforms } = await buildTier(io, sourceBytes, tier);
    const verification = await verify(io, originalDocument, bytes, tier);
    const validation = await validateBytes(bytes, `${variant.id}-${tier}.glb`);
    const outputDir = path.join(DERIVED_DIR, variant.id);
    await mkdir(outputDir, { recursive: true });
    const outputPath = path.join(outputDir, `${tier}.glb`);
    await writeFile(outputPath, bytes);
    record.tiers[tier] = {
      url: `/anatomy/derived/${variant.id}/${tier}.glb`,
      bytes: bytes.byteLength,
      sha256: sha256Bytes(bytes),
      compression_ratio: round(sourceBytes.byteLength / bytes.byteLength, 2),
      transforms,
      geometry_changed: tier === "preview",
      validation,
      ...verification,
      passed: verification.passed && validation.errors === 0,
      build_ms: Math.round(performance.now() - started),
    };
  }
  return record;
}

async function copyAtlas() {
  const manifest = JSON.parse(await readFile(path.join(ATLAS_RELEASE, "manifest.json"), "utf8"));
  const files = [];
  for (const chunk of manifest.chunks) {
    for (const quality of ["standard", "economy"]) {
      const file = chunk.files[quality];
      const source = path.join(ATLAS_RELEASE, file.path);
      const bytes = new Uint8Array(await readFile(source));
      const sha = sha256Bytes(bytes);
      if (sha !== file.sha256) throw new Error(`Atlas checksum mismatch for ${file.path}`);
      const target = path.join(DERIVED_DIR, "atlas", file.path);
      await mkdir(path.dirname(target), { recursive: true });
      const existing = await stat(target).catch(() => null);
      if (!existing || existing.size !== bytes.byteLength) await writeFile(target, bytes);
      files.push({ chunk: chunk.id, quality, url: `/anatomy/derived/atlas/${file.path}`, bytes: bytes.byteLength, sha256: sha, sha256_matches_release: true });
    }
  }
  for (const name of ["ATTRIBUTION.md", "LICENSES.md"]) {
    await copyFile(path.join(ATLAS_RELEASE, name), path.join(DERIVED_DIR, "atlas", name));
  }
  return { release: manifest.version, channel: manifest.channel, content_hash: manifest.contentHash, files };
}

async function main() {
  const io = await createIO();
  const previous = await readFile(REPORT_PATH, "utf8").then(JSON.parse).catch(() => null);
  const variants = SYSTEMS.flatMap((system) => system.variants.map((variant) => ({ ...variant, system_id: system.id })));
  const selected = onlyFilter ? variants.filter((variant) => variant.id.includes(onlyFilter)) : variants;
  const report = previous && onlyFilter ? previous : { variants: {} };
  report.schema_version = "medtwin-anatomy-derivatives-1.0.0";
  report.generated_at_utc = new Date().toISOString();
  report.generator = "tools/asset-pipeline/optimize.mjs";
  report.policy = {
    originals: "Read-only. Derivatives never replace or modify source files.",
    standard: "Triangle count identical to source; bounds deviation <= 1e-4 of the diagonal; mesh node names preserved.",
    preview: `Generated only above ${PREVIEW_TRIANGLE_THRESHOLD.toLocaleString("en")} triangles; simplified with a bounded error and labelled reduced-detail.`,
  };
  for (const variant of selected) {
    process.stdout.write(`${variant.id} ... `);
    try {
      const record = await deriveVariant(io, variant, previous);
      report.variants[variant.id] = { ...record, system_id: variant.system_id };
      const tiers = Object.entries(record.tiers)
        .map(([tier, value]) => `${tier}:${value.passed ? "PASS" : "FAIL"} ${(value.bytes / 2 ** 20).toFixed(1)}MB tris ${value.after.rendered_triangles} dev ${value.checks.bounds_relative_deviation}`)
        .join(" | ");
      console.log(`${record.reused ? "(reused) " : ""}${tiers}`);
    } catch (error) {
      console.log(`FAILED ${error.stack ?? error}`);
      report.variants[variant.id] = { variant_id: variant.id, system_id: variant.system_id, source: variant.source, failed: String(error.message ?? error) };
    }
  }
  if (!onlyFilter) {
    process.stdout.write("atlas release copy ... ");
    report.atlas = await copyAtlas();
    console.log(`${report.atlas.files.length} files verified against release checksums`);
  }
  await mkdir(path.dirname(REPORT_PATH), { recursive: true });
  await writeFile(REPORT_PATH, JSON.stringify(report, null, 2));
}

await main();
