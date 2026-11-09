import { useEffect, useState } from "react";
import { api, type FilmAssessment } from "../services/api";
import { humanize } from "../lib/format";
import { Button, ErrorBlock, LoadingBlock, StatusBadge } from "./ui";

export default function FilmPanelPreview({ uploadId, assessment, pdfPage }: { uploadId: number; assessment: FilmAssessment; pdfPage?: number }) {
  const [panel, setPanel] = useState<number | null>(assessment.panels[0]?.panel_id ?? null);
  const [loaded, setLoaded] = useState<{ panel: number; url: string } | null>(null);
  const [failure, setFailure] = useState<{ panel: number; message: string } | null>(null);
  const preview = loaded?.panel === panel ? loaded.url : null;
  const error = failure?.panel === panel ? failure.message : null;
  useEffect(() => {
    if (panel === null) return;
    let cancelled = false;
    let url: string | null = null;
    const endpoint = pdfPage ? `/uploads/${uploadId}/pages/${pdfPage}/film-panels/${panel}` as const : `/uploads/${uploadId}/imaging/film-panels/${panel}` as const;
    void api.requestBlob(endpoint).then(({ blob }) => {
      url = URL.createObjectURL(blob);
      if (cancelled) URL.revokeObjectURL(url); else setLoaded({ panel, url });
    }, (err: unknown) => { if (!cancelled) setFailure({ panel, message: err instanceof Error ? err.message : String(err) }); });
    return () => { cancelled = true; if (url) URL.revokeObjectURL(url); };
  }, [uploadId, panel, pdfPage]);
  return <div className="mt-3 space-y-3 rounded-lg border border-line bg-surface-2 p-3">
    <div className="flex flex-wrap items-center gap-2"><StatusBadge status={assessment.inference_eligibility === "ABSTAIN_FILM_INPUT" ? "ABSTAIN" : "PENDING_HUMAN_REVIEW"} label={assessment.inference_eligibility === "ABSTAIN_FILM_INPUT" ? "Viewing only" : "Input review required"} /><span className="text-xs text-ink">{humanize(assessment.source_type)}</span></div>
    <p className="text-xs text-ink-2">{assessment.model_compatibility}. Source assessment requires review.</p>
    {assessment.source_annotations.coloured_marks_suspected && <p className="text-xs text-warning-text">Coloured marks are present in the source; they are not AI lesion masks.</p>}
    {assessment.panels.length > 0 && <><p className="text-xs text-ink-2">{assessment.panels.length} candidate panels · visual row order only · original preserved</p>
      <div className="flex flex-wrap gap-1">{assessment.panels.map((item) => <Button key={item.panel_id} size="sm" variant={panel === item.panel_id ? "primary" : "secondary"} onClick={() => { if (panel !== item.panel_id) { setLoaded(null); setFailure(null); setPanel(item.panel_id); } }}>Panel {item.panel_id + 1}</Button>)}</div>
      {panel !== null && !preview && !error && <LoadingBlock label="Loading source panel" />}
      {preview && <figure><img src={preview} alt={`Source film panel ${(panel ?? 0) + 1}, viewing preview only`} className="h-80 w-full rounded bg-black object-contain" /><figcaption className="mt-1 text-xs text-ink-2">Panel {(panel ?? 0) + 1} · upload #{uploadId} · upright source rectangle {assessment.panels.find((item) => item.panel_id === panel)?.bbox_xyxy.join(", ")}. No spatial calibration.</figcaption></figure>}
    </>}
    {error && <ErrorBlock message={error} />}
    <details className="text-[11px] text-ink-3"><summary>Applicability limitations</summary><p className="mt-1">{assessment.limitations.join(" ")}</p></details>
  </div>;
}
