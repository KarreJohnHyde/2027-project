import { Suspense, lazy, useEffect, useMemo, useRef, useState } from "react"

import { Canvas } from "@react-three/fiber"

import { OrbitControls } from "@react-three/drei"

import * as THREE from "three"

import {
  api,
  type ReferenceAnnotation,
  type ResearchOutput,
  type ResearchRun,
  type UploadedFile,
  type VolumeCorrectionSummary,
} from "../services/api"

import { universalFetch, universalJson } from "../services/universal"

import {
  INDEX_PLANES,
  anatomicalDirection,
  displayToVoxel,
  planeCorners,
  planeIndex,
  planeSize,
  transformPoint,
  voxelToDisplay,
  type IndexPlane,
  type Matrix4Rows,
  type VoxelPoint,
} from "../lib/universalGeometry"

import { ErrorBlock } from "./ui"

import MaskCorrectionEditor from "./MaskCorrectionEditor"
import TemporalImageComparison from "./TemporalImageComparison"


const VolumeSurfaceView = lazy(() => import("./VolumeSurfaceView"))

const COLORS = {
  1: [56, 132, 255, 1],
  2: [245, 170, 40, 1],
  3: [236, 72, 153, 1],
} satisfies Record<number, [number, number, number, number]>

const PLANE_COLORS: Record<IndexPlane, string> = {
  axial: "#22d3ee",
  coronal: "#fbbf24",
  sagittal: "#f472b6",
}

const controlClass =
  "rounded border border-line bg-surface px-2 py-1.5 text-xs text-ink disabled:opacity-40"

export interface SpatialMetadata {
  schema_version: string

  status: "AVAILABLE" | "REFUSED"

  refusal: {
    code: string
    reason: string
  } | null

  source: {
    upload_id?: number
    case_id: number
    sha256?: string
    kind: "UPLOAD" | "DICOM_SERIES"
  }

  dimensions_xyz: VoxelPoint | null

  spacing_xyz_mm: VoxelPoint | null

  affine_voxel_to_world: Matrix4Rows | null

  affine_voxel_to_display: Matrix4Rows | null

  coordinate_frame: "RAS_MM" | "LPS_MM" | null

  display_frame: string

  world_available: boolean

  view_space?: "source" | "anatomical"
  available_view_spaces?: Array<"source" | "anatomical">
  view_to_native_voxel?: Matrix4Rows
  native_to_view_voxel?: Matrix4Rows
  native_geometry?: {
    dimensions_xyz: VoxelPoint
    spacing_xyz_mm: VoxelPoint | null
    affine_voxel_to_world: Matrix4Rows | null
    affine_voxel_to_display: Matrix4Rows
    coordinate_frame: "RAS_MM" | "LPS_MM" | null
  }
  frame_selection?: {
    required: boolean
    count: number
    index: number | null
    kind: "channel" | "time" | null
    header_temporal_units?: string
    semantics: string
  }

  non_axial_vertical_flip: boolean

  plane_definition: string

  warnings: string[]

  render_input: {
    kind: "UPLOAD" | "DICOM_SERIES"
    path: string
    query?: Record<string, string | number>
    body?: {
      upload_ids: number[]
      series_reference?: string | null
      phase?: number | null
      view_space?: "source" | "anatomical"
    }
  }

  series_report?: {
    issues?: Array<{
      code?: string
      message?: string
    }>
    series?: Array<{ series_reference: string }>
    status?: string
  }
}

function SourcePlane({
  axis,
  metadata,
  voxel,
  image,
  centre,
}: {
  axis: IndexPlane
  metadata: SpatialMetadata
  voxel: VoxelPoint
  image?: string
  centre: VoxelPoint
}) {
  const geometry = useMemo(() => {
    const corners = planeCorners(
      axis,
      voxel,
      metadata.dimensions_xyz!,
      metadata.non_axial_vertical_flip,
    ).map((p) =>
      transformPoint(metadata.affine_voxel_to_display!, p).map(
        (v, i) => v - centre[i],
      ),
    )

    const result = new THREE.BufferGeometry()

    result.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(corners.flat(), 3),
    )

    result.setAttribute(
      "uv",
      new THREE.Float32BufferAttribute([0, 1, 1, 1, 1, 0, 0, 0], 2),
    )

    result.setIndex([0, 1, 2, 0, 2, 3])

    result.computeVertexNormals()

    return result
  }, [axis, voxel, metadata, centre])

  const [loadedTexture, setLoadedTexture] = useState<{
    image: string
    texture: THREE.Texture
  } | null>(null)

  const texture =
    loadedTexture && image === loadedTexture.image
      ? loadedTexture.texture
      : null

  useEffect(() => {
    if (!image) return

    let live = true

    const loaded = new THREE.TextureLoader().load(image, (value) => {
      value.colorSpace = THREE.SRGBColorSpace

      value.minFilter = THREE.LinearFilter

      value.magFilter = THREE.NearestFilter

      if (live) setLoadedTexture({ image, texture: value })
      else value.dispose()
    })

    return () => {
      live = false
      loaded.dispose()
    }
  }, [image])

  useEffect(() => () => geometry.dispose(), [geometry])

  if (!texture) return null

  return (
    <mesh geometry={geometry}>
      <meshBasicMaterial
        map={texture}
        side={THREE.DoubleSide}
        transparent
        opacity={0.82}
      />
    </mesh>
  )
}

function SourceScene({
  metadata,
  voxel,
  images,
  reset,
}: {
  metadata: SpatialMetadata
  voxel: VoxelPoint
  images: Partial<Record<IndexPlane, string>>
  reset: number
}) {
  const { centre, radius, geometry } = useMemo(() => {
    const dims = metadata.dimensions_xyz!
    const affine = metadata.affine_voxel_to_display!
    const native = metadata.native_geometry
    const boxDims = native?.dimensions_xyz ?? dims
    const boxAffine = native?.affine_voxel_to_world ?? native?.affine_voxel_to_display ?? affine
    const corners = Array.from({ length: 8 }, (_, i) => {
      const point = transformPoint(boxAffine, [i & 1 ? boxDims[0] - 1 : 0, i & 2 ? boxDims[1] - 1 : 0, i & 4 ? boxDims[2] - 1 : 0])
      return metadata.view_space === "anatomical" && native?.coordinate_frame === "LPS_MM" ? [-point[0], -point[1], point[2]] as VoxelPoint : point
    })

    const centre = transformPoint(
      affine,
      dims.map((n) => (n - 1) / 2) as VoxelPoint,
    )

    const positions: number[] = []

    corners.forEach((corner, index) =>
      [1, 2, 4].forEach((bit) => {
        if (!(index & bit))
          positions.push(
            ...corner.map((v, i) => v - centre[i]),
            ...corners[index | bit].map((v, i) => v - centre[i]),
          )
      }),
    )

    const geometry = new THREE.BufferGeometry()

    geometry.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(positions, 3),
    )

    return {
      centre,
      radius: Math.max(
        1,
        ...corners.map((p) => Math.hypot(...p.map((v, i) => v - centre[i]))),
      ),
      geometry,
    }
  }, [metadata])

  useEffect(() => () => geometry.dispose(), [geometry])

  const marker = transformPoint(metadata.affine_voxel_to_display!, voxel).map(
    (v, i) => v - centre[i],
  ) as VoxelPoint

  return (
    <Canvas
      key={reset}
      camera={{
        position: [radius * 1.6, -radius * 1.6, radius * 1.3],
        fov: 45,
        near: radius / 1000,
        far: radius * 30,
      }}
      aria-label="Source volume with synchronized orthogonal image planes"
    >
      <lineSegments geometry={geometry}>
        <lineBasicMaterial color="#64748b" />
      </lineSegments>
      {INDEX_PLANES.map((axis) => (
        <SourcePlane
          key={axis}
          axis={axis}
          metadata={metadata}
          voxel={voxel}
          image={images[axis]}
          centre={centre}
        />
      ))}
      <mesh position={marker}>
        <sphereGeometry args={[radius * 0.012, 12, 12]} />
        <meshBasicMaterial color="#fb923c" />
      </mesh>
      <OrbitControls makeDefault />
    </Canvas>
  )
}

function SlicePane({
  axis,
  metadata,
  voxel,
  onVoxel,
  image,
  zoom,
  predictionImage,
  reviewerImage,
}: {
  axis: IndexPlane
  metadata: SpatialMetadata
  voxel: VoxelPoint
  onVoxel: (p: VoxelPoint) => void
  image?: string
  zoom: number
  predictionImage?: string
  reviewerImage?: string
}) {
  const group = useRef<SVGGElement>(null)

  const dims = metadata.dimensions_xyz!

  const [width, height] = planeSize(axis, dims)

  const [u, v] = voxelToDisplay(
    axis,
    voxel,
    dims,
    metadata.non_axial_vertical_flip,
  )

  const spacing =
    metadata.spacing_xyz_mm ??
    [0, 1, 2].map((i) =>
      Math.hypot(
        ...metadata.affine_voxel_to_display!.slice(0, 3).map((row) => row[i]),
      ),
    )

  const sx = spacing[axis === "sagittal" ? 1 : 0],
    sy = spacing[axis === "axial" ? 1 : 2]

  const count = dims[axis === "axial" ? 2 : axis === "coronal" ? 1 : 0]

  const index = planeIndex(axis, voxel)

  const setIndex = (next: number) => {
    const point = [...voxel] as VoxelPoint

    point[axis === "axial" ? 2 : axis === "coronal" ? 1 : 0] = Math.min(
      count - 1,
      Math.max(0, next),
    )
    onVoxel(point)
  }

  const direction = (dx: number, dy: number) => {
    if (!metadata.affine_voxel_to_world) return "?"

    const a = displayToVoxel(
      axis,
      0,
      0,
      voxel,
      dims,
      metadata.non_axial_vertical_flip,
    )

    const b = displayToVoxel(
      axis,
      dx ? width - 1 : 0,
      dy ? height - 1 : 0,
      voxel,
      dims,
      metadata.non_axial_vertical_flip,
    )

    const p = transformPoint(metadata.affine_voxel_to_world, a),
      q = transformPoint(metadata.affine_voxel_to_world, b)

    return anatomicalDirection(
      q.map((n, i) => (n - p[i]) * (dx || dy)) as VoxelPoint,
      metadata.coordinate_frame,
    )
  }

  return (
    <section
      className="overflow-hidden rounded-lg border border-line bg-surface"
      aria-label={`${axis} index plane`}
    >
      <div className="flex items-center justify-between border-b border-line px-3 py-2 text-xs">
        <span
          style={{ color: PLANE_COLORS[axis] }}
          className="font-medium capitalize"
        >
          {axis} · {metadata.view_space === "anatomical" ? "anatomical RAS plane" : "index plane"}
        </span>
        <span className="font-mono text-ink-3">
          {index + 1} / {count}
        </span>
      </div>
      <div
        className="relative h-64 overflow-hidden bg-[#080e1a]"
        onWheel={(event) => {
          event.preventDefault()
          setIndex(index + (event.deltaY > 0 ? 1 : -1))
        }}
      >
        {image ? (
          <svg
            className="h-full w-full touch-none"
            viewBox={`0 0 ${width * sx} ${height * sy}`}
            role="img"
            aria-label={`${axis} source image; click to synchronize crosshairs`}
            onPointerDown={(event) => {
              const matrix = group.current?.getScreenCTM()

              if (!matrix) return

              const point = new DOMPoint(
                event.clientX,
                event.clientY,
              ).matrixTransform(matrix.inverse())

              if (
                point.x < 0 ||
                point.x >= width ||
                point.y < 0 ||
                point.y >= height
              )
                return

              onVoxel(
                displayToVoxel(
                  axis,
                  point.x - 0.5,
                  point.y - 0.5,
                  voxel,
                  dims,
                  metadata.non_axial_vertical_flip,
                ),
              )
            }}
          >
            <g
              transform={`translate(${(width * sx) / 2} ${(height * sy) / 2}) scale(${zoom}) translate(${(-width * sx) / 2} ${(-height * sy) / 2})`}
            >
              <g ref={group} transform={`scale(${sx} ${sy})`}>
                <image
                  href={image}
                  width={width}
                  height={height}
                  style={{ imageRendering: "pixelated" }}
                />
                {predictionImage && <image href={predictionImage} width={width} height={height} style={{ imageRendering: "pixelated" }} />}
                {reviewerImage && <image href={reviewerImage} width={width} height={height} style={{ imageRendering: "pixelated" }} />}
                <path
                  d={`M ${u + 0.5} 0 V ${height} M 0 ${v + 0.5} H ${width}`}
                  fill="none"
                  stroke="#fb923c"
                  strokeWidth="1"
                  vectorEffect="non-scaling-stroke"
                  opacity={0.9}
                />
              </g>
            </g>
          </svg>
        ) : (
          <p className="p-4 text-xs text-slate-400">Loading source plane…</p>
        )}
        <span className="pointer-events-none absolute right-2 top-1/2 text-xs text-slate-300">
          {direction(1, 0)}
        </span>
        <span className="pointer-events-none absolute bottom-1 left-1/2 text-xs text-slate-300">
          {direction(0, 1)}
        </span>
        <span className="pointer-events-none absolute left-2 top-1/2 text-xs text-slate-300">
          {direction(-1, 0)}
        </span>
        <span className="pointer-events-none absolute top-1 left-1/2 text-xs text-slate-300">
          {direction(0, -1)}
        </span>
      </div>
      <label className="flex items-center gap-3 px-3 py-2 text-xs text-ink-3">
        Slice{" "}
        <input
          className="min-w-0 flex-1 accent-cyan-500"
          type="range"
          min={0}
          max={count - 1}
          value={index}
          aria-label={`${axis} slice`}
          onChange={(event) => setIndex(Number(event.target.value))}
        />
      </label>
    </section>
  )
}

type RegistrationCandidate = {
  status: string
  sources: Record<string, { upload_id: number; sha256: string }>
  fixed_to_moving_ras_mm: Matrix4Rows
  moving_to_fixed_ras_mm: Matrix4Rows
  elapsed_seconds: number
  metric: string
  initial_metric: number
  final_metric: number
  optimizer_stop: string
  semantics: string
  landmark_evaluation: { status: string; n: number; before_mean_mm?: number; after_mean_mm?: number; after_max_mm?: number }
}

function RegistrationPanel({ caseId, uploads }: { caseId: number; uploads: UploadedFile[] }) {
  const [fixed, setFixed] = useState(""); const [moving, setMoving] = useState("")
  const [fixedKind, setFixedKind] = useState(""); const [movingKind, setMovingKind] = useState("")
  const [fixedFrame, setFixedFrame] = useState(""); const [movingFrame, setMovingFrame] = useState("")
  const [sameSubject, setSameSubject] = useState(false); const [sameRegion, setSameRegion] = useState(false)
  const [landmarks, setLandmarks] = useState(""); const [metric, setMetric] = useState("mattes")
  const [busy, setBusy] = useState(false); const [failure, setFailure] = useState<string | null>(null)
  const [candidate, setCandidate] = useState<RegistrationCandidate | null>(null)
  const ticket = useRef(0)
  useEffect(() => { ticket.current++; setCandidate(null); setFailure(null); setBusy(false); setFixed(""); setMoving(""); setSameSubject(false); setSameRegion(false); setLandmarks("") }, [caseId])
  useEffect(() => { ticket.current++; setCandidate(null); setFailure(null); setBusy(false) }, [fixed, moving, fixedKind, movingKind, fixedFrame, movingFrame, sameSubject, sameRegion, metric, landmarks])
  async function compute() {
    const current = ++ticket.current; setCandidate(null); setFailure(null); setBusy(true)
    try {
      const pairs: unknown = landmarks.trim() ? JSON.parse(landmarks) : []
      if (!Array.isArray(pairs)) throw new Error("Landmarks must be a JSON array of paired RAS-mm coordinates.")
      const source = (id: string, kind: string, frame: string) => ({ upload_id: Number(id), ...(kind && frame !== "" ? { frame_kind: kind, frame_index: Number(frame) } : {}) })
      const result = await universalJson<RegistrationCandidate>(`/cases/${caseId}/spatial/registration`, { method: "POST", body: JSON.stringify({ fixed: source(fixed, fixedKind, fixedFrame), moving: source(moving, movingKind, movingFrame), same_subject_attested: sameSubject, same_anatomical_region_attested: sameRegion, metric, landmarks: pairs, landmark_source: "REVIEWER_SUPPLIED_UNVERIFIED" }) })
      if (current === ticket.current) setCandidate(result)
    } catch (error) { if (current === ticket.current) setFailure(String(error)) }
    finally { if (current === ticket.current) setBusy(false) }
  }
  return <details className="space-y-3 rounded-lg border border-line p-3" data-testid="spatial-registration-panel">
    <summary className="cursor-pointer text-xs font-medium text-ink">Compare source geometry · rigid research registration</summary>
    <p className="text-xs text-ink-3">Compute an unapproved same-case source-to-source rigid transform. Sources need coded physical geometry with known units. Optimization uses bounded grids and never changes source images, model outputs or atlas registration.</p>
    <div className="grid gap-3 md:grid-cols-2">{(["fixed", "moving"] as const).map((which) => {
      const isFixed = which === "fixed", id = isFixed ? fixed : moving, kind = isFixed ? fixedKind : movingKind, frame = isFixed ? fixedFrame : movingFrame
      return <div key={which} className="space-y-2 rounded border border-line p-2"><label className="block text-xs capitalize">{which} source<select className={`${controlClass} mt-1 block w-full`} aria-label={`Registration ${which} source`} value={id} onChange={(event) => { (isFixed ? setFixed : setMoving)(event.target.value); setCandidate(null); setSameSubject(false); setSameRegion(false) }}><option value="">Choose a case-bound source</option>{uploads.map((upload) => <option key={upload.id} value={upload.id}>{upload.filename} · #{upload.id}</option>)}</select></label><div className="flex gap-2"><select className={`${controlClass} min-w-0 flex-1`} aria-label={`Registration ${which} fourth-axis kind`} value={kind} onChange={(event) => (isFixed ? setFixedKind : setMovingKind)(event.target.value)}><option value="">3D source / no fourth axis</option><option value="channel">Explicit channel</option><option value="time">Explicit timepoint</option></select><input className={`${controlClass} w-24`} type="number" min={0} max={4095} aria-label={`Registration ${which} frame index`} placeholder="Index" value={frame} disabled={!kind} onChange={(event) => (isFixed ? setFixedFrame : setMovingFrame)(event.target.value)} /></div></div>
    })}</div>
    <label className="block text-xs"><input type="checkbox" checked={sameSubject} onChange={(event) => setSameSubject(event.target.checked)} /> I confirm these sources describe the same subject.</label>
    <label className="block text-xs"><input type="checkbox" checked={sameRegion} onChange={(event) => setSameRegion(event.target.checked)} /> I confirm these sources cover the same anatomical region with sufficient overlap.</label>
    <label className="block text-xs">Similarity metric<select className={`${controlClass} ml-2`} aria-label="Registration similarity metric" value={metric} onChange={(event) => setMetric(event.target.value)}><option value="mattes">Mattes mutual information</option><option value="mean_squares">Mean squares (comparable intensities)</option></select></label>
    <label className="block text-xs">Optional held-out paired landmarks (3–100) in RAS millimetres<textarea className="mt-1 block min-h-20 w-full rounded border border-line bg-surface p-2 font-mono text-[11px]" aria-label="Registration held-out landmarks JSON" value={landmarks} onChange={(event) => setLandmarks(event.target.value)} placeholder={'[{"fixed_ras_mm":[10,20,30],"moving_ras_mm":[11,20,30]}, ...]'} maxLength={30000} /></label>
    <p className="text-[11px] text-ink-3">These correspondences are evaluated after optimization and are never optimizer inputs. Reviewer-supplied coordinates do not constitute independent expert or clinical validation.</p>
    <button className={controlClass} disabled={!fixed || !moving || !sameSubject || !sameRegion || busy || (!!fixedKind && fixedFrame === "") || (!!movingKind && movingFrame === "")} onClick={() => void compute()}>{busy ? "Computing bounded candidate…" : "Compute unapproved rigid candidate"}</button>
    {failure && <ErrorBlock message={failure} />}
    {candidate && <div className="space-y-2 rounded border border-amber-500/30 p-3 text-xs" role="status"><p className="font-mono text-amber-700">{candidate.status} · no atlas or clinical activation</p><p>{candidate.elapsed_seconds.toFixed(2)} s · {candidate.metric} · same-grid similarity {candidate.initial_metric.toFixed(5)} → {candidate.final_metric.toFixed(5)}</p><p>{candidate.optimizer_stop}</p><p>Held-out landmarks: {candidate.landmark_evaluation.status} · n={candidate.landmark_evaluation.n}{candidate.landmark_evaluation.after_mean_mm != null ? ` · mean TRE ${candidate.landmark_evaluation.after_mean_mm.toFixed(3)} mm · max ${candidate.landmark_evaluation.after_max_mm?.toFixed(3)} mm` : " · no independent localization error measured"}</p><details><summary>Inspect both RAS-mm transform directions</summary><pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-all text-[10px]">{JSON.stringify({ sources: candidate.sources, fixed_to_moving_ras_mm: candidate.fixed_to_moving_ras_mm, moving_to_fixed_ras_mm: candidate.moving_to_fixed_ras_mm }, null, 2)}</pre></details><p className="text-ink-3">{candidate.semantics}</p></div>}
  </details>
}

export default function UniversalImagingWorkbench({
  caseId,
  uploadId = null,
  onSelectUpload,
  findingId,
}: {
  caseId: number | null
  uploadId?: number | null
  onSelectUpload?: (id: number) => void
  findingId?: number | null
}) {
  const [uploads, setUploads] = useState<UploadedFile[]>([])

  const [selected, setSelected] = useState<number | null>(uploadId)

  const [metadata, setMetadata] = useState<SpatialMetadata | null>(null)

  const [voxel, setVoxel] = useState<VoxelPoint>([0, 0, 0])

  const [images, setImages] = useState<Partial<Record<IndexPlane, string>>>({})
  const [predictionImages, setPredictionImages] = useState<Partial<Record<IndexPlane, string>>>({})
  const [reviewerImages, setReviewerImages] = useState<Partial<Record<IndexPlane, string>>>({})
  const [frameKind, setFrameKind] = useState<"" | "channel" | "time">("")
  const [frameIndex, setFrameIndex] = useState("")
  const [frameInfo, setFrameInfo] = useState<SpatialMetadata["frame_selection"]>(undefined)
  const [viewSpace, setViewSpace] = useState<"source" | "anatomical">("source")

  const [error, setError] = useState<string | null>(null)

  const [loading, setLoading] = useState(false)

  const [center, setCenter] = useState("")
  const [windowWidth, setWindowWidth] = useState("")
  const [zoom, setZoom] = useState(1)
  const [reset, setReset] = useState(0)

  const [seriesIds, setSeriesIds] = useState<number[]>([])
  const [seriesReference, setSeriesReference] = useState("")
  const [phase, setPhase] = useState("")

  const [seriesRequest, setSeriesRequest] = useState<{
    upload_ids: number[]
    series_reference: string | null
    phase: number | null
  } | null>(null)

  const [run, setRun] = useState<ResearchRun | null>(null)
  const [showPrediction, setShowPrediction] = useState(false)
  const [showSurface, setShowSurface] = useState(false)

  const [correctionSummary, setCorrectionSummary] =
    useState<VolumeCorrectionSummary | null>(null)

  const [annotations, setAnnotations] = useState<ReferenceAnnotation[]>([])
  const [correctionVersion, setCorrectionVersion] = useState(0)
  const [showCorrections, setShowCorrections] = useState(true)

  const sourceTicket = useRef(0)

  useEffect(() => {
    setSelected(uploadId)
    setFrameKind("")
    setFrameIndex("")
    setFrameInfo(undefined)
    setViewSpace("source")
  }, [uploadId, caseId])

  useEffect(() => {
    const controller = new AbortController()

    setUploads([])
    setMetadata(null)
    setRun(null)
    setSeriesIds([])
    setSeriesRequest(null)
    setError(null)

    if (caseId !== null)
      universalJson<UploadedFile[]>(`/cases/${caseId}/uploads`, {
        signal: controller.signal,
      }).then(
        (data) =>
          setUploads(
            data.filter(
              (item) =>
                item.modality === "IMAGE" &&
                item.is_associated &&
                !item.withdrawn_at &&
                !item.superseded_by_file_id,
            ),
          ),
        (err: unknown) => {
          if (!controller.signal.aborted) setError(String(err))
        },
      )

    return () => controller.abort()
  }, [caseId]) // Selection is updated separately; case changes always clear patient-specific state.

  useEffect(() => {
    const controller = new AbortController()
    const ticket = ++sourceTicket.current

    setMetadata(null)
    setRun(null)
    setShowPrediction(false)
    setShowSurface(false)
    setCorrectionSummary(null)
    setError(null)

    if (
      !caseId ||
      (!seriesRequest &&
        !uploads.some(
          (item) => item.id === selected && item.case_id === caseId,
        ))
    ) {
      setLoading(false)
      return
    }

    setLoading(true)
    const selectors = new URLSearchParams({ view_space: viewSpace })
    if (frameKind && frameIndex !== "") {
      selectors.set("frame_kind", frameKind)
      selectors.set("frame_index", frameIndex)
    }

    const request = seriesRequest
      ? universalJson<SpatialMetadata>(
          `/cases/${caseId}/spatial/series-metadata?view_space=${viewSpace}`,
          {
            method: "POST",
            body: JSON.stringify(seriesRequest),
            signal: controller.signal,
          },
        )
      : universalJson<SpatialMetadata>(
          `/uploads/${selected}/spatial/metadata?${selectors}`,
          { signal: controller.signal },
        )

    request
      .then(
        (data) => {
          if (ticket !== sourceTicket.current || controller.signal.aborted)
            return
          setMetadata(data)
          setFrameInfo(data.frame_selection)
          setVoxel(
            (data.dimensions_xyz ?? [1, 1, 1]).map((n) =>
              Math.floor((n - 1) / 2),
            ) as VoxelPoint,
          )
          setZoom(1)
          setCenter("")
          setWindowWidth("")
          setReset((n) => n + 1)
        },
        (err: unknown) => {
          if (!controller.signal.aborted) setError(String(err))
        },
      )
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => controller.abort()
  }, [caseId, selected, seriesRequest, uploads, frameKind, frameIndex, viewSpace]) // Series parameters are submitted explicitly by the assemble button.

  useEffect(() => {
    if (!metadata || metadata.status !== "AVAILABLE") {
      setImages({})
      return
    }

    const controller = new AbortController()
    const urls: string[] = []
    let live = true

    setImages({})

    const timer = window.setTimeout(() => {
      // Canonical native readers decode the volume per request. Serialize the three
      // planes so one viewer does not multiply the peak decoded-volume allocation.
      const render = async () => {
        const entries: Array<[IndexPlane, string]> = []
        for (const axis of INDEX_PLANES) {
          const input = metadata.render_input

          const index = planeIndex(axis, voxel)

          const windowing =
            center !== "" &&
            windowWidth !== "" &&
            Number.isFinite(Number(center)) &&
            Number(windowWidth) > 0
              ? { center: Number(center), width: Number(windowWidth) }
              : {}

          const response =
            input.kind === "UPLOAD"
              ? await universalFetch(
                  `${input.path}?${new URLSearchParams({ ...Object.fromEntries(Object.entries(input.query ?? {}).map(([key, value]) => [key, String(value)])), axis, index: String(index), ...Object.fromEntries(Object.entries(windowing).map(([key, value]) => [key, String(value)])) })}`,
                  { signal: controller.signal },
                )
              : await universalFetch(input.path, {
                  method: "POST",
                  body: JSON.stringify({
                    ...input.body,
                    axis,
                    index,
                    ...windowing,
                  }),
                  signal: controller.signal,
                })

          const blob = await response.blob()

          if (!live) return entries

          const url = URL.createObjectURL(blob)
          urls.push(url)
          entries.push([axis, url])
        }
        return entries
      }
      void render().then(
        (entries) => {
          if (live) setImages(Object.fromEntries(entries))
        },
        (err: unknown) => {
          if (live) setError(String(err))
        },
      )
    }, 120)

    return () => {
      live = false
      controller.abort()
      window.clearTimeout(timer)
      urls.forEach(URL.revokeObjectURL)
    }
  }, [metadata, voxel, center, windowWidth])

  useEffect(() => {
    const controller = new AbortController()
    setRun(null)

    if (
      metadata?.status === "AVAILABLE" &&
      metadata.source.kind === "UPLOAD" &&
      metadata.source.upload_id &&
      !(metadata.frame_selection?.required && metadata.frame_selection.kind === "time")
    ) {
      universalJson<{ runs: ResearchRun[] }>(
        `/uploads/${metadata.source.upload_id}/research-inference`,
        { signal: controller.signal },
      ).then(
        (data) => {
          if (controller.signal.aborted) return

          const eligible = data.runs.find(
            (item) =>
              (findingId === undefined || (findingId !== null && item.finding_id === findingId)) &&
              item.research_output?.type === "volume_segmentation" &&
              item.research_output.volume_shape_ijk.every(
                (n, i) => n === (metadata.native_geometry?.dimensions_xyz ?? metadata.dimensions_xyz)?.[i],
              ) &&
              (!(metadata.native_geometry?.spacing_xyz_mm ?? metadata.spacing_xyz_mm) ||
                item.research_output.voxel_spacing_mm.every(
                  (n, i) => Math.abs(n - (metadata.native_geometry?.spacing_xyz_mm ?? metadata.spacing_xyz_mm)![i]) < 1e-5,
                )),
          )

          setRun(eligible ?? null)
        },
        (err: unknown) => {
          if (!controller.signal.aborted) setError(String(err))
        },
      )
    }

    return () => controller.abort()
  }, [metadata, findingId])

  const output =
    run?.research_output?.type === "volume_segmentation"
      ? run.research_output
      : null

  const sliceOutput = useMemo(() => {
    if (!output) return null

    const plane = output.slices.find((s) => s.slice_index === voxel[2])

    return {
      type: "segmentation",
      image_size: output.volume_shape_ijk.slice(0, 2),
      coordinate_space: "axial index plane (i,j)",
      segments: (plane?.segments ?? []).map((s) => ({
        ...s,
        segment:
          output.structures.find((item) => item.class_index === s.class_index)
            ?.structure ?? `class ${s.class_index}`,
      })),
    } as Extract<ResearchOutput, { type: "segmentation" }>
  }, [output, voxel])

  useEffect(() => {
    let live = true
    setCorrectionSummary(null)
    setAnnotations([])

    if (run && metadata?.source.upload_id)
      Promise.all([
        api.getVolumeSliceCorrections(run.id),
        api.listReferenceAnnotations(metadata.source.upload_id),
      ]).then(
        ([summary, data]) => {
          if (live) {
            setCorrectionSummary(summary)
            setAnnotations(
              data.annotations.filter(
                (item) =>
                  item.derived_from_run_id === run.id &&
                  item.kind === "VOLUME_SLICE_CORRECTION",
              ),
            )
          }
        },
        (err: unknown) => {
          if (live) setError(String(err))
        },
      )

    return () => {
      live = false
    }
  }, [run, metadata, correctionVersion])

  useEffect(() => {
    setPredictionImages({}); setReviewerImages({})
    if (!metadata || metadata.status !== "AVAILABLE" || !run || metadata.render_input.kind !== "UPLOAD") return
    const controller = new AbortController(); const urls: string[] = []; let live = true
    const load = async () => {
      for (const layer of ["prediction", "reviewer"] as const) {
        if (layer === "prediction" ? !showPrediction : !showCorrections || !annotations.length) continue
        const entries: Array<[IndexPlane, string]> = []
        for (const axis of INDEX_PLANES) {
          const query = new URLSearchParams(Object.fromEntries(Object.entries(metadata.render_input.query ?? {}).map(([key, value]) => [key, String(value)])))
          query.set("axis", axis); query.set("index", String(planeIndex(axis, voxel))); query.set("layer", layer); query.set("run_id", String(run.id))
          const response = await universalFetch(`${metadata.render_input.path}?${query}`, { signal: controller.signal })
          const blob = await response.blob(); if (!live) return
          const url = URL.createObjectURL(blob); urls.push(url); entries.push([axis, url])
        }
        if (live) (layer === "prediction" ? setPredictionImages : setReviewerImages)(Object.fromEntries(entries))
      }
    }
    const timer = window.setTimeout(() => { void load().catch((err: unknown) => { if (live) setError(String(err)) }) }, 150)
    return () => { live = false; controller.abort(); window.clearTimeout(timer); urls.forEach(URL.revokeObjectURL) }
  }, [metadata, run, voxel, showPrediction, showCorrections, annotations, correctionVersion])

  const world = metadata?.affine_voxel_to_world
    ? transformPoint(metadata.affine_voxel_to_world, voxel)
    : null
  const nativeVoxel = metadata?.view_to_native_voxel ? transformPoint(metadata.view_to_native_voxel, voxel) : voxel

  return (
    <div className="space-y-4" data-testid="universal-imaging-workbench">
      {caseId != null && <RegistrationPanel key={caseId} caseId={caseId} uploads={uploads} />}
      {caseId != null && <TemporalImageComparison key={`temporal-${caseId}`} caseId={caseId} uploads={uploads} />}
      <div className="flex flex-wrap items-end gap-3">
        <label className="min-w-48 flex-1 text-xs text-ink-2">
          Case source image
          <select
            className={`${controlClass} mt-1 block w-full`}
            aria-label="Spatial source upload"
            value={selected ?? ""}
            onChange={(event) => {
              const id = Number(event.target.value)
              setSeriesRequest(null)
              setSelected(id || null)
              setFrameKind("")
              setFrameIndex("")
              setFrameInfo(undefined)
              setViewSpace("source")
              if (id) onSelectUpload?.(id)
            }}
          >
            <option value="">Select an associated image</option>
            {uploads.map((item) => (
              <option key={item.id} value={item.id}>
                {item.filename} · #{item.id}
              </option>
            ))}
          </select>
        </label>
        <button
          className={controlClass}
          onClick={() => {
            if (metadata?.dimensions_xyz)
              setVoxel(
                metadata.dimensions_xyz.map((n) =>
                  Math.floor((n - 1) / 2),
                ) as VoxelPoint,
              )
            setCenter("")
            setWindowWidth("")
            setZoom(1)
            setReset((n) => n + 1)
          }}
        >
          Reset view
        </button>
      </div>
      {frameInfo?.required && <div className="flex flex-wrap items-end gap-3 rounded-lg border border-cyan-500/30 p-3" aria-label="Explicit fourth-axis selection">
        <label className="text-xs text-ink-2">Fourth-axis interpretation<select className={`${controlClass} mt-1 block`} aria-label="Fourth-axis interpretation" value={frameKind} onChange={(event) => setFrameKind(event.target.value as typeof frameKind)}><option value="">Choose explicitly</option><option value="channel">Channels / sequences</option><option value="time">Timepoints</option></select></label>
        <label className="text-xs text-ink-2">Zero-based frame index<input className={`${controlClass} mt-1 block w-32`} aria-label="Fourth-axis frame index" type="number" min={0} max={frameInfo.count - 1} placeholder={`0–${frameInfo.count - 1}`} value={frameIndex} onChange={(event) => setFrameIndex(event.target.value)} /></label>
        <p className="max-w-xl text-xs text-ink-3">{frameInfo.count} entries on axis 3. Header time units: {frameInfo.header_temporal_units ?? "unknown"}. Select both fields; no frame is selected automatically. Declaring channels or time does not establish the sequence identity.</p>
      </div>}
      {metadata?.status === "AVAILABLE" && <label className="flex flex-wrap items-center gap-3 text-xs text-ink-2">Plane geometry<select className={controlClass} aria-label="Plane geometry" value={viewSpace} onChange={(event) => setViewSpace(event.target.value as typeof viewSpace)}><option value="source">Original source index planes</option><option value="anatomical" disabled={!metadata.available_view_spaces?.includes("anatomical")}>Resampled anatomical RAS planes</option></select>{!metadata.available_view_spaces?.includes("anatomical") && <span className="text-ink-3">Anatomical resampling requires a coded transform with known spatial units.</span>}</label>}
      <details className="rounded-lg border border-line p-3">
        <summary className="cursor-pointer text-xs font-medium text-ink">
          Assemble native multi-file DICOM
        </summary>
        <p className="mt-2 text-xs text-ink-3">
          Select DICOM files from this case. Geometry validation rejects
          inconsistent series, gaps and ambiguous phases; this does not run a
          model.
        </p>
        <div className="my-2 max-h-32 overflow-auto">
          {uploads.map((item) => (
            <label key={item.id} className="flex gap-2 py-1 text-xs text-ink-2">
              <input
                type="checkbox"
                checked={seriesIds.includes(item.id)}
                onChange={(event) =>
                  setSeriesIds((ids) =>
                    event.target.checked
                      ? [...ids, item.id]
                      : ids.filter((id) => id !== item.id),
                  )
                }
              />
              {item.filename} · #{item.id}
            </label>
          ))}
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-xs">
            Series reference (if requested)
            <input
              value={seriesReference}
              className={`${controlClass} block`}
              onChange={(event) => setSeriesReference(event.target.value)}
              maxLength={16}
            />
          </label>
          <label className="text-xs">
            Phase ordinal (if requested)
            <input
              type="number"
              min={0}
              max={1000}
              className={`${controlClass} block w-32`}
              value={phase}
              onChange={(event) => setPhase(event.target.value)}
            />
          </label>
          <button
            className={controlClass}
            disabled={seriesIds.length < 2 || loading}
            onClick={() =>
              setSeriesRequest({
                upload_ids: [...seriesIds],
                series_reference: seriesReference || null,
                phase: phase === "" ? null : Number(phase),
              })
            }
          >
            Validate and assemble
          </button>
        </div>
      </details>
      {!caseId && (
        <p className="text-sm text-ink-3">
          Select a case to inspect its spatial evidence.
        </p>
      )}
      {error && <ErrorBlock message={error} />}
      {loading && (
        <p className="text-xs text-ink-3">Reading bounded source geometry…</p>
      )}
      {metadata?.status === "REFUSED" && (
        <div
          role="status"
          className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4"
        >
          <p className="font-mono text-xs text-amber-700">
            {metadata.refusal?.code}
          </p>
          <p className="mt-1 text-sm text-ink-2">{metadata.refusal?.reason}</p>
          {metadata.series_report && (
            <pre className="mt-2 max-h-52 overflow-auto whitespace-pre-wrap text-[10px] text-ink-3">
              {JSON.stringify(metadata.series_report, null, 2)}
            </pre>
          )}
        </div>
      )}
      {metadata?.status === "AVAILABLE" && metadata.dimensions_xyz && (
        <>
          <div className="flex flex-wrap items-end gap-3 rounded-lg border border-line p-3">
            <label className="text-xs text-ink-2">
              Window centre
              <input
                className={`${controlClass} mt-1 block w-28`}
                type="number"
                placeholder="Auto"
                value={center}
                onChange={(event) => setCenter(event.target.value)}
              />
            </label>
            <label className="text-xs text-ink-2">
              Window width
              <input
                className={`${controlClass} mt-1 block w-28`}
                type="number"
                min="0.000001"
                placeholder="Auto"
                value={windowWidth}
                onChange={(event) => setWindowWidth(event.target.value)}
              />
            </label>
            <label className="text-xs text-ink-2">
              Zoom {zoom.toFixed(1)}×
              <input
                className="mt-2 block accent-cyan-500"
                type="range"
                min={1}
                max={5}
                step={0.1}
                value={zoom}
                onChange={(event) => setZoom(Number(event.target.value))}
              />
            </label>
            <div className="text-xs text-ink-2">
              <p className="font-mono">{metadata.view_space === "anatomical" ? "View voxel" : "Voxel"} (i,j,k): {voxel.join(", ")}</p>
              {metadata.view_space === "anatomical" && <p className="mt-1 font-mono">Native voxel (i,j,k): {nativeVoxel.map((n) => n.toFixed(3)).join(", ")} · continuous interpolation location</p>}
              <p className="mt-1 font-mono">
                {world
                  ? `${metadata.coordinate_frame}: ${world.map((n) => n.toFixed(2)).join(", ")} mm`
                  : "Patient coordinates unavailable · source grid only"}
              </p>
            </div>
          </div>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {INDEX_PLANES.map((axis) => (
              <SlicePane
                key={axis}
                axis={axis}
                metadata={metadata}
                voxel={voxel}
                onVoxel={setVoxel}
                image={images[axis]}
                zoom={zoom}
                predictionImage={predictionImages[axis]}
                reviewerImage={reviewerImages[axis]}
              />
            ))}
            <section className="overflow-hidden rounded-lg border border-line">
              <div className="border-b border-line px-3 py-2 text-xs font-medium text-ink">
                3D source image planes · {metadata.display_frame}
              </div>
              <div className="h-64 bg-[#080e1a]">
                <SourceScene
                  metadata={metadata}
                  voxel={voxel}
                  images={images}
                  reset={reset}
                />
              </div>
              <p className="px-3 py-2 text-[11px] text-ink-3">
                Drag to orbit; scroll to zoom. Orange point is the selected
                source voxel. Image planes and source bounds are derived from
                this source, with no segmented surface inferred.
              </p>
            </section>
          </div>
          <div className="rounded-lg border border-line p-3 text-xs text-ink-3">
            <p>{metadata.plane_definition}</p>
            <p className="mt-1">
              Auto window uses each plane's 0.5–99.5 percentile. Set both window
              fields to apply the same intensity window to all planes.
            </p>
            <p className="mt-1">
              Dimensions {metadata.dimensions_xyz.join(" × ")} ·{" "}
              {metadata.spacing_xyz_mm
                ? `spacing ${metadata.spacing_xyz_mm.map((n) => n.toFixed(3)).join(" × ")} mm`
                : "spacing units unverified"}{" "}
              · no atlas registration available. Edge labels follow the source
              affine only when verified; combined labels denote oblique
              directions.
            </p>
            {metadata.warnings.map((warning) => (
              <p key={warning} className="mt-1 text-amber-700">
                {warning}
              </p>
            ))}
            <p className="mt-1 break-all font-mono text-[10px]">
              Source {metadata.source.kind}{" "}
              {metadata.source.upload_id
                ? `#${metadata.source.upload_id} · SHA-256 ${metadata.source.sha256}`
                : "· individually hashed case-bound DICOM uploads"}
            </p>
          </div>
          {run && output && (
            <section className="space-y-3 rounded-lg border border-line p-3">
              <p className="text-xs font-medium text-ink">
                Stored research segmentation · run #{run.id}
              </p>
              <div className="flex flex-wrap gap-3 text-xs text-ink-2">
                <label>
                  <input
                    type="checkbox"
                    checked={showPrediction}
                    onChange={(event) =>
                      setShowPrediction(event.target.checked)
                    }
                  />{" "}
                  Show original model mask on all planes
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={showCorrections}
                    onChange={(event) =>
                      setShowCorrections(event.target.checked)
                    }
                  />{" "}
                  Show saved reviewer corrections (orange)
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={showSurface}
                    onChange={(event) => setShowSurface(event.target.checked)}
                  />{" "}
                  Show actual mask-derived surfaces
                </label>
              </div>
              {metadata.frame_selection?.required && <p className="text-[11px] text-ink-3">This stored run consumed its declared multi-input source. Its 3D spatial mask is shared across channels; selecting a channel does not run or validate an independent channel-specific model.</p>}
              {showSurface && (
                <Suspense
                  fallback={<p className="text-xs">Loading surface viewer…</p>}
                >
                  <VolumeSurfaceView runId={run.id} colors={COLORS} />
                </Suspense>
              )}
              {!metadata.spacing_xyz_mm && (
                <p
                  role="status"
                  className="rounded border border-amber-500/30 p-2 text-xs text-amber-700"
                >
                  Physical scale is unverified in this source header. The legacy
                  research surface panel reports mm under the model's spacing
                  convention; these are not verified patient millimetres or
                  clinical measurements.
                </p>
              )}
              <p className="text-[11px] text-ink-3">
                Surfaces use the existing run's source voxel grid scaled by
                spacing; they are displayed separately from patient-world
                planes. Reviewer corrections are stored beside the original
                prediction and do not retrain the model.
              </p>
              {correctionSummary && (
                <p className="text-[11px] text-ink-3">
                  Saved corrections: {correctionSummary.corrected_slices.length}{" "}
                  slice/structure entries. {correctionSummary.semantics}
                </p>
              )}
              {metadata.view_space === "anatomical" && <p className="text-xs text-ink-3">Reviewer edits remain anchored to original native axial voxels. Select original source index planes to edit; masks displayed here are remapped with nearest-neighbour interpolation.</p>}
              {metadata.view_space !== "anatomical" && sliceOutput && images.axial && (
                <details>
                  <summary className="cursor-pointer text-xs text-ink">
                    Correct axial index plane {voxel[2]} · brush, eraser,
                    polygon, undo
                  </summary>
                  <MaskCorrectionEditor
                    key={`${run.id}-${voxel[2]}`}
                    run={run}
                    output={sliceOutput}
                    imageUrl={images.axial}
                    classNames={output.structures.map((s) => s.structure)}
                    save={(mask, fields) =>
                      api.addVolumeSliceCorrection(
                        run.id,
                        voxel[2],
                        mask,
                        fields,
                      )
                    }
                    onSaved={() => {
                      setShowCorrections(true)
                      setCorrectionVersion((n) => n + 1)
                    }}
                  />
                </details>
              )}
            </section>
          )}
          {!run && (
            <p className="text-xs text-ink-3">
              No matching stored native-volume segmentation was found. Lesion
              meshes and correction tools require an actual eligible model run.
            </p>
          )}
        </>
      )}
    </div>
  )
}
