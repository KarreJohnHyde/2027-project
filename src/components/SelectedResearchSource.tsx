import { useEffect, useState } from "react";
import { api, type ResearchRun } from "../services/api";
import { useAsync } from "../lib/useAsync";
import { ErrorBlock, LoadingBlock, StatusBadge } from "./ui";
import { OverlayLayer } from "./ResearchModelPanel";

/** Historical research output on its own source, without starting another model. */
export default function SelectedResearchSource({ uploadId, findingId }: { uploadId: number; findingId: number | null }) {
  const stored = useAsync(() => api.listResearchRuns(uploadId), [uploadId]);
  const [image, setImage] = useState<string | null>(null);
  const [size, setSize] = useState<[number, number] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [visible, setVisible] = useState(true);
  const [opacity, setOpacity] = useState(.65);
  useEffect(() => {
    let live = true; let url: string | null = null;
    setImage(null); setError(null); setSize(null);
    void api.getUploadObjectUrl(uploadId).then((result) => { url = result; if (live) setImage(url); else URL.revokeObjectURL(url); }).catch((failure: unknown) => { if (live) setError(String(failure)); });
    return () => { live = false; if (url) URL.revokeObjectURL(url); };
  }, [uploadId]);
  const run: ResearchRun | undefined = stored.loading ? undefined : stored.data?.runs.find((item) => findingId != null && item.finding_id === findingId);
  const output = run?.research_output;
  const sourceSize = output && (output.type === "segmentation" || output.type === "detection") ? output.image_size : null;
  const aligned = size && sourceSize && size[0] === sourceSize[0] && size[1] === sourceSize[1];
  if (error) return <ErrorBlock message={error} />;
  if (!image) return <LoadingBlock label="Loading selected original image" />;
  return <div className="space-y-2">
    <div className="relative overflow-hidden rounded-lg bg-black">
      <img src={image} alt={`Original medical image upload ${uploadId}`} className="h-auto w-full object-contain" onLoad={(event) => setSize([event.currentTarget.naturalWidth, event.currentTarget.naturalHeight])} />
      {visible && aligned && output && <svg viewBox={`0 0 ${sourceSize[0]} ${sourceSize[1]}`} className="pointer-events-none absolute inset-0 h-full w-full" role="img" aria-label="Selected finding source-coordinate model overlay"><OverlayLayer output={output} showBelow={false} highlight={null} opacity={opacity} /></svg>}
    </div>
    {sourceSize && <div className="flex flex-wrap gap-3 text-xs"><label><input type="checkbox" checked={visible} onChange={(e) => setVisible(e.target.checked)} /> Show original model overlay</label><label className="flex items-center gap-2">Opacity<input type="range" aria-label="Selected finding overlay opacity" min={0} max={1} step={.05} value={opacity} onChange={(e) => setOpacity(Number(e.target.value))} /></label></div>}
    {sourceSize && size && !aligned && <p className="text-xs text-warning-text">SOURCE_GRID_MISMATCH: overlay withheld; original image and prediction dimensions differ.</p>}
    {stored.error && <ErrorBlock message={stored.error} />}
    {run ? <><StatusBadge status={run.status} /><p className="text-xs text-ink-2">Saved run #{run.id} · {run.model_name} · finding #{run.finding_id}. Historical research output; commercial and clinical eligibility remain separate.</p></> : <p className="text-xs text-ink-3">No model output pinned to this selected finding; the original image is shown without an invented overlay.</p>}
  </div>;
}
