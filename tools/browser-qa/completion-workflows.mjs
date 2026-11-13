// Focused local commercial-profile UI verification; no model execution or source uploads.
import { chromium } from "playwright-core";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import path from "node:path";

const root = process.cwd();
const read = (file) => JSON.parse(readFileSync(file, "utf8").replace(/^\uFEFF/, ""));
const stack = read(path.join(root, ".cache/review-20261113/stack.json"));
if (stack.mode !== "qa") throw new Error("Isolated QA stack required");
const credentials = read(stack.credentials_file);
const out = path.join(root, "artifacts/completion-2026-11-13/browser");
mkdirSync(out, { recursive: true });
const clean = (value) => [credentials.username, credentials.password].filter(Boolean).reduce((s, secret) => s.split(secret).join("[REDACTED]"), String(value));
const report = { schema_version: "medtwin.completion-browser-workflows.v1", started_at: new Date().toISOString(),
  scope: "Existing isolated fictional/public QA cases. Actual UI and saved source rendering only; no inference, uploads, clinical edits or publication.",
  checks: [], page_errors: [], http_errors: [], blocked_inference_requests: [] };
report.qa_adjustments = ["Precision–recall selector accepts punctuation after Precision; initial selector required a space.", "Root confirmed historical GI raster fixture is case 3/run 3; case 5 is document-only.", "Literal node-ID plus label selector replaces an overescaped regular expression in the QA harness."];
const browser = await chromium.launch({ channel: "msedge", headless: true, args: ["--use-angle=d3d11"] });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
page.setDefaultTimeout(35000);
page.on("pageerror", (error) => report.page_errors.push(clean(error)));
page.on("response", (response) => {
  if (response.url().includes("/api/v1/") && response.status() >= 400) report.http_errors.push({ path: new URL(response.url()).pathname, status: response.status() });
});
await context.route("**/api/v1/**", async (route) => {
  const request = route.request();
  const pathname = new URL(request.url()).pathname;
  if (request.method() === "POST" && /(?:inference|\/infer(?:\/|$)|\/analy[sz]e(?:\/|$)|\/jobs(?:\/|$))/.test(pathname)) {
    report.blocked_inference_requests.push({ method: request.method(), path: pathname });
    return route.abort("blockedbyclient");
  }
  return route.continue();
});
const persist = () => {
  report.server_errors = report.http_errors.filter((entry) => entry.status >= 500);
  const content = JSON.stringify(report, null, 2);
  writeFileSync(path.join(out, "workflows.json"), content);
  writeFileSync(path.join(out, "proof.json"), content);
};
const check = (condition, message) => { if (!condition) throw new Error(message); };
const responseFor = (suffix) => {
  const pending = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith(suffix) && response.status() === 200);
  pending.catch(() => {}); // A failed earlier UI action must not leave an unhandled event timer.
  return pending;
};
async function step(name, action) {
  const started = Date.now();
  try { report.checks.push({ name, status: "PASSED", details: await action(), seconds: (Date.now() - started) / 1000 }); }
  catch (error) { report.checks.push({ name, status: "FAILED", error: clean(error), seconds: (Date.now() - started) / 1000 }); }
  persist();
}
async function selectCase(caseId) {
  await page.evaluate((id) => localStorage.setItem("medtwin.selectedCase", String(id)), caseId);
  const pending = responseFor(`/cases/${caseId}/evidence-graph`);
  await page.goto(stack.web_url + "/universal");
  const response = await pending;
  await page.getByRole("button", { name: "Export evidence snapshot", exact: true }).waitFor({ state: "visible" });
  await page.waitForFunction(() => Array.from(document.querySelectorAll("button")).some((b) => b.textContent === "Export evidence snapshot" && !b.disabled));
  return response.json();
}

try {
  await page.goto(stack.web_url + "/account");
  await page.locator("#account-identifier").fill(credentials.username);
  await page.locator("#account-secret").fill(credentials.password);
  await page.getByRole("button", { name: "Open account", exact: true }).click();
  await page.getByRole("button", { name: "Sign out", exact: true }).waitFor();

  await step("Official ICD classification notice", async () => {
    await selectCase(11);
    const title = page.getByText(/^Official classification reference: ICD-10-CM /);
    await title.waitFor();
    const banner = title.locator("..");
    await page.getByText("98,403 source entries indexed", { exact: true }).waitFor();
    const text = await banner.innerText();
    check(/98,403/.test(text), "Official entry count missing");
    check(/reference|diagnos|validat|eligib/i.test(text), "Classification scope notice missing");
    await banner.screenshot({ path: path.join(out, "official-icd-notice.png") });
    return { text: clean(text) };
  });

  await step("Case 11 chronological UI backtest", async () => {
    const pending = responseFor("/cases/11/research/backtest");
    await page.getByRole("tab", { name: "Time & comparison", exact: true }).click();
    const response = await pending;
    const payload = await response.json();
    await page.getByText("Same 5 chronological targets", { exact: true }).waitFor();
    check(payload.matched_comparison?.n === 5, "Actual API did not supply five matched targets");
    check(payload.never_writes === true, "Backtest response lost read-only guarantee");
    check(payload.status === "CHRONOLOGICAL_BASELINES_EVALUATED", "Chronological gate did not pass for reviewed synthetic fixture");
    const panel = page.locator("#workspace-panel-history");
    await panel.screenshot({ path: path.join(out, "case11-chronological-backtest.png") });
    return { case_id: 11, status: payload.status, targets: payload.matched_comparison.n,
      persistence_mae: payload.matched_comparison.persistence_mae, linear_mae: payload.matched_comparison.linear_mae,
      read_only: payload.never_writes, visible_caption: "Same 5 chronological targets" };
  });

  await step("PTB Arena curves, bytes and patient-cluster interval", async () => {
    await page.goto(stack.web_url + "/arena");
    await page.getByLabel("Baseline model", { exact: true }).selectOption("ptbxl_ecg_baseline");
    await page.getByLabel("Candidate model", { exact: true }).selectOption("ptbxl_ecg_demographic_fusion");
    const comparisonPending = responseFor("/universal/arena/compare");
    await page.getByRole("button", { name: "Check comparability", exact: true }).click();
    const comparison = await (await comparisonPending).json();
    const paired = comparison.paired_statistics;
    check(paired?.status === "COMPUTED_PAIRED_PATIENT_BOOTSTRAP", "Actual paired computation unavailable");
    check(paired.conclusion === "NO_DIFFERENCE_SHOWN" && paired.ci95[0] < 0 && paired.ci95[1] > 0, "Patient interval/conclusion inconsistent");
    const cluster = page.getByRole("heading", { name: "Patient-cluster paired comparison", exact: true }).locator("xpath=ancestor::section[1]");
    await cluster.getByText(/"conclusion": "NO_DIFFERENCE_SHOWN"/).waitFor();
    await cluster.screenshot({ path: path.join(out, "arena-patient-cluster-comparison.png") });
    const diagnostics = [];
    for (const modelId of ["ptbxl_ecg_baseline", "ptbxl_ecg_demographic_fusion"]) {
      const side = modelId === "ptbxl_ecg_baseline" ? "Baseline model" : "Candidate model";
      const label = (await page.getByLabel(side, { exact: true }).locator("option:checked").textContent()).trim();
      const card = page.getByRole("heading", { name: label, exact: true }).locator("xpath=ancestor::section[1]");
      const pending = responseFor(`/universal/arena/models/${modelId}/diagnostics`);
      await card.getByRole("button", { name: "Show computed diagnostics", exact: true }).click();
      const payload = await (await pending).json();
      await page.getByLabel(`Diagnostic class for ${modelId}`, { exact: true }).waitFor();
      check(payload.status === "COMPUTED_FROM_SAVED_PREDICTIONS", `Diagnostics blocked for ${modelId}`);
      await card.getByText(`Prediction bytes SHA-256 ${payload.prediction_sha256}`, { exact: true }).waitFor();
      for (const prefix of ["ROC", "Precision", "Reliability"]) {
        const chart = card.getByRole("img", { name: new RegExp(`^${prefix}.*actual saved predictions$`) });
        await chart.waitFor();
        check(await chart.locator("path.recharts-line-curve").count() === 1, `Actual ${prefix} plot has no rendered line`);
      }
      if (payload.paired_arms) {
        await card.getByText("Same-run ECG-only versus fusion", { exact: true }).waitFor();
        const interval = payload.paired_arms.ci95;
        await card.getByText(`Patient-cluster delta ${payload.paired_arms.right_minus_left.toFixed(6)}; 95% interval ${interval.map((n) => n.toFixed(6)).join(" to ")}.`, { exact: true }).waitFor();
        check(payload.paired_arms.conclusion === "NO_DIFFERENCE_SHOWN", "Same-run fusion incorrectly implies improvement");
      }
      await card.screenshot({ path: path.join(out, `arena-${modelId}.png`) });
      diagnostics.push({ model_id: modelId, status: payload.status, n: payload.n, patient_count: payload.patient_count,
        probability_prefix: payload.probability_prefix, prediction_sha256: payload.prediction_sha256,
        rendered_curves: ["ROC", "PR", "reliability"], same_run_conclusion: payload.paired_arms?.conclusion ?? null });
    }
    return { comparison_status: comparison.status, paired_statistics: paired, diagnostics };
  });

  await step("Case 3 saved raster source and exact overlay", async () => {
    const graph = await selectCase(3);
    const imageIds = new Set(graph.nodes.filter((n) => n.kind === "upload" && n.details.modality === "IMAGE").map((n) => n.source_file_id));
    const finding = graph.nodes.find((n) => n.kind === "finding" && imageIds.has(n.source_file_id) && n.details.model_provenance?.source === "MODEL_INFERENCE");
    check(finding, "No saved image-model finding available in QA case 3");
    const target = page.locator('[aria-label="Case evidence observations"]').getByRole("button").filter({ hasText: finding.id }).filter({ hasText: finding.label });
    report.raster_selection_debug = { graph_case_id: graph.case_id, node_id: finding.id, finding_id: finding.finding_id,
      upload_id: finding.source_file_id, observation_buttons: await page.locator('[aria-label="Case evidence observations"]').getByRole("button").count(),
      matching_buttons: await target.count() }; persist();
    const pending = responseFor(`/uploads/${finding.source_file_id}/research-inference`);
    await target.click();
    const runs = await (await pending).json();
    const run = runs.runs.find((item) => item.finding_id === finding.finding_id);
    check(run?.research_output?.type === "segmentation", "Selected saved QA finding does not have its expected segmentation output");
    const output = run.research_output;
    const image = page.getByRole("img", { name: `Original medical image upload ${finding.source_file_id}`, exact: true });
    await image.waitFor();
    await image.evaluate((element) => element.complete && element.naturalWidth > 0 ? true : new Promise((resolve, reject) => { element.onload = resolve; element.onerror = reject; }));
    const overlay = page.getByRole("img", { name: "Selected finding source-coordinate model overlay", exact: true });
    await overlay.waitFor();
    const size = await image.evaluate((element) => [element.naturalWidth, element.naturalHeight]);
    check(JSON.stringify(size) === JSON.stringify(output.image_size), "Original image / prediction grid mismatch");
    check(await overlay.getAttribute("viewBox") === `0 0 ${size[0]} ${size[1]}`, "SVG overlay viewBox misaligned");
    const href = await overlay.locator("image").getAttribute("href");
    check(href?.startsWith("data:image/png;base64,"), "Rendered mask image missing");
    writeFileSync(path.join(out, "case3-overlay-rendered.png"), Buffer.from(href.split(",")[1], "base64"));
    writeFileSync(path.join(out, "case3-overlay-reference.json"), JSON.stringify({ image_size: output.image_size, segments: output.segments.map((s) => ({ rle: s.rle })) }));
    const python = `import json,sys\nfrom pathlib import Path\nimport numpy as np\nfrom PIL import Image\nfrom pycocotools import mask as coco\np=Path(sys.argv[1])\nr=json.loads((p/'case3-overlay-reference.json').read_text())\na=np.asarray(Image.open(p/'case3-overlay-rendered.png').convert('RGBA'))[:,:,3]>0\ne=np.zeros((r['image_size'][1],r['image_size'][0]),dtype=bool)\nfor s in r['segments']:\n d=dict(s['rle']);d['counts']=d['counts'].encode('ascii');e |= coco.decode(d).astype(bool)\nassert a.shape==e.shape\nprint(json.dumps({'shape':list(a.shape),'mask_differing_pixels':int(np.count_nonzero(a!=e)),'foreground_pixels':int(e.sum()),'reference_decoder':'pycocotools independent COCO decoder','criterion':0}))`;
    const exact = JSON.parse(execFileSync(path.join(root, ".venv/Scripts/python.exe"), ["-c", python, out], { encoding: "utf8", timeout: 20000 }));
    check(exact.mask_differing_pixels === 0, "Rendered source mask differs from independent COCO reference");
    const toggle = page.getByLabel("Show original model overlay", { exact: true });
    await toggle.uncheck(); check(await overlay.count() === 0, "Overlay toggle failed to hide layer"); await toggle.check(); await overlay.waitFor();
    const slider = page.getByRole("slider", { name: "Selected finding overlay opacity", exact: true });
    const before = await slider.inputValue(); await slider.focus(); await slider.press("ArrowLeft"); await slider.press("ArrowLeft");
    const after = await slider.inputValue(); check(Number(after) < Number(before), "Overlay opacity control did not respond to keyboard");
    const card = page.getByRole("heading", { name: "Selected source & review trail", exact: true }).locator("xpath=ancestor::section[1]");
    await card.screenshot({ path: path.join(out, "case3-original-source-overlay.png") });
    return { case_id: 3, finding_id: finding.finding_id, source_id: finding.source_file_id, saved_run_id: run.id, original_size: size,
      viewBox: await overlay.getAttribute("viewBox"), independent_mask_comparison: exact, overlay_toggle: true, opacity_before: before, opacity_after: after,
      new_inference: false };
  });

  await step("Optional anatomy scope remains generic", async () => {
    await page.getByRole("button", { name: "Show linked reference anatomy", exact: true }).click();
    await page.getByText("L1 generic reference; atlas coordinates do not establish patient-specific localization.", { exact: true }).waitFor();
    const generic = page.getByRole("group", { name: "Generic source-associated anatomy reference", exact: true });
    const unavailable = page.getByText(/^No dedicated commercially reusable standalone asset/);
    await generic.or(unavailable).first().waitFor();
    const available = await generic.count() === 1;
    return { available, generic_scope_notice: true, patient_geometry_claimed: false,
      canvas_count: available ? await generic.locator("canvas").count() : 0 };
  });

  await step("Mobile timeline remains usable", async () => {
    await page.setViewportSize({ width: 390, height: 844 });
    await selectCase(11);
    await page.getByRole("tab", { name: "Time & comparison", exact: true }).click();
    await page.getByText("Same 5 chronological targets", { exact: true }).waitFor();
    const layout = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth }));
    check(layout.document <= layout.viewport + 1, "Mobile timeline causes horizontal document overflow");
    await page.locator("#workspace-panel-history").screenshot({ path: path.join(out, "mobile-case11-backtest.png") });
    return { width: 390, layout, visible_target_count: 5 };
  });
  report.status = report.checks.every((item) => item.status === "PASSED") && !report.page_errors.length && !report.blocked_inference_requests.length ? "VERIFIED_FOCUSED_UI_WORKFLOWS" : "ISSUES_FOUND";
} catch (error) { report.status = "FAILED"; report.failure = clean(error); }
finally {
  report.finished_at = new Date().toISOString(); persist();
  await Promise.race([browser.close(), new Promise((resolve) => setTimeout(resolve, 8000))]);
}
console.log(JSON.stringify({ status: report.status, passed: report.checks.filter((item) => item.status === "PASSED").length,
  failed: report.checks.filter((item) => item.status === "FAILED").map((item) => item.name), page_errors: report.page_errors.length,
  inference_requests: report.blocked_inference_requests.length }));
process.exit(report.status === "VERIFIED_FOCUSED_UI_WORKFLOWS" ? 0 : 1);
