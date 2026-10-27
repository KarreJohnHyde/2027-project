import { useState } from "react";
import { Combine } from "lucide-react";
import EcgResearchPanel from "../components/EcgResearchPanel";
import { Button, Card, ErrorBlock, KeyValue, Metric, PageHeader, StatusBadge, Table, Unavailable } from "../components/ui";
import { api, type FusionRecord } from "../services/api";
import { errorMessage, formatDate, humanize } from "../lib/format";
import { useAsync } from "../lib/useAsync";
import { useSelectedCase, useWorkspace } from "../state/workspace";

const MODALITIES = ["REPORT", "IMAGE", "ECG"] as const;

export default function MultimodalPage() {
  const selected = useSelectedCase()!;
  const evidence = useWorkspace((state) => state.evidence);
  const evidenceVersion = useWorkspace((state) => state.evidenceVersion);
  const fusion = useAsync(() => api.getFusion(selected.id), [selected.id, evidenceVersion]);
  const concordance = useAsync(() => api.getConcordance(selected.id), [selected.id, evidenceVersion]);
  const [record, setRecord] = useState<FusionRecord | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const exams = [...selected.examinations].sort((left, right) => left.exam_date.localeCompare(right.exam_date));
  const shown = record ?? fusion.data;

  async function run() {
    setBusy(true);
    setError(null);
    try {
      setRecord(await api.runFusion(selected.id));
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  const counts = Object.fromEntries(MODALITIES.map((modality) => [modality, evidence.uploads.filter((upload) => upload.modality === modality && upload.is_associated).length]));
  return (
    <>
      <PageHeader eyebrow="Multimodal Intelligence" title="Modality inventory, fusion and concordance" description="Fusion combines modalities only when they are genuinely paired for the same patient and a validated fusion model exists. Otherwise the gate abstains and says why." />
      <div className="grid gap-3 sm:grid-cols-3">
        {MODALITIES.map((modality) => <Metric key={modality} label={`${humanize(modality)} evidence`} value={counts[modality]} note="Case-bound uploads" />)}
      </div>
      <div className="mt-4 grid gap-4 xl:grid-cols-[1.3fr_1fr]">
        <Card title="Pairing by examination" eyebrow="Same-date evidence matrix" padded={false}>
          {exams.length === 0 ? <p className="p-4 text-sm text-ink-2">No dated examinations; pairing cannot be assessed.</p> : (
            <Table headers={["Examination", ...MODALITIES.map(humanize), "Paired?"]} dense>
              {exams.map((exam) => {
                const present = MODALITIES.map((modality) => evidence.uploads.some((upload) => upload.examination_id === exam.id && upload.modality === modality && upload.is_associated));
                const count = present.filter(Boolean).length;
                return (
                  <tr key={exam.id}>
                    <td className="text-ink">{formatDate(exam.exam_date)}</td>
                    {present.map((has, index) => <td key={MODALITIES[index]}><StatusBadge status={has ? "AVAILABLE" : "NOT_AVAILABLE"} label={has ? "Present" : "None"} /></td>)}
                    <td><StatusBadge status={count >= 2 ? "PENDING_HUMAN_REVIEW" : "NOT_AVAILABLE"} label={count >= 2 ? "Same date; pairing unverified" : "Single modality"} /></td>
                  </tr>
                );
              })}
            </Table>
          )}
        </Card>
        <Card title="Gated fusion" eyebrow="Masked attention gate" actions={<Button size="sm" icon={Combine} loading={busy} onClick={() => void run()}>Evaluate gate</Button>}>
          {error && <ErrorBlock message={error} />}
          {shown ? (
            <div className="space-y-3">
              <KeyValue items={[
                { label: "Status", value: <StatusBadge status={shown.fused_status} /> },
                { label: "Active modalities", value: String(shown.active_modalities_count) },
                { label: "Modality mask", value: Object.entries(shown.modality_mask).map(([key, value]) => `${key}:${value}`).join(" · ") },
                { label: "Paired data validated", value: <StatusBadge status={shown.paired_data_validated ? "VALIDATED" : "NOT_VALIDATED"} /> },
              ]} />
              {shown.abstention_reason && <Unavailable compact code={shown.fused_status} reason={shown.abstention_reason} />}
              {!shown.fused_prediction && <p className="text-xs text-ink-3">No fused prediction exists; gate weights are not reported without a validated model.</p>}
            </div>
          ) : fusion.loading ? <p className="text-sm text-ink-2">Loading…</p> : <Unavailable code="NOT_RUN" reason="The fusion gate has not been evaluated for this case." />}
        </Card>
      </div>
      <Card title="Report–model concordance" eyebrow="Disagreement flags for review" className="mt-4" padded={false}>
        {concordance.data ? (
          concordance.data.items.length === 0 ? (
            <div className="p-4"><Unavailable code="UNCOMPARABLE" reason="Concordance needs a model finding to compare against report statements; no validated model has produced one." /></div>
          ) : (
            <Table headers={["Category", "Report entity", "Report status", "Model label", "Flag"]}>
              {concordance.data.items.map((item, index) => <tr key={index}><td>{item.finding_category}</td><td>{item.report_entity}</td><td><StatusBadge status={item.report_status} /></td><td>{item.model_label}</td><td><StatusBadge status={item.review_flag} /></td></tr>)}
            </Table>
          )
        ) : <p className="p-4 text-sm text-ink-2">{concordance.error ?? "Loading…"}</p>}
      </Card>
      <Card title="ECG research model" eyebrow="Research only · digital 12-lead records" className="mt-4">
        <EcgResearchPanel uploads={evidence.uploads} />
      </Card>
    </>
  );
}
