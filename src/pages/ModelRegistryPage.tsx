import { useState } from "react";
import { Badge, Card, KeyValue, Metric, PageHeader, StatusBadge } from "../components/ui";
import type { ModelRegistryRecord } from "../services/api";
import { frameworkLabel, publicText, runtimeLabel } from "../lib/displayNames";
import { formatNumber, humanize } from "../lib/format";
import { useWorkspace } from "../state/workspace";

function declared(value: unknown): string {
  if (value === null || value === undefined || value === "" || (typeof value === "object" && Object.keys(value as object).length === 0)) return "Not declared";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

function ModelCard({ model }: { model: ModelRegistryRecord }) {
  const bundle = model.artifact_bundle as Record<string, unknown>;
  return (
    <Card
      title={model.display_name}
      eyebrow={`${humanize(model.anatomy)} · ${humanize(model.task)}`}
      actions={<><StatusBadge status={model.registry_state} /><StatusBadge status={model.activation.eligible ? "ACTIVATION_ELIGIBLE" : "BLOCKED"} label={model.activation.eligible ? "Activation eligible" : "Activation blocked"} /></>}
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
        { label: "Deployment readiness", value: <StatusBadge status={model.activation.eligible ? "READY" : "NOT_READY"} /> },
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
          <p className="text-xs font-medium text-ink">Activation blockers</p>
          <div className="mt-1.5 flex flex-wrap gap-1">{model.activation.blockers.map((blocker) => <StatusBadge key={blocker} status={blocker} />)}</div>
          {model.activation.missing_fields.length > 0 && <p className="mt-2 text-[11px] leading-4 text-ink-3">Missing bundle fields: {model.activation.missing_fields.join(", ")}</p>}
        </div>
      )}
      {model.limitations.length > 0 && <ul className="mt-3 list-disc space-y-0.5 pl-4 text-xs leading-5 text-ink-2">{model.limitations.map((limitation) => <li key={limitation}>{publicText(limitation)}</li>)}</ul>}
    </Card>
  );
}

export default function ModelRegistryPage() {
  const models = useWorkspace((state) => state.models);
  const [state, setState] = useState("ALL");
  const states = [...new Set(models.map((model) => model.registry_state))].sort();
  const shown = models.filter((model) => state === "ALL" || model.registry_state === state);
  return (
    <>
      <PageHeader eyebrow="Model Registry" title="Models and activation gates" description="A model's ability to run is not evidence that it is reliable. Activation requires a complete artifact bundle: licensed dataset and version, patient-level split, task and label definitions, preprocessing, hashed checkpoint, calibration, thresholds, held-out predictions, evaluation report and model card." />
      <div className="grid gap-3 sm:grid-cols-3">
        <Metric label="Registered models" value={models.length} />
        <Metric label="Activation eligible" value={models.filter((model) => model.activation.eligible).length} note="Validated with a complete bundle" />
        <Metric label="Processor-only baselines" value={models.filter((model) => model.processor_only).length} note="Transparent rules, not learned models" />
      </div>
      <div className="my-4 flex flex-wrap gap-1.5">
        {["ALL", ...states].map((value) => (
          <button key={value} type="button" onClick={() => setState(value)} aria-pressed={state === value}>
            <Badge tone={state === value ? "accent" : "neutral"} icon={false}>{value === "ALL" ? `All (${models.length})` : `${humanize(value)} (${models.filter((model) => model.registry_state === value).length})`}</Badge>
          </button>
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-2">{shown.map((model) => <ModelCard key={model.model_id} model={model} />)}</div>
    </>
  );
}
