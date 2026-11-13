import { useState } from "react";
import { universalJson } from "../services/universal";
import { useAsync } from "../lib/useAsync";
import { Card, EmptyState, ErrorBlock, LoadingBlock, SelectInput, StatusBadge, TextInput } from "./ui";
import { humanize } from "../lib/format";

type Group = { examination_id: number; exam_date: string | null; status: string; present_modalities: string[]; missing_modalities: string[]; source_ids: number[]; conflicts: unknown[]; fusion_reason: string };
type Pairing = { case_id: number; status: string; groups: Group[]; unlinked_source_ids: number[]; notice: string; never_writes: true };
type Backtest = { case_id: number; status: string; reason?: string | null; models: Record<string, Record<string, unknown>>; matched_comparison: { n: number; persistence_mae: number; linear_mae: number; linear_minus_persistence_mae: number; significance: string; selection: string } | null; notice: string };

export default function CompletionResearchPanel({ caseId, examId, biomarkers }: { caseId: number; examId: number | null; biomarkers: { name: string; unit: string }[] }) {
  const [confirmed, setConfirmed] = useState(false);
  const [metric, setMetric] = useState("");
  const [horizon, setHorizon] = useState(30);
  const selected = biomarkers.find((item) => `${item.name}|${item.unit}` === metric) ?? biomarkers[0];
  const pairs = useAsync(() => universalJson<Pairing>(`/cases/${caseId}/research/paired-evidence?confirmed_same_patient=${confirmed}${examId ? `&exam_id=${examId}` : ""}`), [caseId, examId, confirmed]);
  const backtest = useAsync(() => selected ? universalJson<Backtest>(`/cases/${caseId}/research/backtest?metric=${encodeURIComponent(selected.name)}&unit=${encodeURIComponent(selected.unit)}&horizon_days=${horizon}`) : null, [caseId, selected?.name, selected?.unit, horizon]);
  return <div className="grid gap-4 lg:grid-cols-2">
    <Card title="Matched source evidence" eyebrow="Identity, examination and missing modalities">
      <label className="flex items-start gap-2 text-xs text-ink-2"><input type="checkbox" className="mt-1" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />I have checked that the selected examination sources concern the same patient. This is an explicit attestation, not an automated identity inference.</label>
      {pairs.loading && <LoadingBlock label="Checking source groups" />}{pairs.error && <ErrorBlock message={pairs.error} />}
      {!pairs.loading && pairs.data?.case_id === caseId && <div className="mt-3 space-y-3">{pairs.data.groups.map((group) => <div key={group.examination_id} className="space-y-1 rounded-lg border border-line p-3 text-xs"><StatusBadge status={group.status} /><p>Examination #{group.examination_id} · {group.exam_date?.slice(0, 10) ?? "Date missing"}</p><p>Sources: {group.source_ids.join(", ") || "none"} · present: {group.present_modalities.join(", ") || "none"}</p><p>Missing: {group.missing_modalities.join(", ") || "none"} · {group.conflicts.length} conflicts requiring review</p><p className="text-ink-3">{group.fusion_reason}</p></div>)}{!pairs.data.groups.length && <EmptyState title="No dated source groups" detail="Associate sources with a dated examination before comparing modalities." />}<p className="text-xs text-ink-3">{pairs.data.notice} {pairs.data.unlinked_source_ids.length} sources have no examination link.</p></div>}
    </Card>
    <Card title="Chronological baseline backtest" eyebrow="Observed series · earlier observations only">
      {selected ? <><div className="grid gap-2 sm:grid-cols-[1fr_7rem]"><SelectInput aria-label="Backtest biomarker" value={`${selected.name}|${selected.unit}`} onChange={(e) => setMetric(e.target.value)}>{biomarkers.map((item) => <option key={`${item.name}|${item.unit}`} value={`${item.name}|${item.unit}`}>{humanize(item.name)} ({item.unit})</option>)}</SelectInput><label className="text-xs text-ink-2">Horizon, days<TextInput type="number" aria-label="Backtest horizon in days" min={1} max={3650} value={horizon} onChange={(e) => setHorizon(Math.max(1, Math.min(3650, Number(e.target.value) || 1)))} /></label></div>{backtest.loading && <LoadingBlock label="Evaluating historical folds" />}{backtest.error && <ErrorBlock message={backtest.error} />}{!backtest.loading && backtest.data?.case_id === caseId && <div className="mt-3 space-y-2 text-xs"><StatusBadge status={backtest.data.status} />{backtest.data.reason && <p>{humanize(backtest.data.reason)}</p>}{backtest.data.matched_comparison && <table className="w-full text-left"><caption className="mb-2 text-left">Same {backtest.data.matched_comparison.n} chronological targets</caption><tbody><tr><th className="py-1 font-normal">Persistence MAE</th><td>{backtest.data.matched_comparison.persistence_mae.toFixed(4)} {selected.unit}</td></tr><tr><th className="py-1 font-normal">Linear MAE</th><td>{backtest.data.matched_comparison.linear_mae.toFixed(4)} {selected.unit}</td></tr></tbody></table>}<p className="leading-5 text-ink-3">{backtest.data.notice}</p><details><summary className="cursor-pointer text-accent-text">Inspect eligibility and fold evidence</summary><pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-all text-[10px]">{JSON.stringify(backtest.data.models, null, 2)}</pre></details></div>}</> : <EmptyState title="No sourced numerical series" detail="Upload dated reports and complete the required independent review before eligible chronological evaluation." />}
    </Card>
  </div>;
}
