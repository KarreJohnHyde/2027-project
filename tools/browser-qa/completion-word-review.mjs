// Live fictional-source word-review UI checks. Credentials remain local and are
// never logged; no source correction or clinical record is submitted.
import { chromium } from "playwright-core";
import { createRequire } from "node:module";
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const require = createRequire(import.meta.url);
const root = process.cwd();
const read = (file) => JSON.parse(readFileSync(file, "utf8").replace(/^\uFEFF/, ""));
const stack = read(path.join(root, ".cache/review-20261113/stack.json"));
if (stack.mode !== "qa") throw new Error("Isolated QA stack required");
const origin = new URL(stack.web_url);
if (!["localhost", "127.0.0.1"].includes(origin.hostname) || origin.port !== "8458") throw new Error("Expected isolated loopback QA8458");
const credentials = read(stack.credentials_file);
const redact = (value) => [credentials.username, credentials.password].filter(Boolean).reduce((text, secret) => text.split(secret).join("[LOCAL_CREDENTIAL_REDACTED]"), String(value));
const output = path.join(root, "artifacts/completion-2026-11-13/word-review/browser-proof.json");
const report = { schema_version: "medtwin.upright-word-browser.v1", started_at: new Date().toISOString(),
  scope: "Actual UI/API against fictional scanned PDF case13/upload30; software controls and automated accessibility only, not OCR accuracy or clinical validation",
  case_id: 13, upload_id: 30, engine: "Installed Edge through Playwright1.63; axe-core4.14",
  preserved_previous_failure: "artifacts/completion-2026-11-13/word-review/browser-proof-before-button-transition-fix.json",
  checks: [], accessibility: [], page_errors: [] };
const browser = await chromium.launch({ channel: "msedge", headless: true, args: ["--use-angle=d3d11"] });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage(); page.setDefaultTimeout(45000);
page.on("pageerror", (error) => report.page_errors.push(redact(error).slice(0, 600)));
const save = () => writeFileSync(output, JSON.stringify(report, null, 2));
const check = (name, passed, details = {}) => {
  report.checks.push({ name, passed: Boolean(passed), ...details }); save();
  if (!passed) throw new Error(name);
};

async function keyboardNumber(input, value) {
  await input.focus();
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.type(String(value));
  if (await input.inputValue() !== String(value)) throw new Error("Keyboard number entry did not update the intended field");
}

try {
  await page.goto(stack.web_url + "/account");
  await page.locator("#account-identifier").fill(credentials.username);
  await page.locator("#account-secret").fill(credentials.password);
  await page.getByRole("button", { name: "Open account", exact: true }).click();
  await page.getByRole("button", { name: "Sign out", exact: true }).waitFor();
  check("Existing QA account authenticates through actual UI", true);
  await page.evaluate(() => localStorage.setItem("medtwin.selectedCase", "13"));

  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
    await page.goto(stack.web_url + "/universal");
    await page.getByRole("heading", { name: "Case Command Center", exact: true }).waitFor();
    const observations = page.getByLabel("Case evidence observations", { exact: true });
    const source = observations.getByRole("button").filter({ hasText: "upload:30" });
    await source.waitFor(); await source.click();
    const sourceImage = page.getByRole("img", { name: "Original report page 1 for upload 30", exact: true });
    await sourceImage.waitFor();
    const naturalSize = await sourceImage.evaluate((image) => [image.naturalWidth, image.naturalHeight]);
    check("Exact fictional source preview has canonical native dimensions", naturalSize.join(",") === "910,1287", { width, natural_size: naturalSize });
    const reveal = page.getByRole("button", { name: "Select one upright word for review", exact: true });
    await reveal.click();
    check("Word crop disclosure expands for exact source", await reveal.getAttribute("aria-expanded") === "true", { width });
    const form = page.getByText("Drag tightly around one Latin-script word, or enter preview-pixel coordinates below. This preserves an explicitly upright crop; it does not apply the policy to a full page.", { exact: true }).locator("xpath=..");
    const recognize = form.getByRole("button", { name: "Recognize selected word", exact: true });
    check("Recognition is disabled before all source attestations", await recognize.isDisabled(), { width });
    const fields = ["left", "top", "right", "bottom"].map((name) => form.getByLabel("Word crop " + name, { exact: true }));
    const values = [42, 48, 160, 86];
    const keyboardOrder = [];
    await fields[0].focus();
    for (let index = 0; index < fields.length; index += 1) {
      const focused = await page.evaluate(() => document.activeElement?.getAttribute("aria-label"));
      keyboardOrder.push(focused);
      await page.keyboard.press("ControlOrMeta+A"); await page.keyboard.type(String(values[index]));
      if (index < fields.length - 1) await page.keyboard.press("Tab");
    }
    check("Numeric coordinates are entered in keyboard tab order", keyboardOrder.join("|") === ["left", "top", "right", "bottom"].map((name) => "Word crop " + name).join("|")
      && (await Promise.all(fields.map((field) => field.inputValue()))).map(Number).join(",") === values.join(","), { width, keyboard_order: keyboardOrder });
    check("A valid crop alone does not enable un-attested recognition", await recognize.isDisabled(), { width });
    const attestations = ["The word is upright", "The crop contains exactly one word", "The text uses Latin script"].map((name) => form.getByLabel(name, { exact: true }));
    await attestations[0].check();
    check("One attestation is insufficient", await recognize.isDisabled(), { width });
    await attestations[1].check();
    check("Two attestations are insufficient", await recognize.isDisabled(), { width });
    await attestations[2].check();
    check("Complete declared word context enables recognition", await recognize.isEnabled(), { width });
    const responsePromise = page.waitForResponse((response) => response.url().endsWith("/api/v1/uploads/30/ocr/upright-word") && response.request().method() === "POST");
    await recognize.click();
    const response = await responsePromise; const payload = await response.json();
    const submitted = response.request().postDataJSON();
    check("UI submits native preview coordinates and current source identity", submitted.page === 1
      && submitted.bbox_xyxy.join(",") === values.join(",") && submitted.expected_image_size.join(",") === naturalSize.join(",")
      && submitted.source_file_sha256 === payload.source?.file_sha256 && submitted.coordinate_space === "REPORT_PAGE_PREVIEW_110_DPI"
      && submitted.upright_attested === true && submitted.single_word_attested === true && submitted.latin_text_attested === true, { width });
    check("Actual engine proposes the fictional source word", response.status() === 200 && payload.status === "AVAILABLE" && payload.text_proposal === "Hemoglobin", { width, response_status: response.status(), output_status: payload.status, source_page: payload.source?.page, source_dimensions: naturalSize });
    await form.getByText("Hemoglobin", { exact: true }).waitFor();
    check("Proposal is visibly review-only without record mutation", await form.getByText("OCR proposes text for human checking. Confidence is not correctness; no extracted field or clinical record is changed.", { exact: true }).count() === 1
      && payload.review_required === true && payload.persisted_finding_or_correction === false && payload.clinical_activation === false, { width });

    await page.evaluate(() => document.fonts.ready);
    const stableButton = await recognize.evaluate(async (button) => {
      await Promise.all(button.getAnimations().filter((animation) => animation.effect?.getTiming().iterations !== Infinity).map((animation) => animation.finished.catch(() => {})));
      return { disabled: button.disabled, opacity: getComputedStyle(button).opacity, transition: getComputedStyle(button).transitionProperty,
        class_includes_transition_colors: button.classList.contains("transition-colors") };
    });
    check("Enabled recognition has stable full opacity after colour-only transition", stableButton.disabled === false && stableButton.opacity === "1" && stableButton.class_includes_transition_colors, { width, computed: stableButton });

    await page.addScriptTag({ path: require.resolve("axe-core/axe.min.js") });
    const axe = await page.evaluate(async () => window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] } }));
    const layout = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth }));
    report.accessibility.push({ width, expanded_form: true, proposal_visible: true, layout, passes: axe.passes.length,
      violations: axe.violations.map((violation) => ({ id: violation.id, impact: violation.impact, help: violation.help, helpUrl: violation.helpUrl, nodes: violation.nodes.map((node) => ({ target: node.target, summary: node.failureSummary })) })),
      incomplete: axe.incomplete.map((entry) => ({ id: entry.id, nodes: entry.nodes.length })) });
    check("Expanded form has no automated WCAG A/AA violations", axe.violations.length === 0, { width, violations: axe.violations.length });
    check("Expanded word form remains within viewport", layout.document <= layout.viewport + 1, { width, layout });

    await keyboardNumber(fields[0], 43);
    check("Changed source crop invalidates a completed proposal", await form.getByText("Hemoglobin", { exact: true }).count() === 0
      && await form.getByText("OCR proposes text for human checking. Confidence is not correctness; no extracted field or clinical record is changed.", { exact: true }).count() === 0, { width });
    await keyboardNumber(fields[0], 42);
    let release; let started;
    const gate = new Promise((resolve) => { release = resolve; });
    const fetched = new Promise((resolve) => { started = resolve; });
    const pattern = "**/api/v1/uploads/30/ocr/upright-word";
    await page.route(pattern, async (route) => { const actual = await route.fetch(); started(); await gate; await route.fulfill({ response: actual }); });
    await recognize.click(); await fetched;
    await keyboardNumber(fields[2], 161);
    release(); await page.waitForTimeout(400);
    check("Changed crop discards an older delayed actual engine response", await form.getByText("Hemoglobin", { exact: true }).count() === 0, { width });
    await page.unroute(pattern);
    await attestations[0].uncheck();
    check("Removing an attestation disables subsequent recognition", await recognize.isDisabled(), { width });
  }
  check("No browser page exceptions", report.page_errors.length === 0);
  report.status = "VERIFIED_DECLARED_SOFTWARE_AND_AUTOMATED_ACCESSIBILITY_SCOPE";
} catch (error) {
  report.status = "FAILED"; report.failure = redact(error).slice(0, 3000);
} finally {
  report.finished_at = new Date().toISOString(); save();
  await Promise.race([browser.close(), new Promise((resolve) => setTimeout(resolve, 10000))]);
}
console.log(JSON.stringify({ status: report.status, checks_passed: report.checks.filter((check) => check.passed).length,
  axe_violations: report.accessibility.reduce((total, audit) => total + audit.violations.length, 0), artifact: path.relative(root, output), failure: report.failure }));
process.exit(report.status.startsWith("VERIFIED") ? 0 : 1);
