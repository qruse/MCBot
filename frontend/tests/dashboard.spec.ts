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
  await expect(page.getByTestId("paper-cash-input")).toHaveValue("100000000");
  await expect(page.locator('g[class*="candleLayer"] rect')).toHaveCount(84);
  await expect(page.locator('path[class*="ma5Path"]')).toHaveCount(1);
  await expect(page.locator('path[class*="ma20Path"]')).toHaveCount(1);
  await expect(page.locator('path[class*="ma60Path"]')).toHaveCount(1);
  await expect(page.locator('path[class*="ma120Path"]')).toHaveCount(1);
  await expect(page.locator('svg[class*="themeSparkline"]')).toHaveCount(2);
  await expect(page.locator('button[class*="stockThemeHeader"]').first()).toBeVisible();
  await expect(page.locator('line[class*="volumeDivider"]')).toHaveCount(1);
  await expect(page.locator('div[class*="chartCanvas"]')).toHaveCSS("background-color", "rgb(10, 16, 24)");
  await expect(page.locator('text[class*="axisLabel"]').filter({ hasText: /\d{2}\/\d{2}\s\d{2}:\d{2}/ }).first()).toBeVisible();
  await page.getByTestId("range-1D").click();
  await expect(page.locator('g[class*="candleLayer"] rect')).toHaveCount(96);
  await expect(page.locator('text[class*="axisLabel"]').filter({ hasText: /06\/11\s\d{2}:\d{2}/ }).first()).toBeVisible();
  await expect(page.getByText(/0\.4%.*0\.25%.*7\/10/).first()).toBeVisible();
  await expect(page.getByText("정수 1주 단위 매수 · 잔여 현금 유지")).toBeVisible();
  await expect(page.locator('g[class*="extremeLabels"] text')).toHaveCount(2);
  await expect(page.getByText("거래비용 국내 0.01405% / 편도")).toBeVisible();
  await expect(page.getByTestId("universe-refresh")).toBeVisible();
  await page.getByTestId("universe-refresh").click();
  await expect(page.getByText("테마/시총 TOP10 갱신 완료")).toBeVisible();

  await page.getByTestId("market-tab-overseas").click();
  await expect(page.getByText("NVDA").first()).toBeVisible();
  await expect(page.getByText(/FX 1,380/).first()).toBeVisible();
  await expect(page.getByText(/미국 매수 0.250%/).first()).toBeVisible();
  await expect(page.getByText(/매도 0.252%/).first()).toBeVisible();

  await page.locator('input[placeholder]').fill("MSFT");
  await expect(page.getByText("MSFT").first()).toBeVisible();

  await page.getByTestId("chart-type-line").click();
  await expect(page.locator('path[class*="pricePath"]')).toHaveCount(1);
  await page.getByTestId("chart-type-candle").click();
  await expect(page.locator('g[class*="candleLayer"] rect').first()).toBeVisible();

  await page.getByTestId("auto-run-toggle").uncheck();
  await expect(page.getByTestId("auto-run-toggle")).not.toBeChecked();
  await page.getByTestId("auto-run-toggle").check();
  await expect(page.getByTestId("auto-run-toggle")).toBeChecked();
  await page.getByTestId("auto-run-toggle").uncheck();
  await expect(page.getByTestId("auto-run-toggle")).not.toBeChecked();

  await page.getByTestId("simulation-reset").click();
  await expect(page.getByText("Reset: 100,000,000 KRW paper account")).toBeVisible();
  await expect(page.getByText(/100,000,000/).first()).toBeVisible();
  await page.getByTestId("paper-cash-input").fill("50000000");
  await page.getByTestId("simulation-reset").click();
  await expect(page.getByText("Reset: 50,000,000 KRW paper account")).toBeVisible();

  await page.screenshot({ path: "../test_logs/frontend-dashboard-qa-desktop.png", fullPage: false });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "../test_logs/frontend-dashboard-qa-mobile.png", fullPage: false });

  expect(consoleIssues).toEqual([]);
});
