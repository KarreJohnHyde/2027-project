import { useState } from "react";
import { Badge, Card, KeyValue, Metric, PageHeader, Segmented, StatusBadge, Table } from "../components/ui";
import type { ModelRegistryRecord } from "../services/api";
import { frameworkLabel, publicText, runtimeLabel } from "../lib/displayNames";
import { formatNumber, humanize } from "../lib/format";
import { useWorkspace } from "../state/workspace";

function declared(value: unknown): string {
  if (value === null || value === undefined || value === "" || (typeof value === "object" && Object.keys(value as object).length === 0)) return "Not declared";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

type RegistryView = "evidence" | "cards";

function isRecorded(value: unknown): boolean {
  return value !== null && value !== undefined && value !== "" && value !== "UNKNOWN" && value !== "UNVERIFIED";
}

function externalEvaluationRecorded(model: ModelRegistryRecord): boolean {
  const bundle = model.artifact_bundle as Record<string, unknown>;
  const extended = model as ModelRegistryRecord & { external_evaluation?: unknown; external_validation?: unknown };
  return Boolean(
    bundle.external_evaluation_path
    || bundle.external_validation_report_path
    || extended.external_evaluation
    || extended.external_validation,
  );
}

function Facet({ value, yes = "Recorded", no = "Not recorded", yesStatus = "RECORDED", noStatus = "NOT_RECORDED" }: {
  value: boolean;
  yes?: string;
  no?: string;
  yesStatus?: string;
  noStatus?: string;
}) {
  return <StatusBadge status={value ? yesStatus : noStatus} label={value ? yes : no} />;
}

function ModelCard({ model }: { model: ModelRegistryRecord }) {
  const bundle = model.artifact_bundle as Record<string, unknown>;
  return (
    <Card
      title={model.display_name}
      eyebrow={`${humanize(model.anatomy)} · ${humanize(model.task)}`}
      actions={<><StatusBadge status={model.registry_state} /><StatusBadge status={model.activation.eligible ? "GATE_PASSED" : "BLOCKED"} label={model.activation.eligible ? "Registry gate passed" : "Registry gate blocked"} /></>}
    >
      <KeyValue columns={3} items={[
        { label: "Task", value: humanize(model.task) },
        { label: "Anatomy", value: humanize(model.anatomy) },
        { label: "Modality / inputs", value: model.supported_inputs.join(", ") || "Not declared" },
        { label: "Supported classes", value: model.supported_classes.join(", ") || "Not declared" },
        { label: "Architecture / method", value: frameworkLabel(model.framework) },
        { label: "Runtime", value: `${runtimeLabel(model.dependency_environment)} · ${model.device}` },
        { label: "Checkpoint", value: bundle.checkpoint_path ? "Registered; verified by SHA-256 before loading" : "Not declared" },
        { label: "Checkpoint SHA-256", value: declared(bundle.checkpoint_sha256), mono: true },
        { label: "Preprocessing", value: declared(bundle.preprocessing_version) },
        { label: "Calibration", value: declared(bundle.calibration) },
        { label: "Evaluation dataset", value: declared(bundle.dataset_version) },
        { label: "Operating thresholds", value: declared(bundle.decision_thresholds) },
        { label: "Abstention thresholds", value: declared(bundle.abstention_thresholds) },
        { label: "Output schema", value: "Not declared" },
        { label: "Registry artifact gate", value: <StatusBadge status={model.activation.eligible ? "GATE_PASSED" : "GATE_BLOCKED"} /> },
      ]} />
      {model.research_gate && (
        <div className="mt-3 rounded-lg border border-line p-3">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-xs font-medium text-ink">Research-only inference</p>
            <StatusBadge status={model.research_gate.allowed ? "RESEARCH_ONLY_UNVALIDATED" : "BLOCKED"} label={model.research_gate.allowed ? "Runnable for research" : "Research use blocked"} />
          </div>
          {model.research_gate.blockers.length > 0 && <div className="mt-1.5 flex flex-wrap gap-1">{model.research_gate.blockers.map((blocker) => <StatusBadge key={blocker} status={blocker} />)}</div>}
          {model.held_out_evaluation && (
            <p className="mt-1.5 text-[11px] leading-4 text-ink-2">
              Internal held-out evaluation on the public training source (not external or clinical validation):{" "}
              {Object.entries(model.held_out_evaluation).filter(([, value]) => typeof value === "number").map(([key, value]) => `${humanize(key)} ${key === "test_n" ? value : formatNumber(value as number, 3)}`).join(" · ")}.
              {" "}{bundle.evaluation_report_path ? "The evaluation report and model card are registered with this entry." : "No evaluation report is registered."}
            </p>
          )}
        </div>
      )}
      {!model.activation.eligible && (
        <div className="mt-3 rounded-lg border border-line bg-surface-2 p-3">
          <p className="text-xs font-medium text-ink">Registry gate blockers</p>
          <div className="mt-1.5 flex flex-wrap gap-1">{model.activation.blockers.map((blocker) => <StatusBadge key={blocker} status={blocker} />)}</div>
          {model.activation.missing_fields.length > 0 && <p className="mt-2 text-[11px] leading-4 text-ink-3">Missing bundle fields: {model.activation.missing_fields.join(", ")}</p>}
        </div>
      )}
      {model.limitations.length > 0 && <ul className="mt-3 list-disc space-y-0.5 pl-4 text-xs leading-5 text-ink-2">{model.limitations.map((limitation) => <li key={limitation}>{publicText(limitation)}</li>)}</ul>}
    </Card>
  );
}

function EvidenceMatrix({ models }: { models: ModelRegistryRecord[] }) {
  return (
    <>
      <Card title="How to read this matrix" eyebrow="Separate facts, never a single readiness score" className="mb-4">
        <p className="text-sm leading-6 text-ink-2">
          A registry entry, dataset citation, installed dependency, checkpoint, runnable research path, internal evaluation, external evaluation,
          and clinical activation are different claims. A green cell in one column never upgrades another column. “Not recorded” means this
          registry response contains no evidence for that facet. External-report cells show references, not independently verified results.
          The registry gate checks declared status and artifacts; passing it is not clinical approval.
        </p>
      </Card>
      <Card title="Model evidence facets" eyebrow="Current authenticated registry response" padded={false}>
        <Table headers={["Model", "Registry state", "Dataset + licence", "Dependency", "Checkpoint hash", "Research gate", "Internal evaluation", "External report reference", "Registry artifact gate"]} dense>
          {models.map((model) => {
            const bundle = model.artifact_bundle as Record<string, unknown>;
            const datasetRecorded = isRecorded(bundle.dataset_version) && isRecorded(bundle.dataset_license);
            const dependencyBlocked = model.status === "DEPENDENCY_MISSING" || model.status === "NOT_INSTALLED";
            const internalEvaluation = isRecorded(bundle.evaluation_report_path) && Boolean(model.held_out_evaluation);
            return (
              <tr key={model.model_id}>
                <td className="min-w-56">
                  <p className="font-medium text-ink">{model.display_name}</p>
                  <p className="mt-0.5 font-mono text-[10px] text-ink-3">{model.model_id}</p>
                </td>
                <td><StatusBadge status={model.registry_state} /></td>
                <td><Facet value={datasetRecorded} /></td>
                <td>
                  <Facet
                    value={!dependencyBlocked}
                    yes="No block recorded"
                    no="Blocked"
                    yesStatus="AVAILABLE"
                    noStatus="DEPENDENCY_MISSING"
                  />
                </td>
                <td>
                  <Facet
                    value={model.activation.checkpoint_hash_matches}
                    yes="Hash matched"
                    no={isRecorded(bundle.checkpoint_path) ? "Not matched" : "No checkpoint"}
                    yesStatus="VERIFIED"
                    noStatus="CHECKPOINT_MISSING"
                  />
                </td>
                <td>
                  <Facet
                    value={model.research_gate?.allowed === true}
                    yes="Runnable"
                    no="Blocked / not routed"
                    yesStatus="RESEARCH_ONLY_UNVALIDATED"
                    noStatus="BLOCKED"
                  />
                </td>
                <td><Facet value={internalEvaluation} yes="Held-out report" no="Not recorded" yesStatus="INTERNALLY_EVALUATED" /></td>
                <td><Facet value={externalEvaluationRecorded(model)} yes="Referenced" no="Not recorded" yesStatus="RECORDED" /></td>
                <td>
                  <Facet
                    value={model.activation.eligible}
                    yes="Eligible"
                    no="Not eligible"
                    yesStatus="GATE_PASSED"
                    noStatus="GATE_BLOCKED"
                  />
                </td>
              </tr>
            );
          })}
        </Table>
      </Card>
    </>
  );
}

export default function ModelRegistryPage() {
  const models = useWorkspace((state) => state.models);
  const [state, setState] = useState("ALL");
  const [view, setView] = useState<RegistryView>("evidence");
  const states = [...new Set(models.map((model) => model.registry_state))].sort();
  const shown = models.filter((model) => state === "ALL" || model.registry_state === state);
  const internalEvaluated = models.filter((model) => {
    const bundle = model.artifact_bundle as Record<string, unknown>;
    return isRecorded(bundle.evaluation_report_path) && Boolean(model.held_out_evaluation);
  }).length;
  const externalEvaluated = models.filter(externalEvaluationRecorded).length;
  return (
    <>
      <PageHeader
        eyebrow="Model Registry"
        title="Models and activation gates"
        description="A model's ability to run is not evidence that it is reliable. The registry gate checks declared validation status and an artifact bundle: dataset licence and version, split manifest, task and labels, preprocessing, hashed checkpoint, calibration, thresholds, held-out predictions, evaluation report and model card. It does not independently establish external validation or clinical approval."
        actions={
          <Segmented
            label="Model registry view"
            value={view}
            onChange={setView}
            options={[
              { value: "evidence", label: "Evidence matrix" },
              { value: "cards", label: "Model cards" },
            ]}
          />
        }
      />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Registry entries" value={models.length} note="Includes frameworks and text processors" />
        <Metric label="Internal evaluation recorded" value={internalEvaluated} note="Not external or clinical validation" />
        <Metric label="External report references" value={externalEvaluated} note="Metadata references, not independent verification" />
        <Metric label="Registry gate eligible" value={models.filter((model) => model.activation.eligible).length} note="Artifact/status checks, not clinical approval" />
      </div>
      {view === "evidence" ? (
        <div className="mt-4"><EvidenceMatrix models={models} /></div>
      ) : (
        <>
          <div className="my-4 flex flex-wrap gap-1.5">
            {["ALL", ...states].map((value) => (
              <button key={value} type="button" onClick={() => setState(value)} aria-pressed={state === value}>
                <Badge tone={state === value ? "accent" : "neutral"} icon={false}>{value === "ALL" ? `All (${models.length})` : `${humanize(value)} (${models.filter((model) => model.registry_state === value).length})`}</Badge>
              </button>
            ))}
          </div>
          <div className="grid gap-4 xl:grid-cols-2">{shown.map((model) => <ModelCard key={model.model_id} model={model} />)}</div>
        </>
      )}
    </>
  );
}
