// Browser regression checks on a throwaway stack (see ../playwright.config.mjs). Every upload is a
// synthetic fixture built here; nothing comes from a patient record.

import { expect, test } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

const ROUTES = ["/", "/cases", "/upload", "/documents", "/imaging", "/biomarkers", "/history", "/anatomy-studio", "/prognosis-studio",
  "/multimodal", "/risk", "/models", "/datasets", "/validation", "/reports", "/settings", "/attribution"];
const MARKER = "SYNTHETIC-E2E-PATIENT-FIELD";
const fixtures = path.join(process.env.MEDTWIN_E2E_STATE, "fixtures");
mkdirSync(fixtures, { recursive: true });

function fixture(name, content) {
  const file = path.join(fixtures, name);
  writeFileSync(file, content);
  return file;
}

function field(value, width) {
  return String(value).padEnd(width, " ").slice(0, width);
}

/** A two-record EDF with one 10 Hz sine channel (128 Hz) and a filled patient field that must never be shown. */
function edf() {
  const rate = 128;
  const records = 2;
  let header = field("0", 8) + field(MARKER, 80) + field("Startdate X X X X", 80) + field("03.02.26", 8) + field("09.15.00", 8);
  header += field(512, 8) + field("", 44) + field(records, 8) + field(1, 8) + field(1, 4);
  header += field("EEG Cz-REF", 16) + field("AgAgCl electrode", 80) + field("uV", 8) + field(-200, 8) + field(200, 8);
  header += field(-32768, 8) + field(32767, 8) + field("HP:0.1Hz LP:70Hz", 80) + field(rate, 8) + field("", 32);
  const data = Buffer.alloc(rate * records * 2);
  for (let i = 0; i < rate * records; i += 1) {
    const microvolts = 100 * Math.sin((2 * Math.PI * 10 * i) / rate);
    data.writeInt16LE(Math.round(((microvolts + 200) / 400) * 65535 - 32768), i * 2);
  }
  return Buffer.concat([Buffer.from(header, "ascii"), data]);
}

async function signIn(page) {
  await page.goto("/");
  await page.fill("#login-username", process.env.MEDTWIN_E2E_USERNAME);
  await page.fill("#login-password", process.env.MEDTWIN_E2E_PASSWORD);
  await page.click("button[type=submit]");
  await page.waitForFunction(() => Boolean(localStorage.getItem("medtwin_token")), null, { timeout: 30_000 });
  const token = await page.evaluate(() => localStorage.getItem("medtwin_token"));
  const cases = await (await page.request.get("/api/v1/cases", { headers: { Authorization: `Bearer ${token}` } })).json();
  const caseId = cases[0]?.id ?? cases.items?.[0]?.id;
  expect(caseId, "the seeded case exists").toBeTruthy();
  await page.evaluate((id) => localStorage.setItem("medtwin.selectedCase", String(id)), caseId);
  return { token, caseId };
}

async function upload(page, file) {
  await page.goto("/upload", { waitUntil: "networkidle" });
  await page.setInputFiles("[data-testid=upload-file]", file);
  await page.check("[data-testid=same-case-confirmation]");
  await page.check("[data-testid=deidentified-attestation]");
  await page.click("[data-testid=upload-submit]");
  // "Not run" is the terminal state when the file was read but no model applies (e.g. EDF).
  await expect(page.getByText(/^(Completed|Not run)$/i).first()).toBeVisible({ timeout: 90_000 });
}

test("every page renders after sign-in without uncaught errors", async ({ page }) => {
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await signIn(page);
  for (const route of ROUTES) {
    await page.goto(route, { waitUntil: "domcontentloaded" });
    await expect(page.locator("h1").first(), `${route} shows its heading`).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/something went wrong|unexpected application error/i)).toHaveCount(0);
  }
  expect(pageErrors, "no uncaught page errors").toEqual([]);
});

test("a report upload is analysed and its statements and values are shown with their source", async ({ page }) => {
  await signIn(page);
  await upload(page, fixture("e2e-report.txt", [
    "SYNTHETIC E2E FIXTURE - NOT A PATIENT RECORD",
    "Report date: 2026-10-24",
    "Haemoglobin 13.2 g/dL (Reference range 12.0 - 15.5 g/dL)",
    "No pleural effusion is identified.",
  ].join("\n")));
  await page.goto("/documents", { waitUntil: "networkidle" });
  await expect(page.locator("[data-testid=source-statement]").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/Ha?emoglobin/i).first()).toBeVisible();
});

test("an HL7 v2 result message is imported without its patient segment", async ({ page }) => {
  const { token, caseId } = await signIn(page);
  await upload(page, fixture("e2e-results.hl7", [
    "MSH|^~\\&|SYNTH_LAB|SYNTH_SITE|MEDTWIN|MEDTWIN|20260203091500||ORU^R01|MSG0001|P|2.5.1",
    `PID|1||${MARKER}^^^SYNTH||${MARKER}^GIVEN`,
    "OBR|1|||24323-8^Metabolic panel^LN|||20260203080000",
    "OBX|1|NM|2160-0^Creatinine^LN||1.42|mg/dL^^UCUM|0.70-1.30|H|||F",
  ].join("\r")));
  const measurements = await (await page.request.get(`/api/v1/cases/${caseId}/measurements`, { headers: { Authorization: `Bearer ${token}` } })).json();
  const creatinine = measurements.find((item) => item.name === "creatinine" && item.extraction_method === "HL7_V2_OBX_IMPORT");
  expect(creatinine?.value).toBe(1.42);
  expect(JSON.stringify(measurements)).not.toContain(MARKER);
});

test("an EDF recording is read and drawn without showing its patient field", async ({ page }) => {
  await signIn(page);
  await upload(page, fixture("e2e-recording.edf", edf()));
  await page.goto("/multimodal", { waitUntil: "networkidle" });
  const panel = page.locator("section").filter({ has: page.getByRole("heading", { name: "EEG and physiological recordings" }) });
  await expect(panel.getByText("EDF", { exact: true }).first()).toBeVisible({ timeout: 30_000 });
  await expect(panel.locator("svg[role=img] path").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(MARKER)).toHaveCount(0);
});

test("a patient account sees only the results its clinician has reviewed", async ({ page, browser }) => {
  const { token, caseId } = await signIn(page);
  const auth = { Authorization: `Bearer ${token}` };
  const password = `Pt-${Date.now()}-aA1!`;
  const registered = await page.request.post("/api/v1/auth/register", { data: {
    username: "e2e_patient", email: "e2e_patient@example.invalid", password, full_name: "Synthetic Patient", requested_role: "patient",
  } });
  expect(registered.status()).toBe(201);
  expect((await page.request.post(`/api/v1/cases/${caseId}/members`, { headers: auth, data: { username: "e2e_patient", role: "PATIENT" } })).status()).toBe(201);
  await upload(page, fixture("e2e-portal.txt", "SYNTHETIC E2E FIXTURE\nReport date: 2026-10-24\nPotassium 4.6 mmol/L (Reference range 3.5 - 5.1 mmol/L)\n"));
  const measurements = await (await page.request.get(`/api/v1/cases/${caseId}/measurements`, { headers: auth })).json();
  const findingId = measurements.find((item) => item.name === "potassium").finding_id;

  const patient = await browser.newPage();
  await patient.goto("/");
  await patient.fill("#login-username", "e2e_patient");
  await patient.fill("#login-password", password);
  await patient.click("button[type=submit]");
  await expect(patient.getByRole("heading", { name: "Your health record" })).toBeVisible({ timeout: 30_000 });
  await expect(patient.getByText("No reviewed results yet.", { exact: false })).toBeVisible();
  await expect(patient.getByRole("link", { name: "Document Intelligence" })).toHaveCount(0);

  expect((await page.request.post(`/api/v1/reviews/${findingId}`, { headers: auth, data: { review_status: "CONFIRMED" } })).status()).toBe(201);
  await patient.reload();
  await expect(patient.getByRole("cell", { name: "Potassium" })).toBeVisible({ timeout: 30_000 });
  await expect(patient.getByRole("cell", { name: /3\.5 – 5\.1/ })).toBeVisible();
  await patient.goto("/documents");
  await expect(patient.getByRole("heading", { name: "Your health record" })).toBeVisible();
  await patient.close();
});
