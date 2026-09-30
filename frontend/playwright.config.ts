import { defineConfig } from "@playwright/test";
import { resolve } from "node:path";

export default defineConfig({
  testDir: "./tests",
  testMatch: "**/*.spec.ts",
  timeout: 30_000,
  workers: 1,
  webServer: {
    command: `"${resolve(process.platform === "win32" ? "../backend/.venv/Scripts/python.exe" : "../backend/.venv/bin/python")}" "${resolve("../backend/tests/browser_server.py")}"`,
    url: "http://127.0.0.1:8011/health",
    reuseExistingServer: false,
    timeout: 20000,
  },
  use: {
    baseURL: "http://127.0.0.1:3001",
    browserName: "chromium",
    channel: "chrome",
    trace: "off",
    video: "off",
    screenshot: "only-on-failure",
    viewport: { width: 1440, height: 1000 },
  },
});
