import { useCallback, useMemo, useState } from "react";
import { TrendingUp } from "lucide-react";
import AnatomyViewport, { type TargetSummary, type ViewportLayer } from "../anatomy/AnatomyViewport";
import { loadAtlasIndex, loadManifest, selectAtlasStructures } from "../anatomy/data";
import type { AnatomyManifest, AtlasIndex } from "../anatomy/types";
import { ObservedHorizonChart } from "../components/charts";
import { ImageTile } from "../components/ImageTile";
import { Badge, Button, Card, ErrorBlock, Field, KeyValue, LoadingBlock, PageHeader, SelectInput, StatusBadge, Table, TextInput, Unavailable } from "../components/ui";
import { api, type PrognosisCapability, type PrognosisEvaluation, type ScenarioBlock } from "../services/api";
import { errorMessage, formatDate, humanize } from "../lib/format";
import { useAsync } from "../lib/useAsync";
import { useSelectedCase, useWorkspace } from "../state/workspace";

const HORIZONS = [90, 180, 365, 730, 1825];
const EMPTY = new Set<string>();
const HYBRID_GROUPS = ["cardiovascular.heart", "visceral.respiratory_system", "visceral.liver", "visceral.pancreas", "visceral.digestive_canal", "visceral.urinary_system", "nervous.brain"];

function StateLegend() {
  const items: Array<[string, string, string]> = [
    ["OBSERVED", "Documented value or uploaded image", "bg-[var(--mt-series-1)]"],
    ["ESTIMATED", "Model estimate within observed time (none available)", "bg-[var(--mt-series-2)]"],
    ["FORECAST", "Validated projection beyond the last observation (none available)", "border-2 border-dashed border-[var(--mt-series-1)]"],
    ["UNAVAILABLE", "No validated model or estimand; nothing is drawn", "hatch border border-line-strong"],
  ];
  return (
    <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
      {items.map(([code, meaning, swatch]) => (
        <li key={code} className="flex items-start gap-2 text-xs"><span aria-hidden className={`mt-0.5 h-3.5 w-6 shrink-0 rounded-sm ${swatch}`} /><span><b className="font-medium text-ink">{humanize(code)}</b><span className="block text-ink-3">{meaning}</span></span></li>
      ))}
    </ul>
  );
}

function anatomyLayers(manifest: AnatomyManifest, atlas: AtlasIndex, organ: string): ViewportLayer[] {
  const variant = manifest.variants[`atlas-${organ}`];
  const groups = variant?.atlas?.groups ?? (organ === "hybrid" ? HYBRID_GROUPS : []);
  const structures = selectAtlasStructures(atlas, { groups });
  const chunkIds = new Set(atlas.chunks.filter((chunk) => structures.some((structure) => structure.meshes.some((mesh) => mesh >= chunk.mesh_start && mesh < chunk.mesh_start + chunk.mesh_count))).map((chunk) => chunk.id));
  return structures.length ? [{ kind: "atlas", key: `prognosis:${organ}`, chunks: atlas.chunks.filter((chunk) => chunkIds.has(chunk.id)).map((chunk) => ({ id: chunk.id, url: chunk.standard.url })), structures, palette: atlas.palette }] : [];
}

function ScenarioPanel({ scenario, evaluation, layers, shared }: {
  scenario: ScenarioBlock;
  evaluation: PrognosisEvaluation;
  layers: ViewportLayer[];
  shared: { selected: TargetSummary | null; hovered: TargetSummary | null; setSelected: (target: TargetSummary | null) => void; setHovered: (target: TargetSummary | null) => void };
}) {
  const uploads = useWorkspace((state) => state.evidence.uploads);
  const images = evaluation.observed.imaging_studies;
  const baseline = images[0];
  const latest = images.length > 1 ? images[images.length - 1] : null;
  const capability = evaluation.capability;
  const framing = useMemo(() => ({ mode: "fit" as const }), []);
  const section = useMemo(() => ({ axis: "y" as const, offset: 0, flip: false }), []);
  return (
    <Card
      title={scenario.label}
      eyebrow={`Horizon ${evaluation.horizon_days} days`}
      actions={<StatusBadge status={scenario.status} />}
    >
      <div className="flex flex-wrap gap-1">{scenario.reason_codes.map((code) => <Badge key={code} tone="unavailable">{code}</Badge>)}</div>

      <h3 className="mt-4 text-xs font-semibold text-ink-2">2D medical images</h3>
      <div className="mt-2 grid grid-cols-3 gap-2">
        {baseline ? <ImageTile upload={uploads.find((upload) => upload.id === baseline.upload_id)!} caption={`Baseline ${baseline.date ? formatDate(baseline.date) : "undated"}`} /> : <div className="hatch grid aspect-square place-items-center rounded-lg border border-line-strong p-2 text-center text-[11px] text-ink-2">No observed image</div>}
        {latest ? <ImageTile upload={uploads.find((upload) => upload.id === latest.upload_id)!} caption={`Follow-up ${latest.date ? formatDate(latest.date) : "undated"}`} /> : <div className="hatch grid aspect-square place-items-center rounded-lg border border-line-strong p-2 text-center text-[11px] text-ink-2">No follow-up image</div>}
        <div className="hatch grid aspect-square place-items-center rounded-lg border border-line-strong p-2 text-center text-[11px] leading-4 text-ink-2" role="img" aria-label="Future image unavailable">Future image<br /><b className="font-medium">{capability.forecast_2d.reason}</b></div>
      </div>

      <h3 className="mt-4 text-xs font-semibold text-ink-2">3D anatomy</h3>
      <div className="relative mt-2 h-64 overflow-hidden rounded-lg">
        {layers.length ? (
          <AnatomyViewport
            layers={layers}
            framing={framing}
            viewMode="EXTERIOR"
            opacity={1}
            section={section}
            isolate={false}
            labels={false}
            projection="perspective"
            selectedKey={shared.selected?.key ?? null}
            hoveredKey={shared.hovered?.key ?? null}
            hidden={EMPTY}
            onSelect={shared.setSelected}
            onHover={shared.setHovered}
            resetToken={0}
          />
        ) : <Unavailable code="NOT_AVAILABLE" reason="No atlas reference exists for this system." />}
        <span className="pointer-events-none absolute left-2 top-2 rounded-md bg-black/65 px-2 py-1 text-[11px] text-white">Baseline: generic L1 reference · forecast geometry {capability.forecast_3d.status.toLowerCase()}</span>
        {shared.selected && <span className="pointer-events-none absolute bottom-2 left-2 rounded-md bg-black/65 px-2 py-1 text-[11px] text-white">{shared.selected.label}</span>}
      </div>

      <h3 className="mt-4 text-xs font-semibold text-ink-2">Progression measurements</h3>
      {evaluation.observed.biomarker_series.filter((series) => series.points.length > 0).length === 0 ? (
        <div className="mt-2"><Unavailable compact code="INSUFFICIENT_EVIDENCE" reason="No dated measurement relevant to this system is documented in the case." /></div>
      ) : (
        <div className="mt-2 space-y-3">
          {evaluation.observed.biomarker_series.filter((series) => series.points.length > 0).slice(0, 2).map((series) => (
            <div key={series.name}>
              <p className="text-xs text-ink"><b className="font-medium">{series.display_name}</b> <span className="text-ink-3">({series.unit}, {series.points.length} observed)</span></p>
              <ObservedHorizonChart series={series} horizonDays={evaluation.horizon_days} />
            </div>
          ))}
        </div>
      )}

      <h3 className="mt-4 text-xs font-semibold text-ink-2">Uncertainty</h3>
      <div className="mt-2"><Unavailable compact code="NOT_AVAILABLE" reason="Intervals are reported only by a validated model with a calibrated uncertainty method." /></div>

      <h3 className="mt-4 text-xs font-semibold text-ink-2">Evidence and model</h3>
      <div className="mt-2">
        <KeyValue items={[
          { label: "Trained model", value: <StatusBadge status={capability.trained_model_status} /> },
          { label: "Validation", value: <StatusBadge status={capability.model_validation_status} /> },
          { label: "Candidate methods", value: capability.candidate_models.join("; ") },
          { label: "Forecast availability", value: <StatusBadge status={scenario.status} /> },
        ]} />
      </div>
    </Card>
  );
}

function CapabilityTable({ capability }: { capability: PrognosisCapability }) {
  return (
    <KeyValue columns={3} items={[
      { label: "Outcome variables", value: capability.outcome_variables.map((outcome) => `${outcome.name} (${humanize(outcome.type)})`).join("; ") },
      { label: "Suitable data", value: capability.suitable_data },
      { label: "Candidate models", value: capability.candidate_models.join("; ") },
      { label: "Trained model status", value: <StatusBadge status={capability.trained_model_status} /> },
      { label: "Validation status", value: <StatusBadge status={capability.model_validation_status} /> },
      { label: "Applicable population", value: capability.applicable_population ?? "Not established" },
      { label: "Required inputs", value: capability.required_inputs.join("; ") },
      { label: "Forecast horizon", value: capability.forecast_horizon ?? "Not validated" },
      { label: "Uncertainty method", value: capability.uncertainty_method ?? "Not defined" },
      { label: "Treatment comparison", value: <StatusBadge status={capability.treatment_comparison.reason} /> },
      { label: "2D forecasting", value: <StatusBadge status={capability.forecast_2d.reason} /> },
      { label: "3D forecasting", value: <StatusBadge status={capability.forecast_3d.reason} /> },
    ]} />
  );
}

export default function PrognosisStudioPage() {
  const selected = useSelectedCase()!;
  const capabilities = useAsync(() => api.getPrognosisCapabilities(), []);
  const anatomy = useAsync(() => Promise.all([loadManifest(), loadAtlasIndex()]), []);
  const history = useAsync(() => api.getPrognosisEvaluations(selected.id), [selected.id]);
  const [organ, setOrgan] = useState("heart");
  const [intervention, setIntervention] = useState("");
  const [horizon, setHorizon] = useState(365);
  const [evaluation, setEvaluation] = useState<PrognosisEvaluation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sharedSelected, setSharedSelected] = useState<TargetSummary | null>(null);
  const [sharedHovered, setSharedHovered] = useState<TargetSummary | null>(null);
  const capability = capabilities.data?.capabilities.find((item) => item.organ_system === organ) ?? null;
  const layers = useMemo(() => (anatomy.data ? anatomyLayers(anatomy.data[0], anatomy.data[1], organ) : []), [anatomy.data, organ]);
  const shared = { selected: sharedSelected, hovered: sharedHovered, setSelected: setSharedSelected, setHovered: setSharedHovered };

  const evaluate = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setEvaluation(await api.evaluatePrognosis({ case_id: selected.id, organ_system: organ, intervention_id: intervention.trim() || null, horizon_days: horizon }));
      history.reload();
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }, [selected.id, organ, intervention, horizon, history]);

  return (
    <>
      <PageHeader
        eyebrow="Prognosis Studio"
        title="MedTwin Prognosis Studio — Evidence-Based Longitudinal Risk and Scenario Analysis"
        description="Scenario A and Scenario B are shown side by side only with validated estimates. Without a trained, validated model and a defined causal estimand, each panel shows the observed evidence and why its forecast is unavailable."
      />
      <Card title="Scenario definition">
        <div className="grid gap-3 md:grid-cols-[1fr_1.4fr_10rem_auto] md:items-end">
          <Field label="Organ system">
            <SelectInput value={organ} onChange={(event) => { setOrgan(event.target.value); setEvaluation(null); setSharedSelected(null); }}>
              {(capabilities.data?.capabilities ?? []).map((item) => <option key={item.organ_system} value={item.organ_system}>{item.label}</option>)}
            </SelectInput>
          </Field>
          <Field label="Specified treatment" hint={capability && capability.interventions.length === 0 ? "No intervention estimand is registered for this system." : undefined}>
            <TextInput placeholder="e.g. a drug class or procedure" value={intervention} onChange={(event) => setIntervention(event.target.value)} />
          </Field>
          <Field label="Time horizon">
            <SelectInput value={horizon} onChange={(event) => setHorizon(Number(event.target.value))}>{HORIZONS.map((days) => <option key={days} value={days}>{days} days</option>)}</SelectInput>
          </Field>
          <Button variant="primary" icon={TrendingUp} loading={busy} disabled={!capability} onClick={() => void evaluate()}>Evaluate</Button>
        </div>
        {error && <div className="mt-3"><ErrorBlock message={error} /></div>}
        {capability && <div className="mt-4 border-t border-line pt-4"><CapabilityTable capability={capability} /></div>}
        <div className="mt-4 border-t border-line pt-4"><StateLegend /></div>
      </Card>

      {capabilities.loading && <div className="mt-4"><LoadingBlock /></div>}
      {!evaluation && !busy && capability && <p className="mt-4 text-sm text-ink-2">Evaluate to see each scenario's observed evidence and availability. Every evaluation is recorded in the case audit trail.</p>}
      {evaluation && (
        <>
          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <ScenarioPanel scenario={evaluation.scenarios.A} evaluation={evaluation} layers={layers} shared={shared} />
            <ScenarioPanel scenario={evaluation.scenarios.B} evaluation={evaluation} layers={layers} shared={shared} />
          </div>
          <Card title="Treatment versus no-treatment effect" eyebrow="Causal estimand" className="mt-4" actions={<StatusBadge status={evaluation.treatment_effect.status} />}>
            <div className="flex flex-wrap gap-1">{evaluation.treatment_effect.reason_codes.map((code) => <Badge key={code} tone="unavailable">{code}</Badge>)}</div>
            <p className="mt-2 text-sm leading-6 text-ink-2">A patient-specific treatment effect needs a target-trial specification and a validated causal method (for example inverse probability weighting or doubly robust estimation with balance, positivity and sensitivity diagnostics). None is defined, so no effect is estimated and no treatment is recommended.</p>
            <div className="mt-3">
              <Table headers={["Target-trial component", "Specification"]} dense>
                {(capabilities.data?.target_trial_fields ?? []).map((field) => (
                  <tr key={field.id}><td className="text-ink">{field.label}</td><td><StatusBadge status="NOT_DEFINED" label="Not defined" /></td></tr>
                ))}
              </Table>
            </div>
            <p className="mt-3 text-xs text-ink-3">Guideline information: {evaluation.guideline_information.reason}</p>
          </Card>
        </>
      )}
      {(history.data ?? []).length > 0 && (
        <Card title="Evaluation history" eyebrow="Persisted requests" className="mt-4" padded={false}>
          <Table headers={["#", "System", "Treatment", "Horizon", "Outcome", "Requested"]} dense>
            {history.data!.map((row) => (
              <tr key={row.id}><td className="tabular">{row.id}</td><td>{humanize(row.organ_system)}</td><td className="text-xs text-ink-2">{row.intervention_id ?? "—"}</td><td className="tabular">{row.horizon_days} d</td><td><StatusBadge status={row.status} /></td><td className="text-xs text-ink-2">{formatDate(row.created_at, true)}</td></tr>
            ))}
          </Table>
        </Card>
      )}
    </>
  );
}
