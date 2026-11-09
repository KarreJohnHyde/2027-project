import { useState } from "react";
import { Combine, Download } from "lucide-react";
import { api, type EvidenceSynthesis } from "../services/api";
import { useAsync } from "../lib/useAsync";
import { errorMessage, humanize } from "../lib/format";
import { Link } from "../lib/router";
import { useWorkspace } from "../state/workspace";
import { Button, Card, ErrorBlock, LoadingBlock, StatusBadge, Table } from "./ui";

export default function EvidenceSynthesisPanel({ caseId }: { caseId: number }) {
  const version = useWorkspace((state) => state.evidenceVersion);
  const preview = useAsync(() => api.getEvidenceSynthesis(caseId), [caseId, version]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<{ caseId: number; id: number } | null>(null);
  const data: EvidenceSynthesis | null = preview.loading ? null : preview.data;
  async function save() {
    setBusy(true); setError(null);
    try {
      const result = await api.runFusion(caseId);
      setSaved({ caseId, id: result.id! });
      preview.reload();
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }
  function download() {
    const url = URL.createObjectURL(new Blob([JSON.stringify({ case_id: caseId, generated_at: new Date().toISOString(), ...data }, null, 2)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = `medtwin-case-${caseId}-evidence.json`; link.click(); URL.revokeObjectURL(url);
  }
  return <Card title="Source-linked evidence synthesis" eyebrow="Rule-based concordance · research only" className="mt-4"
    actions={<><Button size="sm" icon={Download} disabled={!data} onClick={download}>Export</Button><Button size="sm" icon={Combine} loading={busy} onClick={() => void save()}>Save synthesis</Button></>}>
    {error && <ErrorBlock message={error} />}
    {preview.error && <ErrorBlock message={preview.error} onRetry={preview.reload} />}
    {preview.loading ? <LoadingBlock /> : data && <div className="space-y-4">
      <p className="text-sm text-ink">{data.summary}</p>
      <div className="flex flex-wrap gap-3 text-xs text-ink-2"><span>{data.report_findings.length} distinct report findings</span><span>{data.model_findings.length} model outputs</span><span>{data.abstentions.length} model outcomes without predictions</span>{(data.secondary_model_mentions?.length ?? 0) > 0 && <span>{data.secondary_model_mentions?.length} secondary NLP reading(s) of the same text, not counted as findings</span>}{(data.superseded_report_run_ids?.length ?? 0) > 0 && <span>{data.superseded_report_run_ids?.length} earlier report analysis(es) superseded by re-analysis, kept as history</span>}</div>
      <p className="text-xs text-ink-2">Concordance: {humanize(data.concordance)}. Patient-specific lesion location unavailable. No overall disease probability is assigned.</p>
      {saved?.caseId === caseId && <p className="text-xs text-accent-text">Synthesis run #{saved.id} saved with source and review references.</p>}
      <Table headers={["Reported finding", "Assertion / review", "Source evidence"]} dense>
        {data.report_findings.map((item, index) => <tr key={index}>
          <td><b className="font-medium text-ink">{item.entity}</b><p className="text-xs text-ink-2">{item.anatomical_site ?? item.laterality ?? "Site not specified"}</p><p className="mt-1 text-[11px] text-ink-3">{item.anatomical_association}</p>{item.assertion === "AFFIRMED" && item.atlas_structure_id?.startsWith("nervous.") && <Link to={`/anatomy-studio?system=brain&structure=${encodeURIComponent(item.atlas_structure_id)}`} className="mt-1 block text-xs text-accent-text">View reported brain region</Link>}</td>
          <td><StatusBadge status={item.assertion} /><div className="mt-1"><StatusBadge status={item.review_status} /></div><Link to="/documents" className="mt-1 block text-xs text-accent-text">Review sources</Link>{!item.examination_id && <Link to="/cases" className="mt-1 block text-xs text-warning-text">Link examination</Link>}</td>
          <td className="max-w-md"><p className="text-xs text-ink-2">“{item.sources[0]?.normalized_span}”</p><details className="mt-2 text-xs text-ink-3"><summary>{item.sources.length} source statement{item.sources.length === 1 ? "" : "s"} · pages {[...new Set(item.sources.map((source) => source.page ?? "unrecorded"))].join(", ")}</summary>{item.sources.map((source) => <div key={source.statement_id} className="my-2 text-xs">
            <p className="text-ink-3">Upload #{source.upload_id}{source.page ? ` · page ${source.page}` : " · page not recorded"} · statement #{source.statement_id}</p>
            <p className="mt-1 text-ink-2">“{source.normalized_span}”</p>
            {source.normalized_span !== source.source_span && <details className="mt-1 text-ink-3"><summary>Raw OCR</summary>{source.source_span}</details>}
          </div>)}</details></td>
        </tr>)}
      </Table>
      {data.report_findings.length === 0 && <p className="text-sm text-ink-2">No eligible report statements. Run Document Intelligence on an active case upload.</p>}
      {data.abstentions.map((item, index) => <div key={index} className="rounded-md border border-line p-3 text-xs text-ink-2"><StatusBadge status={item.status} label="No model prediction" /> Upload #{item.upload_id} · {item.model_id}<p className="mt-2">{item.reason.startsWith("MODEL_INPUT_PHOTOGRAPHED_FILM") ? "The image is a suspected photographed film or montage. Report synthesis and source panel previews remain available; a compatible native image is needed for this model." : item.reason}</p><details className="mt-2 text-ink-3"><summary>{item.attempt_count} recorded attempt{item.attempt_count === 1 ? "" : "s"} · technical provenance</summary><p className="mt-1">Runs: {item.run_ids.join(", ") || "none"}{item.job_ids.length ? ` · jobs: ${item.job_ids.join(", ")}` : ""}</p><p>{item.reason}</p></details></div>)}
      {data.model_findings.map((item) => <div key={item.run_id} className="space-y-2 rounded-md border border-line p-3 text-xs text-ink-2"><p>Model run #{item.run_id}: {item.label} · {humanize(item.validation_status)}</p><StatusBadge status={item.review_status} /><p>{item.model_id} · version {item.model_version} · source upload #{item.upload_id}</p><Link to={item.modality === "IMAGE" ? `/imaging?upload=${item.upload_id}` : "/multimodal"} className="block text-accent-text">Open stored model output</Link>{item.run_ids.length > 1 && <details className="text-ink-3"><summary>{item.run_ids.length} stored runs on the same source and model version</summary><p>Latest output shown. Runs {item.run_ids.join(", ")} are retained; they are not independent source confirmation and their probabilities are not averaged.</p></details>}</div>)}
      {data.contradictions.map((item, index) => <p key={index} role="alert" className="text-sm text-warning-text">{humanize(item.type)}: {humanize(item.resolution)}</p>)}
      <p className="text-[11px] text-ink-3">{data.limitations.join(" ")}</p>
      <div className="flex gap-4 text-xs text-accent-text"><Link to="/documents">Review report statements</Link><Link to={data.report_findings.some((item) => item.atlas_structure_id?.startsWith("nervous.")) ? "/anatomy-studio?system=brain" : "/anatomy-studio"}>Open anatomy</Link><Link to="/cases">Link examinations</Link></div>
    </div>}
  </Card>;
}
