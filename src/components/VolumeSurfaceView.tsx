import { useEffect, useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { ErrorBlock, LoadingBlock } from "./ui";
import { api, type VolumeSurfaces } from "../services/api";
import { formatNumber, humanize } from "../lib/format";
import { useAsync } from "../lib/useAsync";

type Rgba = [number, number, number, number];

/** Centre and size of the largest structure: the default view frames it; separate fragments of the
 * predicted mask stay in the scene and are reached by zooming out. */
function focus(data: VolumeSurfaces): { centre: THREE.Vector3; size: number } {
  const largest = [...data.surfaces].sort((a, b) => b.voxels - a.voxels)[0];
  if (!largest) return { centre: new THREE.Vector3(...data.extent_mm).multiplyScalar(0.5), size: Math.max(...data.extent_mm) };
  // 5th to 95th percentile per axis, so small islands of the same structure do not widen the frame.
  const axes = [0, 1, 2].map((axis) => largest.vertices_mm.filter((_, index) => index % 3 === axis).sort((a, b) => a - b));
  const at = (values: number[], q: number) => values[Math.floor(q * (values.length - 1))];
  const low = axes.map((values) => at(values, 0.05));
  const high = axes.map((values) => at(values, 0.95));
  return {
    centre: new THREE.Vector3((low[0] + high[0]) / 2, (low[1] + high[1]) / 2, (low[2] + high[2]) / 2),
    size: Math.max(high[0] - low[0], high[1] - low[1], high[2] - low[2]),
  };
}

function SurfaceMeshes({ data, colors, centre }: { data: VolumeSurfaces; colors: Record<number, Rgba>; centre: THREE.Vector3 }) {
  const meshes = useMemo(() => data.surfaces.map((surface) => {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(surface.vertices_mm, 3));
    geometry.setIndex(surface.faces);
    geometry.computeVertexNormals();
    const [r, g, b] = colors[surface.class_index] ?? [34, 211, 238, 1];
    return { key: surface.class_index, geometry, color: new THREE.Color(`rgb(${r}, ${g}, ${b})`) };
  }), [data, colors]);
  // Geometries passed as props are not disposed by react-three-fiber; free their GPU buffers here.
  useEffect(() => () => meshes.forEach((mesh) => mesh.geometry.dispose()), [meshes]);
  return (
    // x = i·sx, y = j·sy, z = k·sz as the API returns them, shifted so the framed structure is at the origin.
    <group position={[-centre.x, -centre.y, -centre.z]}>
      {meshes.map((mesh) => (
        <mesh key={mesh.key} geometry={mesh.geometry}>
          <meshStandardMaterial color={mesh.color} roughness={0.6} metalness={0} transparent opacity={0.85} side={THREE.DoubleSide} />
        </mesh>
      ))}
    </group>
  );
}

/** Patient-derived surfaces of one volumetric research run, in the scan's own frame (never the atlas). */
export default function VolumeSurfaceView({ runId, colors }: { runId: number; colors: Record<number, Rgba> }) {
  const surfaces = useAsync(() => api.getVolumeSurfaces(runId), [runId]);
  if (surfaces.loading || !surfaces.data) return surfaces.error ? <ErrorBlock message={surfaces.error} onRetry={surfaces.reload} /> : <LoadingBlock label="Building surfaces" />;
  const data = surfaces.data;
  const { centre, size } = focus(data);
  const distance = Math.max(size, 20) * 2.6;
  const far = Math.max(...data.extent_mm) * 10;
  return (
    <div className="space-y-2">
      <div className="relative h-72 overflow-hidden rounded-lg bg-[#0b1220]">
        <Canvas camera={{ position: [0, -distance * 0.35, distance], fov: 40, near: 1, far }} aria-label="Patient-derived surfaces">
          <ambientLight intensity={0.6} />
          <directionalLight position={[1, 1, 2]} intensity={1.1} />
          <SurfaceMeshes data={data} colors={colors} centre={centre} />
          <OrbitControls makeDefault />
        </Canvas>
        <p className="pointer-events-none absolute left-2 top-2 rounded bg-black/60 px-2 py-1 text-[11px] text-white">Scan voxel frame (mm) · from this run's mask · not registered to the atlas</p>
        <p className="pointer-events-none absolute bottom-2 left-2 rounded bg-black/60 px-2 py-1 text-[11px] text-white">Framed on the largest structure; zoom out for any separate fragments the model predicted</p>
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-ink-2">
        {data.surfaces.map((surface) => (
          <li key={surface.class_index}>{humanize(surface.structure)} · {formatNumber(surface.volume_ml, 1)} mL · {formatNumber(surface.triangles, 0)} triangles</li>
        ))}
      </ul>
      <p className="text-[11px] leading-4 text-ink-3">{data.semantics} Voxel spacing {data.voxel_spacing_mm.map((value) => formatNumber(value, 3)).join(" × ")} mm.</p>
    </div>
  );
}
