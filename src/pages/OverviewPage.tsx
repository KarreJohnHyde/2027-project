import { ArrowRight, Fingerprint, History } from "lucide-react";
import { Card, Metric, PageHeader, StatusBadge, Table } from "../components/ui";
import { loadManifest } from "../anatomy/data";
import { api } from "../services/api";
import { formatBytes, formatCount, formatDate, humanize } from "../lib/format";
import { Link } from "../lib/router";
import { useAsync } from "../lib/useAsync";
import { NAV_ITEMS } from "../navigation";
import { useSelectedCase, useWorkspace } from "../state/workspace";

export default function OverviewPage() {
  const selected = useSelectedCase();
  const evidence = useWorkspace((state) => state.evidence);
  const capabilities = useWorkspace((state) => state.capabilities);
  const models = useWorkspace((state) => state.models);
  const datasets = useWorkspace((state) => state.datasets);
  const health = useWorkspace((state) => state.health);
  const manifest = useAsync(() => loadManifest(), []);
  const readiness = useAsync(() => api.getReadiness(), []);
  const gpu = useAsync(() => api.getGpuTelemetry(), []);
  const activatable = models.filter((model) => model.activation.eligible).length;
  const eligibleDatasets = datasets?.datasets.filter((item) => item.training_eligible || item.validation_eligible).length ?? 0;

  return (
    <>
      <PageHeader
        eyebrow="Overview Dashboard"
        title={selected ? selected.pseudonymous_id : "MedTwin 2.0"}
        description={selected?.description || "Unified patient-case workspace with evidence provenance. Results that do not exist are shown as unavailable, never estimated."}
      >
        {selected && <p className="mt-2 inline-flex items-center gap-1.5 text-xs text-ink-3"><Fingerprint aria-hidden size={13} /> Case #{selected.id} · created {formatDate(selected.created_at)} · {selected.examinations.length} examination(s)</p>}
      </PageHeader>

      {selected && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <Metric label="Uploads" value={formatCount(evidence.uploads.length)} note="Content-addressed, SHA-256" />
          <Metric label="Analysis jobs" value={formatCount(evidence.jobs.length)} note={evidence.jobs[0] ? `Latest ${humanize(evidence.jobs[0].status)}` : "None recorded"} />
          <Metric label="Source-linked statements" value={formatCount(evidence.statements.length)} note={`${evidence.statements.filter((item) => item.certainty !== "CERTAIN").length} qualified by context`} />
          <Metric label="Measurements" value={formatCount(evidence.measurements.length)} note={`${evidence.measurements.filter((item) => item.reference_source).length} with documented interval`} />
          <Metric label="Audit events" value={formatCount(evidence.provenance.length)} note="Metadata-only history" />
        </div>
      )}

      <div className="mt-4 grid gap-4 xl:grid-cols-[1.4fr_1fr]">
        <Card title="Capability truth" eyebrow="What runs today" padded={false}>
          <Table headers={["Capability", "Runtime", "Verification", "Boundary"]}>
            {capabilities.map((capability) => (
              <tr key={capability.capability_id}>
                <td className="font-medium text-ink">{capability.label}</td>
                <td><StatusBadge status={capability.operational ? "OPERATIONAL" : "NOT_AVAILABLE"} /></td>
                <td><StatusBadge status={capability.verification_status} /></td>
                <td className="max-w-sm text-xs text-ink-2">{capability.limitations[0] ?? "—"}</td>
              </tr>
            ))}
          </Table>
        </Card>
        <div className="space-y-4">
          <Card title="Registries" eyebrow="Activation gates">
            <ul className="space-y-2.5 text-sm">
              <li className="flex items-center justify-between gap-2"><Link to="/models" className="text-ink hover:underline">Models activation-eligible</Link><span className="tabular text-ink-2">{activatable} of {models.length}</span></li>
              <li className="flex items-center justify-between gap-2"><Link to="/datasets" className="text-ink hover:underline">Datasets eligible for training/validation</Link><span className="tabular text-ink-2">{eligibleDatasets} of {datasets?.datasets.length ?? "—"}</span></li>
              <li className="flex items-center justify-between gap-2"><Link to="/anatomy-studio" className="text-ink hover:underline">Anatomy systems / variants</Link><span className="tabular text-ink-2">{manifest.data ? `${manifest.data.totals.systems} / ${manifest.data.totals.available_variants}` : "—"}</span></li>
              <li className="flex items-center justify-between gap-2"><span>Named atlas structures</span><span className="tabular text-ink-2">{manifest.data ? formatCount(manifest.data.totals.atlas_structures) : "—"}</span></li>
            </ul>
          </Card>
          <Card title="System" eyebrow="Live status">
            <ul className="space-y-2 text-sm">
              <li className="flex items-center justify-between gap-2"><span>API</span><StatusBadge status={health?.status ?? "NOT_AVAILABLE"} /></li>
              <li className="flex items-center justify-between gap-2"><span>Readiness</span><StatusBadge status={readiness.data ? (readiness.data.ready ? "READY" : "NOT_READY") : readiness.error ? "ERROR" : "PENDING"} /></li>
              <li className="flex items-center justify-between gap-2"><span>Database</span><StatusBadge status={health?.database_status ?? "PENDING"} /></li>
              <li className="flex items-center justify-between gap-2"><span>GPU</span><span className="text-right text-xs text-ink-2">{gpu.data?.device ? `${gpu.data.device.name} · ${formatBytes(gpu.data.device.memory_free_bytes)} free` : gpu.data ? "CUDA not available" : "—"}</span></li>
              <li className="flex items-center justify-between gap-2"><span>Resident models</span><span className="text-xs text-ink-2">{gpu.data ? (gpu.data.loaded_models.length ? gpu.data.loaded_models.join(", ") : "None (on-demand only)") : "—"}</span></li>
            </ul>
          </Card>
        </div>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[1.4fr_1fr]">
        <Card title="Workspaces" eyebrow="Navigate">
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {NAV_ITEMS.filter((item) => item.path !== "/").map((item) => {
              const Icon = item.icon;
              return (
                <Link key={item.path} to={item.path} className="group rounded-lg border border-line p-3 transition hover:bg-surface-2">
                  <div className="flex items-center justify-between"><Icon aria-hidden size={16} className="text-accent-text" /><ArrowRight aria-hidden size={14} className="text-ink-3 opacity-0 transition group-hover:opacity-100" /></div>
                  <p className="mt-2 text-sm font-medium text-ink">{item.label}</p>
                  <p className="mt-0.5 text-xs leading-5 text-ink-2">{item.summary}</p>
                </Link>
              );
            })}
          </div>
        </Card>
        <Card title="Recent activity" eyebrow="Case audit trail">
          {evidence.provenance.length === 0 ? <p className="text-sm text-ink-2">No events for this case yet.</p> : (
            <ol className="space-y-2.5">
              {evidence.provenance.slice(0, 8).map((event) => (
                <li key={event.id} className="flex items-start gap-2.5 text-sm">
                  <History aria-hidden size={14} className="mt-0.5 shrink-0 text-ink-3" />
                  <span className="min-w-0 flex-1"><span className="font-medium text-ink">{humanize(event.action)}</span><span className="block text-xs text-ink-3">{event.resource_type} #{event.resource_id ?? "—"} · {formatDate(event.timestamp, true)}</span></span>
                </li>
              ))}
            </ol>
          )}
        </Card>
      </div>
    </>
  );
}
