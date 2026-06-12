import { expect, test } from "@playwright/test";

test("brokerage dashboard controls work", async ({ page }) => {
  const consoleIssues: string[] = [];

  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) {
      consoleIssues.push(`${message.type()}: ${message.text()}`);
    }
  });

  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "Money Copy Bot" })).toBeVisible();
  await expect(page.getByTestId("auto-run-toggle")).toBeChecked();
  await expect(page.getByTestId("simulation-reset")).toBeVisible();
  await expect(page.locator('g[class*="candleLayer"] rect')).toHaveCount(84);
  await expect(page.locator('svg[class*="themeSparkline"]')).toHaveCount(2);
  await expect(page.locator('button[class*="stockThemeHeader"]').first()).toBeVisible();
  await expect(page.locator('line[class*="volumeDivider"]')).toHaveCount(1);
  await expect(page.getByText("거래비용 0.065% / 편도")).toBeVisible();

  await page.getByTestId("market-tab-overseas").click();
  await expect(page.getByText("NVDA").first()).toBeVisible();
  await expect(page.getByText(/해외 모의매매/).first()).toBeVisible();
  await expect(page.getByText(/FX 1,380/).first()).toBeVisible();

  await page.getByPlaceholder("티커, 회사, 시장, 테마 검색").fill("MSFT");
  await expect(page.getByText("MSFT").first()).toBeVisible();

  await page.getByTestId("chart-type-line").click();
  await expect(page.locator('path[class*="pricePath"]')).toHaveCount(1);
  await page.getByTestId("chart-type-candle").click();
  await expect(page.locator('g[class*="candleLayer"] rect').first()).toBeVisible();

  await page.getByTestId("auto-run-toggle").uncheck();
  await expect(page.getByTestId("auto-run-toggle")).not.toBeChecked();
  await page.getByTestId("auto-run-toggle").check();
  await expect(page.getByTestId("auto-run-toggle")).toBeChecked();

  await page.getByTestId("simulation-reset").click();
  await expect(page.getByText("Reset: 10,000,000 KRW paper account")).toBeVisible();
  await expect(page.getByText("10,000,000원").first()).toBeVisible();

  await page.screenshot({ path: "../test_logs/frontend-dashboard-qa-desktop.png", fullPage: false });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "../test_logs/frontend-dashboard-qa-mobile.png", fullPage: false });

  expect(consoleIssues).toEqual([]);
});
