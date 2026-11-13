import { useEffect, useRef, useState } from "react";
import type { UploadedFile } from "../services/api";
import { universalFetch, universalJson } from "../services/universal";
import { ErrorBlock } from "./ui";

type Axis = "axial" | "coronal" | "sagittal";
type Mode = "blend" | "checkerboard" | "difference";
type Comparison = { comparison_id: string; expires_in_seconds: number; status: string; alignment_evidence: string; semantics: string; sources: Record<string, { upload_id: number; sha256: string }>; reference_grid: { dimensions_xyz: [number, number, number] }; intensity: { difference_allowed: boolean; refusal: { code: string; reason: string } | null; previous: { unit: string | null } } };
const control = "rounded border border-line bg-surface px-2 py-1.5 text-xs text-ink disabled:opacity-40";

export default function TemporalImageComparison({ caseId, uploads }: { caseId: number; uploads: UploadedFile[] }) {
  const [previous, setPrevious] = useState(""); const [current, setCurrent] = useState("");
  const [previousKind, setPreviousKind] = useState(""); const [currentKind, setCurrentKind] = useState("");
  const [previousFrame, setPreviousFrame] = useState(""); const [currentFrame, setCurrentFrame] = useState("");
  const [previousRegion, setPreviousRegion] = useState(""); const [currentRegion, setCurrentRegion] = useState("");
  const [subject, setSubject] = useState(false); const [region, setRegion] = useState(false); const [intensity, setIntensity] = useState(false); const [shared, setShared] = useState(false);
  const [alignment, setAlignment] = useState("compute_rigid"); const [busy, setBusy] = useState(false);
  const [comparison, setComparison] = useState<Comparison | null>(null); const [error, setError] = useState<string | null>(null);
  const [axis, setAxis] = useState<Axis>("axial"); const [index, setIndex] = useState(0); const [mode, setMode] = useState<Mode>("checkerboard");
  const [center, setCenter] = useState(""); const [width, setWidth] = useState(""); const [blend, setBlend] = useState(.5);
  const [images, setImages] = useState<Record<string, string>>({}); const [statistics, setStatistics] = useState<Record<string, number> | null>(null);
  const ticket = useRef(0);
  useEffect(() => { ticket.current++; setComparison(null); setImages({}); setError(null); setBusy(false); }, [caseId, previous, current, previousKind, currentKind, previousFrame, currentFrame, previousRegion, currentRegion, subject, region, intensity, shared, alignment]);
  const source = (id: string, kind: string, frame: string) => ({ upload_id: Number(id), sha256: uploads.find((item) => item.id === Number(id))?.file_hash ?? "", ...(kind && frame !== "" ? { frame_kind: kind, frame_index: Number(frame) } : {}) });
  async function prepare() {
    const currentTicket = ++ticket.current; setBusy(true); setError(null); setComparison(null);
    try {
      const result = await universalJson<Comparison>(`/cases/${caseId}/temporal-comparisons`, { method: "POST", body: JSON.stringify({ previous: source(previous, previousKind, previousFrame), current: source(current, currentKind, currentFrame), previous_region: previousRegion, current_region: currentRegion, same_subject_attested: subject, same_region_attested: region, comparable_intensity_attested: intensity, alignment, shared_physical_space_attested: shared }) });
      if (ticket.current === currentTicket) { setComparison(result); setAxis("axial"); setIndex(Math.floor(result.reference_grid.dimensions_xyz[2]/2)); setMode("checkerboard"); }
    } catch (failure) { if (ticket.current === currentTicket) setError(String(failure)); }
    finally { if (ticket.current === currentTicket) setBusy(false); }
  }
  useEffect(() => {
    setImages({}); setStatistics(null);
    if (!comparison) return;
    let live = true; const controller = new AbortController(); const urls: string[] = [];
    const render = async () => {
      const result: Record<string, string> = {};
      for (const view of ["previous", "current", mode]) {
        const response = await universalFetch(`/cases/${caseId}/temporal-comparisons/${comparison.comparison_id}/render`, { method: "POST", body: JSON.stringify({ axis, index, mode: view, blend, ...(center !== "" && width !== "" ? { center: Number(center), width: Number(width) } : {}) }), signal: controller.signal });
        const blob = await response.blob(); if (!live) return;
        const url = URL.createObjectURL(blob); urls.push(url); result[view] = url;
        if (view === mode) setStatistics(JSON.parse(response.headers.get("X-MedTwin-Comparison") ?? "{}").statistics ?? null);
      }
      if (live) setImages(result);
    };
    const timer = window.setTimeout(() => { void render().catch((failure: unknown) => { if (live) setError(String(failure)); }); }, 150);
    return () => { live = false; controller.abort(); window.clearTimeout(timer); urls.forEach(URL.revokeObjectURL); };
  }, [comparison, caseId, axis, index, mode, center, width, blend]);
  const dimensions = comparison?.reference_grid.dimensions_xyz;
  const count = dimensions?.[axis === "axial" ? 2 : axis === "coronal" ? 1 : 0] ?? 1;
  return <details className="space-y-3 rounded-lg border border-line p-3" data-testid="temporal-image-comparison">
    <summary className="cursor-pointer text-xs font-medium text-ink">Time-travel imaging · matched source comparison</summary>
    <p className="text-xs text-ink-3">Declare previous/current source order and matching anatomy. Alignment remains an unvalidated research candidate. Pixel changes do not establish disease progression. Upload timestamps are not scan dates.</p>
    <div className="grid gap-3 md:grid-cols-2">{(["previous", "current"] as const).map((which) => {
      const old = which === "previous", id = old ? previous : current, kind = old ? previousKind : currentKind, frame = old ? previousFrame : currentFrame;
      return <div className="space-y-2 rounded border border-line p-2" key={which}><label className="block text-xs capitalize">{which} source<select className={`${control} mt-1 w-full`} aria-label={`Temporal ${which} source`} value={id} onChange={(event) => (old ? setPrevious : setCurrent)(event.target.value)}><option value="">Select a source</option>{uploads.map((upload) => <option value={upload.id} key={upload.id}>{upload.filename} · #{upload.id}</option>)}</select></label><div className="flex gap-2"><select className={`${control} min-w-0 flex-1`} aria-label={`Temporal ${which} frame kind`} value={kind} onChange={(event) => (old ? setPreviousKind : setCurrentKind)(event.target.value)}><option value="">3D source</option><option value="channel">Explicit channel</option><option value="time">Explicit timepoint</option></select><input type="number" min={0} max={4095} disabled={!kind} className={`${control} w-24`} aria-label={`Temporal ${which} frame index`} value={frame} onChange={(event) => (old ? setPreviousFrame : setCurrentFrame)(event.target.value)} placeholder="Index" /></div><label className="block text-xs">Anatomical region<input className={`${control} mt-1 w-full`} aria-label={`Temporal ${which} anatomical region`} value={old ? previousRegion : currentRegion} onChange={(event) => (old ? setPreviousRegion : setCurrentRegion)(event.target.value)} maxLength={80} placeholder="e.g. brain, left knee, synthetic phantom" /></label></div>;
    })}</div>
    <label className="block text-xs"><input type="checkbox" checked={subject} onChange={(event) => setSubject(event.target.checked)} /> Same subject at both declared timepoints</label>
    <label className="block text-xs"><input type="checkbox" checked={region} onChange={(event) => setRegion(event.target.checked)} /> Matching anatomical region and acquisition coverage</label>
    <label className="block text-xs"><input type="checkbox" checked={intensity} onChange={(event) => setIntensity(event.target.checked)} /> Comparable intensity protocol (actual encoded metadata must also qualify)</label>
    <label className="block text-xs">Alignment<select className={`${control} ml-2`} aria-label="Temporal alignment" value={alignment} onChange={(event) => setAlignment(event.target.value)}><option value="compute_rigid">Compute bounded rigid candidate</option><option value="shared_physical_space">Already shares physical space</option></select></label>
    {alignment === "shared_physical_space" && <label className="block text-xs"><input type="checkbox" checked={shared} onChange={(event) => setShared(event.target.checked)} /> I explicitly attest pre-existing anatomical alignment; coded affines alone do not verify it.</label>}
    <button className={control} disabled={busy || !previous || !current || !subject || !region || previousRegion.length < 2 || currentRegion.length < 2 || (alignment === "shared_physical_space" && !shared) || (!!previousKind && previousFrame === "") || (!!currentKind && currentFrame === "")} onClick={() => void prepare()}>{busy ? "Preparing source comparison…" : "Prepare matched comparison"}</button>
    {error && <ErrorBlock message={error} />}
    {comparison && <div className="space-y-3"><p className="font-mono text-xs text-amber-700">{comparison.status} · {comparison.alignment_evidence} · expires in {comparison.expires_in_seconds} seconds</p><p className="text-xs text-ink-3">{comparison.semantics}</p><div className="flex flex-wrap items-end gap-3"><label className="text-xs">Plane<select className={`${control} ml-2`} aria-label="Temporal plane" value={axis} onChange={(event) => { const next = event.target.value as Axis; setAxis(next); setIndex(Math.floor(comparison.reference_grid.dimensions_xyz[next === "axial" ? 2 : next === "coronal" ? 1 : 0]/2)); }}>{["axial", "coronal", "sagittal"].map((value) => <option key={value}>{value}</option>)}</select></label><label className="text-xs">Comparison view<select className={`${control} ml-2`} aria-label="Temporal comparison view" value={mode} onChange={(event) => setMode(event.target.value as Mode)}><option value="checkerboard">Checkerboard</option><option value="blend">Blend</option><option value="difference" disabled={!comparison.intensity.difference_allowed}>Signed raw-intensity difference</option></select></label><label className="text-xs">Window centre<input type="number" className={`${control} ml-1 w-24`} aria-label="Temporal window centre" value={center} onChange={(event) => setCenter(event.target.value)} placeholder="Pooled auto" /></label><label className="text-xs">Width<input type="number" min={.000001} className={`${control} ml-1 w-24`} aria-label="Temporal window width" value={width} onChange={(event) => setWidth(event.target.value)} placeholder="Pooled auto" /></label></div><label className="flex gap-2 text-xs">Slice {index+1}/{count}<input type="range" min={0} max={count-1} value={index} aria-label="Temporal slice" className="min-w-0 flex-1 accent-cyan-500" onChange={(event) => setIndex(Number(event.target.value))} /></label>{mode === "blend" && <label className="flex gap-2 text-xs">Current opacity<input type="range" min={0} max={1} step={.05} value={blend} aria-label="Temporal current opacity" onChange={(event) => setBlend(Number(event.target.value))} /></label>}<div className="grid gap-2 lg:grid-cols-3">{["previous", "current", mode].map((view) => <figure className="min-w-0 rounded border border-line" key={view}><figcaption className="px-2 py-1 text-xs capitalize">{view === "current" ? "Current mapped into previous source space" : view}</figcaption>{images[view] ? <img src={images[view]} alt={`Matched ${view} comparison plane`} className="h-64 w-full bg-[#080e1a] object-contain" /> : <p className="h-64 p-3 text-xs">Rendering bounded source plane…</p>}</figure>)}</div>{mode === "difference" && <p className="text-xs text-ink-3">Red: current intensity greater. Blue: lower. Black: zero difference. Hatched areas lack valid source overlap and are excluded. Units: {comparison.intensity.previous.unit}. These colours are not disease labels.</p>}{comparison.intensity.refusal && <p className="text-xs text-amber-700">{comparison.intensity.refusal.code}: {comparison.intensity.refusal.reason}</p>}{statistics && <p className="text-xs text-ink-3">Valid shared pixels: {statistics.valid_pixels}/{statistics.total_pixels} ({(statistics.valid_fraction*100).toFixed(1)}%). {statistics.mean_absolute_difference != null ? `Mean absolute raw intensity difference ${statistics.mean_absolute_difference.toPrecision(4)}.` : "No numeric change measured: intensity compatibility is unverified."}</p>}<details><summary className="cursor-pointer text-xs">Verified source identities</summary><pre tabIndex={0} aria-label="Verified temporal source identities" className="max-h-40 overflow-auto whitespace-pre-wrap break-all text-[10px]">{JSON.stringify(comparison.sources, null, 2)}</pre></details></div>}
  </details>;
}
