import type { AnatomyManifest, AnatomyVariant, AtlasIndex, AtlasStructure, TierName } from "./types";
import type { DetailPreference } from "../lib/preferences";

const BASE = import.meta.env.BASE_URL.replace(/\/+$/, "");

/** Manifest paths are site-absolute; prefix the deployment base path. */
export function assetUrl(path: string): string {
  return `${BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

let manifestPromise: Promise<AnatomyManifest> | null = null;
let atlasPromise: Promise<AtlasIndex> | null = null;

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(assetUrl(path));
  if (!response.ok) throw new Error(`${path} could not be loaded (${response.status}). Run tools/asset-pipeline to generate it.`);
  return (await response.json()) as T;
}

export function loadManifest(): Promise<AnatomyManifest> {
  manifestPromise ??= fetchJson<AnatomyManifest>("/anatomy/manifest.json").catch((error) => {
    manifestPromise = null;
    throw error;
  });
  return manifestPromise;
}

export function loadAtlasIndex(): Promise<AtlasIndex> {
  atlasPromise ??= fetchJson<AtlasIndex>("/anatomy/atlas-index.json").catch((error) => {
    atlasPromise = null;
    throw error;
  });
  return atlasPromise;
}

const LARGE_ASSET_BYTES = 40 * 2 ** 20;

export function chooseTier(variant: AnatomyVariant, preference: DetailPreference, override?: TierName | null): TierName {
  const tiers = variant.tiers ?? {};
  if (override && tiers[override]) return override;
  if (preference === "preview" && tiers.preview) return "preview";
  if (preference === "standard" || !tiers.preview) return "standard";
  return (tiers.standard?.bytes ?? 0) > LARGE_ASSET_BYTES ? "preview" : "standard";
}

export type AtlasLookup = {
  byId: Map<string, AtlasStructure>;
  byMesh: Map<number, AtlasStructure>;
  children: Map<string, AtlasStructure[]>;
};

const lookupCache = new WeakMap<AtlasIndex, AtlasLookup>();

export function atlasLookup(index: AtlasIndex): AtlasLookup {
  const cached = lookupCache.get(index);
  if (cached) return cached;
  const byId = new Map(index.structures.map((structure) => [structure.id, structure]));
  const byMesh = new Map<number, AtlasStructure>();
  const children = new Map<string, AtlasStructure[]>();
  for (const structure of index.structures) {
    for (const mesh of structure.meshes) byMesh.set(mesh, structure);
    if (structure.parent) {
      const list = children.get(structure.parent) ?? [];
      list.push(structure);
      children.set(structure.parent, list);
    }
  }
  const lookup = { byId, byMesh, children };
  lookupCache.set(index, lookup);
  return lookup;
}

export function ancestry(lookup: AtlasLookup, structure: AtlasStructure): AtlasStructure[] {
  const chain: AtlasStructure[] = [];
  let current: AtlasStructure | undefined = structure;
  while (current) {
    chain.push(current);
    current = current.parent ? lookup.byId.get(current.parent) : undefined;
  }
  return chain.reverse();
}

/** Leaf structures under any of the groups or systems, minus excluded groups. */
export function selectAtlasStructures(index: AtlasIndex, selection: { groups?: string[]; systems?: string[]; exclude?: string[] }): AtlasStructure[] {
  const lookup = atlasLookup(index);
  const groups = new Set(selection.groups ?? []);
  const systems = new Set(selection.systems ?? []);
  const exclude = new Set(selection.exclude ?? []);
  return index.structures.filter((structure) => {
    if (structure.kind !== "structure") return false;
    const chain = ancestry(lookup, structure).map((item) => item.id);
    if (chain.some((id) => exclude.has(id))) return false;
    return systems.has(structure.system) || chain.some((id) => groups.has(id));
  });
}

/** Chunk files that contain any of the given structures. */
export function chunksFor(index: AtlasIndex, structures: AtlasStructure[]) {
  const meshes = structures.flatMap((structure) => structure.meshes);
  return index.chunks.filter((chunk) => meshes.some((mesh) => mesh >= chunk.mesh_start && mesh < chunk.mesh_start + chunk.mesh_count));
}
