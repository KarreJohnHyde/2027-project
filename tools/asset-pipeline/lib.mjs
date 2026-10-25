// Shared helpers for the MedTwin anatomy asset pipeline.
// Every function here treats source assets as read-only inputs.

import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { readdir, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { NodeIO } from "@gltf-transform/core";
import { ALL_EXTENSIONS } from "@gltf-transform/extensions";
import draco3d from "draco3dgltf";
import { MeshoptDecoder, MeshoptEncoder, MeshoptSimplifier } from "meshoptimizer";

export const PIPELINE_DIR = path.dirname(fileURLToPath(import.meta.url));
export const PROJECT_ROOT = path.resolve(PIPELINE_DIR, "..", "..");
export const INVENTORY_DIR = path.join(PROJECT_ROOT, "docs", "anatomy", "inventory");
export const DERIVED_DIR = path.join(PROJECT_ROOT, "public", "anatomy", "derived");
export const MANIFEST_PATH = path.join(PROJECT_ROOT, "public", "anatomy", "manifest.json");

export async function createIO() {
  await Promise.all([MeshoptDecoder.ready, MeshoptEncoder.ready, MeshoptSimplifier.ready]);
  return new NodeIO()
    .registerExtensions(ALL_EXTENSIONS)
    .registerDependencies({
      "draco3d.decoder": await draco3d.createDecoderModule(),
      "draco3d.encoder": await draco3d.createEncoderModule(),
      "meshopt.decoder": MeshoptDecoder,
      "meshopt.encoder": MeshoptEncoder,
    });
}

export function sha256File(filePath) {
  return new Promise((resolve, reject) => {
    const hash = createHash("sha256");
    createReadStream(filePath)
      .on("data", (chunk) => hash.update(chunk))
      .on("error", reject)
      .on("end", () => resolve(hash.digest("hex")));
  });
}

export function sha256Bytes(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

/** Stable identifier derived from the project-relative path. */
export function assetIdFor(relativePath) {
  return relativePath
    .toLowerCase()
    .replace(/\.(glb|gltf)$/, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function toPosix(relativePath) {
  return relativePath.split(path.sep).join("/");
}

/** Parse the 12-byte GLB header and chunk table without trusting declared sizes. */
export function parseGlbContainer(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const problems = [];
  if (bytes.byteLength < 20) return { valid: false, problems: ["File is shorter than a GLB header."] };
  const magic = view.getUint32(0, true);
  const version = view.getUint32(4, true);
  const declaredLength = view.getUint32(8, true);
  if (magic !== 0x46546c67) problems.push("Missing glTF magic.");
  if (version !== 2) problems.push(`Unsupported container version ${version}.`);
  if (declaredLength !== bytes.byteLength) {
    problems.push(`Declared length ${declaredLength} differs from file length ${bytes.byteLength}.`);
  }
  const chunks = [];
  let offset = 12;
  while (offset + 8 <= bytes.byteLength) {
    const chunkLength = view.getUint32(offset, true);
    const chunkType = view.getUint32(offset + 4, true);
    const typeName = chunkType === 0x4e4f534a ? "JSON" : chunkType === 0x004e4942 ? "BIN" : `0x${chunkType.toString(16)}`;
    if (chunkLength % 4 !== 0) problems.push(`${typeName} chunk length is not 4-byte aligned.`);
    if (offset + 8 + chunkLength > bytes.byteLength) {
      problems.push(`${typeName} chunk overruns the file.`);
      break;
    }
    chunks.push({ type: typeName, byteLength: chunkLength });
    offset += 8 + chunkLength;
  }
  if (chunks[0]?.type !== "JSON") problems.push("First chunk is not JSON.");
  let json = null;
  if (chunks[0]?.type === "JSON") {
    try {
      json = JSON.parse(new TextDecoder().decode(bytes.subarray(20, 20 + chunks[0].byteLength)));
    } catch (error) {
      problems.push(`JSON chunk does not parse: ${error.message}`);
    }
  }
  return { valid: problems.length === 0, magic, version, declaredLength, chunks, json, problems };
}

export async function walkFiles(directory, predicate, { maxDepth = 8 } = {}) {
  const results = [];
  async function visit(current, depth) {
    let entries;
    try {
      entries = await readdir(current, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) {
        if (depth < maxDepth && !["node_modules", ".git", "dist"].includes(entry.name)) await visit(full, depth + 1);
      } else if (predicate(full)) {
        results.push(full);
      }
    }
  }
  await visit(directory, 0);
  return results;
}

export async function fileSize(filePath) {
  return (await stat(filePath)).size;
}

export function round(value, digits = 4) {
  if (value === null || value === undefined || !Number.isFinite(value)) return null;
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}
