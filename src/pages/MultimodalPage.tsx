import { useState } from "react";
import { Combine } from "lucide-react";
import EcgResearchPanel from "../components/EcgResearchPanel";
import SignalRecordingPanel from "../components/SignalRecordingPanel";
import EvidenceSynthesisPanel from "../components/EvidenceSynthesisPanel";
import ExaminationEvidenceLinker from "../components/ExaminationEvidenceLinker";
import { Button, Card, ErrorBlock, KeyValue, Metric, PageHeader, StatusBadge, Table, Unavailable } from "../components/ui";
import { api } from "../services/api";
import { Link } from "../lib/router";
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
  const synthesis = useAsync(() => api.getEvidenceSynthesis(selected.id), [selected.id, evidenceVersion]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const exams = [...selected.examinations].sort((left, right) => left.exam_date.localeCompare(right.exam_date));
  const shown = fusion.loading ? null : fusion.data;

  async function run() {
    setBusy(true);
    setError(null);
    try {
      await api.runFusion(selected.id);
      fusion.reload();
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  const activeUploads = evidence.uploads.filter((upload) => upload.is_associated && !upload.withdrawn_at && !upload.superseded_by_file_id);
  const counts = Object.fromEntries(MODALITIES.map((modality) => [modality, activeUploads.filter((upload) => upload.modality === modality).length]));
  return (
    <>
      <PageHeader eyebrow="Multimodal Intelligence" title="Modality inventory, fusion and concordance" description="Source-linked report synthesis remains available when imaging models abstain. Learned prediction fusion requires validated paired data and compatible models." />
      {/* Sibling keys must differ; each panel still resets when the case changes. */}
      <EvidenceSynthesisPanel key={`synthesis-${selected.id}`} caseId={selected.id} />
      <div className="grid gap-3 sm:grid-cols-3">
        {MODALITIES.map((modality) => <Metric key={modality} label={`${humanize(modality)} evidence`} value={counts[modality]} note="Case-bound uploads" />)}
      </div>
      <div className="mt-4 grid gap-4 xl:grid-cols-[1.3fr_1fr]">
        <Card title="Pairing by examination" eyebrow="Same-date evidence matrix" padded={false}>
          <p className="px-4 pt-4 text-xs text-ink-2">Examination links record source association. They do not establish a validated training cohort or learned fusion model.</p>
          {exams.length === 0 ? <div className="p-4 text-sm text-ink-2"><p>The uploads are available, but no dated examination links have been recorded.</p><p className="mt-2">Review the source dates and patient identity using the examination linker below.</p></div> : (
            <Table headers={["Examination", ...MODALITIES.map(humanize), "Paired?"]} dense>
              {exams.map((exam) => {
                const present = MODALITIES.map((modality) => activeUploads.some((upload) => upload.examination_id === exam.id && upload.modality === modality));
                const count = present.filter(Boolean).length;
                return (
                  <tr key={exam.id}>
                    <td className="text-ink">{formatDate(exam.exam_date)}</td>
                    {present.map((has, index) => <td key={MODALITIES[index]}><StatusBadge status={has ? "AVAILABLE" : "NOT_AVAILABLE"} label={has ? "Present" : "None"} /></td>)}
                    <td><StatusBadge status={count >= 2 ? "AVAILABLE" : "NOT_AVAILABLE"} label={count >= 2 ? "Linked to same examination" : "Single modality"} /></td>
                  </tr>
                );
              })}
            </Table>
          )}
        </Card>
        <Card title="Learned prediction fusion" eyebrow="Separate from report synthesis" actions={<Button size="sm" icon={Combine} loading={busy} onClick={() => void run()}>Evaluate eligibility</Button>}>
          {error && <ErrorBlock message={error} />}
          {fusion.error && <ErrorBlock message={fusion.error} onRetry={fusion.reload} />}
          {synthesis.error && <ErrorBlock message={synthesis.error} onRetry={synthesis.reload} />}
          {synthesis.data && !synthesis.loading && <div className="mb-4 space-y-2 text-xs text-ink-2"><p><b>Uploaded evidence:</b> {Object.entries(synthesis.data.evidence_mask).map(([key, value]) => `${humanize(key)} ${value ? "present" : "absent"}`).join(" · ")}</p><p><b>Model output modalities:</b> {Object.entries(synthesis.data.model_output_mask).filter(([, value]) => value).map(([key]) => humanize(key)).join(", ") || "None"}</p><p>Report extraction is available for synthesis. A present upload does not imply a model prediction; separate model runs are not proof of statistically independent evidence.</p></div>}
          {shown ? (
            <div className="space-y-3">
              <KeyValue items={[
                { label: "Status", value: <StatusBadge status={shown.fused_status} /> },
                { label: "Modalities with processed findings (saved evaluation)", value: String(shown.active_modalities_count) },
                { label: "Paired data validated", value: <StatusBadge status={shown.paired_data_validated ? "VALIDATED" : "NOT_VALIDATED"} /> },
              ]} />
              <p className="text-xs text-ink-2">No learned fusion prediction or weights are available. Eligibility requires compatible model outputs, confirmed examination links and a validated fusion model.</p>
            </div>
          ) : fusion.loading ? <p className="text-sm text-ink-2">Loading…</p> : <Unavailable code="NOT_RUN" reason="The fusion gate has not been evaluated for this case." />}
          <p className="mt-3 text-[11px] leading-4 text-ink-3">
            Report synthesis above remains usable while prediction fusion is unavailable. The ECG + demographics model has a separate input contract and runs only when a compatible ECG record is supplied.
          </p>
        </Card>
      </div>
      <ExaminationEvidenceLinker key={`linker-${selected.id}`} />
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
      {counts.ECG > 0 ? <Card title="ECG research model" eyebrow="Research only · digital 12-lead records" className="mt-4">
        <EcgResearchPanel uploads={evidence.uploads} />
      </Card> : <p className="mt-4 text-xs text-ink-2">No ECG record supplied. <Link to="/upload" className="text-accent-text">Add ECG evidence</Link> to enable the ECG research workflow.</p>}
      {activeUploads.some((upload) => upload.modality === "SIGNAL") && <Card title="EEG and physiological recordings" eyebrow="EDF / EDF+ / BDF · read as recorded, no model" className="mt-4">
        <SignalRecordingPanel uploads={evidence.uploads} />
      </Card>}
    </>
  );
}
