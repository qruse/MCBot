import { expect, test } from "@playwright/test";

test("paper session records profit every five seconds without price charts or rapid broker polling", async ({ page }) => {
  let priceCalls = 0;
  let strategyCalls = 0;
  let failed = false;
  await page.clock.install();
  await page.route(/\/universe\/themes/, route => route.fulfill({ json: { source: "fixture", themes: [], count: 0, notes: [] } }));
  await page.route(/\/brokers\/toss\/status$/, route => route.fulfill({ json: { configured: true, execution: "local-paper" } }));
  await page.route(/\/brokers\/toss\/connection$/, route => route.fulfill({ json: { accounts: [{ account_seq: 1, type: "BROKERAGE" }] } }));
  await page.route(/\/brokers\/toss\/prices\?/, route => {
    priceCalls++;
    const symbols = new URL(route.request().url()).searchParams.get("symbols")!.split(",");
    return route.fulfill({ status: failed ? 503 : 200, json: failed ? { detail: "Toss calls paused during cooldown. Retry later." } : {
      data: symbols.map(symbol => ({ symbol, lastPrice: "100", currency: /^\d/.test(symbol) ? "KRW" : "USD", timestamp: new Date().toISOString() })),
      usd_krw: "1380.5", source: "Toss Securities Open API",
      synced_at: new Date().toISOString(),
    } });
  });
  await page.route(/\/brokers\/toss\/strategy\//, route => {
    strategyCalls++;
    const candles = Array.from({ length: 120 }, (_, i) => ({ timestamp: new Date(Date.now() - (120 - i) * 60000).toISOString(), openPrice: "100", highPrice: "100", lowPrice: "100", closePrice: "100", volume: "1000" }));
    return route.fulfill({ json: { minute: candles, daily: candles, synced_at: new Date().toISOString() } });
  });
  await page.goto("/");
  const start = page.getByTestId("auto-run-toggle");
  await expect(start).toBeEnabled();
  await expect(page.getByTestId("profit-empty")).toBeVisible();
  await expect(page.getByTestId("profit-chart")).toHaveCount(0);
  await expect(page.getByRole("img", { name: /price chart/ })).toHaveCount(0);
  expect(strategyCalls).toBe(0);
  await start.check();
  await expect(page.getByTestId("profit-samples")).toContainText("1 samples");
  await page.clock.fastForward(5000);
  await expect(page.getByTestId("profit-samples")).toContainText("2 samples");
  await start.uncheck();
  await page.clock.fastForward(10000);
  await expect(page.getByTestId("profit-samples")).toContainText("2 samples");
  expect(priceCalls).toBe(1);
  await start.check();
  await page.clock.fastForward(5000);
  await expect(page.getByTestId("profit-samples")).toContainText("3 samples");
  await page.screenshot({ path: "../artifacts/toss-paper-profit.png", fullPage: true });
  failed = true;
  await page.getByRole("button", { name: "Refresh quotes", exact: true }).click();
  await expect(page.getByText("Toss calls paused during cooldown. Retry later.", { exact: true }).first()).toBeVisible();
  await page.clock.fastForward(5000);
  await expect(page.getByTestId("profit-samples")).toContainText("3 samples");
  await start.uncheck(); // Stop remains available during broker errors.
  await page.getByTestId("simulation-reset").click();
  await expect(start).not.toBeChecked();
  await expect(page.getByTestId("profit-chart")).toHaveCount(0);
  await expect(page.getByTestId("profit-empty")).toBeVisible();
});
