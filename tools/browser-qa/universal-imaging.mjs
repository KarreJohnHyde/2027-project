// Verifies an existing isolated QA source; no upload, inference or review mutation.
import { chromium } from "playwright-core";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
const root = process.cwd();
const read = (file) => JSON.parse(readFileSync(file, "utf8").replace(/^\uFEFF/, ""));
const stack = read(path.join(root, ".cache/review-20261113/stack.json"));
if (stack.mode !== "qa") throw new Error("Isolated QA stack required");
const credentials = read(stack.credentials_file);
const proof = read(path.join(root, "artifacts/universal-2026-11-13/imaging-native-proof/proof.json"));
const out = path.join(root, "artifacts/universal-2026-11-13/imaging-browser"); mkdirSync(out, { recursive: true });
const results = { source: { case_id: proof.case_id, upload_id: proof.upload_id }, checks: [], page_errors: [], server_errors: [] };
const browser = await chromium.launch({ channel: "msedge", headless: true, args: ["--use-angle=d3d11", "--enable-gpu-rasterization", "--ignore-gpu-blocklist"] });
const context = await browser.newContext({ viewport: { width: 1500, height: 1100 } });
const page = await context.newPage(); page.setDefaultTimeout(30000);
page.on("pageerror", (err) => results.page_errors.push(String(err)));
page.on("response", (r) => { if (r.status() >= 500) results.server_errors.push({ status: r.status(), path: new URL(r.url()).pathname }); });
const check = (name, value) => { results.checks.push({ name, passed: Boolean(value) }); if (!value) throw new Error(name); };
try {
  await page.goto(stack.web_url + "/account");
  await page.locator("#account-identifier").fill(credentials.username);
  await page.locator("#account-secret").fill(credentials.password);
  await page.getByRole("button", { name: "Open account", exact: true }).click();
  await page.getByRole("button", { name: "Sign out", exact: true }).waitFor();
  await page.evaluate((id) => localStorage.setItem("medtwin.selectedCase", String(id)), proof.case_id);
  await page.goto(stack.web_url + "/universal");
  await page.getByRole("tab", { name: "Spatial imaging", exact: true }).click();
  await page.getByLabel("Spatial source upload", { exact: true }).selectOption(String(proof.upload_id));
  const workbench = page.getByTestId("universal-imaging-workbench");
  await workbench.getByText("Voxel (i,j,k):", { exact: false }).waitFor();
  for (const axis of ["axial", "coronal", "sagittal"]) {
    await page.locator(`section[aria-label="${axis} index plane"] svg image`).first().waitFor({ state: "attached" });
    check(axis + " real source PNG displayed", await page.locator(`section[aria-label="${axis} index plane"] svg image`).first().getAttribute("href").then((value) => value.startsWith("blob:")));
  }
  check("3D canvas mounted", await workbench.locator("canvas").count() >= 1);
  results.layout = await page.evaluate(() => ({ viewport: innerWidth, document_width: document.documentElement.scrollWidth, workbench_width: document.querySelector('[data-testid="universal-imaging-workbench"]').getBoundingClientRect().width, widest: [...document.querySelectorAll("main,aside,section,[class*=grid]")].map((element) => ({ tag: element.tagName, class: element.className, width: Math.round(element.getBoundingClientRect().width) })).filter((item) => item.width > innerWidth).slice(0, 12) }));
  check("unknown patient frame is explicit", await workbench.getByText("Patient coordinates unavailable · source grid only", { exact: true }).count() === 1);
  const slider = page.getByLabel("axial slice", { exact: true });
  await slider.fill("2");
  await workbench.getByText(/Voxel \(i,j,k\): .*2$/).waitFor();
  check("axial slider synchronizes shared source voxel", true);
  const source = page.locator('section[aria-label="axial index plane"] svg');
  await source.click({ position: { x: 150, y: 120 } });
  check("click keeps synchronized crosshairs in all three views", await workbench.locator('svg path[stroke="#fb923c"]').count() === 3);
  await workbench.getByLabel("Window centre", { exact: true }).fill("100");
  await workbench.getByLabel("Window width", { exact: true }).fill("400");
  await page.locator('section[aria-label="sagittal index plane"] svg image').first().waitFor({ state: "attached" });
  await page.getByRole("button", { name: "Reset view", exact: true }).click();
  check("reset restores automatic window", await workbench.getByLabel("Window centre", { exact: true }).inputValue() === "");
  const surface = workbench.getByLabel("Show actual mask-derived surfaces", { exact: true });
  if (await surface.count()) {
    await surface.check();
    await workbench.getByText("Physical scale is unverified in this source header.", { exact: false }).waitFor();
    await page.getByText(/Scan voxel frame \(mm\)/).waitFor();
    check("actual stored-run surface and unknown physical scale warning displayed", true);
  }
  await workbench.scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(out, "spatial-workbench.png"), fullPage: false });
  check("no uncaught page errors", results.page_errors.length === 0);
  check("no backend server errors", results.server_errors.length === 0);
} catch (err) {
  results.failure = String(err);
  await page.screenshot({ path: path.join(out, "failure.png"), fullPage: false });
  process.exitCode = 1;
} finally {
  writeFileSync(path.join(out, "proof.json"), JSON.stringify(results, null, 2));
  await browser.close();
  console.log(JSON.stringify(results));
}
