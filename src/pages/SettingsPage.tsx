import { Card, ErrorBlock, KeyValue, PageHeader, Segmented, StatusBadge, Table } from "../components/ui";
import { api } from "../services/api";
import { formatBytes, formatDate, humanize } from "../lib/format";
import { usePreferences } from "../lib/preferences";
import { useAsync } from "../lib/useAsync";
import { Link } from "../lib/router";
import { useWorkspace } from "../state/workspace";

export default function SettingsPage() {
  const preferences = usePreferences();
  const user = useWorkspace((state) => state.user);
  const health = useWorkspace((state) => state.health);
  const readiness = useAsync(() => api.getReadiness(), []);
  const gpu = useAsync(() => api.getGpuTelemetry(), []);

  return (
    <>
      <PageHeader eyebrow="Settings" title="Workspace settings" description="Preferences are stored only in this browser. Server configuration is read-only here." />
      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Appearance and 3D detail">
          <div className="space-y-5">
            <div>
              <p className="mb-1.5 text-xs font-medium text-ink-2">Theme</p>
              <Segmented label="Theme" value={preferences.theme} onChange={preferences.setTheme} options={[{ value: "system", label: "System" }, { value: "light", label: "Light" }, { value: "dark", label: "Dark" }]} />
            </div>
            <div>
              <p className="mb-1.5 text-xs font-medium text-ink-2">Anatomy detail</p>
              <Segmented label="Anatomy detail" value={preferences.detail} onChange={preferences.setDetail} options={[{ value: "adaptive", label: "Adaptive" }, { value: "standard", label: "Always standard" }, { value: "preview", label: "Prefer preview" }]} />
              <p className="mt-1.5 text-xs leading-5 text-ink-3">Adaptive loads the reduced-detail preview only for assets over 40 MB that have one. Standard tiers keep every source triangle; previews are labelled with their simplification.</p>
            </div>
            <label className="flex items-center gap-2 text-sm text-ink">
              <input type="checkbox" checked={preferences.showPerformance} onChange={(event) => preferences.setShowPerformance(event.target.checked)} className="accent-[var(--mt-accent)]" />
              Show the 3D performance monitor by default
            </label>
          </div>
        </Card>
        <Card title="Privacy and data handling">
          <ul className="space-y-2 text-sm leading-6 text-ink-2">
            <li>Uploads require an explicit de-identification attestation and are stored by SHA-256 on this server.</li>
            <li>No external AI service is called by MedTwin; case evidence never leaves this deployment.</li>
            <li>Report text is de-identified (identifiers, dates of birth, contact details) before extraction; ages over 89 are aggregated.</li>
            <li>DICOM uploads with non-empty identifying elements are flagged in the imaging viewer.</li>
            <li>No regulatory compliance (HIPAA, GDPR or other) is claimed; that requires an independent assessment.</li>
            <li>Original dataset and anatomy-model sources, creators and licence terms are credited on <Link to="/attribution" className="text-accent-text hover:underline">Data sources and licences</Link>.</li>
          </ul>
        </Card>
        <Card title="Session">
          <KeyValue items={[
            { label: "User", value: user?.full_name || user?.username },
            { label: "Role", value: user ? humanize(user.role) : "—" },
            { label: "Verification", value: user ? <StatusBadge status={user.verification_status} /> : "—" },
            { label: "API version", value: health?.version ?? "—" },
            { label: "Health scope", value: humanize(health?.health_scope) },
          ]} />
        </Card>
        <Card title="Compute">
          {gpu.data ? (
            <KeyValue items={[
              { label: "CUDA", value: <StatusBadge status={gpu.data.cuda_available ? "AVAILABLE" : "NOT_AVAILABLE"} /> },
              { label: "Device", value: gpu.data.device?.name ?? "—" },
              { label: "VRAM free / total", value: gpu.data.device ? `${formatBytes(gpu.data.device.memory_free_bytes)} / ${formatBytes(gpu.data.device.memory_total_bytes)}` : "—" },
              { label: "PyTorch", value: `${gpu.data.torch_version} (CUDA ${gpu.data.cuda_build ?? "none"})` },
              { label: "Host memory available", value: formatBytes(gpu.data.host_memory.available_bytes) },
              { label: "Resident models", value: gpu.data.loaded_models.length ? gpu.data.loaded_models.join(", ") : "None — models load on demand" },
            ]} />
          ) : <p className="text-sm text-ink-2">{gpu.error ?? "Loading…"}</p>}
        </Card>
        <Card title="Readiness checks" padded={false} className="xl:col-span-2">
          {readiness.data ? (
            <Table headers={["Check", "State", "Detail"]}>
              {Object.entries(readiness.data.checks).map(([name, check]) => (
                <tr key={name}>
                  <td className="font-medium text-ink">{humanize(name)}</td>
                  <td><StatusBadge status={check.ready ? "READY" : check.optional ? "NOT_AVAILABLE" : "NOT_READY"} /></td>
                  <td className="text-xs text-ink-2">{Object.entries(check).filter(([key]) => key !== "ready").map(([key, value]) => `${key}: ${typeof value === "object" ? JSON.stringify(value) : String(value)}`).join(" · ") || "—"}</td>
                </tr>
              ))}
            </Table>
          ) : <p className="p-4 text-sm text-ink-2">{readiness.error ?? "Loading…"}</p>}
        </Card>
        {user?.role === "admin" && <SystemAudit />}
      </div>
    </>
  );
}

/** Administrator-only, workspace-wide audit trail (metadata only; clinical text is never logged). */
function SystemAudit() {
  const audit = useAsync(() => api.getAuditLogs(200), []);
  return (
    <Card title="System audit log" eyebrow="All cases · administrators only" padded={false} className="xl:col-span-2">
      {audit.error && <div className="p-3"><ErrorBlock message={audit.error} onRetry={audit.reload} /></div>}
      {audit.data && audit.data.length === 0 && <p className="p-4 text-sm text-ink-2">No events recorded.</p>}
      {audit.data && audit.data.length > 0 && (
        <div className="max-h-[32rem] overflow-y-auto">
          <Table headers={["Event", "Resource", "User", "Time"]} dense>
            {audit.data.map((event) => (
              <tr key={event.id}>
                <td><span className="font-medium text-ink">{humanize(event.action)}</span>{event.details && <code className="mt-0.5 block max-w-lg truncate text-[11px] text-ink-3" title={JSON.stringify(event.details)}>{JSON.stringify(event.details)}</code>}</td>
                <td className="whitespace-nowrap text-xs text-ink-2">{event.resource_type} #{event.resource_id ?? "—"}</td>
                <td className="whitespace-nowrap text-xs text-ink-2">{event.user_id ?? "system"}</td>
                <td className="whitespace-nowrap text-xs text-ink-2">{formatDate(event.timestamp, true)}</td>
              </tr>
            ))}
          </Table>
        </div>
      )}
    </Card>
  );
}
