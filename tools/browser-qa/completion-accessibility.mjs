// Local axe-core audit of fictional/public sources; no cloud uploads or paid services.
import { chromium } from "playwright-core";
import { createRequire } from "node:module";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
const require = createRequire(import.meta.url);
const root = process.cwd();
const read = (file) => JSON.parse(readFileSync(file, "utf8").replace(/^\uFEFF/, ""));
const stack = read(path.join(root, ".cache/review-20261113/stack.json"));
if (stack.mode !== "qa") throw new Error("An isolated QA stack is required");
const credentials = read(stack.credentials_file);
const out = path.join(root, "artifacts/completion-2026-11-13/accessibility"); mkdirSync(out, { recursive: true });
const report = { schema_version: "medtwin.accessibility.v1", started_at: new Date().toISOString(), tool: "axe-core 4.14.0 MPL-2.0", scope: "Automated WCAG2/2.1/2.2 AA checks plus keyboard and viewport controls, not a complete manual conformance certification", pages: [], errors: [] };
const browser = await chromium.launch({ channel: "msedge", headless: true, args: ["--use-angle=d3d11"] });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage(); page.setDefaultTimeout(45000);
page.on("pageerror", (e) => report.errors.push(String(e).slice(0, 500)));
try {
  await page.goto(`${stack.web_url}/account`); await page.locator("#account-identifier").fill(credentials.username); await page.locator("#account-secret").fill(credentials.password); await page.getByRole("button", { name: "Open account", exact: true }).click(); await page.getByRole("button", { name: "Sign out", exact: true }).waitFor();
  await page.evaluate(() => localStorage.setItem("medtwin.selectedCase", "5"));
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
    for (const route of ["/universal", "/arena", "/upload", "/history"]) {
      await page.goto(stack.web_url + route); await page.locator("h1").waitFor();
      if (route === "/universal") { await page.getByRole("button", { name: "Export evidence snapshot", exact: true }).waitFor(); await page.waitForFunction(() => !document.querySelector('button[disabled]')?.textContent?.includes("Export evidence snapshot")); }
      if (route === "/arena") await page.getByLabel("Baseline model", { exact: true }).waitFor();
      await page.addScriptTag({ path: require.resolve("axe-core/axe.min.js") });
      const result = await page.evaluate(async () => await window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] } }));
      const layout = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth }));
      report.pages.push({ route, width, layout, pass_count: result.passes.length, violations: result.violations.map((v) => ({ id: v.id, impact: v.impact, help: v.help, helpUrl: v.helpUrl, nodes: v.nodes.map((n) => ({ target: n.target, summary: n.failureSummary })) })), incomplete: result.incomplete.map((v) => ({ id: v.id, nodes: v.nodes.length })) });
      if (route === "/universal") {
        const first = page.getByRole("tab", { name: "Evidence & sources", exact: true }); await first.focus(); await page.keyboard.press("ArrowRight");
        report.pages.at(-1).keyboard_tabs = await page.getByRole("tab", { name: "Spatial imaging", exact: true }).evaluate((e) => e === document.activeElement && e.getAttribute("aria-selected") === "true");
      }
      writeFileSync(path.join(out, "report.json"), JSON.stringify(report, null, 2));
    }
  }
  report.status = report.errors.length === 0 && report.pages.every((p) => !p.violations.length && p.layout.document <= p.layout.viewport + 1 && p.keyboard_tabs !== false) ? "VERIFIED_AUTOMATED_SCOPE" : "ISSUES_FOUND";
} catch (e) { report.status = "FAILED"; report.failure = String(e); }
finally { report.finished_at = new Date().toISOString(); writeFileSync(path.join(out, "report.json"), JSON.stringify(report, null, 2)); await Promise.race([browser.close(), new Promise((done) => setTimeout(done, 10000))]); }
console.log(JSON.stringify({ status: report.status, pages: report.pages.length, violations: report.pages.reduce((n, p) => n + p.violations.length, 0), failure: report.failure })); process.exit(report.status === "VERIFIED_AUTOMATED_SCOPE" ? 0 : 1);
