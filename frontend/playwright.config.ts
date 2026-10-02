import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  globalTeardown: "./e2e/teardown.ts",
  workers: 1,
  retries: 0,
  use: {
    baseURL: "http://127.0.0.1:3100",
    trace: "off",
    channel: process.env.E2E_BROWSER_CHANNEL,
  },
  webServer: [
    {
      command: process.platform === "win32" ? "..\\backend\\.venv\\Scripts\\python.exe -m scripts.e2e_server" : "../backend/.venv/bin/python -m scripts.e2e_server",
      cwd: "../backend",
      url: "http://127.0.0.1:8100/health/ready",
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "npm run dev -- --port 3100",
      url: "http://127.0.0.1:3100",
      env: { E2E_TEST: "1", NEXT_PUBLIC_API_URL: "http://127.0.0.1:8100", NEXT_TELEMETRY_DISABLED: "1" },
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
