import { expect, test } from "@playwright/test";

test("brokerage dashboard controls work", async ({ page }) => {
  const consoleIssues: string[] = [];
  const ionqDownloadedHistory = {
    source: "Yahoo Finance chart download",
    environment: "paper",
    symbol: "IONQ",
    range: "1M",
    interval: "daily",
    count: 3,
    data: [
      {
        symbol: "IONQ",
        timestamp: "2026-06-10T00:00:00Z",
        open: 41.2,
        high: 42.9,
        low: 40.5,
        close: 42.1,
        volume: 12500000,
        source: "Yahoo Finance chart download",
      },
      {
        symbol: "IONQ",
        timestamp: "2026-06-11T00:00:00Z",
        open: 42.1,
        high: 44.2,
        low: 41.7,
        close: 43.8,
        volume: 13900000,
        source: "Yahoo Finance chart download",
      },
      {
        symbol: "IONQ",
        timestamp: "2026-06-12T00:00:00Z",
        open: 43.8,
        high: 45.6,
        low: 43.2,
        close: 45.1,
        volume: 14600000,
        source: "Yahoo Finance chart download",
      },
    ],
    errors: [],
  };

  await page.route(/\/universe\/themes/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        source: "e2e empty theme fixture",
        count: 0,
        themes: [],
        notes: [],
      }),
    });
  });

  await page.route(/\/quotes\/kis\/watchlist$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        source: "e2e quote fixture",
        environment: "paper",
        count: 0,
        data: [],
        errors: [],
      }),
    });
  });

  await page.route(/\/quotes\/kis\/history\//, async (route) => {
    const requestUrl = new URL(route.request().url());
    const pathParts = requestUrl.pathname.split("/");
    const symbol = pathParts[pathParts.length - 1];
    const range = requestUrl.searchParams.get("range");

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        symbol === "IONQ" && range === "1M"
          ? ionqDownloadedHistory
          : {
              source: "e2e empty chart fixture",
              environment: "paper",
              symbol,
              range,
              interval: "fixture",
              count: 0,
              data: [],
              errors: [],
            },
      ),
    });
  });

  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) {
      if (message.text().includes("ERR_CONNECTION_REFUSED")) {
        return;
      }

      consoleIssues.push(`${message.type()}: ${message.text()}`);
    }
  });

  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "Money Copy Bot" })).toBeVisible();
  await expect(page.getByTestId("auto-run-toggle")).not.toBeChecked();
  await expect(page.getByTestId("theme-mode-core")).toBeVisible();
  await expect(page.getByTestId("theme-refresh-meta")).toContainText(/Core 6/);
  await expect(page.getByTestId("simulation-reset")).toBeVisible();
  await expect(page.getByTestId("paper-cash-input")).toHaveValue("100000000");
  await expect(page.locator("aside nav button")).toHaveCount(1);
  await expect(page.locator('g[class*="candleLayer"] rect')).toHaveCount(84);
  await expect(page.locator('path[class*="ma5Path"]')).toHaveCount(1);
  await expect(page.locator('path[class*="ma20Path"]')).toHaveCount(1);
  await expect(page.locator('path[class*="ma60Path"]')).toHaveCount(1);
  await expect(page.locator('path[class*="ma120Path"]')).toHaveCount(1);
  await expect(page.locator('svg[class*="themeSparkline"]')).toHaveCount(3);
  await expect(page.locator('button[class*="stockThemeHeader"]').first()).toBeVisible();
  await expect(page.locator('line[class*="volumeDivider"]')).toHaveCount(1);
  await expect(page.getByTestId("chart-source-label")).toContainText(/candles/);
  await expect(page.locator('div[class*="chartCanvas"]')).toHaveCSS("background-color", "rgb(10, 16, 24)");
  const chartPanelBox = await page.locator('[class*="chartPanel"]').boundingBox();
  const chartCanvasBox = await page.locator('[class*="chartCanvas"]').boundingBox();
  const watchPanelBox = await page.locator('[class*="watchPanel"]').boundingBox();

  expect(chartPanelBox).not.toBeNull();
  expect(chartCanvasBox).not.toBeNull();
  expect(watchPanelBox).not.toBeNull();
  expect(chartCanvasBox!.x + chartCanvasBox!.width).toBeLessThanOrEqual(chartPanelBox!.x + chartPanelBox!.width + 1);
  expect(chartCanvasBox!.x + chartCanvasBox!.width).toBeLessThanOrEqual(watchPanelBox!.x - 1);
  await expect(page.locator('text[class*="axisLabel"]').filter({ hasText: /\d{2}\/\d{2}\s\d{2}:\d{2}/ }).first()).toBeVisible();
  await page.getByTestId("range-1D").click();
  await page.waitForTimeout(1500);
  const oneDayCandleCount = await page.locator('g[class*="candleLayer"] rect').count();
  expect(oneDayCandleCount).toBeGreaterThanOrEqual(12);
  await page.waitForTimeout(1200);
  await expect(page.locator('g[class*="candleLayer"] rect')).toHaveCount(oneDayCandleCount);
  await expect(page.locator('text[class*="axisLabel"]').filter({ hasText: /\d{2}\/\d{2}\s\d{2}:\d{2}/ }).first()).toBeVisible();
  await expect(page.getByText(/0\.4%.*0\.25%.*7\/10/).first()).toBeVisible();
  await expect(page.getByText("TOP5 고르게 분산 · 정수 1주 단위")).toBeVisible();
  await expect(page.getByText(/1위 테마 상승추세/).first()).toBeVisible();
  await expect(page.locator('g[class*="extremeLabels"] text')).toHaveCount(0);
  await expect(page.getByText("거래비용 국내 0.01405% / 편도")).toBeVisible();
  await expect(page.getByText("국내 방산").first()).toBeVisible();
  await expect(page.getByTestId("universe-refresh")).toBeVisible();
  await page.getByTestId("universe-refresh").click();
  await expect(page.getByText(/테마.*(갱신 완료|샘플 유니버스 유지)/).first()).toBeVisible();

  await page.getByTestId("market-tab-overseas").click();
  await expect(page.getByText("NVDA").first()).toBeVisible();
  await expect(page.getByText(/FX 1,380/).first()).toBeVisible();
  await expect(page.getByText(/미국 매수 0.250%/).first()).toBeVisible();
  await expect(page.getByText(/매도 0.252%/).first()).toBeVisible();

  await page.getByTestId("theme-mode-all").click();
  await expect(page.getByTestId("theme-refresh-meta")).toContainText(/Extended/);
  await page.locator('input[placeholder]').fill("IONQ");
  await page.getByRole("button", { name: /IONQ/ }).first().click();
  await page.getByTestId("range-1M").click();
  await expect(page.getByTestId("chart-source-label")).toContainText(/Yahoo Finance chart download.*3 candles/);

  await page.locator('input[placeholder]').fill("MSFT");
  await expect(page.getByText("MSFT").first()).toBeVisible();

  await page.getByTestId("chart-type-line").click();
  await expect(page.locator('path[class*="pricePath"]')).toHaveCount(1);
  await page.getByTestId("chart-type-candle").click();
  await expect(page.locator('g[class*="candleLayer"] rect').first()).toBeVisible();

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

test("theme fallback follows the selected universe mode when the API is unavailable", async ({ page }) => {
  await page.route(/\/universe\/themes/, async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "theme service unavailable" }),
    });
  });

  await page.route(/\/quotes\/kis\/watchlist$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        source: "e2e quote fixture",
        environment: "paper",
        count: 0,
        data: [],
        errors: [],
      }),
    });
  });

  await page.route(/\/quotes\/kis\/history\//, async (route) => {
    const requestUrl = new URL(route.request().url());
    const pathParts = requestUrl.pathname.split("/");

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        source: "e2e empty chart fixture",
        environment: "paper",
        symbol: pathParts[pathParts.length - 1],
        range: requestUrl.searchParams.get("range"),
        interval: "fixture",
        count: 0,
        data: [],
        errors: [],
      }),
    });
  });

  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("theme-refresh-meta")).toContainText(/Core 6/);

  await page.getByTestId("theme-mode-all").click();
  await expect(page.getByTestId("theme-refresh-meta")).toContainText(/Extended/);
  await expect(page.getByTestId("theme-refresh-meta")).not.toContainText(/Extended 6/);

  await page.getByTestId("market-tab-overseas").click();
  await expect(page.getByText("IONQ").first()).toBeVisible();
});
