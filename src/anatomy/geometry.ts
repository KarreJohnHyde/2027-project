import * as THREE from "three";
import { clone as cloneWithSkeleton } from "three/examples/jsm/utils/SkeletonUtils.js";
import type { AtlasStructure, StructureEntry } from "./types";

/** One selectable unit in the viewport: a mesh (or points) bound to a structure. */
export type StyleTarget = {
  object: THREE.Mesh | THREE.Points;
  key: string;
  layer: string;
  structureId: string;
  label: string;
};

export type PreparedLayer = { root: THREE.Object3D; targets: StyleTarget[]; dispose: () => void };

type OriginalStyle = { opacity: number; transparent: boolean; depthWrite: boolean; side: THREE.Side; emissive: THREE.Color | null; emissiveIntensity: number; color: THREE.Color | null };
type StylableMaterial = THREE.Material & { emissive?: THREE.Color; emissiveIntensity?: number; color?: THREE.Color };

const SECTION_CAP = new THREE.Color("#b8a99a");

function materialsOf(object: THREE.Mesh | THREE.Points): StylableMaterial[] {
  return (Array.isArray(object.material) ? object.material : [object.material]) as StylableMaterial[];
}

/** Colour back faces exposed by a clipping plane so a section reads as a cut surface. */
function installSectionShader(material: THREE.Material): void {
  if (material.userData.medtwinSection) return;
  material.userData.medtwinSection = true;
  material.onBeforeCompile = (shader) => {
    shader.uniforms.uSectionCap = { value: SECTION_CAP };
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", "#include <common>\nuniform vec3 uSectionCap;")
      .replace("#include <color_fragment>", "#include <color_fragment>\n\tif ( !gl_FrontFacing ) { diffuseColor.rgb = mix( diffuseColor.rgb, uSectionCap, 0.6 ); }");
  };
  material.customProgramCacheKey = () => "medtwin-section-v1";
}

function rememberOriginal(material: StylableMaterial): void {
  if (material.userData.medtwinOriginal) return;
  const original: OriginalStyle = {
    opacity: material.opacity,
    transparent: material.transparent,
    depthWrite: material.depthWrite,
    side: material.side,
    emissive: material.emissive ? material.emissive.clone() : null,
    emissiveIntensity: material.emissiveIntensity ?? 1,
    color: material.color ? material.color.clone() : null,
  };
  material.userData.medtwinOriginal = original;
}

function originalName(object: THREE.Object3D): string {
  return (object.userData?.name as string | undefined) ?? object.name;
}

/**
 * Clone a loaded asset and bind each mesh to a manifest structure using the
 * same grouping rule the manifest builder used (material, parent or node).
 */
export function prepareAsset(scene: THREE.Object3D, layer: string, structures: StructureEntry[], groupBy: string): PreparedLayer {
  const root = cloneWithSkeleton(scene);
  const byKey = new Map(structures.map((structure) => [structure.source_key, structure]));
  const targets: StyleTarget[] = [];
  const cloned: THREE.Material[] = [];
  root.traverse((object) => {
    const renderable = object as THREE.Mesh | THREE.Points;
    if (!(renderable as THREE.Mesh).isMesh && !(renderable as THREE.Points).isPoints) return;
    renderable.material = Array.isArray(renderable.material) ? renderable.material.map((material) => material.clone()) : renderable.material.clone();
    const materials = materialsOf(renderable);
    materials.forEach((material) => {
      rememberOriginal(material);
      installSectionShader(material);
      cloned.push(material);
    });
    const materialName = materials[0]?.name ?? "";
    const candidates: string[] = groupBy === "material" ? [materialName] : [];
    let cursor: THREE.Object3D | null = renderable;
    while (cursor) {
      candidates.push(originalName(cursor));
      cursor = cursor.parent;
    }
    candidates.push(materialName);
    const structure = candidates.map((name) => byKey.get(name)).find(Boolean);
    const structureId = structure?.id ?? "unassigned";
    const key = `${layer}:${structureId}`;
    renderable.userData.medtwinKey = key;
    if ((renderable as THREE.Points).isPoints) renderable.raycast = () => undefined;
    targets.push({ object: renderable, key, layer, structureId, label: structure?.label ?? "Unassigned geometry" });
  });
  return { root, targets, dispose: () => cloned.forEach((material) => material.dispose()) };
}

type RangeMap = Map<number, Array<[number, number]>>;

/** Contiguous index ranges per atlas mesh index (the _id x-component). Cached per geometry. */
function meshRanges(geometry: THREE.BufferGeometry): RangeMap {
  if (geometry.userData.medtwinRanges) return geometry.userData.medtwinRanges as RangeMap;
  const index = geometry.index;
  const ids = geometry.getAttribute("_id");
  const ranges: RangeMap = new Map();
  if (!index || !ids) return ranges;
  let current = -1;
  let start = 0;
  for (let i = 0; i < index.count; i += 3) {
    const meshIndex = ids.getX(index.getX(i));
    if (meshIndex !== current) {
      if (current >= 0) ranges.set(current, [...(ranges.get(current) ?? []), [start, i - start]]);
      current = meshIndex;
      start = i;
    }
  }
  if (current >= 0) ranges.set(current, [...(ranges.get(current) ?? []), [start, index.count - start]]);
  geometry.userData.medtwinRanges = ranges;
  return ranges;
}

/** Per-vertex colour from the atlas tissue palette (the _id y-component). */
function ensurePaletteColors(geometry: THREE.BufferGeometry, palette: string[]): void {
  if (geometry.getAttribute("color")) return;
  const ids = geometry.getAttribute("_id");
  const colors = new Float32Array(ids.count * 3);
  const swatches = palette.map((hex) => new THREE.Color(hex));
  const fallback = new THREE.Color("#c9b8a8");
  for (let vertex = 0; vertex < ids.count; vertex++) {
    const color = swatches[ids.getY(vertex)] ?? fallback;
    colors[vertex * 3] = color.r;
    colors[vertex * 3 + 1] = color.g;
    colors[vertex * 3 + 2] = color.b;
  }
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
}

function rangeBounds(geometry: THREE.BufferGeometry, start: number, count: number): THREE.Box3 {
  const index = geometry.index!;
  const position = geometry.getAttribute("position");
  const box = new THREE.Box3();
  const point = new THREE.Vector3();
  for (let i = start; i < start + count; i++) {
    const vertex = index.getX(i);
    point.set(position.getX(vertex), position.getY(vertex), position.getZ(vertex));
    box.expandByPoint(point);
  }
  return box;
}

/**
 * Split one atlas chunk into per-structure meshes. Sub-meshes share the
 * chunk's GPU buffers and differ only in draw range and material.
 */
export function prepareAtlasChunk(scene: THREE.Object3D, layer: string, structures: AtlasStructure[], palette: string[]): PreparedLayer {
  scene.updateMatrixWorld(true);
  let source: THREE.Mesh | null = null;
  scene.traverse((object) => {
    if (!source && (object as THREE.Mesh).isMesh) source = object as THREE.Mesh;
  });
  const group = new THREE.Group();
  const targets: StyleTarget[] = [];
  const created: Array<THREE.BufferGeometry | THREE.Material> = [];
  if (!source) return { root: group, targets, dispose: () => undefined };
  const chunkMesh = source as THREE.Mesh;
  const geometry = chunkMesh.geometry;
  ensurePaletteColors(geometry, palette);
  const ranges = meshRanges(geometry);
  group.matrixAutoUpdate = false;
  group.matrix.copy(chunkMesh.matrixWorld);
  for (const structure of structures) {
    for (const meshIndex of structure.meshes) {
      for (const [start, count] of ranges.get(meshIndex) ?? []) {
        const part = new THREE.BufferGeometry();
        part.setIndex(geometry.index);
        for (const name of ["position", "normal", "color"]) {
          const attribute = geometry.getAttribute(name);
          if (attribute) part.setAttribute(name, attribute);
        }
        part.setDrawRange(start, count);
        part.boundingBox = rangeBounds(geometry, start, count);
        part.boundingSphere = part.boundingBox.getBoundingSphere(new THREE.Sphere());
        const material = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.62, metalness: 0.02 });
        material.name = structure.id;
        rememberOriginal(material);
        installSectionShader(material);
        const mesh = new THREE.Mesh(part, material);
        mesh.name = structure.id;
        mesh.userData.medtwinKey = `${layer}:${structure.id}`;
        group.add(mesh);
        created.push(part, material);
        targets.push({ object: mesh, key: `${layer}:${structure.id}`, layer, structureId: structure.id, label: structure.name });
      }
    }
  }
  return { root: group, targets, dispose: () => created.forEach((item) => item.dispose()) };
}

export type ViewMode = "EXTERIOR" | "INTERIOR" | "TRANSPARENT" | "SECTION";

export type StyleState = {
  hidden: Set<string>;
  isolateKey: string | null;
  selectedKey: string | null;
  hoveredKey: string | null;
  verifiedKeys: Set<string>;
  schematicKeys: Set<string>;
  /** Named in an affirmed report statement, not yet confirmed by a clinician. */
  documentedKeys: Set<string>;
  translucentKeys: Set<string>;
  viewMode: ViewMode;
  opacity: number;
  plane: THREE.Plane | null;
  colors: { selected: THREE.Color; hover: THREE.Color; verified: THREE.Color; schematic: THREE.Color; documented: THREE.Color };
};

export function applyStyles(targets: StyleTarget[], state: StyleState): void {
  for (const target of targets) {
    const visible = !state.hidden.has(target.key) && (!state.isolateKey || state.isolateKey === target.key);
    target.object.visible = visible;
    for (const material of materialsOf(target.object)) {
      const original = material.userData.medtwinOriginal as OriginalStyle;
      let opacity = original.opacity;
      if (state.viewMode === "TRANSPARENT") opacity = Math.min(original.opacity, state.opacity);
      else if (state.viewMode === "INTERIOR" && state.translucentKeys.has(target.key)) opacity = Math.min(original.opacity, 0.16);
      const transparent = original.transparent || opacity < 0.999;
      const side = state.viewMode === "SECTION" ? THREE.DoubleSide : original.side;
      const clipping = state.plane ? [state.plane] : null;
      const signature = `${transparent}|${side}|${clipping ? 1 : 0}`;
      if (material.userData.medtwinSignature !== signature) {
        material.transparent = transparent;
        material.side = side;
        material.clippingPlanes = clipping;
        material.needsUpdate = true;
        material.userData.medtwinSignature = signature;
      } else if (clipping) {
        material.clippingPlanes = clipping;
      }
      material.opacity = opacity;
      material.depthWrite = opacity >= 0.999 ? original.depthWrite : false;
      if (material.color && original.color) {
        // A documented region also tints the surface: an emissive glow alone washes out on
        // pale tissue under tone mapping. Selection and hover keep their own colours.
        const documented = state.documentedKeys.has(target.key) && target.key !== state.selectedKey && target.key !== state.hoveredKey
          && !state.verifiedKeys.has(target.key);
        material.color.copy(documented ? state.colors.documented : original.color);
      }
      if (material.emissive && original.emissive) {
        if (target.key === state.selectedKey) {
          material.emissive.copy(state.colors.selected);
          material.emissiveIntensity = 0.55;
        } else if (target.key === state.hoveredKey) {
          material.emissive.copy(state.colors.hover);
          material.emissiveIntensity = 0.3;
        } else if (state.verifiedKeys.has(target.key)) {
          material.emissive.copy(state.colors.verified);
          material.emissiveIntensity = 0.5;
        } else if (state.documentedKeys.has(target.key)) {
          material.emissive.copy(state.colors.documented);
          material.emissiveIntensity = 0.35;
        } else if (state.schematicKeys.has(target.key)) {
          material.emissive.copy(state.colors.schematic);
          material.emissiveIntensity = 0.22;
        } else {
          material.emissive.copy(original.emissive);
          material.emissiveIntensity = original.emissiveIntensity;
        }
      }
    }
  }
}

/** World-space bounds of the visible targets. */
export function targetBounds(targets: StyleTarget[]): THREE.Box3 {
  const box = new THREE.Box3();
  for (const target of targets) {
    target.object.updateWorldMatrix(true, false);
    const geometry = target.object.geometry;
    if (!geometry.boundingBox) geometry.computeBoundingBox();
    if (geometry.boundingBox) box.union(geometry.boundingBox.clone().applyMatrix4(target.object.matrixWorld));
  }
  return box;
}

/** The structure with the largest bounding volume: made translucent in interior view. */
export function outermostKey(targets: StyleTarget[]): string | null {
  const volumes = new Map<string, THREE.Box3>();
  for (const target of targets) {
    const box = volumes.get(target.key) ?? new THREE.Box3();
    box.union(targetBounds([target]));
    volumes.set(target.key, box);
  }
  let best: string | null = null;
  let bestVolume = -1;
  for (const [key, box] of volumes) {
    const size = box.getSize(new THREE.Vector3());
    const volume = size.x * size.y * size.z;
    if (volume > bestVolume && volumes.size > 1) {
      bestVolume = volume;
      best = key;
    }
  }
  return best;
}

const references = new Map<string, number>();
const pending = new Map<string, number>();

export function retainAsset(url: string): void {
  const timer = pending.get(url);
  if (timer !== undefined) {
    window.clearTimeout(timer);
    pending.delete(url);
  }
  references.set(url, (references.get(url) ?? 0) + 1);
}

/** Release GPU memory once no viewport uses the asset (deferred so a remount can reclaim it). */
export function releaseAsset(url: string, scene: THREE.Object3D, clear: (url: string) => void): void {
  const count = (references.get(url) ?? 1) - 1;
  if (count > 0) {
    references.set(url, count);
    return;
  }
  references.delete(url);
  pending.set(url, window.setTimeout(() => {
    pending.delete(url);
    if (references.has(url)) return;
    scene.traverse((object) => {
      const mesh = object as THREE.Mesh;
      if (!mesh.geometry) return;
      mesh.geometry.dispose();
      const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      for (const material of materials) {
        if (!material) continue;
        for (const value of Object.values(material)) if (value && (value as THREE.Texture).isTexture) (value as THREE.Texture).dispose();
        material.dispose();
      }
    });
    clear(url);
  }, 250));
}
