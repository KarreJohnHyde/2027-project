// Browser regression suite (CI and local): starts a throwaway backend (SQLCipher-encrypted SQLite in a
// temporary directory, encrypted uploads, per-run keys, one seeded clinician and case) and the built
// frontend, then drives Chromium. Only synthetic fixtures are uploaded.
//
//   npm run build:check                       # in the repository root, once
//   cd tools/browser-qa && npx playwright test
//
// MEDTWIN_E2E_PYTHON selects the interpreter (default "python"; locally e.g. ..\..\.venv\Scripts\python.exe).

import { defineConfig } from "@playwright/test";
import { randomBytes } from "node:crypto";
import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..", "..");
const backendPort = 8017;
const frontendPort = 4317;
// Generated once per run in the main process; test workers inherit them.
process.env.MEDTWIN_E2E_USERNAME ??= "e2e_clinician";
process.env.MEDTWIN_E2E_PASSWORD ??= `${randomBytes(12).toString("base64url")}aA1!`;
process.env.MEDTWIN_E2E_STATE ??= mkdtempSync(path.join(tmpdir(), "medtwin-e2e-"));
const state = process.env.MEDTWIN_E2E_STATE;
mkdirSync(state, { recursive: true });
const python = process.env.MEDTWIN_E2E_PYTHON || "python";

export default defineConfig({
  testDir: "e2e",
  timeout: 120_000,
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never", outputFolder: path.join(state, "report") }]] : "list",
  outputDir: path.join(state, "results"),
  use: {
    baseURL: `http://127.0.0.1:${frontendPort}`,
    // CI installs Chromium; a workstation can use its installed Edge instead (MEDTWIN_E2E_CHANNEL=msedge).
    channel: process.env.MEDTWIN_E2E_CHANNEL || undefined,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: `"${python}" -m uvicorn app.main:app --host 127.0.0.1 --port ${backendPort}`,
      cwd: path.join(root, "backend"),
      url: `http://127.0.0.1:${backendPort}/health`,
      timeout: 180_000,
      reuseExistingServer: false,
      env: {
        ENVIRONMENT: "development",
        DATABASE_URL: `sqlite:///${path.join(state, "e2e.db").replaceAll("\\", "/")}`,
        UPLOAD_DIR: path.join(state, "uploads"),
        SECRET_KEY: randomBytes(32).toString("base64url"),
        MEDTWIN_STORAGE_ENCRYPTION: "required",
        MEDTWIN_STORAGE_KEYS: randomBytes(32).toString("base64"),
        MEDTWIN_DB_ENCRYPTION: "sqlcipher",
        MEDTWIN_DB_KEY: randomBytes(32).toString("hex"),
        MEDTWIN_JOB_EXECUTION: "inline",
        DEV_SEED_ENABLED: "true",
        DEV_SEED_USERNAME: process.env.MEDTWIN_E2E_USERNAME,
        DEV_SEED_PASSWORD: process.env.MEDTWIN_E2E_PASSWORD,
        DEV_SEED_EMAIL: "e2e_clinician@example.invalid",
        DEV_SEED_ROLE: "clinician",
        DEV_SEED_CASE_ENABLED: "true",
        CORS_ORIGINS: `["http://127.0.0.1:${frontendPort}"]`,
        RATE_LIMIT_LOGIN_PER_MINUTE: "60",
      },
    },
    {
      command: `npx vite preview --mode check --host 127.0.0.1 --port ${frontendPort} --strictPort`,
      cwd: root,
      url: `http://127.0.0.1:${frontendPort}/`,
      timeout: 60_000,
      reuseExistingServer: false,
      env: { MEDTWIN_BACKEND_URL: `http://127.0.0.1:${backendPort}`, PORT: String(frontendPort) },
    },
  ],
});
