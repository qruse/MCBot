import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  use: {
    baseURL: "http://127.0.0.1:3001",
    browserName: "chromium",
    channel: "chrome",
    trace: "off",
    video: "off",
    viewport: { width: 1440, height: 1000 },
  },
});
