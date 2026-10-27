import { useState } from "react";
import {
  Card,
  EmptyState,
  KeyValue,
  Metric,
  PageHeader,
  Segmented,
  StatusBadge,
  Table,
  TextInput,
} from "../components/ui";
import type {
  DatasetRegistryRecord,
  DatasetRegistryResponse,
  DatasetTaskAuditDataset,
  DatasetTaskAuditResponse,
  DatasetTaskAuditTask,
} from "../services/api";
import { datasetName, licenceLabel, licenceStatusLabel, publicText, taskName } from "../lib/displayNames";
import { formatBytes, formatCount, humanize } from "../lib/format";
import { useWorkspace } from "../state/workspace";
import { DATASET_CANDIDATES, LABEL_BOUNDARIES, SYSTEM_COVERAGE, type RoadmapPriority } from "../data/expansionRoadmap";

type AuditedRecord = DatasetRegistryRecord & {
  file_inventory?: { extension_counts?: Record<string, number>; total_bytes?: number; scan_truncated?: boolean };
  annotation_evidence?: {
    image_mask_pairing?: { image_files?: number; mask_files?: number; matching_stems?: number } | null;
    coco?: unknown[];
    yolo?: unknown;
  };
  observed_top_level_directories?: string[];
  bounded_readability_probes?: { images?: { readable: number; checked: number } };
};

type RegistryView = "discovery" | "task-audit" | "roadmap";
type TaskRow = { key: string; dataset: DatasetTaskAuditDataset; task: DatasetTaskAuditTask | null };

function DiscoveryDetail({ dataset }: { dataset: AuditedRecord }) {
  const inventory = dataset.file_inventory ?? {};
  const pairing = dataset.annotation_evidence?.image_mask_pairing;
  const probe = dataset.bounded_readability_probes?.images;
  return (
    <Card title={datasetName(dataset.dataset_id)} eyebrow={`Local data folder · ${humanize(dataset.registry_kind)}`} actions={<StatusBadge status={dataset.integration_status} />}>
      <KeyValue
        columns={3}
        items={[
          { label: "Kind", value: humanize(dataset.registry_kind) },
          { label: "Domain / modality", value: `${humanize(dataset.medical_domain)} / ${humanize(dataset.modality)}` },
          { label: "Task", value: humanize(dataset.task) },
          { label: "Media files", value: `${formatCount(dataset.sample_count)} (${dataset.sample_count_semantics})` },
          { label: "Size on disk", value: formatBytes(inventory.total_bytes) },
          {
            label: "Formats",
            value:
              Object.entries(inventory.extension_counts ?? {})
                .map(([extension, count]) => `${extension} ${formatCount(count)}`)
                .join(", ") || "Not available",
          },
          { label: "Annotation format", value: humanize(dataset.annotation_format) },
          {
            label: "Image/mask pairing",
            value: pairing
              ? `${formatCount(pairing.matching_stems)} matched stems of ${formatCount(pairing.image_files)} images / ${formatCount(pairing.mask_files)} masks`
              : "No pairing evidence",
          },
          { label: "Readability probe", value: probe ? `${probe.readable}/${probe.checked} readable` : "Not probed" },
          { label: "Split status", value: <StatusBadge status={dataset.split_status.toUpperCase()} /> },
          { label: "Licence", value: <StatusBadge status={dataset.license_status.toUpperCase()} label={licenceStatusLabel(dataset.license_status)} /> },
          {
            label: "Training / validation",
            value: (
              <StatusBadge
                status={dataset.training_eligible ? "ELIGIBLE" : "NOT_ELIGIBLE"}
                label={`${dataset.training_eligible ? "Train" : "No train"} / ${dataset.validation_eligible ? "Validate" : "No validate"}`}
              />
            ),
          },
        ]}
      />
      {(dataset.observed_top_level_directories ?? []).length > 0 && (
        <p className="mt-3 text-xs text-ink-2">
          Top-level folders: {formatCount(dataset.observed_top_level_directories!.length)} (folder names are not treated as labels)
        </p>
      )}
      <ul className="mt-3 list-disc space-y-0.5 pl-4 text-xs leading-5 text-ink-2">
        {(Array.isArray(dataset.limitations) ? dataset.limitations : [String(dataset.limitations)]).map((limitation) => (
          <li key={limitation}>{publicText(limitation)}</li>
        ))}
      </ul>
    </Card>
  );
}

function DiscoveryRegistry({ registry }: { registry: DatasetRegistryResponse | null }) {
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  if (!registry) {
    return <EmptyState title="Discovery registry unavailable" detail="The generated path-level evidence registry could not be loaded." />;
  }
  const datasets = registry.datasets as AuditedRecord[];
  const needle = query.trim().toLowerCase();
  const shown = datasets.filter((dataset) => datasetName(dataset.dataset_id).toLowerCase().includes(needle));
  const selected = datasets.find((dataset) => dataset.dataset_id === selectedId) ?? null;
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-4">
        <Metric label="Catalogued paths" value={datasets.length} />
        <Metric
          label="Media files observed"
          value={formatCount(datasets.reduce((sum, dataset) => sum + dataset.sample_count, 0))}
          note="Overlapping roots are not deduplicated"
        />
        <Metric
          label="Training eligible"
          value={datasets.filter((dataset) => dataset.training_eligible).length}
          note="Path-level discovery only; task readiness is audited separately"
        />
        <Metric label="Global readiness" value={<StatusBadge status={registry.global_readiness} />} note={registry.global_blockers[0]} />
      </div>
      <div className="mt-4 grid gap-4 xl:grid-cols-[1.1fr_1fr]">
        <Card
          title="Discovered paths"
          eyebrow="Path-level discovery registry"
          padded={false}
          actions={
            <TextInput
              aria-label="Filter discovered datasets"
              placeholder="Filter"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="h-8 w-48 text-xs"
            />
          }
        >
          <Table headers={["Dataset", "Files", "Annotation", "Licence", "Status"]} dense>
            {shown.map((dataset) => (
              <tr
                key={dataset.dataset_id}
                data-testid="dataset-registry-record"
                onClick={() => setSelectedId(dataset.dataset_id)}
                className={`cursor-pointer ${selectedId === dataset.dataset_id ? "bg-accent-soft" : "hover:bg-surface-2"}`}
              >
                <td className="font-medium text-ink">{datasetName(dataset.dataset_id)}</td>
                <td className="tabular text-ink-2">{formatCount(dataset.sample_count)}</td>
                <td className="text-xs text-ink-2">{humanize(dataset.annotation_format)}</td>
                <td><StatusBadge status={dataset.license_status.toUpperCase()} label={licenceStatusLabel(dataset.license_status)} /></td>
                <td><StatusBadge status={dataset.integration_status} /></td>
              </tr>
            ))}
          </Table>
        </Card>
        <div>
          {selected ? (
            <DiscoveryDetail dataset={selected} />
          ) : (
            <EmptyState title="Select a discovered path" detail="Integrity, annotation, and conservative readiness evidence appears here." />
          )}
        </div>
      </div>
    </>
  );
}

function splitCounts(task: DatasetTaskAuditTask | null): string {
  const splits = task?.preparation?.per_split;
  if (!splits) return "Not generated";
  const preferred = ["train", "val", "test"];
  const names = [...preferred.filter((name) => name in splits), ...Object.keys(splits).filter((name) => !preferred.includes(name))];
  return names.map((name) => `${name} ${formatCount(splits[name])}`).join(" / ");
}

function taskLabels(dataset: DatasetTaskAuditDataset, task: DatasetTaskAuditTask | null): string {
  const labels = task?.preparation?.labels ?? [];
  if (labels.length === 0) return humanize(dataset.labels);
  const preview = labels.slice(0, 3).join(", ");
  return labels.length > 3 ? `${preview} +${labels.length - 3}` : preview;
}

function TaskAuditDetail({ row }: { row: TaskRow }) {
  const { dataset, task } = row;
  const flags = task?.flags ?? ["NO_TASK_DEFINED"];
  return (
    <Card
      title={task ? taskName(task.task_id, task.target) : datasetName(dataset.id)}
      eyebrow={datasetName(dataset.id)}
      actions={<StatusBadge status={task?.readiness ?? "NO_TASK_DEFINED"} />}
    >
      <KeyValue
        columns={3}
        items={[
          { label: "Dataset", value: datasetName(dataset.id) },
          { label: "Task type", value: task ? humanize(task.type) : "No task unit" },
          { label: "Target", value: task?.target ?? "No task target was defined" },
          { label: "Labels", value: taskLabels(dataset, task) },
          { label: "Label source", value: humanize(dataset.labels) },
          { label: "Split counts", value: splitCounts(task) },
          { label: "Training eligible", value: <StatusBadge status={task?.training_eligible ? "ELIGIBLE" : "NOT_ELIGIBLE"} /> },
          { label: "Licence", value: <StatusBadge status={dataset.license?.status ?? "UNKNOWN"} label={licenceLabel(dataset.license)} /> },
          { label: "Privacy", value: <StatusBadge status={dataset.privacy} /> },
          { label: "Patient IDs", value: humanize(dataset.patient_ids) },
          { label: "Official splits", value: dataset.official_splits ? "Yes" : "No" },
          { label: "Modality / system", value: `${humanize(dataset.modality)} / ${humanize(dataset.system)}` },
          { label: "Audited files", value: formatCount(dataset.files) },
          { label: "Split method", value: publicText(task?.preparation?.split_method ?? "Not generated") },
          { label: "Dataset version", value: task?.preparation?.dataset_version ?? "Not generated", mono: true },
        ]}
      />
      <div className="mt-4 border-t border-line pt-3">
        <p className="text-[11px] font-medium uppercase tracking-wide text-ink-3">Audit flags</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {flags.map((flag) => <StatusBadge key={flag} status={flag} />)}
        </div>
      </div>
      {dataset.notes.length > 0 && (
        <ul className="mt-3 list-disc space-y-1 pl-4 text-xs leading-5 text-ink-2">
          {dataset.notes.map((note) => <li key={note}>{publicText(note)}</li>)}
        </ul>
      )}
    </Card>
  );
}

function TaskAudit({ audit, discoveryEligible }: { audit: DatasetTaskAuditResponse | null; discoveryEligible: number }) {
  const [query, setQuery] = useState("");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  if (!audit) {
    return <EmptyState title="Task audit unavailable" detail="The generated task-level evidence artifact could not be loaded." />;
  }
  const rows: TaskRow[] = audit.datasets.flatMap((dataset): TaskRow[] =>
    dataset.tasks.length > 0
      ? dataset.tasks.map((task) => ({ key: `${dataset.id}/${task.task_id}`, dataset, task }))
      : [{ key: `${dataset.id}/no-task`, dataset, task: null }],
  );
  const tasks = rows.filter((row) => row.task !== null);
  const eligible = tasks.filter((row) => row.task?.training_eligible).length;
  const ready = tasks.filter((row) => row.task?.readiness === "READY_FOR_TRAINING").length;
  const exploratory = tasks.filter((row) => row.task?.readiness === "EXPLORATORY_TRAINING_ONLY").length;
  const blocked = tasks.filter((row) => row.task?.readiness === "BLOCKED").length;
  const needle = query.trim().toLowerCase();
  const shown = rows.filter((row) =>
    [datasetName(row.dataset.id), row.task ? taskName(row.task.task_id, row.task.target) : null, row.dataset.labels, row.task?.target, row.task?.type]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(needle)),
  );
  const selected = rows.find((row) => row.key === selectedKey) ?? null;
  return (
    <>
      <Card title="Why the readiness counts differ" eyebrow="Two distinct generated evidence layers" className="mb-4">
        <p className="text-sm leading-6 text-ink-2">
          The path-level discovery registry can correctly show {discoveryEligible} eligible datasets because it keeps every discovered directory
          conservative: names, file counts, and structural hints do not activate training. This task audit applies later, task-specific checks for
          actual labels, licence, privacy, duplicate leakage, and split preparation. It currently marks {eligible} task units training-eligible:
          {" "}{ready} ready for planned training and {exploratory} explicitly exploratory-only, while keeping {blocked} blocked. The denominators
          and evidence stages differ; task readiness does not rewrite or override a discovery record.
        </p>
      </Card>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
        <Metric label="Audited identities" value={audit.datasets.length} note={`Generated ${audit.generated_at}`} />
        <Metric label="Task units" value={tasks.length} note={audit.tool} />
        <Metric label="Training eligible" value={eligible} note="Includes exploratory-only" />
        <Metric label="Ready for training" value={ready} status="READY_FOR_TRAINING" />
        <Metric label="Exploratory only" value={exploratory} status="EXPLORATORY_TRAINING_ONLY" />
        <Metric label="Blocked" value={blocked} status="BLOCKED" />
      </div>
      <div className="mt-4 grid gap-4 xl:grid-cols-[1.35fr_1fr]">
        <Card
          title="Audited task units"
          eyebrow="Task-level audit"
          padded={false}
          actions={
            <TextInput
              aria-label="Filter audited task units"
              placeholder="Filter"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="h-8 w-48 text-xs"
            />
          }
        >
          <Table headers={["Dataset / task", "Labels / type", "Readiness", "Eligible", "Splits", "Licence / privacy", "Flags"]} dense>
            {shown.map((row) => {
              const flags = row.task?.flags ?? ["NO_TASK_DEFINED"];
              return (
                <tr
                  key={row.key}
                  data-testid="dataset-task-audit-record"
                  onClick={() => setSelectedKey(row.key)}
                  className={`cursor-pointer ${selectedKey === row.key ? "bg-accent-soft" : "hover:bg-surface-2"}`}
                >
                  <td className="min-w-44">
                    <p className="font-medium text-ink">{datasetName(row.dataset.id)}</p>
                    <p className="mt-0.5 text-[11px] text-ink-3">{row.task ? taskName(row.task.task_id, row.task.target) : "No task defined"}</p>
                  </td>
                  <td className="min-w-40 text-xs text-ink-2">
                    <p>{taskLabels(row.dataset, row.task)}</p>
                    <p className="mt-0.5 text-ink-3">{row.task ? humanize(row.task.type) : humanize(row.dataset.labels)}</p>
                  </td>
                  <td><StatusBadge status={row.task?.readiness ?? "NO_TASK_DEFINED"} /></td>
                  <td><StatusBadge status={row.task?.training_eligible ? "ELIGIBLE" : "NOT_ELIGIBLE"} label={row.task?.training_eligible ? "Yes" : "No"} /></td>
                  <td className="min-w-36 text-xs text-ink-2">{splitCounts(row.task)}</td>
                  <td className="min-w-44">
                    <div className="flex flex-col items-start gap-1">
                      <StatusBadge status={row.dataset.license?.status ?? "UNKNOWN"} label={licenceLabel(row.dataset.license)} />
                      <StatusBadge status={row.dataset.privacy} />
                    </div>
                  </td>
                  <td className="min-w-48">
                    <div className="flex flex-wrap gap-1">
                      {flags.slice(0, 3).map((flag) => <StatusBadge key={`${row.key}-${flag}`} status={flag} />)}
                      {flags.length > 3 && <span className="text-[11px] text-ink-3">+{flags.length - 3}</span>}
                    </div>
                  </td>
                </tr>
              );
            })}
          </Table>
        </Card>
        <div>
          {selected ? (
            <TaskAuditDetail row={selected} />
          ) : (
            <EmptyState title="Select a task unit" detail="Labels, splits, licence, privacy, readiness, and audit flags appear here." />
          )}
        </div>
      </div>
    </>
  );
}

function ExpansionRoadmap() {
  const [priority, setPriority] = useState<"ALL" | RoadmapPriority>("ALL");
  const shownCandidates = DATASET_CANDIDATES.filter((candidate) => priority === "ALL" || candidate.priority === priority);
  const verifyFirst = SYSTEM_COVERAGE.filter((row) => row.action === "VERIFY_FIRST").length;
  const additions = SYSTEM_COVERAGE.filter((row) => row.action === "ADD").length;

  return (
    <>
      <Card title="Decision rule" eyebrow="Keep · add · verify first" className="mb-4">
        <div className="grid gap-3 text-sm leading-6 text-ink-2 md:grid-cols-3">
          <div className="rounded-lg border border-line bg-surface-2 p-3">
            <StatusBadge status="KEEP" label="Keep" />
            <p className="mt-2">Preserve existing sources and task definitions where they already cover the intended capability.</p>
          </div>
          <div className="rounded-lg border border-line bg-surface-2 p-3">
            <StatusBadge status="ADD" label="Add" />
            <p className="mt-2">Add only a genuinely new disease, modality, annotation type, or anatomical region.</p>
          </div>
          <div className="rounded-lg border border-line bg-surface-2 p-3">
            <StatusBadge status="VERIFY_FIRST" label="Verify first" />
            <p className="mt-2">Withhold training when provenance, rights, labels, pairing, or patient-level splits are uncertain.</p>
          </div>
        </div>
        <p className="mt-3 text-xs leading-5 text-ink-3">
          This roadmap is a planning layer, not proof that a dataset is present or eligible. Only the generated discovery and task-audit views report local evidence.
        </p>
      </Card>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Anatomical systems" value={SYSTEM_COVERAGE.length} note="Programme-level gap review" />
        <Metric label="Verify before expansion" value={verifyFirst} status="VERIFY_FIRST" note="Reconcile existing local evidence" />
        <Metric label="New capability gaps" value={additions} status="ADD" note="No activation implied" />
        <Metric label="Critical candidates" value={DATASET_CANDIDATES.filter((item) => item.priority === "CRITICAL").length} note="Every item still has an evidence gate" />
      </div>

      <Card title="Coverage by anatomical system" eyebrow="Reported coverage and remaining research gap" padded={false} className="mt-4">
        <Table headers={["System", "Current coverage", "Important gap", "Recommendation", "Action"]} dense>
          {SYSTEM_COVERAGE.map((row) => (
            <tr key={row.system}>
              <td className="whitespace-nowrap font-medium text-ink">{row.system}</td>
              <td className="min-w-56 text-xs leading-5 text-ink-2">{row.currentCoverage}</td>
              <td className="min-w-56 text-xs leading-5 text-ink-2">{row.remainingGap}</td>
              <td className="min-w-64 text-xs leading-5 text-ink">{row.recommendation}</td>
              <td><StatusBadge status={row.action} /></td>
            </tr>
          ))}
        </Table>
      </Card>

      <Card title="Claim boundaries" eyebrow="What the labels can and cannot establish" padded={false} className="mt-4">
        <Table headers={["Source", "Supported interpretation", "Do not claim"]} dense>
          {LABEL_BOUNDARIES.map((boundary) => (
            <tr key={boundary.source}>
              <td className="whitespace-nowrap font-medium text-ink">{boundary.source}</td>
              <td className="min-w-64 text-xs leading-5 text-ink-2">{boundary.supportedClaim}</td>
              <td className="min-w-72 text-xs leading-5 text-danger">{boundary.unsupportedClaim}</td>
            </tr>
          ))}
        </Table>
      </Card>

      <Card
        title="Candidate intake queue"
        eyebrow="Capability additions, not download authorization"
        padded={false}
        className="mt-4"
        actions={
          <Segmented
            label="Candidate priority"
            value={priority}
            onChange={setPriority}
            options={[
              { value: "ALL", label: "All" },
              { value: "CRITICAL", label: "Critical" },
              { value: "HIGH", label: "High" },
              { value: "OPTIONAL", label: "Optional" },
            ]}
          />
        }
      >
        <Table headers={["Priority", "Candidate", "System", "Capability gained", "Required gate"]} dense>
          {shownCandidates.map((candidate) => (
            <tr key={candidate.name}>
              <td><StatusBadge status={candidate.priority} /></td>
              <td className="min-w-44 font-medium text-ink">{candidate.name}</td>
              <td className="whitespace-nowrap text-xs text-ink-2">{candidate.system}</td>
              <td className="min-w-56 text-xs leading-5 text-ink-2">{candidate.capability}</td>
              <td className="min-w-72 text-xs leading-5 text-ink">{candidate.gate}</td>
            </tr>
          ))}
        </Table>
      </Card>
    </>
  );
}

export default function DatasetRegistryPage() {
  const registry = useWorkspace((state) => state.datasets);
  const taskAudit = useWorkspace((state) => state.datasetTaskAudit);
  const [view, setView] = useState<RegistryView>("discovery");
  const discoveryEligible = registry?.datasets.filter((dataset) => dataset.training_eligible || dataset.validation_eligible).length ?? 0;
  return (
    <>
      <PageHeader
        eyebrow="Dataset Registry"
        title="Dataset evidence and task readiness"
        description="Two authenticated, read-only generated artifacts: conservative path discovery and a later task-specific label/readiness audit. Neither view creates labels, activates data, or changes the stored evidence."
        actions={
          <Segmented
            label="Dataset registry view"
            value={view}
            onChange={setView}
            options={[
              { value: "discovery", label: "Discovery registry" },
              { value: "task-audit", label: "Task audit" },
              { value: "roadmap", label: "Expansion roadmap" },
            ]}
          />
        }
      />
      {view === "discovery" && <DiscoveryRegistry registry={registry} />}
      {view === "task-audit" && <TaskAudit audit={taskAudit} discoveryEligible={discoveryEligible} />}
      {view === "roadmap" && <ExpansionRoadmap />}
    </>
  );
}
