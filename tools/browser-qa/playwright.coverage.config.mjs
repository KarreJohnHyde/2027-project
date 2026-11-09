// Explicit component-only UI check. It does not test authentication or the API.
import { defineConfig } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
process.env.MEDTWIN_COVERAGE_FIXTURE = "1";

export default defineConfig({
  testDir: "e2e", testMatch: "capability-coverage.spec.mjs", workers: 1, timeout: 90_000,
  reporter: "list", outputDir: path.join(root, "artifacts/verify/coverage-component-2026-11-09"),
  use: { baseURL: "http://127.0.0.1:4318", channel: "msedge", screenshot: "only-on-failure" },
  webServer: {
    command: "npx vite preview --mode check --host 127.0.0.1 --port 4318 --strictPort", cwd: root,
    url: "http://127.0.0.1:4318", timeout: 60_000, reuseExistingServer: false,
  },
});
