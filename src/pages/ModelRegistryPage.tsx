import { useState } from "react";
import { Badge, Card, ErrorBlock, KeyValue, Metric, PageHeader, Segmented, StatusBadge, Table } from "../components/ui";
import { api, type ExternalEvaluationSummary, type ModelRegistryRecord } from "../services/api";
import { useAsync } from "../lib/useAsync";
import { frameworkLabel, publicText, runtimeLabel } from "../lib/displayNames";
import { formatNumber, humanize } from "../lib/format";
import { useWorkspace } from "../state/workspace";
import CapabilityCoverage from "../components/CapabilityCoverage";
import ResearchJobProgress from "../components/ResearchJobProgress";
import TabularModelForm from "../components/TabularModelForm";

function declared(value: unknown): string {
  if (value === null || value === undefined || value === "" || (typeof value === "object" && Object.keys(value as object).length === 0)) return "Not declared";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

type RegistryView = "evidence" | "cards" | "coverage";

function isRecorded(value: unknown): boolean {
  return value !== null && value !== undefined && value !== "" && value !== "UNKNOWN" && value !== "UNVERIFIED";
}

function externalEvaluationRecorded(model: ModelRegistryRecord): boolean {
  const bundle = model.artifact_bundle as Record<string, unknown>;
  const extended = model as ModelRegistryRecord & { external_validation?: unknown };
  return Boolean(
    bundle.external_evaluation_path
    || bundle.external_validation_report_path
    || (model.external_evaluation?.length ?? 0) > 0
    || extended.external_validation,
  );
}

const COHORT_SCOPE: Record<string, string> = {
  FULL_REFERENCED_COHORT: "the full referenced cohort",
  FULL_REFERENCED_COHORT_EXCEPT_DOCUMENTED_SOURCE_DEFECTS: "the full referenced cohort, except scans whose public source copy is defective",
  PILOT_SUBSET_NOT_FULL_COHORT: "a pilot subset, not the full cohort",
};

function share(value: number | null): string {
  return value === null ? "Not computed" : `${(value * 100).toFixed(1)}%`;
}

function ExternalEvaluation({ result }: { result: ExternalEvaluationSummary }) {
  return (
    <div className="mt-3 rounded-lg border border-line p-3">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-xs font-medium text-ink">External evaluation on a public cohort</p>
        <StatusBadge status="EXTERNALLY_EVALUATED" label="Research measurement" />
        <StatusBadge status="NOT_CLINICALLY_VALIDATED" label="Not clinical validation" />
      </div>
      <p className="mt-1.5 text-[11px] leading-4 text-ink-2">
        {publicText(result.dataset)}; {COHORT_SCOPE[result.scope ?? ""] ?? humanize(result.scope ?? "scope not stated")}.
        {result.reference_standard && <> Reference standard: {result.reference_standard}.</>}
        {" "}{result.scored ?? 0} scans scored; {result.refused ?? 0} refused by the input checks. Refused scans are reported separately and never counted as normal.
        {result.excluded.length > 0 && <> Excluded: {result.excluded.map((item) => `${item.scan} (${item.reason ?? "reason not stated"})`).join("; ")}.</>}
      </p>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full border-collapse text-left text-xs tabular">
          <thead>
            <tr className="border-b border-line text-[11px] text-ink-3">
              {["Finding", "Positive / negative", "AUROC (95% CI)", "Sensitivity", "Specificity"].map((header) => <th key={header} scope="col" className="px-1.5 py-1 font-medium">{header}</th>)}
            </tr>
          </thead>
          <tbody className="divide-y divide-line text-ink-2 [&_td]:px-1.5 [&_td]:py-1 [&_td]:align-top">
            {result.labels.map((label) => (
              <tr key={label.label}>
                <td className="font-medium text-ink">{label.label}</td>
                <td className="whitespace-nowrap">{label.positives ?? "?"} / {label.negatives ?? "?"}</td>
                <td>
                  <span className="text-ink">{label.auroc === null ? "Not computed" : label.auroc.toFixed(3)}</span>
                  {label.auroc_ci95 && <span className="block whitespace-nowrap text-[10px] text-ink-3">{label.auroc_ci95[0].toFixed(3)}–{label.auroc_ci95[1].toFixed(3)}</span>}
                </td>
                <td>{share(label.sensitivity)}</td>
                <td>{share(label.specificity)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-1.5 text-[11px] leading-4 text-ink-3">
        {result.threshold_policy ? `${result.threshold_policy}. ` : ""}
        Measured the registered checkpoint (same SHA-256). Small positive counts give wide uncertainty. Report: <code>{result.report_path}</code>
      </p>
    </div>
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
      {model.external_evaluation?.map((result) => <ExternalEvaluation key={result.report_path} result={result} />)}
      {model.task === "tabular_classification" && model.research_gate?.allowed && <TabularModelForm modelId={model.model_id} />}
      {(model.inference_route || model.local_evaluation) && (
        <div className="mt-3 rounded-lg border border-line p-3 text-[11px] leading-4 text-ink-2">
          {model.inference_route && <p>Runs through its own endpoint: <code>{model.inference_route}</code>.</p>}
          {model.local_evaluation && (
            <p className={model.inference_route ? "mt-1" : ""}>
              Local check, {model.local_evaluation.scope.toLowerCase()}: {publicText(model.local_evaluation.headline)} ({publicText(model.local_evaluation.dataset)}).
              This is narrower than a held-out evaluation of the model's outputs.
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
          registry response contains no evidence for that facet. An external-evaluation cell shows either a saved research result on a public cohort
          the model never trained on, for the registered checkpoint only, or a reference to an outside report. Neither is clinical validation.
          The registry gate checks declared status and artifacts; passing it is not clinical approval.
        </p>
      </Card>
      <Card title="Model evidence facets" eyebrow="Current authenticated registry response" padded={false}>
        <Table headers={["Model", "Registry state", "Dataset + licence", "Dependency", "Checkpoint hash", "Research gate", "Internal evaluation", "External evaluation", "Registry artifact gate"]} dense>
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
                  {!model.research_gate && model.inference_route && model.activation.checkpoint_hash_matches ? (
                    <span title={model.inference_route}><StatusBadge status="RESEARCH_ONLY_UNVALIDATED" label="Runnable (own route)" /></span>
                  ) : (
                    <Facet
                      value={model.research_gate?.allowed === true}
                      yes="Runnable"
                      no="Blocked / not routed"
                      yesStatus="RESEARCH_ONLY_UNVALIDATED"
                      noStatus="BLOCKED"
                    />
                  )}
                </td>
                <td>
                  {!internalEvaluation && model.local_evaluation ? (
                    <span title={`${model.local_evaluation.headline} (${model.local_evaluation.dataset})`}><StatusBadge status="PARTIAL" label={`Local check: ${model.local_evaluation.scope}`} /></span>
                  ) : <Facet value={internalEvaluation} yes="Held-out report" no="Not recorded" yesStatus="INTERNALLY_EVALUATED" />}
                </td>
                <td>
                  {model.external_evaluation?.length ? (
                    <span title={model.external_evaluation.map((result) => publicText(result.dataset)).join("; ")}><StatusBadge status="EXTERNALLY_EVALUATED" label="Public-cohort result" /></span>
                  ) : <Facet value={externalEvaluationRecorded(model)} yes="Referenced" no="Not recorded" yesStatus="RECORDED" />}
                </td>
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
  const learning = useAsync(() => api.getResearchLearning(), []);
  const registry = useAsync(() => api.getModels(), []);
  const workspaceModels = useWorkspace((state) => state.models);
  // Registry evidence should not wait for unrelated dataset inventories in shell loading.
  const models = registry.data?.models ?? workspaceModels;
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
              { value: "coverage", label: "Organ / test coverage" },
            ]}
          />
        }
      />
      <ResearchJobProgress />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Registry entries" value={registry.loading && models.length === 0 ? "Loading" : models.length} note="Includes frameworks and text processors" />
        <Metric label="Internal evaluation recorded" value={internalEvaluated} note="Not external or clinical validation" />
        <Metric label="External evaluation recorded" value={externalEvaluated} note="Research results or references, not clinical validation" />
        <Metric label="Registry gate eligible" value={models.filter((model) => model.activation.eligible).length} note="Artifact/status checks, not clinical approval" />
      </div>
      {registry.error && <ErrorBlock message={registry.error} onRetry={registry.reload} />}
      <div className="mt-4"><Card title="Experimental learning strategies" eyebrow="Public-data research only">
        <p className="text-sm text-ink-2">{learning.data?.notice ?? "Unsupervised novelty, semi-supervised self-training, and offline reinforcement learning run as isolated research experiments. No automatic training on uploads or treatment selection."}</p>
        {learning.loading && <p className="mt-2 text-xs text-ink-2">Reading experiment report...</p>}
        {learning.error && <p className="mt-2 text-xs text-ink-2">Experiment report unavailable.</p>}
        {learning.data?.strategies.map((strategy) => <p className="mt-2 text-xs text-ink-2" key={strategy}>{strategy}</p>)}
        {learning.data?.benchmark && <KeyValue columns={3} items={[
          { label: "Benchmark", value: learning.data.benchmark.dataset },
          { label: "Seed labeled / unlabeled", value: `${learning.data.benchmark.labeled_rows} / ${learning.data.benchmark.unlabeled_rows}` },
          { label: "Supervised / semi-supervised accuracy", value: `${formatNumber(learning.data.benchmark.metrics.supervised_seed.accuracy * 100, 1)}% / ${formatNumber(learning.data.benchmark.metrics.semi_supervised.accuracy * 100, 1)}%` },
          { label: "Offline policy coverage", value: `${formatNumber(learning.data.benchmark.metrics.offline_workflow_policy.coverage * 100, 1)}%` },
          { label: "Policy accuracy on accepted samples", value: learning.data.benchmark.metrics.offline_workflow_policy.selective_accuracy === null ? "No accepted samples" : `${formatNumber(learning.data.benchmark.metrics.offline_workflow_policy.selective_accuracy * 100, 1)}%` },
          { label: "Clinical activation", value: "Disabled; benchmark results only" },
        ]} />}
      </Card></div>
      {view === "coverage" ? (
        <div className="mt-4"><CapabilityCoverage models={models} /></div>
      ) : view === "evidence" ? (
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
