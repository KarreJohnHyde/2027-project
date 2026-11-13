// Actual authenticated reference hierarchy checks; no model inference or writes.
import { chromium } from "playwright-core";
import { createRequire } from "node:module";
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
const require = createRequire(import.meta.url);
const root = process.cwd();
const read = (p) => JSON.parse(readFileSync(p, "utf8").replace(/^\uFEFF/, ""));
const stack = read(path.join(root, ".cache/review-20261113/stack.json"));
if (stack.mode !== "qa") throw new Error("Isolated QA required");
const credentials = read(stack.credentials_file);
const redact = (error) => [credentials.username, credentials.password].reduce((text, value) => text.split(value).join("[REDACTED]"), String(error));
const output = path.join(root, "artifacts/expansion-2026-11-13/catalogue/browser-proof.json");
const report = { started_at: new Date().toISOString(), scope: "Actual source hierarchy/API/accessibility software controls; no new model inference or clinical validation", checks: [], accessibility: [], errors: [] };
const browser = await chromium.launch({ channel: "msedge", headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage(); page.setDefaultTimeout(45000);
page.on("pageerror", (error) => report.errors.push(redact(error)));
const check = (name, ok, extra = {}) => { report.checks.push({ name, passed: Boolean(ok), ...extra }); writeFileSync(output, JSON.stringify(report, null, 2)); if (!ok) throw new Error(name); };
try {
  check("Reference hierarchy rejects unauthenticated access", (await context.request.get(stack.web_url + "/api/v1/universal/structures/systems")).status() === 401);
  await page.goto(stack.web_url + "/account"); await page.locator("#account-identifier").fill(credentials.username); await page.locator("#account-secret").fill(credentials.password);
  await page.getByRole("button", { name: "Open account", exact: true }).click(); await page.getByRole("button", { name: "Sign out", exact: true }).waitFor();
  const systems = await (await context.request.get(stack.web_url + "/api/v1/universal/structures/systems")).json();
  check("Actual API exposes all25 families and4907 source nodes", systems.systems.length === 25 && systems.node_count === 4907, { families: systems.systems.length, nodes: systems.node_count });
  const left = await (await context.request.get(stack.web_url + "/api/v1/universal/structures/atlas%3Aregions.eyelashes_l/detail")).json();
  check("Source laterality and explicit parent remain separate from system context", left.node.laterality === "left" && left.node.laterality_source === "atlas.side" && left.node.parent_id === "atlas:regions.hairs" && left.node.parent_relation === "SOURCE_EXPLICIT_PARENT");
  check("Unknown per-chunk commercial rights stay uncleared", left.assets.every((asset) => asset.commercial_use_declared === false));
  check("WHO native reference/crosswalk limits remain explicit", systems.icd11.available === false && systems.icd11.crosswalk_mapping_available === false && systems.icd11.local_icd10cm_is_icd11 === false);
  await page.evaluate(() => localStorage.setItem("medtwin.selectedCase", "13")); await page.goto(stack.web_url + "/universal");
  await page.getByRole("button", { name: "Browse source anatomy hierarchy", exact: true }).click();
  const heading = page.getByRole("heading", { name: "Whole-body structures & capability hierarchy", exact: true }); await heading.waitFor();
  const card = heading.locator("xpath=ancestor::section[1]");
  const selector = card.getByLabel("Structure hierarchy system", { exact: true });
  await selector.locator("option").nth(25).waitFor({ state: "attached" });
  check("Whole-body selector includes25 source contexts", await selector.locator("option").count() === 26);
  await selector.selectOption("systemic");
  const search = card.getByLabel("Search structure hierarchy", { exact: true }); await search.fill("eyelashes");
  const leftButton = card.getByRole("button").filter({ hasText: "Eyelashes (left)" }); await leftButton.waitFor(); await leftButton.click();
  await card.getByText(/Parent relation: SOURCE_EXPLICIT_PARENT/).waitFor();
  check("Live source selection retains exact side and relation detail", await card.getByText(/Laterality: left/).count() === 1);
  await search.fill("hairs"); const children = card.getByRole("button", { name: "Browse children of Hairs", exact: true }); await children.waitFor(); await children.click();
  await card.getByRole("button", { name: "Back", exact: true }).waitFor(); await card.getByRole("button").filter({ hasText: "Eyelashes (left)" }).waitFor();
  check("Explicit source children can be browsed and returned", true);
  await card.getByRole("button", { name: "Back", exact: true }).click();
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
    await page.evaluate(() => document.fonts.ready); await page.addScriptTag({ path: require.resolve("axe-core/axe.min.js") });
    const audit = await card.evaluate(async (element) => window.axe.run(element, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] } }));
    const layout = await page.evaluate(() => ({ width: innerWidth, document: document.documentElement.scrollWidth }));
    report.accessibility.push({ width, violations: audit.violations.map((v) => ({ id: v.id, impact: v.impact, targets: v.nodes.map((n) => n.target) })), incomplete: audit.incomplete.map((v) => ({ id: v.id, nodes: v.nodes.length })), layout });
    check("Hierarchy has no automated accessibility violations", audit.violations.length === 0, { width });
    check("Expanded hierarchy stays within viewport", layout.document <= layout.width + 1, { width, layout });
  }
  check("No browser exceptions", report.errors.length === 0);
  report.status = "VERIFIED_DECLARED_SOFTWARE_SCOPE";
} catch (error) { report.status = "FAILED"; report.failure = redact(error); }
finally { report.finished_at = new Date().toISOString(); writeFileSync(output, JSON.stringify(report, null, 2)); await browser.close(); }
console.log(JSON.stringify({ status: report.status, checks: report.checks.filter((c) => c.passed).length, failure: report.failure }));
process.exit(report.status.startsWith("VERIFIED") ? 0 : 1);
