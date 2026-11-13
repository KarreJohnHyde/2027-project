// Read-only aggregate/UX proof. No private report import, model execution or uploads.
import { chromium } from "playwright-core";
import { createRequire } from "node:module";
import { createHash } from "node:crypto";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
const require = createRequire(import.meta.url);
const root = process.cwd(); const read = (file) => JSON.parse(readFileSync(file, "utf8").replace(/^\uFEFF/, ""));
const stack = read(path.join(root, ".cache/review-20261113/stack.json"));
if (stack.mode !== "qa") throw new Error("Isolated QA stack required");
const credentials = read(stack.credentials_file);
const evidenceFile = path.join(root, "docs/universal/evidence/finalization-2026-11-13.json");
const evidence = read(evidenceFile); const evidenceSha = createHash("sha256").update(readFileSync(evidenceFile)).digest("hex");
const out = path.join(root, "artifacts/finalization-2026-11-13/readiness"); mkdirSync(out, { recursive: true });
const report = { schema_version: "medtwin.readiness-proof.v1", scope: "Authenticated public engineering aggregates plus pending independent-reference state; no private source data or model inference.", checks: [], page_errors: [], server_errors: [], accessibility: [] };
const browser = await chromium.launch({ channel: "msedge", headless: true });
const context = await browser.newContext({ viewport: { width: 1500, height: 1100 } }); const page = await context.newPage(); page.setDefaultTimeout(30000);
page.on("pageerror", (error) => report.page_errors.push(String(error)));
page.on("response", (response) => { if (response.status() >= 500) report.server_errors.push({ status: response.status(), path: new URL(response.url()).pathname }); });
const assert = (name, passed) => { report.checks.push({ name, passed: Boolean(passed) }); if (!passed) throw new Error(name); };
try {
  const anonymous = await browser.newContext();
  assert("aggregate endpoint requires authentication", (await anonymous.request.get(stack.web_url+"/api/v1/universal/research/readiness")).status() === 401); await anonymous.close();
  await page.goto(stack.web_url+"/account"); await page.locator("#account-identifier").fill(credentials.username); await page.locator("#account-secret").fill(credentials.password);
  await page.getByRole("button", { name: "Open account", exact: true }).click(); await page.getByRole("button", { name: "Sign out", exact: true }).waitFor();
  const api = async (route, options) => { const response = await context.request.fetch(stack.web_url+"/api/v1"+route, { ...options, headers: { "X-MedTwin-Client": "web" } }); if (!response.ok()) throw new Error(`Aggregate QA request failed ${response.status()}`); return response.json(); };
  const readiness = await api("/universal/research/readiness");
  const metrics = Object.fromEntries(readiness.metrics.map((metric) => [metric.metric_id, metric.value]));
  assert("recorded checks match exact committed evidence rather than a fixed code constant", metrics.backend_passed === evidence.backend.passed && metrics.backend_skipped === evidence.backend.skipped);
  assert("displayed source hash matches exact served evidence file bytes", readiness.sources.find((source) => source.source_id === "committed_engineering_evidence")?.sha256 === evidenceSha);
  const registry = await api("/models"); const models = await api("/research-models");
  assert("live registry count uses complete canonical manifest", readiness.live_model_counts.registry_models === registry.model_count);
  assert("live eligibility count matches canonical research gate", readiness.live_model_counts.research_allowed === models.models.filter((model) => model.gate?.allowed).length);
  const matched = await api("/universal/research/matched-records/query", { method: "POST", data: { mode: "global", label: "NORM", limit: 1 } });
  assert("current cohort denominator and snapshot match independently requested source-bound explorer", readiness.live_matched_cohort.records === matched.cohort.records && readiness.live_matched_cohort.patients === matched.cohort.patients && readiness.live_matched_cohort.snapshot_sha256 === matched.snapshot_id);
  assert("pending independent import is not represented as zero accuracy", readiness.independent_reports.status === "PENDING_REFERENCE_IMPORT" && readiness.independent_reports.documents === null && readiness.independent_reports.metrics.length === 0 && readiness.independent_reports.sources.length === 0);
  assert("neither clinical activation nor new inference is claimed", readiness.clinical_activation === false && readiness.new_inference === false);
  assert("API contains no private paths or per-report hashes", !/source_pdf_sha256s|source_page_sha256s|raw_text|[A-Z]:\\|\\Users\\|patient_id\"/.test(JSON.stringify(readiness)));
  report.aggregate = { recorded_backend: { passed: metrics.backend_passed, skipped: metrics.backend_skipped }, committed_evidence_sha256: evidenceSha, live_model_counts: readiness.live_model_counts, current_cohort: readiness.live_matched_cohort, independent_status: readiness.independent_reports.status, current_registry_sha256: readiness.sources.find((source) => source.source_id === "current_original_model_registry")?.sha256 };
  await page.goto(stack.web_url+"/universal"); const panel = page.getByTestId("research-readiness-panel"); await panel.getByText("Pending reference import", { exact: true }).waitFor();
  await panel.getByText("Measured checks & source identities", { exact: true }).click(); await panel.getByText("Independent-report evaluation & limitations", { exact: true }).click();
  assert("measured count is visible in the application", await panel.getByText(`${new Intl.NumberFormat().format(evidence.backend.passed)} passed`, { exact: true }).count() === 1);
  assert("source identities are inspectable without a JSON dump", await panel.locator("code").filter({ hasText: evidenceSha }).count() === 1 && await panel.locator("pre").count() === 0);
  assert("full report accuracy remains pending beside explicit limitations", await panel.getByText("No independent accuracy metric is disclosed in this view.", { exact: true }).count() === 1 && await panel.getByText(/unreviewed model outputs are not independent gold/).count() === 1);
  await page.addScriptTag({ path: require.resolve("axe-core/axe.min.js") });
  for (const width of [1500, 390]) {
    await page.setViewportSize({ width, height: 1100 });
    const axe = await page.evaluate(async () => window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] } }));
    const layout = await page.evaluate(() => ({ viewport: innerWidth, document_width: document.documentElement.scrollWidth }));
    report.accessibility.push({ width, layout, passes: axe.passes.length, violations: axe.violations.map((violation) => ({ id: violation.id, impact: violation.impact, nodes: violation.nodes.map((node) => ({ target: node.target, summary: node.failureSummary })) })), incomplete: axe.incomplete.map((entry) => ({ id: entry.id, nodes: entry.nodes.length })) });
    assert(`expanded readiness has no automated WCAG A/AA violations at${width}px`, axe.violations.length === 0);
    assert(`readiness layout fits ${width}px viewport`, layout.document_width <= layout.viewport);
    await panel.scrollIntoViewIfNeeded(); await page.screenshot({ path: path.join(out, `readiness-${width}.png`), fullPage: false });
  }
  assert("no uncaught page errors", report.page_errors.length === 0); assert("no backend500 responses", report.server_errors.length === 0);
} catch (error) {
  report.failure = String(error); process.exitCode = 1; await page.screenshot({ path: path.join(out, "failure.png"), fullPage: false });
} finally { writeFileSync(path.join(out, "proof.json"), JSON.stringify(report, null, 2)); await browser.close(); console.log(JSON.stringify(report)); }
