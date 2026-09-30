import { expect, test } from "@playwright/test";

test.afterAll(async ({ request }) => {
  await request.post("http://127.0.0.1:8011/__test__/shutdown");
});

test("paper controls use one server session across reload and tabs", async ({ page, context }) => {
  const errors: string[] = [];
  const brokerCalls: string[] = [];
  context.on("weberror", error => errors.push(error.error().message));
  await context.route("**/paper/**", async route => {
    const url = new URL(route.request().url());
    const response = await route.fetch({ url: "http://127.0.0.1:8011" + url.pathname + url.search });
    await route.fulfill({ response });
  });
  await context.route("**/brokers/**", route => {
    brokerCalls.push(route.request().url());
    return route.abort();
  });
  await page.goto("/");
  await page.getByRole("combobox", { name: "시세 데이터" }).selectOption("demo");
  await page.getByRole("button", { name: "설정 저장" }).click();
  await page.getByRole("button", { name: "모의매매 시작", exact: true }).click();
  await expect(page.getByTestId("profit-chart")).toBeVisible({ timeout: 12000 });
  await expect(page.getByTestId("strategy-library")).toContainText("테마 추세");
  await expect(page.getByTestId("standing-candidate")).toHaveCount(3);
  await expect(page.getByTestId("standing-candidate").first()).not.toBeVisible();
  const chart = await page.getByTestId("performance-panel").boundingBox();
  const candidates = await page.getByTestId("candidates").boundingBox();
  expect(chart!.y).toBeLessThan(candidates!.y);
  await page.reload();
  await expect(page.getByTestId("session-lifecycle")).toHaveText("실행 중");
  const second = await context.newPage();
  await second.goto("/");
  await second.getByRole("button", { name: "시뮬레이션 정지" }).click();
  await expect(page.getByTestId("session-lifecycle")).toHaveText("일시정지", { timeout: 10000 });
  await expect(page.getByTestId("chart-gap")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  expect(brokerCalls).toEqual([]);
  expect(errors).toEqual([]);
});

test("backend outage cannot create a browser session or a demo fallback", async ({ page }) => {
  await page.route("**/paper/**", route => route.abort());
  await page.goto("/");
  await expect(page.getByText("서버에 연결할 수 없습니다. 마지막으로 받은 정보를 표시합니다.")).toBeVisible();
  await expect(page.getByRole("button", { name: "모의매매 시작", exact: true })).toHaveCount(0);
  await expect(page.getByTestId("profit-chart")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "다시 연결" })).toBeVisible();
});
