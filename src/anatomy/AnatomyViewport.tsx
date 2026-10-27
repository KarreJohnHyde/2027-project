import { Component, Suspense, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Canvas, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { Html, OrbitControls, OrthographicCamera, PerspectiveCamera, useGLTF, useProgress } from "@react-three/drei";
import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { TriangleAlert } from "lucide-react";
import { applyStyles, outermostKey, prepareAsset, prepareAtlasChunk, releaseAsset, retainAsset, targetBounds, type PreparedLayer, type StyleTarget, type ViewMode } from "./geometry";
import type { AtlasStructure, StructureEntry } from "./types";
import { assetUrl } from "./data";
import { useViewportStats } from "./viewportStats";

export type ViewportLayer =
  | { kind: "asset"; key: string; url: string; structures: StructureEntry[]; groupBy: string; matrix?: THREE.Matrix4 }
  | { kind: "atlas"; key: string; chunks: Array<{ id: string; url: string }>; structures: AtlasStructure[]; palette: string[]; matrix?: THREE.Matrix4 };

export type TargetSummary = { key: string; layer: string; structureId: string; label: string; meshes: number };
export type ViewportApi = { screenshot: () => string | null; reset: () => void };
export type SectionState = { axis: "x" | "y" | "z"; offset: number; flip: boolean };

export type ViewportProps = {
  layers: ViewportLayer[];
  framing: { mode: "fit" } | { mode: "box"; min: number[]; max: number[] };
  viewMode: ViewMode;
  opacity: number;
  section: SectionState;
  isolate: boolean;
  labels: boolean;
  projection: "perspective" | "orthographic";
  selectedKey: string | null;
  hoveredKey: string | null;
  hidden: Set<string>;
  verifiedKeys?: Set<string>;
  schematicKeys?: Set<string>;
  onSelect: (target: TargetSummary | null) => void;
  onHover: (target: TargetSummary | null) => void;
  onTargets?: (targets: TargetSummary[], interiorKey: string | null) => void;
  onApi?: (api: ViewportApi) => void;
  measurePerformance?: boolean;
  resetToken: number;
};

const EMPTY = new Set<string>();
const COLORS = {
  selected: new THREE.Color("#2dd4bf"),
  hover: new THREE.Color("#ffffff"),
  verified: new THREE.Color("#3987e5"),
  schematic: new THREE.Color("#86b6ef"),
};
const AXES = { x: new THREE.Vector3(1, 0, 0), y: new THREE.Vector3(0, 1, 0), z: new THREE.Vector3(0, 0, 1) };
const CAMERA_HOME = new THREE.Vector3(0, 0.15, 3.7);

/** Keep the latest callback without making it an effect dependency. */
function useLatest<T>(value: T) {
  const ref = useRef(value);
  useLayoutEffect(() => {
    ref.current = value;
  });
  return ref;
}

type BoundaryProps = { children: ReactNode; resetKey: string; onError: (message: string) => void };

class LayerErrorBoundary extends Component<BoundaryProps, { failed: boolean; resetKey: string }> {
  state = { failed: false, resetKey: this.props.resetKey };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  // A different layer set gets a fresh attempt without remounting the scene.
  static getDerivedStateFromProps(props: BoundaryProps, state: { failed: boolean; resetKey: string }) {
    return props.resetKey === state.resetKey ? null : { failed: false, resetKey: props.resetKey };
  }
  componentDidCatch(error: unknown) {
    this.props.onError(error instanceof Error ? error.message : String(error));
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

function useRetained(url: string, scene: THREE.Object3D) {
  useEffect(() => {
    retainAsset(url);
    return () => releaseAsset(url, scene, (target) => useGLTF.clear(target));
  }, [url, scene]);
}

function LayerGroup({ matrix, children }: { matrix?: THREE.Matrix4; children: ReactNode }) {
  const ref = useRef<THREE.Group>(null);
  useLayoutEffect(() => {
    const group = ref.current;
    if (!group) return;
    group.matrixAutoUpdate = !matrix;
    if (matrix) {
      group.matrix.copy(matrix);
      group.matrixWorldNeedsUpdate = true;
    }
  }, [matrix]);
  return <group ref={ref}>{children}</group>;
}

type PreparedCallback = (key: string, prepared: PreparedLayer | null) => void;

function AssetLayerNode({ layer, onPrepared }: { layer: Extract<ViewportLayer, { kind: "asset" }>; onPrepared: PreparedCallback }) {
  const url = assetUrl(layer.url);
  const gltf = useGLTF(url, false, true);
  useRetained(url, gltf.scene);
  const prepared = useMemo(() => prepareAsset(gltf.scene, layer.key, layer.structures, layer.groupBy), [gltf.scene, layer.key, layer.structures, layer.groupBy]);
  useLayoutEffect(() => {
    onPrepared(layer.key, prepared);
    return () => {
      onPrepared(layer.key, null);
      prepared.dispose();
    };
  }, [prepared, layer.key, onPrepared]);
  return (
    <LayerGroup matrix={layer.matrix}>
      <primitive object={prepared.root} />
    </LayerGroup>
  );
}

type AtlasLayer = Extract<ViewportLayer, { kind: "atlas" }>;

function AtlasChunkNode({ layer, chunk, onPrepared }: { layer: AtlasLayer; chunk: AtlasLayer["chunks"][number]; onPrepared: PreparedCallback }) {
  const url = assetUrl(chunk.url);
  // A single URL gives the loader the same cache key used by releaseAsset.
  // Array loads create a tuple cache that clearing individual URLs cannot evict.
  const gltf = useGLTF(url, false, true);
  useRetained(url, gltf.scene);
  const preparedKey = `${layer.key}:chunk:${chunk.id}`;
  const prepared = useMemo(() => prepareAtlasChunk(gltf.scene, layer.key, layer.structures, layer.palette), [gltf.scene, layer.key, layer.structures, layer.palette]);
  useLayoutEffect(() => {
    onPrepared(preparedKey, prepared);
    return () => {
      onPrepared(preparedKey, null);
      prepared.dispose();
    };
  }, [prepared, preparedKey, onPrepared]);
  return <primitive object={prepared.root} />;
}

function AtlasLayerNode({ layer, onPrepared }: { layer: AtlasLayer; onPrepared: PreparedCallback }) {
  return (
    <LayerGroup matrix={layer.matrix}>
      {layer.chunks.map((chunk) => <AtlasChunkNode key={`${chunk.id}:${chunk.url}`} layer={layer} chunk={chunk} onPrepared={onPrepared} />)}
    </LayerGroup>
  );
}

function EnvironmentLighting() {
  const { gl, scene } = useThree();
  useEffect(() => {
    const generator = new THREE.PMREMGenerator(gl);
    const environment = generator.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environment = environment;
    return () => {
      scene.environment = null;
      environment.dispose();
      generator.dispose();
    };
  }, [gl, scene]);
  return (
    <>
      <ambientLight intensity={0.25} />
      <directionalLight position={[3, 4, 5]} intensity={1.6} />
      <directionalLight position={[-4, 1, -3]} intensity={0.6} />
    </>
  );
}

function CameraRig({ projection, resetToken, onApi }: { projection: "perspective" | "orthographic"; resetToken: number; onApi?: (api: ViewportApi) => void }) {
  const { camera, gl, scene, size, controls, invalidate } = useThree();
  const onApiRef = useLatest(onApi);
  const zoom = Math.min(size.width, size.height) / 2.8;
  const reset = useCallback(() => {
    camera.position.copy(CAMERA_HOME);
    camera.lookAt(0, 0, 0);
    const orbit = controls as unknown as { target: THREE.Vector3; update: () => void } | null;
    orbit?.target.set(0, 0, 0);
    orbit?.update();
    invalidate();
  }, [camera, controls, invalidate]);
  useEffect(reset, [resetToken, reset]);
  useEffect(() => {
    onApiRef.current?.({
      screenshot: () => {
        gl.render(scene, camera);
        return gl.domElement.toDataURL("image/png");
      },
      reset,
    });
  }, [gl, scene, camera, reset, onApiRef]);
  return projection === "perspective"
    ? <PerspectiveCamera makeDefault position={CAMERA_HOME.toArray()} fov={34} near={0.01} far={60} />
    : <OrthographicCamera makeDefault position={CAMERA_HOME.toArray()} zoom={zoom} near={-60} far={60} />;
}

function PerformanceProbe() {
  const publish = useViewportStats((state) => state.publish);
  const sample = useRef({ frames: 0, elapsed: 0 });
  useFrame((state, delta) => {
    sample.current.frames += 1;
    sample.current.elapsed += Math.min(delta, 1);
    if (sample.current.elapsed < 0.5) return;
    const info = state.gl.info;
    const memory = (performance as Performance & { memory?: { usedJSHeapSize: number } }).memory;
    publish({
      fps: sample.current.frames / sample.current.elapsed,
      calls: info.render.calls,
      triangles: info.render.triangles,
      points: info.render.points,
      geometries: info.memory.geometries,
      textures: info.memory.textures,
      programs: info.programs?.length ?? 0,
      heapMb: memory ? memory.usedJSHeapSize / 2 ** 20 : null,
      sampledAt: performance.now(),
    });
    sample.current = { frames: 0, elapsed: 0 };
  });
  return null;
}

type SceneProps = Omit<ViewportProps, "onApi" | "resetToken" | "projection" | "measurePerformance">;

function SceneContent(props: SceneProps) {
  const { layers, framing, viewMode, opacity, section, isolate, labels, selectedKey, hoveredKey, hidden, verifiedKeys = EMPTY, schematicKeys = EMPTY } = props;
  const invalidate = useThree((state) => state.invalidate);
  const callbacks = useLatest({ onSelect: props.onSelect, onHover: props.onHover, onTargets: props.onTargets });
  const root = useRef<THREE.Group>(null);
  const [prepared, setPrepared] = useState<ReadonlyMap<string, PreparedLayer>>(() => new Map());
  const [frameVersion, setFrameVersion] = useState(0);
  const plane = useMemo(() => new THREE.Plane(), []);
  const framingKey = framing.mode === "box" ? `box:${framing.min.join(",")}:${framing.max.join(",")}` : "fit";

  const onPrepared = useCallback<PreparedCallback>((key, layer) => {
    setPrepared((current) => {
      const next = new Map(current);
      if (layer) next.set(key, layer);
      else next.delete(key);
      return next;
    });
  }, []);

  const targets = useMemo<StyleTarget[]>(() => [...prepared.values()].flatMap((layer) => layer.targets), [prepared]);
  const interiorKey = useMemo(() => outermostKey(targets), [targets]);

  useLayoutEffect(() => {
    const group = root.current;
    if (!group || targets.length === 0) return;
    group.position.set(0, 0, 0);
    group.scale.setScalar(1);
    group.updateMatrixWorld(true);
    const [mode, min, max] = framingKey.split(":");
    const box = mode === "box"
      ? new THREE.Box3(new THREE.Vector3(...min.split(",").map(Number)), new THREE.Vector3(...max.split(",").map(Number)))
      : targetBounds(targets);
    if (box.isEmpty()) return;
    const sphere = box.getBoundingSphere(new THREE.Sphere());
    const scale = sphere.radius > 0 ? 1 / sphere.radius : 1;
    group.scale.setScalar(scale);
    group.position.copy(sphere.center).multiplyScalar(-scale);
    group.updateMatrixWorld(true);
    // Label positions are world-space and depend on this transform.
    setFrameVersion((value) => value + 1);
    invalidate();
  }, [targets, framingKey, invalidate]);

  useEffect(() => {
    const summaries = new Map<string, TargetSummary>();
    for (const target of targets) {
      const existing = summaries.get(target.key);
      summaries.set(target.key, existing ? { ...existing, meshes: existing.meshes + 1 } : { key: target.key, layer: target.layer, structureId: target.structureId, label: target.label, meshes: 1 });
    }
    callbacks.current.onTargets?.([...summaries.values()], interiorKey);
  }, [targets, interiorKey, callbacks]);

  useEffect(() => {
    const sectioned = viewMode === "SECTION";
    if (sectioned) {
      const normal = AXES[section.axis].clone().multiplyScalar(section.flip ? 1 : -1);
      plane.set(normal, section.offset * (section.flip ? -1 : 1));
    }
    applyStyles(targets, {
      hidden,
      isolateKey: isolate ? selectedKey : null,
      selectedKey,
      hoveredKey,
      verifiedKeys,
      schematicKeys,
      translucentKeys: interiorKey ? new Set([interiorKey]) : EMPTY,
      viewMode,
      opacity,
      plane: sectioned ? plane : null,
      colors: COLORS,
    });
    invalidate();
  }, [targets, hidden, isolate, selectedKey, hoveredKey, verifiedKeys, schematicKeys, interiorKey, viewMode, opacity, section.axis, section.offset, section.flip, plane, invalidate]);

  function pick(event: ThreeEvent<PointerEvent | MouseEvent>): TargetSummary | null {
    const hit = event.intersections.find((intersection) => {
      let object: THREE.Object3D | null = intersection.object;
      while (object) {
        if (!object.visible) return false;
        object = object.parent;
      }
      if (viewMode === "SECTION" && plane.distanceToPoint(intersection.point) < 0) return false;
      return Boolean(intersection.object.userData.medtwinKey);
    });
    if (!hit) return null;
    const key = hit.object.userData.medtwinKey as string;
    const target = targets.find((item) => item.key === key);
    return target ? { key, layer: target.layer, structureId: target.structureId, label: target.label, meshes: 1 } : null;
  }

  const labelTargets = useMemo(() => {
    const keys = new Set<string>([selectedKey, hoveredKey].filter((key): key is string => Boolean(key)));
    if (labels) {
      const sizes = new Map<string, number>();
      for (const target of targets) {
        if (hidden.has(target.key)) continue;
        sizes.set(target.key, Math.max(sizes.get(target.key) ?? 0, targetBounds([target]).getSize(new THREE.Vector3()).length()));
      }
      [...sizes.entries()].sort((left, right) => right[1] - left[1]).slice(0, 10).forEach(([key]) => keys.add(key));
    }
    return [...keys].flatMap((key) => {
      const members = targets.filter((target) => target.key === key);
      if (!members.length || frameVersion === 0) return [];
      return [{ key, label: members[0].label, center: targetBounds(members).getCenter(new THREE.Vector3()) }];
    });
  }, [targets, labels, selectedKey, hoveredKey, hidden, frameVersion]);

  return (
    <>
    <group
      ref={root}
      onClick={(event) => {
        event.stopPropagation();
        callbacks.current.onSelect(pick(event));
      }}
      onPointerMove={(event) => {
        event.stopPropagation();
        const target = pick(event);
        if ((target?.key ?? null) !== hoveredKey) callbacks.current.onHover(target);
      }}
      onPointerOut={() => {
        if (hoveredKey) callbacks.current.onHover(null);
      }}
    >
      {layers.map((layer) => (
        <Suspense key={layer.key} fallback={null}>
          {layer.kind === "asset" ? <AssetLayerNode layer={layer} onPrepared={onPrepared} /> : <AtlasLayerNode layer={layer} onPrepared={onPrepared} />}
        </Suspense>
      ))}
    </group>
    {labelTargets.map((item) => (
      <Html key={item.key} position={item.center} center zIndexRange={[20, 0]} style={{ pointerEvents: "none" }}>
        <span className={`whitespace-nowrap rounded-md px-1.5 py-0.5 text-[11px] font-medium shadow ${item.key === selectedKey ? "bg-[#2dd4bf] text-[#04201d]" : "bg-black/70 text-white"}`}>{item.label}</span>
      </Html>
    ))}
    </>
  );
}

function LoadingOverlay() {
  const { active, progress, loaded, total } = useProgress();
  if (!active) return null;
  return (
    <div className="pointer-events-none absolute inset-x-0 top-0 z-10 p-3">
      <div className="mx-auto max-w-sm rounded-lg border border-white/10 bg-black/70 p-2.5 text-xs text-white backdrop-blur">
        <div className="flex justify-between"><span>Loading anatomy</span><span className="tabular">{Math.round(progress)}% · {loaded}/{total}</span></div>
        <div className="mt-1.5 h-1 overflow-hidden rounded bg-white/15"><div className="h-full bg-[#2dd4bf] transition-[width]" style={{ width: `${progress}%` }} /></div>
      </div>
    </div>
  );
}

export default function AnatomyViewport(props: ViewportProps) {
  const { projection, resetToken, onApi, measurePerformance = false, ...sceneProps } = props;
  const signature = props.layers.map((layer) => (layer.kind === "asset" ? layer.url : layer.chunks.map((chunk) => chunk.url).join(","))).join("|");
  const [failure, setFailure] = useState<{ signature: string; message: string } | null>(null);
  const error = failure && failure.signature === signature ? failure.message : null;
  const onSelect = useLatest(props.onSelect);
  return (
    <div className="relative h-full w-full overflow-hidden bg-viewport">
      <Canvas
        frameloop="demand"
        dpr={[1, 1.75]}
        gl={{ antialias: true, localClippingEnabled: true }}
        raycaster={{ params: { Points: { threshold: 0.01 }, Line: { threshold: 0.01 }, Mesh: {}, LOD: {}, Sprite: {} } }}
        onPointerMissed={() => onSelect.current(null)}
        aria-label="Interactive anatomical model"
      >
        <EnvironmentLighting />
        <CameraRig projection={projection} resetToken={resetToken} onApi={onApi} />
        <LayerErrorBoundary resetKey={signature} onError={(message) => setFailure({ signature, message })}>
          <Suspense fallback={null}>
            <SceneContent {...sceneProps} />
          </Suspense>
        </LayerErrorBoundary>
        <OrbitControls makeDefault enableDamping={false} minDistance={0.4} maxDistance={14} />
        {measurePerformance && <PerformanceProbe />}
      </Canvas>
      <LoadingOverlay />
      {error && (
        <div role="alert" className="absolute inset-x-3 bottom-3 z-10 flex items-start gap-2 rounded-lg border border-[#d03b3b]/50 bg-black/80 p-3 text-xs text-white">
          <TriangleAlert aria-hidden size={15} className="mt-0.5 shrink-0 text-[#e66767]" />
          <span><b>Asset could not be rendered.</b> {error} The source file is unchanged; see docs/anatomy/derivatives.json for its derivative.</span>
        </div>
      )}
    </div>
  );
}
