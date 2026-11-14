import { useState } from "react";
import { Button, ErrorBlock, SelectInput, StatusBadge, TextInput } from "./ui";
import { api, type TabularContract, type TabularResult } from "../services/api";
import { errorMessage, humanize } from "../lib/format";

/** Typed values for a tabular research model, checked against its development envelope. Nothing is stored. */
export default function TabularModelForm({ modelId }: { modelId: string }) {
  const [contract, setContract] = useState<TabularContract | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [result, setResult] = useState<TabularResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function open() {
    setBusy(true);
    setError(null);
    try {
      setContract(await api.getTabularContract(modelId));
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }

  async function run() {
    if (!contract) return;
    setBusy(true);
    setError(null);
    setResult(null);
    const payload: Record<string, number | string | null> = {};
    for (const field of contract.fields) {
      const raw = (values[field.name] ?? "").trim();
      payload[field.name] = raw === "" ? null : field.type === "number" ? Number(raw) : raw;
    }
    try {
      setResult(await api.runTabularModel(modelId, payload));
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }

  if (!contract) {
    return (
      <div className="mt-3">
        <Button size="sm" variant="secondary" loading={busy} onClick={() => void open()}>Enter values (research)</Button>
        {error && <div className="mt-2"><ErrorBlock message={error} /></div>}
      </div>
    );
  }
  return (
    <div className="mt-3 rounded-lg border border-line p-3">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-xs font-medium text-ink">Enter values · {contract.target}</p>
        <StatusBadge status="RESEARCH_ONLY_UNVALIDATED" label="Research only · not stored" />
      </div>
      <p className="mt-1 text-[11px] leading-4 text-ink-3">Units {contract.units}. {contract.rules.join("; ")}.</p>
      {!contract.runnable ? (
        <p className="mt-2 text-xs text-ink-2">This model is exploratory only: it showed no skill over the prevalence baseline on its held-out test, so it does not run on new values.</p>
      ) : (
        <>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            {contract.fields.map((field) => (
              <label key={field.name} className="block text-[11px] text-ink-2">
                {humanize(field.name)}{field.may_be_blank ? " (optional)" : ""}
                {field.type === "number" && field.allowed_values ? (
                  <SelectInput aria-label={field.name} value={values[field.name] ?? ""} onChange={(event) => setValues({ ...values, [field.name]: event.target.value })}>
                    <option value="">{field.may_be_blank ? "Blank" : "Choose"}</option>
                    {field.allowed_values.map((code) => <option key={code} value={String(code)}>{code}</option>)}
                  </SelectInput>
                ) : field.type === "number" ? (
                  <TextInput aria-label={field.name} inputMode="decimal" value={values[field.name] ?? ""} placeholder={`${field.min} to ${field.max}`}
                    onChange={(event) => setValues({ ...values, [field.name]: event.target.value })} />
                ) : (
                  <SelectInput aria-label={field.name} value={values[field.name] ?? ""} onChange={(event) => setValues({ ...values, [field.name]: event.target.value })}>
                    <option value="">{field.may_be_blank ? "Blank" : "Choose"}</option>
                    {(field.categories ?? []).map((category) => <option key={category} value={category}>{category}</option>)}
                  </SelectInput>
                )}
              </label>
            ))}
          </div>
          <Button className="mt-3" size="sm" loading={busy} onClick={() => void run()}>Run model</Button>
        </>
      )}
      {error && <div className="mt-2"><ErrorBlock message={error} /></div>}
      {result && (
        <div className="mt-3 space-y-1 text-xs text-ink-2">
          <p className="text-sm text-ink">
            Research probability <span className="tabular font-semibold">{result.probability.toFixed(3)}</span>; {result.at_or_above_threshold ? "at or above" : "below"} the
            threshold {result.threshold.toFixed(3)}.
          </p>
          {result.imputed_fields.length > 0 && <p>Imputed (left blank): {result.imputed_fields.map(humanize).join(", ")}.</p>}
          <p className="text-[11px] leading-4 text-ink-3">{result.probability_semantics} Threshold: {result.threshold_rule}. Checkpoint {result.checkpoint_sha256.slice(0, 12)}…. Not a diagnosis; not stored.</p>
        </div>
      )}
    </div>
  );
}
