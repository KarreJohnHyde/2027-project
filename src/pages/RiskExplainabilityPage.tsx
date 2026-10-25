import { Card, ErrorBlock, LoadingBlock, PageHeader, StatusBadge, Table } from "../components/ui";
import { api } from "../services/api";
import { humanize } from "../lib/format";
import { useAsync } from "../lib/useAsync";
import { useWorkspace } from "../state/workspace";

export default function RiskExplainabilityPage() {
  const registry = useAsync(() => api.getRiskRegistry(), []);
  const findings = useWorkspace((state) => state.evidence.findings);
  if (registry.error) return <ErrorBlock message={registry.error} onRetry={registry.reload} />;
  if (!registry.data) return <LoadingBlock />;
  return (
    <>
      <PageHeader eyebrow="Risk & Explainability" title="Risk instruments and explanation methods" description={registry.data.notice} />
      <div className="grid gap-3 md:grid-cols-3">
        {registry.data.distinctions.map((item) => (
          <div key={item.term} className="rounded-xl border border-line bg-surface p-4 shadow-card">
            <p className="text-sm font-semibold text-ink">{item.term}</p>
            <p className="mt-1 text-xs leading-5 text-ink-2">{item.meaning}</p>
          </div>
        ))}
      </div>
      <Card title="Organ-specific risk instruments" eyebrow="Candidates and blockers" className="mt-4" padded={false}>
        <Table headers={["System", "Instrument", "Target and horizon", "Required inputs", "Population", "Calibration", "Status", "Blockers"]} dense>
          {registry.data.models.map((model) => (
            <tr key={model.instrument}>
              <td className="text-ink">{humanize(model.organ_system)}</td>
              <td className="font-medium text-ink">{model.instrument}</td>
              <td className="max-w-[12rem] text-xs text-ink-2">{model.risk_target}{model.risk_horizon ? ` · ${model.risk_horizon}` : ""}</td>
              <td className="max-w-[14rem] text-xs text-ink-2">{model.required_inputs.join(", ")}</td>
              <td className="max-w-[12rem] text-xs text-ink-2">{model.derivation_population}</td>
              <td><StatusBadge status={model.calibration_status} /></td>
              <td><StatusBadge status={model.status} /></td>
              <td className="max-w-[14rem]"><div className="flex flex-wrap gap-1">{model.blockers.map((blocker) => <StatusBadge key={blocker} status={blocker} />)}</div></td>
            </tr>
          ))}
        </Table>
      </Card>
      <div className="mt-4 grid grid-cols-[minmax(0,1fr)] gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <Card title="Explainability methods" padded={false} className="min-w-0">
          <Table headers={["Method", "Applies to", "Status", "Interpretation limits"]} dense>
            {registry.data.explainability_methods.map((method) => (
              <tr key={method.method}><td className="font-medium text-ink">{method.method}</td><td className="text-xs text-ink-2">{method.applies_to}</td><td><StatusBadge status={method.status} /></td><td className="max-w-sm text-xs text-ink-2">{method.limits}</td></tr>
            ))}
          </Table>
        </Card>
        <div className="min-w-0 space-y-4">
          <Card title="Explanation provenance" eyebrow="Recorded with every explanation">
            <ul className="flex flex-wrap gap-1.5">{registry.data.explanation_provenance_fields.map((field) => <li key={field}><code className="rounded bg-surface-2 px-1.5 py-0.5 text-[11px] text-ink-2">{field}</code></li>)}</ul>
            <p className="mt-3 text-xs leading-5 text-ink-3">Explanation maps are never presented as proof of causation or exact lesion location.</p>
          </Card>
          <Card title="Case findings" eyebrow="Confidence and calibration">
            {findings.length === 0 ? <p className="text-sm text-ink-2">No findings in this case.</p> : (
              <ul className="space-y-2">
                {findings.map((finding) => (
                  <li key={finding.id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
                    <span className="min-w-0 truncate text-ink">{finding.label}</span>
                    <span className="flex min-w-0 max-w-full flex-wrap gap-1 sm:justify-end"><StatusBadge status={finding.calibration_status} /><StatusBadge status={finding.explanation_type ? "AVAILABLE" : "NOT_AVAILABLE"} label={finding.explanation_type ? "Explanation" : "No explanation"} /></span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
