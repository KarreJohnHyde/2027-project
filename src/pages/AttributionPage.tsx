import { Card, EmptyState, ErrorBlock, LoadingBlock, PageHeader, Table } from "../components/ui";
import { assetUrl, loadManifest } from "../anatomy/data";
import { datasetName } from "../lib/displayNames";
import { useAsync } from "../lib/useAsync";
import { useWorkspace } from "../state/workspace";

// The one place where original source names, creators and licence terms appear:
// attribution licences (for example CC BY) require them wherever the work is shared.

const external = (url: string | null | undefined) =>
  url && /^https?:\/\//.test(url) ? <a className="break-all text-accent-text hover:underline" href={url} target="_blank" rel="noreferrer">{url}</a> : (url ?? "—");

function DatasetSources() {
  const audit = useWorkspace((state) => state.datasetTaskAudit);
  if (!audit) return <EmptyState title="Dataset audit unavailable" detail="The task-level dataset audit could not be loaded." />;
  // Only datasets whose terms (or an explicit owner authorization) allow use are credited here;
  // the others are catalogued and excluded from training.
  const used = audit.datasets.filter((dataset) => dataset.license?.status === "VERIFIED" || (dataset.license as { authorization_status?: string } | undefined)?.authorization_status === "VERIFIED");
  return (
    <Card title="Datasets" eyebrow={`${used.length} sources with verified terms or recorded authorization`} padded={false}>
      <Table headers={["Name in MedTwin", "Original source", "Licence or terms", "Citation and source"]} dense>
        {used.map((dataset) => {
          const license = dataset.license as { name?: string; source?: string; citation?: string } | undefined;
          return (
            <tr key={dataset.id}>
              <td className="min-w-48 font-medium text-ink">{datasetName(dataset.id)}</td>
              <td className="min-w-48 text-xs text-ink-2">{dataset.title}</td>
              <td className="min-w-56 text-xs text-ink-2">{license?.name ?? "—"}</td>
              <td className="min-w-64 text-xs text-ink-2">
                {license?.citation && <p>{license.citation}</p>}
                <p className="mt-0.5">{license?.source?.split(" ").map((part, index) => <span key={index}>{index > 0 && " "}{external(part)}</span>)}</p>
              </td>
            </tr>
          );
        })}
      </Table>
    </Card>
  );
}

function AnatomySources() {
  const manifest = useAsync(() => loadManifest(), []);
  if (!manifest.data) return manifest.error ? <ErrorBlock message={manifest.error} /> : <LoadingBlock label="Reading the anatomy manifest" />;
  const variants = Object.values(manifest.data.variants);
  return (
    <Card title="Anatomy assets" eyebrow={`${variants.length} reference models`} padded={false}>
      <Table headers={["Name in MedTwin", "Original title", "Creator", "Licence", "Source"]} dense>
        {variants.map((variant) => (
          <tr key={variant.id}>
            <td className="min-w-48 font-medium text-ink">{variant.label}</td>
            <td className="min-w-48 text-xs text-ink-2">{variant.source.title ?? "—"}</td>
            <td className="min-w-32 text-xs text-ink-2">{variant.source.author ?? "—"}</td>
            <td className="min-w-40 text-xs text-ink-2">{variant.source.license_text ?? variant.license.id}</td>
            <td className="min-w-48 text-xs text-ink-2">{external(variant.source.source_url)}</td>
          </tr>
        ))}
      </Table>
      {manifest.data.atlas_attribution_url && (
        <p className="border-t border-line px-4 py-3 text-xs text-ink-2">
          Structure-labelled atlas layers: full credits in the <a className="text-accent-text hover:underline" href={assetUrl(manifest.data.atlas_attribution_url)} target="_blank" rel="noreferrer">atlas attribution file</a>.
        </p>
      )}
    </Card>
  );
}

export default function AttributionPage() {
  return (
    <>
      <PageHeader
        eyebrow="Settings"
        title="Data sources and licences"
        description="MedTwin shows datasets, models and anatomy assets under medical names. The original names, creators, licence terms and citations that attribution requires are listed here. Model and checkpoint identifiers keep internal names."
      />
      <div className="space-y-4">
        <DatasetSources />
        <AnatomySources />
      </div>
    </>
  );
}
