import { useState } from "react";
import { Activity, ArrowLeft, ArrowRight, BookOpen, Download, FileText, Globe, ShieldCheck } from "lucide-react";
import { Badge, Button, Card, PageHeader, Table } from "../components/ui";
import { Link, navigate, useLocation } from "../lib/router";
import { PUBLIC_CASE_EXAMPLES, PUBLIC_EXAMPLE_NOTICE, type TeachingCase } from "../data/publicCaseExamples";

function ExampleReport({ example }: { example: TeachingCase }) {
  const [sourceId, setSourceId] = useState(example.sources[0].id);
  const source = example.sources.find((item) => item.id === sourceId) ?? example.sources[0];
  const showSource = (id: string) => {
    setSourceId(id);
    document.getElementById("teaching-source")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const references = (value: string) => <div className="mt-2 flex flex-wrap gap-2">{value.split(",").map((id) => <button key={id} type="button" onClick={() => showSource(id.trim())} className="rounded border border-line px-2 py-1 text-xs font-medium text-accent-text hover:bg-accent-soft">Read source {id.trim()}</button>)}</div>;
  const download = () => {
    const payload = { kind: "SYNTHETIC_TEACHING_CASE", notice: PUBLIC_EXAMPLE_NOTICE, diagnostic_models_run: 0, clinical_validation: "NOT_PERFORMED", ...example };
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url; anchor.download = `medtwin-teaching-${example.id}.json`; anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <div className="space-y-5" id="teaching-report">
    <Card title={`${example.name} · ${example.title}`} eyebrow="Fictional teaching case">
      <p className="text-sm leading-6 text-ink-2">{example.summary}</p>
      <div className="mt-4 flex flex-wrap items-center gap-2"><Badge tone="info">Illustrative records</Badge><Badge tone="unavailable">Clinical validation not performed</Badge><Badge tone="neutral">0 diagnostic models run</Badge></div>
      <p className="mt-3 text-xs leading-5 text-ink-3">Every source and value below is authored for this demonstration. Source links open the fictional text used to construct the explanation.</p>
      <Button className="mt-4" onClick={download}><Download size={15} /> Download teaching case</Button>
    </Card>

    <div className="grid items-start gap-5 xl:grid-cols-[1.1fr_1fr]">
      <div className="space-y-5">
        <Card title="What the reports say" eyebrow="Prepared teaching overview"><div className="space-y-5">{example.findings.map((finding) => <article key={finding.title}><h3 className="text-sm font-semibold text-ink">{finding.title}</h3><p className="mt-1 text-sm leading-6 text-ink-2">{finding.explanation}</p><p className="mt-1.5 text-xs text-ink-3">{finding.certainty}</p>{references(finding.source)}</article>)}</div></Card>
        <Card title="Differences worth checking" eyebrow="Keep uncertainty visible"><ul className="list-disc space-y-2.5 pl-5 text-sm leading-6 text-ink-2">{example.differences.map((item) => <li key={item}>{item}</li>)}</ul></Card>
      </div>
      <div className="space-y-5">
        <section id="teaching-source" className="scroll-mt-5" aria-label="Fictional source documents"><Card title="Read the source" eyebrow="Authored demonstration text">
          <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label="Source document">{example.sources.map((item) => <button key={item.id} type="button" aria-pressed={item.id === source.id} onClick={() => setSourceId(item.id)} className={`rounded-lg border px-3 py-2 text-xs ${item.id === source.id ? "border-accent-text bg-accent-soft text-accent-text" : "border-line text-ink-2 hover:bg-surface-2"}`}>{item.id} · {item.label}</button>)}</div>
          <h3 className="text-sm font-semibold text-ink">{source.label}</h3>
          <p className="mt-1 text-xs text-ink-3">{source.when} · {source.type}</p>
          <pre className="mt-4 whitespace-pre-wrap rounded-xl border border-line bg-surface-2 p-4 font-sans text-sm leading-7 text-ink-2">{source.text}</pre>
        </Card></section>
        <Card title="Timeline" eyebrow="Illustrative visits"><ol className="space-y-4">{example.timeline.map((item) => <li key={item.when} className="border-l-2 border-line pl-4"><p className="text-xs font-semibold text-accent-text">{item.when}</p><p className="mt-1 text-sm leading-6 text-ink-2">{item.event}</p></li>)}</ol></Card>
      </div>
    </div>

    {example.measurements.length > 0 && <Card title="Illustrative measurements" eyebrow="Invented values for learning" padded={false}><Table headers={["Measurement", "Value", "Visit", "How to read it", "Source"]}>{example.measurements.map((item, index) => <tr key={index}><td className="font-medium">{item.label}</td><td className="tabular whitespace-nowrap">{item.value} {item.unit}</td><td>{item.when}</td><td className="max-w-md text-xs leading-5">{item.context}</td><td>{references(item.source)}</td></tr>)}</Table></Card>}

    <Card title="Understanding and future insight" eyebrow="What more evidence could clarify"><div className="grid gap-5 md:grid-cols-2">{example.insights.map((item) => <article key={item.title}><h3 className="text-sm font-semibold text-ink">{item.title}</h3><p className="mt-1 text-sm leading-6 text-ink-2">{item.detail}</p></article>)}</div>{example.references.length > 0 && <div className="mt-5 border-t border-line pt-4"><p className="mb-2 text-xs font-semibold text-ink-2">General educational references</p>{example.references.map((item) => <a className="mb-2 block text-xs text-accent-text underline" key={item.url} href={item.url} target="_blank" rel="noreferrer">{item.title}</a>)}</div>}</Card>
    <Card title="What is available in this example" eyebrow="Organ + test + finding + model/version" padded={false}><Table headers={["Organ / test", "Question or finding", "Prepared output", "Model/version"]}>{example.capabilities.map((item, index) => <tr key={index}><td>{item.organ}<span className="mt-1 block text-xs text-ink-3">{item.test}</span></td><td className="max-w-xs text-xs leading-5">{item.target}</td><td className="max-w-xs text-xs leading-5">{item.output}</td><td className="max-w-xs text-xs leading-5">{item.model}</td></tr>)}</Table></Card>
    <div className="rounded-xl border border-line bg-surface-2 p-4 text-xs leading-6 text-ink-2"><strong className="text-ink">Learning boundary.</strong> These cases demonstrate how to read evidence, source differences and missing information. They provide no patient-specific diagnosis, treatment instructions or validated future-outcome prediction.</div>
  </div>;
}

export default function PublicExamplesPage() {
  const { search } = useLocation();
  const requested = search.get("case");
  const selected = PUBLIC_CASE_EXAMPLES.find((item) => item.id === requested) ?? PUBLIC_CASE_EXAMPLES[0];
  return <div className="min-h-screen bg-page text-ink">
    <header className="border-b border-line bg-surface"><div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-5 py-4 sm:px-8"><Link to="/" className="inline-flex items-center gap-2.5 font-semibold"><span className="grid h-9 w-9 place-items-center rounded-xl bg-accent text-accent-fg"><Activity size={20} /></span>MedTwin <span className="text-xs font-normal text-ink-3">Public examples</span></Link><Link to="/" className="inline-flex items-center gap-2 text-sm text-accent-text"><ArrowLeft size={15} /> Open workspace</Link></div></header>
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-8 sm:py-12">
      <PageHeader eyebrow="Explore without signing in" title="Three cases. A clearer view of the evidence." description="Read a report, follow its sources and see where the available information stops. Choose a teaching case to explore its prepared overview, timeline and limits." />
      <div className="mb-7 flex items-start gap-3 rounded-xl border border-line bg-surface p-4 sm:p-5"><ShieldCheck aria-hidden size={22} className="mt-0.5 shrink-0 text-accent-text" /><p className="text-sm leading-6 text-ink-2">{PUBLIC_EXAMPLE_NOTICE}</p></div>
      <div className="mb-7 grid gap-4 md:grid-cols-3" role="group" aria-label="Teaching cases">{PUBLIC_CASE_EXAMPLES.map((item) => <button key={item.id} type="button" aria-pressed={item.id === selected.id} onClick={() => navigate(`/examples?case=${item.id}`)} className={`rounded-xl border p-5 text-left transition ${item.id === selected.id ? "border-accent-text bg-accent-soft" : "border-line bg-surface hover:bg-surface-2"}`}><span className="flex items-center justify-between"><BookOpen aria-hidden size={19} className="text-accent-text" /><ArrowRight aria-hidden size={16} className="text-ink-3" /></span><span className="mt-4 block text-base font-semibold">{item.name}</span><span className="mt-1 block text-sm font-medium leading-6">{item.title}</span><span className="mt-2 block text-xs leading-5 text-ink-2">{item.theme}</span><span className="mt-4 inline-flex items-center gap-1.5 text-xs text-ink-3"><FileText aria-hidden size={12} /> {item.sources.length} fictional sources</span></button>)}</div>
      <ExampleReport key={selected.id} example={selected} />
    </main>
    <footer className="border-t border-line px-5 py-6"><div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 text-xs leading-5 text-ink-3"><span className="inline-flex items-center gap-2"><Globe size={14} /> Public teaching library · No sign-in required</span><span>MedTwin research prototype · Educational use</span></div></footer>
  </div>;
}
