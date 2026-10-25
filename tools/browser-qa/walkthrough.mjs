// MedTwin browser walkthrough against an isolated QA stack (scripts/dev.ps1 -Mode qa).
//
// Drives the installed Microsoft Edge through playwright-core. Every input is either a
// synthetic fixture created here or an image from a public research dataset passed on
// the command line; the QA database never contains patient records. Screenshots are
// written to --out (outside the repository), the machine-readable result to
// <out>/walkthrough.json.
//
//   node walkthrough.mjs --state %TEMP%\medtwin-qa --out %TEMP%\medtwin-qa\walkthrough \
//     [--sections routes,responsive,anatomy,lifecycle,labs,evidence,corrections,queue,imaging,validation,trained,prognosis]
//     [--image ENDOSCOPY=path] [--image ANGIOGRAPHY=path]
//     [--model-image MODEL_ID:MODALITY=path]  # repeat for every runnable image_2d model

import { chromium } from "playwright-core";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { inflateSync } from "node:zlib";

const ROUTES = ["/", "/cases", "/upload", "/documents", "/imaging", "/biomarkers", "/history", "/anatomy-studio", "/prognosis-studio", "/multimodal", "/risk", "/models", "/datasets", "/validation", "/reports", "/settings", "/attribution"];
const ALL_SECTIONS = ["routes", "responsive", "anatomy", "lifecycle", "labs", "evidence", "corrections", "queue", "imaging", "validation", "trained", "prognosis"];
// This explicit contract prevents a registry regression from silently reducing browser
// coverage. An intentional 2-D workflow addition/removal must update both the registry
// and this acceptance list. Volumetric/evaluation-only entries are excluded by design.
const EXPECTED_IMAGE_2D_MODEL_IDS = [
  "angiography_stenosis_detector",
  "angiography_syntax_segmenter",
  "gi_gastrovision_27class_classifier",
  "gi_kvasir_seg_polyp_segmenter",
  "gi_kvasir_v2_classifier",
  "hematology_cnmc_all_classifier",
  "kidney_stone_detector",
];
const RAW_EVALUATOR_FIXTURE_TEXT = [
  "SYNTHETIC QA CONDITION",
  "SYNTHETIC QA OCR 5.2",
  "SYNTHETIC QA 0CR 5.2",
];

if (process.argv.slice(2).includes("--help")) {
  console.log([
    "MedTwin isolated-stack browser walkthrough",
    "",
    "Usage:",
    "  node walkthrough.mjs --state <qa-state> --out <scratch-output> [--sections <csv>]",
    "    [--model-image MODEL_ID:MODALITY=<public-research-image>]...",
    "    [--image MODALITY=<public-research-image>]...  # legacy; does not satisfy per-model coverage",
    "",
    `Default sections: ${ALL_SECTIONS.join(",")}`,
    "Full imaging coverage currently requires exactly one --model-image binding for each:",
    ...EXPECTED_IMAGE_2D_MODEL_IDS.map((id) => `  ${id}`),
  ].join("\n"));
  process.exit(0);
}
// Validation Center: text that only the report view for each registry task renders.
const REPORT_MARKERS = {
  image_classification: /^Confusion matrix \(test\)$/,
  object_detection: /^Detection on the test split \(n /,
  semantic_segmentation: /^Segmentation on the test split \(n /,
  multilabel_ecg_classification: /^Macro F1 at validation thresholds$/,
  survival_prediction: /^Brier score by horizon \(held out, IPCW\)$/,
  volumetric_semantic_segmentation: /^Cardiac indices from the segmentations \(test patients\)$/,
};
const DESKTOP_VIEWPORT = { width: 1440, height: 900 };
const PHONE_VIEWPORT = { width: 390, height: 844 };

function parseArgs(argv) {
  const args = { images: {}, modelImages: [] };
  for (let index = 0; index < argv.length; index += 2) {
    const [key, value] = [argv[index].replace(/^--/, ""), argv[index + 1]];
    if (key === "image") {
      const [type, file] = value.split("=");
      args.images[type] = file;
    } else if (key === "model-image") {
      const separator = value.indexOf("=");
      const selector = value.slice(0, separator);
      const file = value.slice(separator + 1);
      const colon = selector.lastIndexOf(":");
      if (separator <= 0 || colon <= 0 || !file) throw new Error("--model-image must be MODEL_ID:MODALITY=path");
      args.modelImages.push({ modelId: selector.slice(0, colon), inputType: selector.slice(colon + 1), file });
    } else args[key] = value;
  }
  return args;
}

const readJson = (file) => JSON.parse(readFileSync(file, "utf8").replace(/^﻿/, ""));

/** Minimal decoder for the 8-bit RGB/RGBA, non-interlaced PNGs that Chromium screenshots produce. */
function decodePng(buffer) {
  let offset = 8;
  let width = 0, height = 0, colorType = 0, bitDepth = 0;
  const idat = [];
  while (offset < buffer.length) {
    const length = buffer.readUInt32BE(offset);
    const type = buffer.toString("ascii", offset + 4, offset + 8);
    const data = buffer.subarray(offset + 8, offset + 8 + length);
    if (type === "IHDR") [width, height, bitDepth, colorType] = [data.readUInt32BE(0), data.readUInt32BE(4), data[8], data[9]];
    else if (type === "IDAT") idat.push(data);
    else if (type === "IEND") break;
    offset += 12 + length;
  }
  if (bitDepth !== 8 || (colorType !== 2 && colorType !== 6)) throw new Error(`Unsupported PNG (bit depth ${bitDepth}, colour type ${colorType}).`);
  const channels = colorType === 6 ? 4 : 3;
  const stride = width * channels;
  const raw = inflateSync(Buffer.concat(idat));
  const out = Buffer.alloc(height * stride);
  for (let y = 0; y < height; y += 1) {
    const filter = raw[y * (stride + 1)];
    const line = raw.subarray(y * (stride + 1) + 1, (y + 1) * (stride + 1));
    for (let x = 0; x < stride; x += 1) {
      const a = x >= channels ? out[y * stride + x - channels] : 0;
      const b = y > 0 ? out[(y - 1) * stride + x] : 0;
      const c = x >= channels && y > 0 ? out[(y - 1) * stride + x - channels] : 0;
      let value = line[x];
      if (filter === 1) value += a;
      else if (filter === 2) value += b;
      else if (filter === 3) value += (a + b) >> 1;
      else if (filter === 4) {
        const p = a + b - c, pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c);
        value += pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
      }
      out[y * stride + x] = value & 255;
    }
  }
  return { width, height, channels, data: out };
}

/** Luminance spread and the share of pixels that differ from the corner (background) colour. */
function pixelStats(png) {
  const { width, height, channels, data } = decodePng(png);
  const luminance = new Float64Array(width * height);
  for (let index = 0; index < width * height; index += 1) {
    const o = index * channels;
    luminance[index] = 0.2126 * data[o] + 0.7152 * data[o + 1] + 0.0722 * data[o + 2];
  }
  const background = luminance[0];
  let sum = 0, squares = 0, differing = 0;
  for (const value of luminance) {
    sum += value;
    squares += value * value;
    if (Math.abs(value - background) > 12) differing += 1;
  }
  const mean = sum / luminance.length;
  return { width, height, luminance_std: Math.sqrt(Math.max(0, squares / luminance.length - mean * mean)), non_background_fraction: differing / luminance.length };
}

function parseCount(text) {
  const match = /([\d.,]+)\s*([kKmM]?)/.exec(text ?? "");
  if (!match) return 0;
  const value = Number(match[1].replace(/,/g, ""));
  return value * ({ k: 1e3, m: 1e6 }[match[2].toLowerCase()] ?? 1);
}

const args = parseArgs(process.argv.slice(2));
const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const stateDir = args.state ?? path.join(process.env.TEMP ?? ".", "medtwin-qa");
const outDir = args.out ?? path.join(stateDir, "walkthrough");
const sections = (args.sections ?? ALL_SECTIONS.join(",")).split(",");
mkdirSync(outDir, { recursive: true });
const stack = readJson(path.join(stateDir, "stack.json"));
const credentials = readJson(stack.credentials_file);
const base = stack.web_url;
const result = { started_at: new Date().toISOString(), base_url: base, browser: null, sections: {}, console_errors: [], expected_client_errors: [], page_errors: [], failed_requests: [] };
let expectedClientErrorWindow = false;

const browser = await chromium.launch({ channel: "msedge", headless: true, args: ["--use-angle=d3d11", "--enable-gpu-rasterization", "--ignore-gpu-blocklist"] });
result.browser = `Microsoft Edge ${browser.version()} (playwright-core 1.63.0, headless)`;
const context = await browser.newContext({ viewport: DESKTOP_VIEWPORT, deviceScaleFactor: 1 });
const page = await context.newPage();
page.on("console", (message) => {
  if (message.type() !== "error") return;
  const entry = { url: page.url(), text: message.text().slice(0, 300) };
  if (expectedClientErrorWindow && /422 \(Unprocessable Entity\)/.test(entry.text)) result.expected_client_errors.push(entry);
  else result.console_errors.push(entry);
});
page.on("pageerror", (error) => result.page_errors.push({ url: page.url(), text: String(error).slice(0, 300) }));
page.on("response", (response) => { if (response.status() >= 500) result.failed_requests.push({ url: response.url(), status: response.status() }); });

async function api(method, endpoint, body) {
  return page.evaluate(async ({ method, endpoint, body }) => {
    const response = await fetch(`/api/v1${endpoint}`, { method, headers: { Authorization: `Bearer ${localStorage.getItem("medtwin_token")}`, ...(body ? { "Content-Type": "application/json" } : {}) }, body: body ? JSON.stringify(body) : undefined });
    return { status: response.status, body: await response.json().catch(() => null) };
  }, { method, endpoint, body });
}

async function shot(name, locator) {
  const file = path.join(outDir, `${name}.png`);
  await (locator ?? page).screenshot({ path: file, ...(locator ? {} : { fullPage: false }) });
  return file;
}

// Sign in through the real form. A fresh Vite server compiles dependencies on the first
// browser request, so the first navigation gets a longer budget.
await page.goto(`${base}/`, { timeout: 120000 });
await page.fill("#login-username", credentials.username);
await page.fill("#login-password", credentials.password);
await page.click("button[type=submit]");
await page.waitForFunction(() => Boolean(localStorage.getItem("medtwin_token")), null, { timeout: 20000 });
const cases = await api("GET", "/cases");
const caseId = cases.body?.[0]?.id ?? cases.body?.items?.[0]?.id;
await page.evaluate((id) => localStorage.setItem("medtwin.selectedCase", String(id)), caseId);
result.qa_case = { id: caseId, pseudonymous_id: cases.body?.[0]?.pseudonymous_id ?? null };
let lifecycleState = null;

if (sections.includes("routes")) {
  const routes = [];
  for (const route of ROUTES) {
    const errorsBefore = result.page_errors.length + result.console_errors.length;
    await page.goto(`${base}${route}`, { waitUntil: "networkidle" }).catch(() => undefined);
    await page.waitForTimeout(800);
    const heading = (await page.locator("h1").first().textContent({ timeout: 5000 }).catch(() => null))?.trim() ?? null;
    const crashed = await page.getByText(/something went wrong|unexpected application error/i).count();
    routes.push({ route, heading, rendered: Boolean(heading) && crashed === 0, new_errors: result.page_errors.length + result.console_errors.length - errorsBefore, screenshot: await shot(`route${route === "/" ? "-overview" : route.replaceAll("/", "-")}`) });
  }
  result.sections.routes = { passed: routes.filter((item) => item.rendered).length, total: routes.length, routes };
}

if (sections.includes("responsive")) {
  const routes = [];
  await page.setViewportSize(PHONE_VIEWPORT);
  let mobileNavigation = { button_visible: false, opened: false, closed: false };
  try {
    await page.goto(`${base}/`, { waitUntil: "domcontentloaded", timeout: 60000 });
    const openNavigation = page.getByRole("button", { name: "Open navigation" });
    // The first phone route can still be mounting after domcontentloaded (especially
    // while Vite compiles a lazy route), so observe the real control rather than
    // sampling it synchronously and recording a false negative.
    mobileNavigation.button_visible = await openNavigation.waitFor({ state: "visible", timeout: 30000 }).then(() => true, () => false);
    if (mobileNavigation.button_visible) {
      await openNavigation.click();
      const closeNavigation = page.getByRole("button", { name: "Close navigation" });
      mobileNavigation.opened = await closeNavigation.isVisible().catch(() => false);
      if (mobileNavigation.opened) {
        await closeNavigation.click();
        mobileNavigation.closed = await closeNavigation.waitFor({ state: "hidden", timeout: 5000 }).then(() => true, () => false);
      }
    }
    for (const route of ROUTES) {
      const errorsBefore = result.page_errors.length + result.console_errors.length;
      await page.goto(`${base}${route}`, { waitUntil: "domcontentloaded", timeout: 60000 }).catch(() => undefined);
      await page.waitForTimeout(700);
      const heading = (await page.locator("h1").first().textContent({ timeout: 10000 }).catch(() => null))?.trim() ?? null;
      const crashed = await page.getByText(/something went wrong|unexpected application error/i).count();
      const layout = await page.evaluate(() => {
        const selectorFor = (element) => {
          const segments = [];
          for (let current = element; current && current !== document.body; current = current.parentElement) {
            if (current.id) {
              segments.unshift(`#${CSS.escape(current.id)}`);
              break;
            }
            let segment = current.tagName.toLowerCase();
            const siblings = current.parentElement
              ? [...current.parentElement.children].filter((candidate) => candidate.tagName === current.tagName)
              : [];
            if (siblings.length > 1) segment += `:nth-of-type(${siblings.indexOf(current) + 1})`;
            segments.unshift(segment);
          }
          return `${segments[0]?.startsWith("#") ? "" : "body > "}${segments.join(" > ")}`;
        };
        const documentWidth = document.documentElement.scrollWidth;
        const bodyWidth = document.body.scrollWidth;
        const overflowing = [...document.querySelectorAll("body *")]
          .map((element) => {
            const rect = element.getBoundingClientRect();
            return {
              selector: selectorFor(element),
              tag: element.tagName.toLowerCase(),
              aria_label: element.getAttribute("aria-label"),
              class_name: String(element.className ?? "").slice(0, 120),
              text: String(element.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 80),
              left: Math.round(rect.left),
              right: Math.round(rect.right),
              width: Math.round(rect.width),
              height: Math.round(rect.height),
              scroll_width: element.scrollWidth,
              client_width: element.clientWidth,
              overflow_x: getComputedStyle(element).overflowX,
              excess: Math.round(rect.right - window.innerWidth),
            };
          })
          .filter((item) => item.excess > 1);
        return {
          inner_width: window.innerWidth,
          inner_height: window.innerHeight,
          document_width: documentWidth,
          body_width: bodyWidth,
          // A wide table inside an overflow-x container can extend far beyond the
          // viewport without widening the document. Keep both views: the widest
          // descendants and the elements whose own box reaches the page edge.
          overflowing_elements: [...overflowing].sort((left, right) => right.excess - left.excess).slice(0, 5),
          page_edge_elements: overflowing
            .filter((item) => item.right <= Math.max(documentWidth, bodyWidth) + 2)
            .sort((left, right) => right.excess - left.excess)
            .slice(0, 5),
        };
      });
      const overflow = Math.max(layout.document_width, layout.body_width) - layout.inner_width;
      const rendered = Boolean(heading) && crashed === 0;
      routes.push({
        route,
        heading,
        rendered,
        viewport_matches: layout.inner_width === PHONE_VIEWPORT.width && layout.inner_height === PHONE_VIEWPORT.height,
        viewport_width: layout.inner_width,
        document_width: layout.document_width,
        body_width: layout.body_width,
        horizontal_overflow_px: Math.max(0, overflow),
        no_page_overflow: overflow <= 1,
        overflowing_elements: layout.overflowing_elements,
        page_edge_elements: layout.page_edge_elements,
        new_errors: result.page_errors.length + result.console_errors.length - errorsBefore,
        screenshot: await shot(`phone${route === "/" ? "-overview" : route.replaceAll("/", "-")}`),
      });
    }
  } finally {
    await page.setViewportSize(DESKTOP_VIEWPORT);
  }
  result.sections.responsive = {
    viewport: PHONE_VIEWPORT,
    mobile_navigation: mobileNavigation,
    passed: routes.filter((item) => item.rendered && item.viewport_matches && item.no_page_overflow).length,
    total: routes.length,
    routes,
  };
}

if (sections.includes("anatomy")) {
  const manifest = readJson(path.resolve(args.manifest ?? path.join(projectRoot, "public/anatomy/manifest.json")));
  await page.evaluate(() => localStorage.setItem("medtwin.preferences.v1", JSON.stringify({ theme: "light", detail: "standard", showPerformance: true })));
  const variants = [];
  const only = args.only ? new Set(args.only.split(",")) : null;
  for (const system of manifest.systems) {
    for (const variant of system.variants) {
      if (only && !only.has(variant) && !only.has(system.id)) continue;
      const started = Date.now();
      await page.goto(`${base}/anatomy-studio?system=${system.id}&variant=${variant}`, { waitUntil: "domcontentloaded" });
      const canvas = page.locator("canvas").first();
      let triangles = 0, points = 0, calls = 0, stats = null, error = null, overlayText = null;
      try {
        await canvas.waitFor({ state: "visible", timeout: 30000 });
        const deadline = Date.now() + 60000;
        while (Date.now() < deadline) {
          const box = await canvas.boundingBox();
          if (box) {
            // The viewer renders on demand; a short orbit drag forces frames so the probe samples.
            const [x, y] = [box.x + box.width / 2, box.y + box.height / 2];
            await page.mouse.move(x, y);
            await page.mouse.down();
            for (let step = 1; step <= 6; step += 1) await page.mouse.move(x + step * 4, y + step * 2);
            await page.mouse.up();
          }
          const text = await page.getByText(/draw calls/).first().textContent({ timeout: 1000 }).catch(() => "");
          overlayText = text || overlayText;
          const match = /([\d.,]+\s*[kKmM]?)\s*draw calls\s*\S+\s*([\d.,]+\s*[kKmM]?)\s*tris(?:\s*\S+\s*([\d.,]+)\s*points)?/.exec(text ?? "");
          if (match) {
            calls = parseCount(match[1]);
            triangles = parseCount(match[2]);
            points = parseCount(match[3]);
            if (triangles > 0 || points > 0) break;
          }
          await page.waitForTimeout(500);
        }
        await page.waitForTimeout(400);
        stats = pixelStats(await canvas.screenshot());
      } catch (failure) {
        error = String(failure).slice(0, 200);
      }
      const alert = (await page.getByRole("alert").first().textContent({ timeout: 300 }).catch(() => null))?.slice(0, 200) ?? null;
      const rendered = (triangles > 0 || points > 0) && stats !== null && stats.luminance_std > 3 && stats.non_background_fraction > 0.01;
      variants.push({ system: system.id, variant, rendered, draw_calls: calls, triangles, points, overlay_text: overlayText, pixel_stats: stats, alert, error, seconds: (Date.now() - started) / 1000, screenshot: await shot(`anatomy-${system.id}-${variant}`) });
    }
  }
  const systems = [...new Set(variants.map((item) => item.system))].map((id) => ({ system: id, variants: variants.filter((item) => item.system === id).length, rendered: variants.filter((item) => item.system === id && item.rendered).length }));
  result.sections.anatomy = { systems_total: systems.length, systems_with_all_variants_rendered: systems.filter((item) => item.rendered === item.variants).length, variants_total: variants.length, variants_rendered: variants.filter((item) => item.rendered).length, systems, variants };
}

if (sections.includes("lifecycle")) {
  // Synthetic, clearly labelled report; the printed interval belongs to this document.
  // The negated lung statement exists only to exercise source -> schematic anatomy routing.
  const report = [
    "SYNTHETIC QA FIXTURE - NOT A PATIENT RECORD",
    "Report date: 2026-10-24",
    "Haemoglobin 13.2 g/dL (Reference range 12.0 - 15.5 g/dL)",
    "Serum creatinine 1.0 mg/dL",
    "No pleural effusion is identified in the right lung.",
    "Impression: no acute abnormality described in this synthetic fixture.",
  ].join("\n");
  const fixture = path.join(outDir, "synthetic-qa-report.txt");
  writeFileSync(fixture, report);
  await page.goto(`${base}/upload`, { waitUntil: "networkidle" });
  await page.setInputFiles("[data-testid=upload-file]", fixture);
  await page.check("[data-testid=same-case-confirmation]");
  await page.check("[data-testid=deidentified-attestation]");
  const queuedUi = page.getByText(/Queued job #\d+:/i).first();
  const queuedMessagePromise = queuedUi.waitFor({ state: "visible", timeout: 90000 })
    .then(() => queuedUi.textContent())
    .catch(() => null);
  await page.click("[data-testid=upload-submit]");
  const queuedMessage = (await queuedMessagePromise)?.trim() ?? null;
  const finished = await page.getByText(/^Completed$/i).first().waitFor({ timeout: 90000 }).then(() => true, () => false);
  const uploadShot = await shot("lifecycle-upload-center");
  const uploads = await api("GET", `/cases/${caseId}/uploads`);
  const upload = (uploads.body ?? []).filter((item) => item.filename === path.basename(fixture)).sort((left, right) => left.id - right.id).at(-1) ?? null;
  const jobs = await api("GET", `/cases/${caseId}/jobs`);
  const queueJob = upload ? (jobs.body ?? []).find((job) => job.file_id === upload.id) ?? null : null;
  const analysisJobs = await api("GET", `/cases/${caseId}/analysis-jobs`);
  const analysisJob = upload ? (analysisJobs.body ?? []).find((job) => job.upload_id === upload.id) ?? null : null;
  lifecycleState = { fixture, report, upload, queueJob, analysisJob };
  await page.goto(`${base}/documents`, { waitUntil: "networkidle" });
  if (upload) await page.getByLabel("Report").selectOption(String(upload.id)).catch(() => undefined);
  await page.waitForTimeout(1500);
  const statements = await page.locator("[data-testid=source-statement]").count();
  const haemoglobinText = (await page.getByText(/Haemoglobin|Hemoglobin/i).count()) > 0;
  result.sections.lifecycle = {
    upload_completed_in_ui: finished,
    upload_id: upload?.id ?? null,
    queued_message_visible_in_ui: Boolean(queuedMessage),
    queued_message: queuedMessage,
    queued_job: queueJob ? { id: queueJob.id, kind: queueJob.kind, status: queueJob.status, execution_mode: queueJob.execution_mode, attempts: queueJob.attempts, result_ref: queueJob.result_ref } : null,
    analysis_job: analysisJob ? { id: analysisJob.id, status: analysisJob.status, model_name: analysisJob.model_name, model_version: analysisJob.model_version } : null,
    document_statements_rendered: statements,
    measurement_text_visible: haemoglobinText,
    screenshots: [uploadShot, await shot("lifecycle-document-intelligence")],
  };
}

if (sections.includes("labs")) {
  if (!lifecycleState?.upload) {
    result.sections.labs = { skipped: true, blocker: "Run the lifecycle section in the same invocation to create the isolated synthetic source report." };
  } else {
    const reportTitle = `Synthetic QA duplicate transcription ${Date.now()}`;
    await page.goto(`${base}/biomarkers`, { waitUntil: "networkidle" });
    await page.getByRole("button", { name: "Transcribe results" }).click();
    const dialog = page.getByRole("dialog", { name: "Transcribe laboratory results" });
    await dialog.waitFor({ state: "visible", timeout: 10000 });
    await dialog.getByLabel("Source document").selectOption(String(lifecycleState.upload.id));
    await dialog.getByLabel("Sample collection date").fill("2026-10-24");
    await dialog.getByLabel("Report title").fill(reportTitle);
    await dialog.getByLabel("Add a test").selectOption("CREAT");
    await dialog.getByLabel("Creatinine value").fill("1.0");
    await dialog.getByRole("button", { name: "Record results" }).click();
    const dialogClosed = await dialog.waitFor({ state: "hidden", timeout: 20000 }).then(() => true, () => false);
    await page.getByText(reportTitle, { exact: true }).waitFor({ timeout: 15000 }).catch(() => undefined);
    await page.waitForTimeout(800);
    const reportBlock = page.locator("div.border-t").filter({ hasText: reportTitle }).last();
    const sourceLinked = (await reportBlock.getByText(new RegExp(`Transcribed from ${path.basename(lifecycleState.fixture)}`)).count()) > 0;
    const missingProvenanceHonest = (await reportBlock.getByText(/Not documented.*specimen not documented/i).count()) > 0;
    const indeterminateVisible = (await reportBlock.getByText(/^Indeterminate$/i).count()) > 0;
    const catalogContextOnly = (await reportBlock.getByText(/For orientation only:/i).count()) > 0;
    const excludedText = (await page.getByText(/Excluded:.*duplicate of m\d+/i).first().textContent({ timeout: 10000 }).catch(() => null))?.trim() ?? null;
    const reports = await api("GET", `/cases/${caseId}/lab-reports`);
    const manualReport = (reports.body ?? []).find((item) => item.report_title === reportTitle) ?? null;
    const trends = await api("GET", `/cases/${caseId}/biomarker-trends`);
    const creatinine = (trends.body?.series ?? []).find((item) => item.name === "creatinine") ?? null;
    const duplicate = manualReport && creatinine
      ? (creatinine.excluded ?? []).find((item) => item.lab_report_id === manualReport.id && /^DUPLICATE_OF_M\d+$/.test(item.reason)) ?? null
      : null;

    // A second, explicitly synthetic software fixture exercises structured provenance
    // and censored values. It is intentionally left unlinked because the lifecycle
    // source report does not contain this value; the browser test must not imply that it
    // was transcribed from evidence which says something else.
    const censoredTitle = `Synthetic QA censored result ${Date.now()}`;
    await page.getByRole("button", { name: "Transcribe results" }).click();
    const censoredDialog = page.getByRole("dialog", { name: "Transcribe laboratory results" });
    await censoredDialog.waitFor({ state: "visible", timeout: 10000 });
    await censoredDialog.getByLabel("Sample collection date").fill("2026-10-23");
    await censoredDialog.getByLabel("Performing laboratory").fill("Software Fixture Lab");
    await censoredDialog.getByLabel("Specimen").fill("serum");
    await censoredDialog.getByLabel("Assay / method").fill("enzymatic assay");
    await censoredDialog.getByLabel("Report title").fill(censoredTitle);
    await censoredDialog.getByLabel("Add a test").selectOption("CREAT");
    await censoredDialog.getByLabel("Creatinine comparator").selectOption("<");
    await censoredDialog.getByLabel("Creatinine value").fill("0.01");
    await censoredDialog.getByLabel("Creatinine interval low").fill("0.7");
    await censoredDialog.getByLabel("Creatinine interval high").fill("1.3");
    await censoredDialog.getByRole("button", { name: "Record results" }).click();
    const censoredDialogClosed = await censoredDialog.waitFor({ state: "hidden", timeout: 20000 }).then(() => true, () => false);
    await page.getByText(censoredTitle, { exact: true }).waitFor({ timeout: 15000 }).catch(() => undefined);
    const censoredBlock = page.locator("div.border-t").filter({ hasText: censoredTitle }).last();
    const censoredOperatorVisible = (await censoredBlock.getByText(/<0\.01\s+mg\/dL/i).count()) > 0;
    const censoredIndeterminateVisible = (await censoredBlock.getByText(/^Indeterminate$/i).count()) > 0;
    const structuredContextVisible = (await censoredBlock.getByText(/Software Fixture Lab.*specimen serum.*method enzymatic assay/i).count()) > 0;
    const structuredReports = await api("GET", `/cases/${caseId}/lab-reports`);
    const censoredReport = (structuredReports.body ?? []).find((item) => item.report_title === censoredTitle) ?? null;
    const censoredResult = censoredReport?.results?.find((item) => item.code === "CREAT") ?? null;
    result.sections.labs = {
      manual_submission_completed_in_ui: dialogClosed && Boolean(manualReport),
      source_document_linked: sourceLinked,
      omitted_lab_and_specimen_render_not_documented: missingProvenanceHonest,
      missing_printed_interval_renders_indeterminate: indeterminateVisible,
      catalog_interval_labelled_orientation_only: catalogContextOnly,
      duplicate_exclusion_visible_in_ui: Boolean(excludedText),
      duplicate_exclusion_text: excludedText,
      duplicate_exclusion_persisted: Boolean(duplicate),
      duplicate_reason: duplicate?.reason ?? null,
      creatinine_points_after_dedup: creatinine?.points?.length ?? null,
      censored_submission_completed_in_ui: censoredDialogClosed && Boolean(censoredReport),
      structured_lab_specimen_method_visible: structuredContextVisible,
      censored_operator_visible: censoredOperatorVisible,
      censored_result_indeterminate_visible: censoredIndeterminateVisible,
      structured_lab_specimen_method_persisted: censoredReport?.lab_name === "Software Fixture Lab"
        && censoredReport?.sample_type === "serum" && censoredReport?.laboratory_method === "enzymatic assay",
      censored_operator_persisted: censoredResult?.result_operator === "<" && censoredResult?.result_value === 0.01,
      censored_result_not_range_classified: censoredResult?.status === "INDETERMINATE"
        && /not treated as an exact result/i.test(censoredResult?.censoring_note ?? ""),
      screenshot: await shot("lab-manual-deduplication"),
    };
  }
}

if (sections.includes("evidence")) {
  if (!lifecycleState?.upload) {
    result.sections.evidence = { skipped: true, blocker: "Run the lifecycle section in the same invocation to create synthetic source evidence." };
  } else {
    await page.goto(`${base}/documents`, { waitUntil: "networkidle" });
    await page.getByLabel("Report").selectOption(String(lifecycleState.upload.id));
    const statementRow = page.locator("[data-testid=source-statement]").filter({ hasText: /Pleural effusion/i }).first();
    const sourceStatementVisible = await statementRow.waitFor({ state: "visible", timeout: 15000 }).then(() => true, () => false);
    const anatomyLink = statementRow.getByRole("link", { name: /lungs/i });
    const linkVisible = await anatomyLink.isVisible().catch(() => false);
    if (linkVisible) {
      await anatomyLink.click();
      await page.waitForURL(/\/anatomy-studio\?system=lungs/, { timeout: 20000 }).catch(() => undefined);
    }
    const anatomyUrlAfterClick = new URL(page.url());
    const lungsHeading = page.getByRole("heading", { name: "Lungs", exact: true });
    await lungsHeading.waitFor({ state: "visible", timeout: 60000 }).catch(() => undefined);
    const anatomyHeading = (await lungsHeading.textContent().catch(() => null))?.trim() ?? null;
    // Anatomy evidence arrives independently of the model/heading. Wait for the
    // source span itself, and tolerate punctuation normalization by the parser.
    const evidenceItem = page.locator("li").filter({ hasText: /No pleural effusion is identified in the right lung/i }).first();
    const sourceSpanVisible = await evidenceItem.waitFor({ state: "visible", timeout: 30000 }).then(() => true, () => false);
    const schematicStatusVisible = (await evidenceItem.getByText(/Schematic organ (?:only|association)/i).count()) > 0;
    const anatomyEvidence = await api("GET", `/cases/${caseId}/anatomy-evidence`);
    const mappedStatement = anatomyEvidence.body?.systems?.lungs?.items?.find((item) => item.source_file_id === lifecycleState.upload.id && item.label === "Pleural effusion") ?? null;
    const clickthroughShot = await shot("evidence-document-to-anatomy");

    await page.goto(`${base}/anatomy-studio?system=hybrid`, { waitUntil: "domcontentloaded" });
    await page.getByRole("heading", { name: "Hybrid full body" }).waitFor({ timeout: 30000 }).catch(() => undefined);
    const reviewLayer = page.locator("li").filter({ hasText: /Vascular.*detailed Z-Anatomy layer/i }).first();
    await reviewLayer.locator("summary").click();
    await reviewLayer.getByLabel("Review decision").selectOption("NEEDS_LANDMARKS");
    const reviewComment = "Synthetic QA review: landmark registration remains required.";
    await reviewLayer.getByLabel("Review comments").fill(reviewComment);
    await reviewLayer.getByRole("button", { name: "Record review" }).click();
    const reviewVisible = await reviewLayer.getByText(/#\d+ Needs landmarks/i).first().waitFor({ timeout: 15000 }).then(() => true, () => false);
    const reviews = await api("GET", "/anatomy/registration-reviews?layer_id=angiology-detailed");
    const recordedReview = (reviews.body ?? []).find((item) => item.comments === reviewComment) ?? null;
    result.sections.evidence = {
      source_statement_visible: sourceStatementVisible,
      anatomy_link_visible: linkVisible,
      navigated_to_lungs_studio: anatomyUrlAfterClick.pathname === "/anatomy-studio" && anatomyUrlAfterClick.searchParams.get("system") === "lungs" && anatomyHeading === "Lungs",
      anatomy_heading_after_click: anatomyHeading,
      source_span_visible_in_anatomy: sourceSpanVisible,
      schematic_mapping_status_visible: schematicStatusVisible,
      schematic_mapping_persisted: mappedStatement?.mapping_state === "SCHEMATIC_ORGAN_ONLY"
        && mappedStatement?.mapping_category === "SCHEMATIC_ORGAN_ASSOCIATION",
      registration_review_recorded_in_ui: reviewVisible,
      registration_review_persisted: Boolean(recordedReview),
      registration_decision: recordedReview?.decision ?? null,
      registration_status_not_upgraded: recordedReview?.decision === "NEEDS_LANDMARKS",
      screenshots: [clickthroughShot, await shot("evidence-registration-review")],
    };
  }
}

if (sections.includes("corrections")) {
  if (!lifecycleState?.upload) {
    result.sections.corrections = { skipped: true, blocker: "Run the lifecycle section in the same invocation to create synthetic source evidence." };
  } else {
    const findings = await api("GET", `/cases/${caseId}/findings`);
    const finding = (findings.body ?? []).find((item) => (item.report_statements ?? []).some((statement) => /pleural effusion/i.test(statement.entity ?? statement.source_span ?? ""))) ?? null;
    const original = finding?.report_statements?.find((statement) => /pleural effusion/i.test(statement.entity ?? statement.source_span ?? "")) ?? null;
    if (!finding || !original) {
      result.sections.corrections = { skipped: true, blocker: "The synthetic lifecycle finding did not expose a source-linked statement for correction review." };
    } else {
      const rationale = `Synthetic QA correction proposal ${Date.now()}: exercise removal review without changing source output.`;
      await page.goto(`${base}/cases`, { waitUntil: "networkidle" });
      const findingCard = page.locator("[data-testid=finding-record]").filter({ hasText: finding.label }).first();
      const cardVisible = await findingCard.waitFor({ state: "visible", timeout: 20000 }).then(() => true, () => false);
      if (cardVisible) {
        await findingCard.getByText("Record clinician review", { exact: true }).click();
        const form = findingCard.locator("form").first();
        await form.getByRole("combobox").first().selectOption("MODIFIED");
        await form.getByLabel("Correction action").selectOption("REMOVE");
        await form.getByLabel("Original extracted evidence").selectOption(String(original.id));
        await form.getByPlaceholder("Rationale (required for a correction)").fill(rationale);
        await form.getByRole("button", { name: "Submit review" }).click();
      }
      const noticeVisible = cardVisible && await page.getByText(/Review #\d+ recorded as MODIFIED; the original output was preserved\./i)
        .waitFor({ state: "visible", timeout: 20000 }).then(() => true, () => false);
      const reviews = await api("GET", `/reviews/${finding.id}`);
      const recorded = (reviews.body ?? []).find((item) => item.reviewer_comments === rationale) ?? null;
      const findingAfter = await api("GET", `/findings/${finding.id}`);
      const originalAfter = findingAfter.body?.report_statements?.find((statement) => statement.id === original.id) ?? null;
      const historySummary = findingCard.getByText("Proposed correction history", { exact: true });
      const historyAvailable = await historySummary.waitFor({ state: "visible", timeout: 15000 }).then(() => true, () => false);
      if (historyAvailable) await historySummary.click();
      const originalPreservedVisible = historyAvailable && (await findingCard.getByText(/Original evidence.*preserved/i).count()) > 0;
      const proposalNotAppliedVisible = historyAvailable
        && (await findingCard.getByText(/Proposed correction.*not applied/i).count()) > 0
        && (await findingCard.getByText(/^Proposed not applied$/i).count()) > 0;
      result.sections.corrections = {
        finding_id: finding.id,
        statement_id: original.id,
        correction_controls_visible: cardVisible,
        modified_review_notice_visible: Boolean(noticeVisible),
        proposed_removal_persisted: recorded?.review_status === "MODIFIED"
          && recorded?.correction_payload?.status === "PROPOSED_NOT_APPLIED"
          && recorded?.correction_payload?.entity_corrections?.[0]?.target_statement_id === original.id
          && recorded?.correction_payload?.entity_corrections?.[0]?.action === "REMOVE",
        original_output_preserved_flag: recorded?.original_output_preserved === true,
        original_statement_unchanged: Boolean(originalAfter) && ["entity", "negation", "temporality", "source_span"]
          .every((field) => originalAfter[field] === original[field]),
        original_preserved_visible_in_ui: originalPreservedVisible,
        proposal_not_applied_visible_in_ui: proposalNotAppliedVisible,
        screenshot: await shot("finding-correction-proposal"),
      };
    }
  }
}

if (sections.includes("queue")) {
  if (!lifecycleState?.queueJob || !lifecycleState?.analysisJob) {
    result.sections.queue = { skipped: true, blocker: "Run the lifecycle section in worker mode in the same invocation to create a queued analysis job." };
  } else {
    await page.goto(`${base}/cases`, { waitUntil: "networkidle" });
    await page.reload({ waitUntil: "networkidle" });
    const historyHeadingVisible = await page.getByText("Processing history", { exact: true }).isVisible().catch(() => false);
    const persistedAnalysisVisible = await page.getByText(`#${lifecycleState.analysisJob.id}`, { exact: true }).isVisible().catch(() => false);
    const queueAfterReload = await api("GET", `/jobs/${lifecycleState.queueJob.id}`);
    const queuePersisted = queueAfterReload.status === 200 && queueAfterReload.body?.id === lifecycleState.queueJob.id;
    result.sections.queue = {
      queued_message_was_visible_in_upload_ui: result.sections.lifecycle?.queued_message_visible_in_ui ?? false,
      persisted_processing_history_visible_after_reload: historyHeadingVisible && persistedAnalysisVisible,
      queued_job_api_record_persisted_after_reload: queuePersisted,
      queued_job_id: lifecycleState.queueJob.id,
      analysis_job_id: lifecycleState.analysisJob.id,
      status_after_reload: queueAfterReload.body?.status ?? null,
      execution_mode: queueAfterReload.body?.execution_mode ?? null,
      attempts: queueAfterReload.body?.attempts ?? null,
      durability_scope: "Browser reload plus persisted database record; worker-process restart is covered by backend tests and was not performed in this walkthrough.",
      screenshot: await shot("queue-persisted-processing-history"),
    };
  }
}

if (sections.includes("imaging")) {
  const runs = [];
  const models = (await api("GET", "/research-models")).body?.models ?? [];
  const runnable2dModels = models.filter((item) => item.gate.allowed && (item.inference_input ?? "image_2d") === "image_2d");
  const registryModelIds = runnable2dModels.map((item) => item.model_id).sort();
  const requestedModelIds = args.modelImages.map((item) => item.modelId);
  const duplicateRequestedModelIds = [...new Set(requestedModelIds.filter((id, index) => requestedModelIds.indexOf(id) !== index))].sort();
  const missingModelIds = registryModelIds.filter((id) => !requestedModelIds.includes(id));
  const unexpectedModelIds = requestedModelIds.filter((id) => !registryModelIds.includes(id));
  const registryMissingContractIds = EXPECTED_IMAGE_2D_MODEL_IDS.filter((id) => !registryModelIds.includes(id));
  const registryUnexpectedContractIds = registryModelIds.filter((id) => !EXPECTED_IMAGE_2D_MODEL_IDS.includes(id));
  const requested = [
    ...Object.entries(args.images).map(([inputType, file]) => ({ inputType, file, modelId: null })),
    ...args.modelImages,
  ];
  for (const { inputType, file, modelId } of requested) {
    if (!existsSync(file)) {
      runs.push({ input_type: inputType, requested_model_id: modelId, status: "INPUT_FILE_NOT_FOUND", input_file: file });
      continue;
    }
    const model = modelId
      ? runnable2dModels.find((item) => item.model_id === modelId && item.supported_modalities.includes(inputType))
      : runnable2dModels.find((item) => item.supported_modalities.includes(inputType));
    if (!model) { runs.push({ input_type: inputType, requested_model_id: modelId, status: "NO_RUNNABLE_MODEL" }); continue; }
    await page.goto(`${base}/upload`, { waitUntil: "networkidle" });
    await page.setInputFiles("[data-testid=upload-file]", file);
    await page.check("[data-testid=same-case-confirmation]");
    await page.check("[data-testid=deidentified-attestation]");
    await page.click("[data-testid=upload-submit]");
    // After processing, the row badge shows the analysis run's own status (an image abstains
    // without a validated clinical model), so wait for the page's stored-evidence notice.
    const stored = await page.getByText(/Stored evidence is available/).first().waitFor({ timeout: 90000 }).then(() => true, () => false);
    const uploadStatus = (await page.locator("tbody tr").first().locator("td").nth(2).textContent().catch(() => null))?.trim() ?? null;
    const uploads = (await api("GET", `/cases/${caseId}/uploads`)).body ?? [];
    const upload = uploads.filter((item) => item.filename === path.basename(file)).at(-1);
    if (!upload) {
      const message = (await page.locator("tbody tr").first().locator("td").nth(3).textContent().catch(() => null))?.trim() ?? null;
      runs.push({
        input_type: inputType,
        model_id: model.model_id,
        upload_stored: stored,
        completed: false,
        status: "UPLOAD_RECORD_MISSING",
        error: message ?? "Upload did not produce a case evidence record.",
        screenshot: await shot(`imaging-${model.model_id}-upload-failed`),
      });
      continue;
    }
    await page.goto(`${base}/imaging?upload=${upload.id}`, { waitUntil: "networkidle" });
    let offered = [];
    try {
      offered = await page.getByLabel("Research model").locator("option").evaluateAll((options) => options.map((option) => option.value).filter(Boolean));
      await page.getByLabel("Research model").selectOption(model.model_id);
      await page.getByText(/I confirm this upload is a/).click();
      await page.getByRole("button", { name: /Run research model/ }).click();
    } catch (failure) {
      runs.push({ input_type: inputType, model_id: model.model_id, upload_id: upload.id, upload_stored: stored, completed: false, offered_model_ids: offered,
                  error: String(failure).split("\n")[0].slice(0, 200), screenshot: await shot(`imaging-${model.model_id}-failed`) });
      continue;
    }
    const done = await page.getByText(/Research only · not clinically validated/).first().waitFor({ timeout: 120000 }).then(() => true, () => false);
    await page.waitForTimeout(800);
    const overlayShapes = await page.locator("svg[aria-label='Research model overlay'] rect, svg[aria-label='Research model overlay'] image").count();
    const probabilityRows = model.task === "image_classification" ? await page.locator("table tbody tr").count() : null;
    runs.push({ input_type: inputType, model_id: model.model_id, task: model.task, upload_id: upload.id, upload_stored: stored, upload_status_badge: uploadStatus, completed: done, overlay_shapes: overlayShapes, probability_rows: probabilityRows, offered_model_ids: offered, screenshot: await shot(`imaging-${model.model_id}`) });
  }
  // ECG, survival and volumetric models have no 2-D upload inference path; the imaging
  // panel must never offer them for these image uploads.
  const evaluationOnly = models.filter((item) => (item.inference_input ?? "image_2d") !== "image_2d").map((item) => item.model_id);
  result.sections.imaging = {
                              registry_expected_count: registryModelIds.length,
                              expected_model_ids: registryModelIds,
                              regression_contract_model_ids: EXPECTED_IMAGE_2D_MODEL_IDS,
                              registry_missing_contract_ids: registryMissingContractIds,
                              registry_unexpected_contract_ids: registryUnexpectedContractIds,
                              requested_model_ids: requestedModelIds,
                              missing_model_ids: missingModelIds,
                              unexpected_model_ids: unexpectedModelIds,
                              duplicate_requested_model_ids: duplicateRequestedModelIds,
                              legacy_modality_only_inputs: Object.keys(args.images),
                              runs, evaluation_only_model_ids: evaluationOnly,
                              evaluation_only_models_offered: runs.flatMap((run) => (run.offered_model_ids ?? []).filter((id) => evaluationOnly.includes(id))) };
}

if (sections.includes("validation")) {
  // These are hand-authored, de-identified software-contract fixtures. They test the
  // evaluator UI and privacy/reportability gates; their scores are not research evidence.
  const nlpSource = RAW_EVALUATOR_FIXTURE_TEXT[0];
  const nlpDocument = {
    document_id: "synthetic-qa-nlp-001",
    character_count: nlpSource.length,
    document_sha256: createHash("sha256").update(nlpSource).digest("hex"),
  };
  const nlpSpan = {
    document_id: nlpDocument.document_id,
    start: 13,
    end: 22,
    label: "CONDITION",
    assertion: "CERTAIN",
    negation: "AFFIRMED",
    temporality: "CURRENT",
  };
  const nlpGold = path.join(outDir, "synthetic-qa-clinical-nlp-gold.json");
  const nlpPredictions = path.join(outDir, "synthetic-qa-clinical-nlp-predictions.json");
  const invalidNlpGold = path.join(outDir, "synthetic-qa-clinical-nlp-invalid.json");
  writeFileSync(nlpGold, JSON.stringify({ schema_version: "medtwin.clinical-nlp-spans.v1", artifact_role: "gold", documents: [nlpDocument], spans: [nlpSpan] }, null, 2));
  writeFileSync(nlpPredictions, JSON.stringify({ schema_version: "medtwin.clinical-nlp-spans.v1", artifact_role: "prediction", documents: [nlpDocument], spans: [nlpSpan] }, null, 2));
  writeFileSync(invalidNlpGold, JSON.stringify({ schema_version: "synthetic-invalid-contract-fixture" }, null, 2));

  const ocrGoldText = RAW_EVALUATOR_FIXTURE_TEXT[1];
  const ocrPredictionText = RAW_EVALUATOR_FIXTURE_TEXT[2];
  const ocrPage = {
    document_id: "synthetic-qa-ocr-001",
    page: 1,
    source_image_sha256: createHash("sha256").update("synthetic-qa-rendered-page").digest("hex"),
  };
  const ocrGold = path.join(outDir, "synthetic-qa-ocr-gold.json");
  const ocrPredictions = path.join(outDir, "synthetic-qa-ocr-predictions.json");
  writeFileSync(ocrGold, JSON.stringify({ schema_version: "medtwin.ocr-pages.v1", artifact_role: "gold", pages: [{ ...ocrPage, text: ocrGoldText }] }, null, 2));
  writeFileSync(ocrPredictions, JSON.stringify({ schema_version: "medtwin.ocr-pages.v1", artifact_role: "prediction", pages: [{ ...ocrPage, text: ocrPredictionText }] }, null, 2));

  const runsBefore = await api("GET", "/evaluation/runs");
  const preexistingRunIds = new Set((runsBefore.body ?? []).map((item) => item.run_id));
  await page.goto(`${base}/validation`, { waitUntil: "networkidle" });
  const taskSelect = page.getByTestId("evaluation-task");
  await taskSelect.selectOption("clinical_nlp");
  await page.getByLabel("Gold entity spans (JSON)").setInputFiles(invalidNlpGold);
  await page.getByLabel("Predicted entity spans (JSON)").setInputFiles(nlpPredictions);
  await page.check("[data-testid=nlp-deidentified-attestation]");
  await page.check("[data-testid=nlp-independent-gold-attestation]");
  const invalidResponsePromise = page.waitForResponse((response) => response.url().endsWith("/api/v1/evaluation/clinical_nlp")
    && response.request().method() === "POST", { timeout: 20000 }).catch(() => null);
  expectedClientErrorWindow = true;
  await page.getByRole("button", { name: "Compute metrics" }).click();
  const invalidResponse = await invalidResponsePromise;
  await page.waitForTimeout(250);
  expectedClientErrorWindow = false;
  const responseRequestId = invalidResponse?.headers()["x-request-id"] ?? null;
  const requestError = page.getByRole("alert").filter({ hasText: /\(request [^)]+\)/i }).last();
  const requestErrorText = (await requestError.waitFor({ state: "visible", timeout: 20000 }).then(() => requestError.textContent(), () => null))?.trim() ?? null;
  const requestId = /\(request ([A-Za-z0-9][A-Za-z0-9._:-]{0,127})\)/.exec(requestErrorText ?? "")?.[1] ?? null;

  await page.getByLabel("Gold entity spans (JSON)").setInputFiles(nlpGold);
  await page.getByLabel("Predicted entity spans (JSON)").setInputFiles(nlpPredictions);
  await page.getByRole("button", { name: "Compute metrics" }).click();
  const clinicalMetricsVisible = await page.getByText("Exact F1", { exact: true }).first().waitFor({ state: "visible", timeout: 30000 }).then(() => true, () => false)
    && (await page.getByText("Overlap F1", { exact: true }).count()) > 0
    && (await page.getByText("Per normalized label", { exact: true }).count()) > 0;
  const clinicalExploratoryVisible = await page.getByText("Exploratory: not eligible for reporting", { exact: true }).isVisible().catch(() => false);
  const clinicalScreenshot = await shot("validation-clinical-nlp-evaluator");
  const afterClinicalRuns = await api("GET", "/evaluation/runs");
  const clinicalRun = (afterClinicalRuns.body ?? []).find((item) => !preexistingRunIds.has(item.run_id) && item.task_type === "clinical_nlp") ?? null;
  const clinicalDetail = clinicalRun ? await api("GET", `/evaluation/runs/${clinicalRun.run_id}`) : { status: 0, body: null };

  await taskSelect.selectOption("ocr");
  await page.getByLabel("Independent page transcriptions (JSON)").setInputFiles(ocrGold);
  await page.getByLabel("OCR page predictions (JSON)").setInputFiles(ocrPredictions);
  await page.check("[data-testid=nlp-deidentified-attestation]");
  await page.check("[data-testid=nlp-independent-gold-attestation]");
  await page.getByRole("button", { name: "Compute metrics" }).click();
  const ocrMetricsVisible = await page.getByText("Character error rate", { exact: true }).waitFor({ state: "visible", timeout: 30000 }).then(() => true, () => false)
    && (await page.getByText("Word error rate", { exact: true }).count()) > 0
    && (await page.getByText("Exact-page rate", { exact: true }).count()) > 0;
  const rawTextMetric = page.getByText("Raw text persisted", { exact: true }).locator("..").locator("..");
  const rawTextNotPersistedVisible = await rawTextMetric.getByText("No", { exact: true }).isVisible().catch(() => false);
  const ocrExploratoryVisible = await page.getByText("Exploratory: not eligible for reporting", { exact: true }).isVisible().catch(() => false);
  const ocrScreenshot = await shot("validation-ocr-evaluator");
  const afterOcrRuns = await api("GET", "/evaluation/runs");
  const ocrRun = (afterOcrRuns.body ?? []).find((item) => !preexistingRunIds.has(item.run_id) && item.task_type === "ocr") ?? null;
  const ocrDetail = ocrRun ? await api("GET", `/evaluation/runs/${ocrRun.run_id}`) : { status: 0, body: null };
  const serializedOcrResult = JSON.stringify(ocrDetail.body ?? {});

  result.sections.validation = {
    fixture_scope: "De-identified hand-authored software-contract fixtures only; metrics are exploratory and are not scientific model claims.",
    artifact_schema_versions: { clinical_nlp: "medtwin.clinical-nlp-spans.v1", ocr: "medtwin.ocr-pages.v1" },
    request_id_error_displayed: Boolean(requestId),
    request_id_matches_error_response_header: invalidResponse?.status() === 422 && Boolean(requestId) && requestId === responseRequestId,
    request_id: requestId,
    clinical_nlp_controls_exercised: clinicalMetricsVisible,
    clinical_nlp_run_persisted: clinicalDetail.status === 200 && clinicalDetail.body?.task_type === "clinical_nlp",
    clinical_nlp_schema_accepted: clinicalDetail.body?.provenance?.schema_version === "medtwin.clinical-nlp-spans.v1"
      && clinicalDetail.body?.config?.schema_version === "medtwin.clinical-nlp-spans.v1",
    clinical_nlp_remained_exploratory: clinicalExploratoryVisible && clinicalDetail.body?.evaluation_context?.reporting_status === "EXPLORATORY",
    clinical_nlp_artifacts_hash_only: ["gold", "predictions"].every((role) => {
      const artifact = clinicalDetail.body?.input_artifacts?.[role];
      return artifact && Object.keys(artifact).sort().join(",") === "role,sha256";
    }),
    ocr_controls_exercised: ocrMetricsVisible,
    ocr_run_persisted: ocrDetail.status === 200 && ocrDetail.body?.task_type === "ocr",
    ocr_schema_accepted: ocrDetail.status === 200 && ocrDetail.body?.task_type === "ocr"
      && ocrDetail.body?.config?.schema_version === "medtwin.ocr-pages.v1"
      && readJson(ocrGold).schema_version === "medtwin.ocr-pages.v1" && readJson(ocrPredictions).schema_version === "medtwin.ocr-pages.v1",
    ocr_remained_exploratory: ocrExploratoryVisible && ocrDetail.body?.evaluation_context?.reporting_status === "EXPLORATORY",
    ocr_raw_text_not_persisted_visible: rawTextNotPersistedVisible,
    ocr_raw_text_not_persisted: ocrDetail.body?.provenance?.raw_text_persisted === false
      && !serializedOcrResult.includes(ocrGoldText) && !serializedOcrResult.includes(ocrPredictionText),
    screenshots: [clinicalScreenshot, ocrScreenshot],
  };
}

if (sections.includes("trained")) {
  // Validation Center → Trained models: every registered report renders its own view.
  const models = (await api("GET", "/research-models")).body?.models ?? [];
  await page.goto(`${base}/validation`, { waitUntil: "networkidle" });
  await page.getByRole("radio", { name: "Trained models" }).click();
  const reports = [];
  for (const model of models) {
    const errorsBefore = result.page_errors.length + result.console_errors.length;
    await page.getByLabel("Trained model", { exact: true }).selectOption(model.model_id);
    const marker = REPORT_MARKERS[model.task] ?? null;
    const rendered = marker ? await page.getByText(marker).first().waitFor({ timeout: 20000 }).then(() => true, () => false) : false;
    const evaluationOnly = (model.inference_input ?? "image_2d") !== "image_2d";
    const exploratory = model.run_scope === "EXPLORATORY_ONLY";
    reports.push({
      model_id: model.model_id, task: model.task, marker: marker ? String(marker) : null, rendered,
      provenance_visible: await page.getByText("Provenance", { exact: true }).first().isVisible().catch(() => false),
      alerts: await page.getByRole("alert").count(),
      evaluation_only: evaluationOnly,
      evaluation_only_badge_visible: await page.getByText("Evaluation evidence only: no upload inference path").isVisible().catch(() => false),
      exploratory, exploratory_badge_visible: await page.getByText("Exploratory only: held-out evidence does not support use").isVisible().catch(() => false),
      new_errors: result.page_errors.length + result.console_errors.length - errorsBefore,
      screenshot: await shot(`validation-trained-${model.model_id}`),
    });
  }
  result.sections.trained = { passed: reports.filter((item) => item.rendered && item.provenance_visible && item.alerts === 0
    && item.evaluation_only_badge_visible === item.evaluation_only && item.exploratory_badge_visible === item.exploratory).length,
                              total: reports.length, reports };
}

if (sections.includes("prognosis")) {
  await page.goto(`${base}/prognosis-studio`, { waitUntil: "networkidle" });
  const separateRoute = new URL(page.url()).pathname === "/prognosis-studio" && (await page.locator("canvas").count()) === 0;
  const unavailableBeforeEvaluate = await page.getByText(/Not trained|Not validated|Estimand undefined/).count();
  // Kidneys: the synthetic report documents serum creatinine, so the scenario has observed evidence.
  const organSelected = await page.locator("select").filter({ has: page.locator("option", { hasText: "Renal conditions" }) }).first()
    .selectOption({ label: "Renal conditions" }).then(() => true, () => false);
  await page.getByRole("button", { name: /Evaluate/ }).click();
  await page.getByText(/Scenario A/).first().waitFor({ timeout: 20000 }).catch(() => undefined);
  await page.waitForTimeout(800);
  const scenarios = await page.getByText(/Scenario A|Scenario B/).count();
  const abstentions = await page.getByText(/MODEL_NOT_VALIDATED|Model not validated|INSUFFICIENT_EVIDENCE|Insufficient evidence|Not identifiable|ESTIMAND_UNDEFINED|Estimand undefined/i).count();
  const percentages = await page.getByText(/\b\d{1,3}(\.\d+)?\s?%\s*(risk|probability|chance)/i).count();
  result.sections.prognosis = { separate_route_without_3d_canvas: separateRoute, unavailable_states_before_evaluate: unavailableBeforeEvaluate, organ: organSelected ? "kidneys" : "default",
                                scenario_panels: scenarios, abstention_markers: abstentions, numeric_risk_statements: percentages, screenshot: await shot("prognosis-studio") };
}

const sectionAssertions = {};
if (sections.includes("routes")) {
  sectionAssertions.routes = result.sections.routes?.passed === result.sections.routes?.total;
}
if (sections.includes("responsive")) {
  const navigation = result.sections.responsive?.mobile_navigation;
  sectionAssertions.responsive = result.sections.responsive?.passed === result.sections.responsive?.total
    && Boolean(navigation?.button_visible && navigation?.opened && navigation?.closed);
}
if (sections.includes("anatomy")) {
  sectionAssertions.anatomy = result.sections.anatomy?.variants_rendered === result.sections.anatomy?.variants_total
    && result.sections.anatomy?.systems_with_all_variants_rendered === result.sections.anatomy?.systems_total;
}
if (sections.includes("lifecycle")) {
  const lifecycle = result.sections.lifecycle;
  sectionAssertions.lifecycle = Boolean(lifecycle?.upload_completed_in_ui && lifecycle?.queued_message_visible_in_ui
    && lifecycle?.document_statements_rendered > 0 && lifecycle?.measurement_text_visible);
}
if (sections.includes("labs")) {
  const labs = result.sections.labs;
  sectionAssertions.labs = Boolean(labs?.manual_submission_completed_in_ui && labs?.source_document_linked
    && labs?.omitted_lab_and_specimen_render_not_documented && labs?.missing_printed_interval_renders_indeterminate
    && labs?.catalog_interval_labelled_orientation_only && labs?.duplicate_exclusion_visible_in_ui
    && labs?.duplicate_exclusion_persisted && labs?.creatinine_points_after_dedup > 0
    && labs?.censored_submission_completed_in_ui && labs?.structured_lab_specimen_method_visible
    && labs?.censored_operator_visible && labs?.censored_result_indeterminate_visible
    && labs?.structured_lab_specimen_method_persisted && labs?.censored_operator_persisted
    && labs?.censored_result_not_range_classified);
}
if (sections.includes("evidence")) {
  const evidence = result.sections.evidence;
  sectionAssertions.evidence = Boolean(evidence?.source_statement_visible && evidence?.anatomy_link_visible
    && evidence?.navigated_to_lungs_studio && evidence?.source_span_visible_in_anatomy
    && evidence?.schematic_mapping_status_visible && evidence?.schematic_mapping_persisted
    && evidence?.registration_review_recorded_in_ui && evidence?.registration_review_persisted
    && evidence?.registration_status_not_upgraded);
}
if (sections.includes("corrections")) {
  const corrections = result.sections.corrections;
  sectionAssertions.corrections = Boolean(corrections?.correction_controls_visible
    && corrections?.modified_review_notice_visible && corrections?.proposed_removal_persisted
    && corrections?.original_output_preserved_flag && corrections?.original_statement_unchanged
    && corrections?.original_preserved_visible_in_ui && corrections?.proposal_not_applied_visible_in_ui);
}
if (sections.includes("queue")) {
  const queue = result.sections.queue;
  sectionAssertions.queue = Boolean(queue?.queued_message_was_visible_in_upload_ui
    && queue?.persisted_processing_history_visible_after_reload && queue?.queued_job_api_record_persisted_after_reload
    && queue?.status_after_reload === "SUCCEEDED" && queue?.execution_mode === "worker" && queue?.attempts >= 1);
}
if (sections.includes("imaging")) {
  const imaging = result.sections.imaging;
  const runs = imaging?.runs ?? [];
  const expectedModelIds = imaging?.expected_model_ids ?? [];
  const everyExpectedModelCompletedOnce = expectedModelIds.every((modelId) => {
    const matching = runs.filter((run) => run.model_id === modelId);
    return matching.length === 1 && matching[0].completed === true && matching[0].upload_stored === true
      && (matching[0].task === "image_classification" ? matching[0].probability_rows > 0 : matching[0].overlay_shapes > 0);
  });
  sectionAssertions.imaging = expectedModelIds.length === EXPECTED_IMAGE_2D_MODEL_IDS.length
    && imaging?.registry_missing_contract_ids?.length === 0 && imaging?.registry_unexpected_contract_ids?.length === 0
    && imaging?.missing_model_ids?.length === 0 && imaging?.unexpected_model_ids?.length === 0
    && imaging?.duplicate_requested_model_ids?.length === 0 && everyExpectedModelCompletedOnce
    && imaging?.evaluation_only_models_offered.length === 0;
}
if (sections.includes("validation")) {
  const validation = result.sections.validation;
  sectionAssertions.validation = Boolean(validation?.request_id_error_displayed && validation?.request_id_matches_error_response_header
    && validation?.clinical_nlp_controls_exercised && validation?.clinical_nlp_run_persisted
    && validation?.clinical_nlp_schema_accepted && validation?.clinical_nlp_remained_exploratory
    && validation?.clinical_nlp_artifacts_hash_only && validation?.ocr_controls_exercised
    && validation?.ocr_run_persisted && validation?.ocr_schema_accepted
    && validation?.ocr_remained_exploratory && validation?.ocr_raw_text_not_persisted_visible
    && validation?.ocr_raw_text_not_persisted);
}
if (sections.includes("trained")) {
  const trained = result.sections.trained;
  sectionAssertions.trained = trained?.total > 0 && trained?.passed === trained?.total;
}
if (sections.includes("prognosis")) {
  const prognosis = result.sections.prognosis;
  sectionAssertions.prognosis = Boolean(prognosis?.separate_route_without_3d_canvas
    && prognosis?.scenario_panels > 0 && prognosis?.abstention_markers > 0 && prognosis?.numeric_risk_statements === 0);
}
const cleanBrowser = result.console_errors.length === 0 && result.page_errors.length === 0 && result.failed_requests.length === 0;
const evaluatorRawTextAbsent = RAW_EVALUATOR_FIXTURE_TEXT.every((marker) => !JSON.stringify(result).includes(marker));
result.assertions = {
  sections: sectionAssertions,
  browser_clean: cleanBrowser,
  evaluator_raw_text_absent_from_walkthrough_json: evaluatorRawTextAbsent,
  all_passed: cleanBrowser && evaluatorRawTextAbsent && Object.values(sectionAssertions).every(Boolean),
};
result.finished_at = new Date().toISOString();
writeFileSync(path.join(outDir, "walkthrough.json"), JSON.stringify(result, null, 2));
await browser.close();
const summary = Object.fromEntries(Object.entries(result.sections).map(([name, value]) => [name, Object.fromEntries(Object.entries(value).filter(([, item]) => typeof item !== "object"))]));
console.log(JSON.stringify({ ...summary, assertions: result.assertions, console_errors: result.console_errors.length, page_errors: result.page_errors.length, failed_requests: result.failed_requests.length }, null, 1));
if (!result.assertions.all_passed) process.exitCode = 1;
