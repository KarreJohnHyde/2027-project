import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { MeshoptDecoder } from "three/examples/jsm/libs/meshopt_decoder.module.js";

if (typeof globalThis.ProgressEvent === "undefined") {
  globalThis.ProgressEvent = class ProgressEvent {};
}

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const registryPath = path.join(projectRoot, "public", "models", "registry.json");
const registry = JSON.parse(await fs.readFile(registryPath, "utf8"));
const loader = new GLTFLoader();
loader.setMeshoptDecoder(MeshoptDecoder);
const results = [];

for (const asset of registry.assets) {
  const localPath = path.join(projectRoot, "public", asset.path.replace(/^\//, ""));
  const bytes = await fs.readFile(localPath);
  const buffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  const gltf = await new Promise((resolve, reject) => loader.parse(buffer, "", resolve, reject));
  let meshes = 0;
  let triangles = 0;
  gltf.scene.traverse((object) => {
    if (!object.isMesh) return;
    meshes += 1;
    const geometry = object.geometry;
    triangles += geometry.index
      ? Math.floor(geometry.index.count / 3)
      : Math.floor((geometry.attributes.position?.count ?? 0) / 3);
  });
  if (meshes < 1 || triangles < 1) throw new Error(`${asset.id} contains no renderable mesh.`);
  results.push({ id: asset.id, bytes: bytes.length, meshes, triangles, valid: true });
}

console.log(JSON.stringify({ schema_version: registry.schema_version, assets: results }, null, 2));
