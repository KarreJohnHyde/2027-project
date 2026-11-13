// Selected persisted research workflow checks against an existing isolated QA stack.
// Reads local credentials without exporting them. No uploads, inference or model changes.
// node tools/browser-qa/review-workflows.mjs [--state .cache/review-20261113]
//   [--evidence artifacts/review-2026-11-13/workflows] [--out artifacts/review-2026-11-13/selected-browser]
import { chromium } from "playwright-core";
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const args = Object.fromEntries(Array.from({ length: Math.floor((process.argv.length - 2) / 2) }, (_, i) => [process.argv[2 + 2 * i].replace(/^--/, ""), process.argv[3 + 2 * i]]));
const resolve = (value) => path.resolve(root, value);
const readJson = (file) => JSON.parse(readFileSync(file, "utf8").replace(/^\uFEFF/, ""));
const stateDir = resolve(args.state ?? ".cache/review-20261113");
const evidenceDir = resolve(args.evidence ?? "artifacts/review-2026-11-13/workflows");
const outDir = resolve(args.out ?? "artifacts/review-2026-11-13/selected-browser");
mkdirSync(outDir, { recursive: true });
const stack = readJson(path.join(stateDir, "stack.json"));
if (stack.mode !== "qa") throw new Error("This script only accepts an isolated QA stack.");
const credentials = readJson(stack.credentials_file);
const evidence = readJson(path.join(evidenceDir, "image-evidence.json"));
const workflows = readJson(path.join(evidenceDir, "workflow-results.json"));
const documentEvidence = readJson(path.join(evidenceDir, "document-evidence.json"));
if (documentEvidence.case.id !== workflows.workflows.document.case_id) throw new Error("Document workflow artifacts disagree on the selected case.");
const imageCase = evidence.case.id;
const uploadId = evidence.upload.id;
const runId = evidence.run.id;
if (imageCase !== workflows.workflows.imaging.case_id || runId !== workflows.workflows.imaging.run_id) throw new Error("Workflow artifacts disagree on the selected imaging run.");
const hash = (value) => createHash("sha256").update(value).digest("hex");
const result = {
  schema_version: "medtwin-selected-browser-workflow-v1", started_at: new Date().toISOString(),
  git_commit: execFileSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).trim(),
  script_sha256: hash(readFileSync(fileURLToPath(import.meta.url))),
  scope: "Actual UI checks of an existing isolated public-research image case; no new inference or clinical evaluation.",
  selected: { case_id: imageCase, upload_id: uploadId, run_id: runId, model_id: evidence.run.model_name },
  document_selected: { case_id: documentEvidence.case.id, upload_ids: documentEvidence.uploads.map((upload) => upload.id),
    scope: "Two synthetic PDF controls; no independently human-annotated real-report accuracy claim." },
  checks: [], page_errors: [], console_errors: [], server_errors: [], limitations: [
    "Verifies one persisted public-research image and its UI export, not general diagnostic accuracy.",
    "L1 reference anatomy is checked as labelled generic geometry; no patient-specific registration is implied.",
    "The reference mask is the dataset publisher annotation, distinct from model output and reviewer confirmation.",
  ],
};
const assert = (name, passed, details = {}) => {
  result.checks.push({ name, passed: Boolean(passed), ...details });
  if (!passed) throw new Error(name);
};
// These expectations come from the printed panels in the two SYNTHETIC controls,
// independently of the extractor's current specimen/method fields. They are not
// claimed to be independently annotated real-report ground truth.
const syntheticBloodAnalytes = new Set(["hemoglobin", "white_blood_cell_count", "platelet_count"]);
const expectedSyntheticSpecimen = (name) => syntheticBloodAnalytes.has(name) ? "Whole blood (EDTA)" : "Serum";
const normalizedContext = (value) => String(value).toLowerCase().replace(/\s+/g, "");
const browser = await chromium.launch({ channel: "msedge", headless: true, args: ["--use-angle=d3d11", "--enable-gpu-rasterization", "--ignore-gpu-blocklist"] });
result.browser = `Microsoft Edge ${browser.version()} (playwright-core)`;
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1, acceptDownloads: true });
const page = await context.newPage();
page.setDefaultTimeout(30000);
page.on("pageerror", (error) => result.page_errors.push(String(error).slice(0, 500)));
page.on("console", (message) => { if (message.type() === "error") result.console_errors.push(message.text().slice(0, 500)); });
page.on("response", (response) => { if (response.status() >= 500) result.server_errors.push({ url: response.url(), status: response.status() }); });
let stage = "login";
const screenshot = async (name) => {
  const file = path.join(outDir, name);
  await page.screenshot({ path: file, fullPage: false });
  return path.relative(root, file).replaceAll("\\", "/");
};
async function overlayState() {
  await page.locator('svg[aria-label="Research model overlay"] image').waitFor({ state: "attached" });
  return page.locator('svg[aria-label="Research model overlay"]').evaluate((overlay) => {
    const original = overlay.parentElement.querySelector("img");
    const a = overlay.getBoundingClientRect();
    const b = original.getBoundingClientRect();
    return {
      view_box: overlay.getAttribute("viewBox"), overlay_images: overlay.querySelectorAll("image").length,
      image_natural_size: [original.naturalWidth, original.naturalHeight],
      alignment_max_css_px: Math.max(Math.abs(a.x - b.x), Math.abs(a.y - b.y), Math.abs(a.width - b.width), Math.abs(a.height - b.height)),
      layer_sha256_input: [...overlay.querySelectorAll("image")].map((image) => image.getAttribute("href")).join("|"),
    };
  });
}
async function downloadCurrentReport(filename) {
  const button = page.getByRole("button", { name: "Export JSON", exact: true });
  await button.waitFor();
  await page.waitForFunction(() => [...document.querySelectorAll("button")].some((item) => item.textContent.trim() === "Export JSON" && !item.disabled));
  const downloading = page.waitForEvent("download");
  await button.click();
  const download = await downloading;
  const saved = path.join(outDir, filename);
  await download.saveAs(saved);
  const bytes = readFileSync(saved);
  const digest = hash(bytes);
  await page.getByText(digest, { exact: true }).waitFor();
  if (!download.suggestedFilename().includes(digest.slice(0, 8))) throw new Error("Document UI download filename/hash mismatch");
  return { payload: JSON.parse(bytes.toString("utf8")), sha256: digest, file: path.relative(root, saved).replaceAll("\\", "/"),
    suggested_filename: download.suggestedFilename() };
}
try {
  await page.goto(`${stack.web_url}/account`, { timeout: 90000 });
  await page.locator("#account-identifier").fill(credentials.username);
  await page.locator("#account-secret").fill(credentials.password);
  await page.getByRole("button", { name: "Open account", exact: true }).click();
  await page.getByRole("button", { name: "Sign out", exact: true }).waitFor();
  assert("QA registered account authenticated through UI", true);
  await page.evaluate((id) => localStorage.setItem("medtwin.selectedCase", String(id)), imageCase);

  stage = "persisted imaging overlay";
  await page.goto(`${stack.web_url}/imaging?upload=${uploadId}`, { waitUntil: "domcontentloaded" });
  await page.getByLabel("Imaging upload", { exact: true }).selectOption(String(uploadId));
  await page.getByLabel("Stored research run", { exact: true }).selectOption(String(runId));
  await page.getByLabel("Reference annotation", { exact: true }).selectOption(String(evidence.reference.id));
  await page.getByRole("radiogroup", { name: "Overlay layer", exact: true }).waitFor();
  const model = await overlayState();
  const modelLayerHash = hash(model.layer_sha256_input);
  delete model.layer_sha256_input;
  const expectedViewBox = `0 0 ${evidence.run.research_output.image_size[0]} ${evidence.run.research_output.image_size[1]}`;
  assert("Persisted real model mask overlays selected original upload", model.view_box === expectedViewBox && model.overlay_images > 0 && model.alignment_max_css_px <= 1,
    { ...model, layer_sha256: modelLayerHash });
  const reviewText = await page.getByLabel("Stored research run", { exact: true }).locator("option:checked").textContent();
  assert("Stored run visibly retains reviewer confirmation", /confirmed/i.test(reviewText), { option_text: reviewText });
  await page.locator('svg[aria-label="Research model overlay"]').scrollIntoViewIfNeeded();
  result.model_screenshot = await screenshot("01-persisted-model-overlay.png");

  stage = "reference annotation layer";
  await page.getByRole("radiogroup", { name: "Overlay layer", exact: true }).getByRole("radio", { name: "Reference", exact: true }).click();
  const reference = await overlayState();
  const referenceHash = hash(reference.layer_sha256_input);
  delete reference.layer_sha256_input;
  assert("Independent publisher reference is selectable and differs from model layer", referenceHash !== modelLayerHash && reference.view_box === expectedViewBox,
    { ...reference, layer_sha256: referenceHash, reference_id: evidence.reference.id, source: evidence.reference.source });
  result.reference_screenshot = await screenshot("02-publisher-reference-overlay.png");

  stage = "reload persistence";
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByLabel("Stored research run", { exact: true }).waitFor();
  const restored = await overlayState();
  const restoredHash = hash(restored.layer_sha256_input);
  delete restored.layer_sha256_input;
  assert("Reload restores same selected upload/run and actual model mask", await page.getByLabel("Imaging upload").inputValue() === String(uploadId)
    && await page.getByLabel("Stored research run").inputValue() === String(runId) && restoredHash === modelLayerHash, { ...restored, layer_sha256: restoredHash });
  result.reload_screenshot = await screenshot("03-reloaded-mask.png");

  stage = "actual report download";
  await page.goto(`${stack.web_url}/reports`, { waitUntil: "domcontentloaded" });
  const exportButton = page.getByRole("button", { name: "Export JSON", exact: true });
  await exportButton.waitFor();
  await page.waitForFunction(() => [...document.querySelectorAll("button")].some((button) => button.textContent.trim() === "Export JSON" && !button.disabled));
  const downloading = page.waitForEvent("download");
  await exportButton.click();
  const download = await downloading;
  const saved = path.join(outDir, "imaging-ui-export.json");
  await download.saveAs(saved);
  const downloadedBytes = readFileSync(saved);
  const payload = JSON.parse(downloadedBytes.toString("utf8"));
  const downloadHash = hash(downloadedBytes);
  await page.getByText(downloadHash, { exact: true }).waitFor();
  const findingId = evidence.run.findings?.[0]?.id ?? evidence.run.finding_id;
  const relatedFindings = payload.original_findings.filter((finding) => finding.id === findingId);
  const relevantProvenance = JSON.stringify({ findings: relatedFindings, provenance: payload.provenance });
  const reviewEvents = payload.provenance.filter((event) => JSON.stringify(event).includes("CONFIRMED") && (String(event.resource_id) === String(findingId) || JSON.stringify(event.details ?? {}).includes(`"finding_id":${findingId}`)));
  assert("UI download hash matches displayed SHA-256 and filename", download.suggestedFilename().includes(downloadHash.slice(0, 8)),
    { downloaded_file: path.relative(root, saved).replaceAll("\\", "/"), sha256: downloadHash, suggested_filename: download.suggestedFilename() });
  assert("UI export is bound to selected case and original upload hash", payload.case.id === imageCase
    && payload.uploads.some((upload) => upload.id === uploadId && upload.file_hash === evidence.source_sha256), { schema: payload.schema_version, case_id: payload.case.id });
  assert("UI export retains selected model/checkpoint provenance", relatedFindings.length > 0
    && relevantProvenance.includes(evidence.run.model_name) && relevantProvenance.includes(evidence.run.research_provenance.checkpoint_sha256),
    { finding_id: findingId, model_id: evidence.run.model_name, checkpoint_sha256: evidence.run.research_provenance.checkpoint_sha256 });
  assert("UI export retains confirmed reviewer audit event", reviewEvents.length > 0, { review_event_count: reviewEvents.length });
  assert("UI export carries research-only limitations", /research/i.test(payload.research_notice) && /not a diagnosis/i.test(payload.research_notice));
  await page.getByText(downloadHash, { exact: true }).scrollIntoViewIfNeeded();
  result.export_screenshot = await screenshot("04-ui-export-hash.png");

  stage = "generic anatomy label";
  await page.goto(`${stack.web_url}/anatomy-studio`, { waitUntil: "domcontentloaded" });
  await page.getByText(/L1 generic reference anatomy.*not patient-specific/i).waitFor({ timeout: 60000 });
  assert("Anatomy visibly labels L1 generic reference and no patient-specific claim", true);
  result.anatomy_screenshot = await screenshot("05-l1-generic-anatomy.png");

  stage = "synthetic document values in actual UI";
  await page.evaluate((id) => localStorage.setItem("medtwin.selectedCase", String(id)), documentEvidence.case.id);
  await page.goto(`${stack.web_url}/documents`, { waitUntil: "domcontentloaded" });
  const valueChecks = [];
  const specimenUiChecks = [];
  for (const upload of documentEvidence.uploads) {
    await page.getByLabel("Report", { exact: true }).selectOption(String(upload.id));
    const table = page.locator("table").filter({ has: page.getByRole("columnheader", { name: "Measurement", exact: true }) });
    await table.locator("tbody tr").first().waitFor();
    const rows = await table.locator("tbody tr").evaluateAll((items) => items.map((item) => {
      const cells = [...item.querySelectorAll("td")].map((cell) => cell.textContent.trim());
      return { name: cells[0], value: cells[1], source: cells[6] };
    }));
    const expected = documentEvidence.measurements.filter((measurement) => measurement.source_file_id === upload.id);
    const matched = expected.filter((measurement) => rows.some((row) => row.name.includes(measurement.name)
      && Number(row.value.match(/[-+]?\d+(?:\.\d+)?/)?.[0]) === measurement.value
      && row.source.replace(/\s+/g, " ").includes(measurement.source_span.replace(/\s+/g, " "))));
    valueChecks.push({ upload_id: upload.id, expected: expected.length, displayed_rows: rows.length, matched_values_and_source_spans: matched.length });
    for (const measurement of expected) {
      const row = rows.find((candidate) => candidate.name.includes(measurement.name));
      const expectedSpecimen = expectedSyntheticSpecimen(measurement.name);
      specimenUiChecks.push({ upload_id: upload.id, name: measurement.name, expected_specimen: expectedSpecimen,
        passed: Boolean(row && normalizedContext(row.name).includes(normalizedContext(`Specimen: ${expectedSpecimen}`))) });
    }
  }
  assert("Both document UI tables show all 18 synthetic values with source spans", valueChecks.length === 2
    && valueChecks.every((item) => item.expected === 9 && item.displayed_rows === 9 && item.matched_values_and_source_spans === 9), { reports: valueChecks });
  assert("Document UI associates all 18 specimens with their printed synthetic panels", specimenUiChecks.length === 18 && specimenUiChecks.every((item) => item.passed),
    { expected_whole_blood_edta: 6, expected_serum: 12, controls: specimenUiChecks });
  await page.getByRole("heading", { name: "Measurements", exact: true }).scrollIntoViewIfNeeded();
  result.document_values_screenshot = await screenshot("06-document-values-and-sources.png");

  stage = "scanned document source-page boxes";
  const scanned = documentEvidence.uploads.find((upload) => documentEvidence.measurements.some((measurement) => measurement.source_file_id === upload.id && measurement.source_bbox));
  if (!scanned) throw new Error("No scanned source boxes exist in the selected synthetic control.");
  await page.goto(`${stack.web_url}/documents/verify?upload=${scanned.id}`, { waitUntil: "domcontentloaded" });
  await page.getByLabel("Report", { exact: true }).selectOption(String(scanned.id));
  const sourceOverlay = page.locator('svg[aria-label="Extracted items on this page"]');
  await sourceOverlay.locator("rect").first().waitFor();
  const sourceView = await sourceOverlay.evaluate((overlay) => {
    const source = overlay.parentElement.querySelector("img");
    return { box_count: overlay.querySelectorAll("rect").length, view_box: overlay.getAttribute("viewBox"),
      source_page_size: [source.naturalWidth, source.naturalHeight], source_image_loaded: source.complete && source.naturalWidth > 0 };
  });
  assert("Scanned synthetic report displays original page and extracted source boxes", sourceView.source_image_loaded
    && sourceView.box_count >= 9 && await page.getByLabel("Page", { exact: true }).inputValue() === "1", { upload_id: scanned.id, ...sourceView });
  result.document_source_screenshot = await screenshot("07-scanned-page-source-boxes.png");

  stage = "document biomarkers and descriptive deltas";
  await page.goto(`${stack.web_url}/biomarkers`, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "Documented measurements over time", exact: true }).waitFor();
  await page.getByRole("button", { name: "Show data table", exact: true }).first().waitFor();
  const chartCount = await page.getByRole("button", { name: "Show data table", exact: true }).count();
  const deltaLabels = await page.getByText("Absolute change (Δx)", { exact: true }).count();
  assert("Biomarker UI displays nine source-linked series and numeric delta panels", chartCount === 9 && deltaLabels === 9,
    { series_charts: chartCount, numeric_delta_panels: deltaLabels, scope: "Descriptive changes on two synthetic dates; not forecasts." });
  await page.getByRole("button", { name: "Show data table", exact: true }).first().click();
  const firstSeries = page.locator("figure").first();
  assert("Biomarker data table retains both dated upload sources", (await firstSeries.innerText()).includes(`upload #${documentEvidence.uploads[0].id}`)
    && (await firstSeries.innerText()).includes(`upload #${documentEvidence.uploads[1].id}`));
  result.document_biomarkers_screenshot = await screenshot("08-source-linked-biomarker-deltas.png");

  stage = "actual document report UI export";
  await page.goto(`${stack.web_url}/reports`, { waitUntil: "domcontentloaded" });
  const documentExport = await downloadCurrentReport("document-ui-export.json");
  const documentPayload = documentExport.payload;
  const exportedMatches = documentEvidence.measurements.filter((expected) => documentPayload.measurements.some((measurement) => measurement.id === expected.id
    && measurement.name === expected.name && measurement.value === expected.value && measurement.unit === expected.unit
    && measurement.source_file_id === expected.source_file_id && measurement.source_span === expected.source_span));
  assert("Actual document UI export contains all 18 measured values/source associations", documentPayload.case.id === documentEvidence.case.id
    && documentPayload.measurements.length === 18 && exportedMatches.length === 18,
    { case_id: documentPayload.case.id, measurement_count: documentPayload.measurements.length, matched: exportedMatches.length });
  const exportedContextChecks = documentPayload.measurements.map((measurement) => ({ id: measurement.id, upload_id: measurement.source_file_id,
    name: measurement.name, expected_specimen: expectedSyntheticSpecimen(measurement.name), observed_specimen: measurement.specimen,
    expected_method: "SYNTHETIC", observed_method: measurement.laboratory_method,
    passed: normalizedContext(measurement.specimen) === normalizedContext(expectedSyntheticSpecimen(measurement.name)) && measurement.laboratory_method === "SYNTHETIC" }));
  assert("Document UI export preserves all 18 source-correct specimens and printed laboratory methods", exportedContextChecks.length === 18
    && exportedContextChecks.every((item) => item.passed), { controls: exportedContextChecks, reference_scope: "Printed synthetic panel headers; not independent real-report gold." });
  assert("Document UI export preserves original source hashes, dates, pages and nine OCR boxes", documentEvidence.uploads.every((expected) => documentPayload.uploads.some((upload) => upload.id === expected.id && upload.file_hash === expected.file_hash))
    && documentPayload.measurements.every((measurement) => measurement.source_page === 1 && measurement.documented_date)
    && documentPayload.measurements.filter((measurement) => Array.isArray(measurement.source_bbox) && measurement.source_bbox.length === 4).length === 9);
  const documentReviewEvents = documentPayload.provenance.filter((event) => event.action === "HUMAN_REVIEW_SUBMITTED" && event.details?.decision === "CONFIRMED" && event.details.original_output_preserved === true);
  assert("Document UI export preserves review decisions and correction metadata", documentReviewEvents.length >= 2
    && documentPayload.correction_review.measurements.length === 18 && /research/i.test(documentPayload.research_notice), { confirmed_review_events: documentReviewEvents.length });
  assert("Document UI export preserves nine dated series and numeric changes", documentPayload.biomarker_trends.length === 9
    && documentPayload.biomarker_trends.every((series) => series.points.length === 2 && Number.isFinite(series.analysis.absolute_change)));
  assert("Document UI downloaded SHA matches displayed hash and filename", true, { ...documentExport, payload: undefined });
  await page.getByText(documentExport.sha256, { exact: true }).scrollIntoViewIfNeeded();
  result.document_export_screenshot = await screenshot("09-document-ui-export-hash.png");

  stage = "document reload and UI re-export";
  await page.reload({ waitUntil: "domcontentloaded" });
  const reloadedExport = await downloadCurrentReport("document-ui-export-after-reload.json");
  const stableMeasurements = (payload) => payload.measurements.map(({ id, name, value, unit, source_file_id, source_span, source_page, source_bbox, documented_date, specimen, laboratory_method }) =>
    ({ id, name, value, unit, source_file_id, source_span, source_page, source_bbox, documented_date, specimen, laboratory_method })).sort((left, right) => left.id - right.id);
  assert("Reload and actual UI re-export preserve document evidence", reloadedExport.payload.case.id === documentEvidence.case.id
    && JSON.stringify(stableMeasurements(reloadedExport.payload)) === JSON.stringify(stableMeasurements(documentPayload)),
    { case_id: reloadedExport.payload.case.id, stable_measurements: reloadedExport.payload.measurements.length,
      reloaded_export_sha256: reloadedExport.sha256, byte_hash_equality_required: false, reason: "Export and evidence-load timestamps legitimately change." });
  result.document_reload_screenshot = await screenshot("10-document-reload-export.png");
  assert("No browser page exceptions or server errors", result.page_errors.length === 0 && result.server_errors.length === 0,
    { page_error_count: result.page_errors.length, server_error_count: result.server_errors.length, console_error_count: result.console_errors.length });
  result.status = "VERIFIED";
} catch (error) {
  result.status = "FAILED";
  result.failure = { stage, message: String(error.message ?? error).slice(0, 1000) };
  if (stage !== "login") result.failure_screenshot = await screenshot("failure.png").catch(() => null);
} finally {
  result.finished_at = new Date().toISOString();
  // Persist observations before native WebGL/browser shutdown, which can stall
  // on a busy Windows GPU. Cleanup is bounded and never hides measured failures.
  writeFileSync(path.join(outDir, "selected-workflows.json"), `${JSON.stringify(result, null, 2)}\n`);
  let closeTimer;
  result.browser_close_completed = await Promise.race([
    browser.close().then(() => true, () => false),
    new Promise((done) => { closeTimer = setTimeout(() => done(false), 10000); }),
  ]);
  clearTimeout(closeTimer);
  if (!result.browser_close_completed) result.limitations.push("Native browser shutdown exceeded 10 seconds; measured checks were saved before bounded cleanup.");
  writeFileSync(path.join(outDir, "selected-workflows.json"), `${JSON.stringify(result, null, 2)}\n`);
  console.log(JSON.stringify({ status: result.status, checks_passed: result.checks.filter((check) => check.passed).length,
    checks_total: result.checks.length, failure: result.failure ?? null, report: path.join(outDir, "selected-workflows.json") }));
}
process.exit(result.status === "VERIFIED" ? 0 : 1);
