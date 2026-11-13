import { chromium } from "playwright-core";
import { createRequire } from "node:module";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
const require = createRequire(import.meta.url);
const read = (p) => JSON.parse(readFileSync(p, "utf8").replace(/^\uFEFF/, ""));
const root = process.cwd();
const stack = read(path.join(root, ".cache/review-20261113/stack.json"));
if (stack.mode !== "qa") throw new Error("Isolated QA stack required");
const credential = read(stack.credentials_file);
const out = path.join(root, "artifacts/expansion-2026-11-13/control-room"); mkdirSync(out, { recursive: true });
const report = { scope: "Isolated fictional/public stored sources; no new model execution, corrections or clinical activation", checks: [], page_errors: [], server_errors: [], accessibility: [] };
const browser = await chromium.launch({ channel: "msedge", headless: true, args: ["--use-angle=d3d11"] });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage(); page.setDefaultTimeout(40000);
page.on("pageerror", (e) => report.page_errors.push(String(e).slice(0, 300)));
page.on("response", (r) => { if (r.status() >= 500 && r.url().includes("/api/v1/")) report.server_errors.push({ path: new URL(r.url()).pathname, status: r.status() }); });
const save = () => writeFileSync(path.join(out, "proof.json"), JSON.stringify(report, null, 2));
function check(name, passed, details = {}) { report.checks.push({ name, passed: !!passed, ...details }); save(); if (!passed) throw new Error(name); }
async function selectCase(id) {
  await page.evaluate((n) => localStorage.setItem("medtwin.selectedCase", String(n)), id);
  await page.goto(stack.web_url + "/universal");
  await page.getByRole("button", { name: "Export evidence snapshot", exact: true }).waitFor();
  await page.waitForFunction(() => [...document.querySelectorAll("button")].some((b) => b.textContent === "Export evidence snapshot" && !b.disabled));
  return page.evaluate(async (n) => (await fetch(`/api/v1/cases/${n}/evidence-graph`, { headers: { "X-MedTwin-Client": "web" } })).json(), id);
}
const escape = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
try {
  await page.goto(stack.web_url + "/account"); await page.locator("#account-identifier").fill(credential.username); await page.locator("#account-secret").fill(credential.password); await page.getByRole("button", { name: "Open account", exact: true }).click(); await page.getByRole("button", { name: "Sign out", exact: true }).waitFor();
  const gi = await selectCase(3);
  check("Unified Twin Control Room is the default selected workspace", await page.getByRole("tab", { name: "Twin Control Room", exact: true }).getAttribute("aria-selected") === "true");
  const finding = gi.nodes.find((n) => n.kind === "finding" && n.details?.model_provenance?.source === "MODEL_INFERENCE");
  if (!finding) throw new Error("Required existing historical GI fixture missing");
  await page.getByRole("button", { name: new RegExp(escape(finding.id)) }).first().click();
  await page.getByRole("img", { name: `Original medical image upload ${finding.source_file_id}`, exact: true }).waitFor();
  await page.getByRole("img", { name: "Selected finding source-coordinate model overlay", exact: true }).waitFor();
  await page.getByRole("heading", { name: "Trust & refusal center", exact: true }).waitFor();
  const trust = page.locator("section").filter({ has: page.getByRole("heading", { name: "Trust & refusal center", exact: true }) }).last();
  check("One selection pins original raster, saved finding overlay and model identity", (await page.getByRole("tabpanel", { name: "Twin Control Room", exact: true }).innerText()).includes(`upload #${finding.source_file_id}`) && (await trust.innerText()).includes(finding.details.model_provenance.model_id), { finding_id: finding.finding_id, source_id: finding.source_file_id });
  await trust.getByText("Checkpoint and source identities", { exact: true }).click();
  check("Trust context exposes actual source/checkpoint identities", (await trust.innerText()).includes(finding.details.source_file_sha256) && (await trust.innerText()).includes(finding.details.model_provenance.checkpoint_sha256));
  await page.getByRole("tab", { name: "Evidence & sources", exact: true }).focus(); await page.keyboard.press("ArrowRight");
  check("Keyboard navigation preserves linked selection between views", await page.getByRole("tab", { name: "Spatial imaging", exact: true }).getAttribute("aria-selected") === "true");
  const brain = await selectCase(7);
  const volumeFinding = brain.nodes.find((n) => n.kind === "finding" && n.details?.model_provenance?.source === "MODEL_INFERENCE");
  await page.getByRole("button", { name: new RegExp(escape(volumeFinding.id)) }).first().click();
  await page.getByLabel("Fourth-axis interpretation", { exact: true }).waitFor();
  check("Linked volumetric finding embeds source workstation and requires explicit 4D semantics", await page.getByLabel("Fourth-axis interpretation", { exact: true }).inputValue() === "");
  await page.getByLabel("Fourth-axis interpretation", { exact: true }).selectOption("channel"); await page.getByLabel("Fourth-axis frame index", { exact: true }).fill("0");
  await page.getByLabel("Plane geometry", { exact: true }).waitFor();
  await page.waitForFunction(() => document.querySelectorAll("canvas").length > 0);
  check("Selected volume renders source-coordinate 2D/3D in unified workspace", await page.getByLabel("Spatial source upload", { exact: true }).inputValue() === String(volumeFinding.source_file_id) && await page.locator("canvas").count() > 0);
  await page.screenshot({ path: path.join(out, "linked-volume.png"), fullPage: true });
  const chronological = await selectCase(11);
  await page.getByText("Same 5 chronological targets", { exact: true }).waitFor();
  check("Observed historical backtest remains in the unified view", await page.getByRole("tab", { name: "Twin Control Room", exact: true }).getAttribute("aria-selected") === "true");
  const measurement = chronological.nodes.find((n) => n.kind === "measurement" && n.examination_id && n.details.documented_date);
  await page.getByRole("button", { name: new RegExp(escape(measurement.id)) }).first().click();
  const selectedContext = await page.getByRole("tabpanel", { name: "Twin Control Room", exact: true }).innerText();
  check("Clinical time context uses documented examination date rather than processing time", selectedContext.includes(measurement.details.documented_date) && selectedContext.includes(`examination #${measurement.examination_id}`));
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
    await page.addScriptTag({ path: require.resolve("axe-core/axe.min.js") });
    const axe = await page.evaluate(async () => window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] } }));
    const layout = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth }));
    report.accessibility.push({ width, layout, violations: axe.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => ({ target: n.target, summary: n.failureSummary })) })), incomplete: axe.incomplete.map((v) => ({ id: v.id, count: v.nodes.length })) });
    check("Unified view automated accessibility and viewport checks", axe.violations.length === 0 && layout.document <= layout.viewport + 1, { width });
  }
  report.status = report.page_errors.length || report.server_errors.length ? "FAILED" : "VERIFIED_UNIFIED_CONTROL_ROOM";
} catch (e) { report.status = "FAILED"; report.failure = String(e); }
finally { save(); await browser.close(); }
console.log(JSON.stringify({ status: report.status, checks: report.checks.length, failure: report.failure })); process.exit(report.status === "VERIFIED_UNIFIED_CONTROL_ROOM" ? 0 : 1);
