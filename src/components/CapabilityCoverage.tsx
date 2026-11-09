import { useState } from "react";
import type { ModelRegistryRecord } from "../services/api";
import { humanize } from "../lib/format";
import { Card, EmptyState, Table, TextInput } from "./ui";

type CoverageModel = ModelRegistryRecord & { supported_modalities?: string[]; inference_input?: string };

export default function CapabilityCoverage({ models }: { models: ModelRegistryRecord[] }) {
  const [query, setQuery] = useState("");
  const rows = (models as CoverageModel[]).flatMap((model) => {
    const bundle = model.artifact_bundle;
    if (model.processor_only || !bundle.checkpoint_path) return [];
    const segmentation = model.task.includes("segmentation");
    return model.supported_classes.filter((label) => label !== "background").map((label) => ({
      organ: segmentation && model.anatomy === "multi_system" ? humanize(label) : humanize(model.anatomy),
      test: (model.supported_modalities ?? []).join(", ") || model.supported_inputs.join(", "),
      target: `${segmentation ? "Anatomical / lesion mask" : "Label"}: ${humanize(label)}`,
      task: humanize(model.task),
      model: model.display_name,
      model_id: model.model_id,
      checkpoint_sha256: String(bundle.checkpoint_sha256 ?? "Not declared"),
      preprocessing: String(bundle.preprocessing_version ?? "Not declared"),
      dataset_licence: String(bundle.dataset_license ?? "Not declared; review required"),
      research: model.inference_input === "tabular_survival" ? "Evaluation only; no upload adapter"
        : model.research_gate?.allowed ? "Research artifact gate passed"
        : model.inference_route ? "Dedicated research adapter; separate input gates"
        : "Research artifact gate blocked",
      clinical: model.activation.eligible ? "Registry gate passed; clinical approval not established" : "Not clinically activated",
      evaluation: String(bundle.evaluation_report_path ?? "No report registered"),
      limitations: model.limitations.join(" "),
    }));
  });
  const needle = query.trim().toLowerCase();
  const shown = rows.filter((row) => [row.organ, row.test, row.target, row.model, row.model_id, row.task]
    .some((value) => value.toLowerCase().includes(needle)));

  function downloadCsv() {
    const fields = ["organ", "test", "target", "task", "model", "model_id", "checkpoint_sha256", "preprocessing", "dataset_licence", "research", "clinical", "evaluation", "limitations"] as const;
    // Quoting does not prevent spreadsheet formulas in source-controlled labels.
    const cell = (value: string) => `"${(/^[=+@\-\t\r\n]/.test(value) ? `'${value}` : value).replace(/"/g, '""')}"`;
    const csv = [fields.join(","), ...shown.map((row) => fields.map((field) => cell(row[field])).join(","))].join("\r\n");
    const url = URL.createObjectURL(new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "medtwin-capability-coverage.csv";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return (
    <Card title="Organ, test and target coverage" eyebrow="Declared model targets and immutable checkpoint versions">
      <p className="text-sm leading-6 text-ink-2">
        These are registered research targets. Labels can describe anatomy, landmarks or normal findings.
        An anatomical mask does not establish disease detection, and a passed artifact gate does not establish clinical accuracy.
        Targets absent from this list have no declared checkpoint-backed coverage here.
      </p>
      <div className="my-4 flex flex-wrap items-center gap-3">
        <TextInput aria-label="Filter capability coverage" placeholder="Search organ, test, finding or model" value={query}
          onChange={(event) => setQuery(event.target.value)} className="min-w-64 flex-1" />
        <span className="text-xs text-ink-2">{shown.length} of {rows.length} targets</span>
        <button type="button" onClick={downloadCsv} disabled={shown.length === 0}
          className="rounded-lg border border-line px-3 py-2 text-xs font-medium text-ink hover:bg-surface-2 disabled:opacity-50">
          Export filtered CSV
        </button>
      </div>
      {shown.length === 0 ? <EmptyState title="No registered target matches" detail="This search does not establish that the application can assess the requested condition." /> : (
        <Table headers={["Organ / system", "Test", "Specific target", "Model / version", "Use and validation"]} dense>
          {shown.map((row, index) => (
            <tr key={`${row.model_id}-${index}`}>
              <td>{row.organ}</td>
              <td>{row.test}</td>
              <td><p>{row.target}</p><p className="mt-1 text-xs text-ink-2">{row.task}</p></td>
              <td><p>{row.model}</p><p className="mt-1 font-mono text-xs text-ink-2" title={row.checkpoint_sha256}>
                SHA-256 {row.checkpoint_sha256.slice(0, 16)}{row.checkpoint_sha256.length === 64 ? "…" : ""}
              </p><p className="mt-1 text-xs text-ink-2">{row.preprocessing}</p></td>
              <td><p className="text-xs">{row.research}</p><p className="mt-1 text-xs text-ink-2">{row.clinical}</p></td>
            </tr>
          ))}
        </Table>
      )}
      <p className="mt-3 text-xs leading-5 text-ink-2">The CSV includes full checkpoint hashes, preprocessing versions, declared dataset licences, evaluation report references and model limitations. Free research access does not establish permission for commercial use. Check the model card for acquisition and patient-population restrictions.</p>
    </Card>
  );
}
