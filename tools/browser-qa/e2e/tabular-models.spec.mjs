// Typed-value research inference for a tabular model through the Model Registry card, on the isolated QA stack.
// Values are generated from the model's own development envelope; nothing is stored as patient evidence.
import { expect, test } from "@playwright/test";
import path from "node:path";

test.use({ viewport: { width: 1440, height: 1000 } });

const MODEL = "tabular_heart_disease_uci";
const TITLE = "Coronary disease from clinical tests (UCI Heart Disease, 4 sites, research)";

async function session(page) {
  const login = await page.request.post("/api/v1/auth/login", { data: { username: process.env.MEDTWIN_E2E_USERNAME, password: process.env.MEDTWIN_E2E_PASSWORD } });
  expect(login.ok()).toBeTruthy();
  const token = (await login.json()).access_token;
  await page.addInitScript((value) => localStorage.setItem("medtwin_token", value), token);
  return token;
}

test("a tabular model runs on typed values inside its envelope and refuses values outside it", async ({ page }, testInfo) => {
  const token = await session(page);
  const contract = await page.request.get(`/api/v1/research-models/${MODEL}/tabular-contract`, { headers: { Authorization: `Bearer ${token}` } });
  test.skip(!contract.ok(), "The tabular model or its checkpoint is not available in this checkout.");
  const fields = (await contract.json()).fields;
  await page.goto("/models");
  await page.getByRole("radio", { name: "Model cards" }).or(page.getByRole("button", { name: "Model cards" })).first().click();
  const card = page.locator("section").filter({ has: page.getByRole("heading", { name: TITLE, exact: true }) });
  await card.getByRole("button", { name: "Enter values (research)" }).click();
  for (const field of fields) {
    if (field.type === "number" && field.allowed_values) await card.getByLabel(field.name, { exact: true }).selectOption(String(field.allowed_values[0]));
    else if (field.type === "number") await card.getByLabel(field.name, { exact: true }).fill(String((field.min + field.max) / 2));
    else await card.getByLabel(field.name, { exact: true }).selectOption(field.categories[0]);
  }
  await card.getByRole("button", { name: "Run model" }).click();
  await expect(card.getByText(/^Research probability/)).toBeVisible();
  await expect(card.getByText(/Not a diagnosis; not stored\./)).toBeVisible();
  await card.screenshot({ path: path.join(testInfo.outputPath(), "tabular-result.png") });
  const age = fields.find((field) => field.name === "age");
  await card.getByLabel("age", { exact: true }).fill(String(age.max * 10));
  await card.getByRole("button", { name: "Run model" }).click();
  await expect(card.getByText(/OUT_OF_DEVELOPMENT_RANGE/)).toBeVisible();
});
