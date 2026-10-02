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
  await page.getByRole("combobox", { name: "거래 시장" }).selectOption("GLOBAL");
  await page.getByRole("button", { name: "설정 저장" }).click();
  await page.getByRole("button", { name: "모의매매 시작", exact: true }).click();
  await expect(page.getByTestId("session-lifecycle")).toHaveText("실행 중", { timeout: 12000 });
  await expect(page.getByTestId("strategy-library")).toContainText("테마 추세");
  await expect(page.getByTestId("standing-candidate")).toHaveCount(0);
  await expect(page.getByTestId("session-cash")).toHaveText("₩100,000,000");
  await expect(page.getByText("국내 · 개장", { exact: true })).toBeVisible();
  await expect(page.getByText("미국 · 개장", { exact: true })).toBeVisible();
  await expect(page.getByTestId("performance-panel")).toHaveCount(0);
  const holdings = await page.getByRole("heading", { name: /^보유 종목/ }).boundingBox();
  const candidates = await page.getByTestId("candidates").boundingBox();
  expect(candidates!.y).toBeLessThan(holdings!.y);
  await page.reload();
  await expect(page.getByTestId("session-lifecycle")).toHaveText("실행 중");
  const second = await context.newPage();
  await second.goto("/");
  await second.getByRole("button", { name: "시뮬레이션 정지" }).click();
  await expect(page.getByTestId("session-lifecycle")).toHaveText("일시정지", { timeout: 10000 });
  await expect(page.getByTestId("profit-chart")).toHaveCount(0);
  await expect(page.getByTestId("performance-panel")).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  expect(brokerCalls).toEqual([]);
  expect(errors).toEqual([]);
});

test("strategy decisions separate entry holds, candidate readiness and allocation targets", async ({ page, request }) => {
  const snapshot = await (await request.get("http://127.0.0.1:8011/paper/snapshot")).json();
  const s = snapshot.session;
  const now = Date.now();
  s.lifecycle = "running";
  s.evaluatedAt = now;
  s.mode = "adaptive";
  s.entryBlock = "cash_policy";
  s.cash = "3000000";
  s.positions = [{ symbol: "005930", shares: 10, entryCost: "1000000", entryPrice: "100000", entryFee: "0", entryFx: "1" }];
  s.policy = { playbook_id: "cash-v1", strategy_version: 1, proposal_id: "ui-current", expires_at: now + 3600000,
    rationale: "Preserve holdings while data is incomplete.", hypothesis: "Reconsider when execution data is complete.", counterevidence: "Opportunity cost remains.", allowed_symbols: ["005930"],
    evidence: [{ evidence_id: "issuer-ui", publisher: "Issuer", source_url: "https://example.com/research", published_at: now - 86400000, retrieved_at: now - 1000, claim: "Research candidate only." }] };
  s.candidateGroups = [{ group_id: "ui-memory", name: "Memory", candidates: [{ symbol: "005930", name: "Samsung", rationale: "Memory theme; valuation unresolved.", evidence_ids: ["issuer-ui"] }] }];
  s.candidateExpiresAt = s.policy.expires_at;
  s.candidateChecks = { "005930": null, "114800": null, "123310": null, "145670": "candidate_quote_unavailable" };
  s.total = 4;
  s.ready = 3;
  s.portfolioStatus = null;
  const quote = { price: "100000", currency: "KRW", sourceTime: now - 1000, receivedAt: now, changePercent: "0" };
  s.latest = { ...s.latest, market: "KR", observedAt: now, quotes: { "005930": quote }, minute: {}, daily: {}, fx: null, provider: "ready" };
  snapshot.research.receipts = [{ proposal_id: "ui-current", status: "accepted", timestamp: now - 1000, source: "toss", reason: "validated", rationale: "Hold entries.", evidence: [] }];
  snapshot.research.nextReviewDue = now + 3600000;
  await page.route("**/paper/snapshot", route => route.fulfill({ json: snapshot }));
  await page.goto("/");
  const overview = page.getByTestId("strategy-overview");
  await expect(overview.getByRole("heading", { name: "신규 매수 보류" })).toBeVisible();
  await expect(overview).toContainText("기존 1종목 유지 · 추가 매수 없음");
  await expect(overview).toContainText("목표 비중 미설정");
  await expect(overview).toContainText("1종목 준비 대기");
  await expect(page.getByTestId("agent-candidate")).toContainText("10주 보유");
  await page.getByTestId("agent-candidate").getByText("선정 근거").click();
  await expect(page.getByRole("link", { name: "Issuer ↗", exact: true })).toHaveAttribute("href", "https://example.com/research");
  await page.getByRole("button", { name: "지수 인버스 3" }).click();
  await expect(page.getByTestId("standing-candidate")).toHaveCount(3);
  await expect(page.getByTestId("standing-candidate").last()).toContainText("시세 대기");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  s.policy.expires_at = now - 1000;
  s.candidateExpiresAt = s.policy.expires_at;
  await page.reload();
  await expect(overview).toContainText("검토 만료");
  await expect(overview).toContainText("새 판단을 기다리는 중 · 신규 매수 중지");
  await expect(page.getByTestId("candidates")).toContainText("개별주 검토 만료");
  await expect(page.getByTestId("agent-candidate")).toContainText("준비 완료");
  s.policy.playbook_id = "adaptive-allocation";
  s.policy.expires_at = now + 3600000;
  s.candidateExpiresAt = s.policy.expires_at;
  s.entryBlock = "none";
  s.portfolioStatus = { mode: "adaptive", rows: [
    { symbol: "CASH", theme: null, standing: false, retiring: false, targetPercent: 30, actualPercent: null, actualAmount: null, targetAmount: null },
    { symbol: "005930", theme: "Memory", standing: false, retiring: false, targetPercent: 70, actualPercent: null, actualAmount: null, targetAmount: null }
  ], nav: null, driftPercent: 2, minimumTradeKrw: 50000, maxTurnoverPercent: 20, lastRebalancedAt: null, nextRebalanceAt: now + 3600000, reason: "data_stale" };
  await page.reload();
  await expect(overview).toContainText("목표 비중 설정됨");
  await expect(page.getByRole("heading", { name: "종목 · 테마 비중", exact: true })).toBeVisible();
  await expect(page.getByRole("row").filter({ hasText: "30.00%" })).toContainText("—");
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("dated prices remain visible while execution is blocked and the chart section is absent", async ({ page, request }) => {
  const snapshot = await (await request.get("http://127.0.0.1:8011/paper/snapshot")).json();
  const s = snapshot.session;
  const now = Date.now();
  s.lifecycle = "running";
  s.evaluatedAt = now;
  s.cash = "1000000";
  s.baseline = "2000000";
  s.config.capital = "2000000";
  s.segment = 3;
  s.positions = [{ symbol: "005930", shares: 10, entryCost: "1000000", entryPrice: "100000", entryFee: "0", entryFx: "1" }];
  const quote = { price: "100000", currency: "KRW", sourceTime: now - 300000, receivedAt: now, changePercent: null };
  s.latest = { ...s.latest, market: "KR", observedAt: now, quotes: { "005930": { ...quote, price: null } },
    displayQuotes: { "005930": quote }, minute: {}, daily: {}, fx: null, provider: "ready" };
  s.samples = [{ timestamp: now - 600000, segment: 2, equity: "1", cash: "1000000", profit: "-1999999", returnPercent: "-99" }];
  await page.route("**/paper/snapshot", route => route.fulfill({ json: snapshot }));
  await page.goto("/");
  await expect(page.getByTestId("session-equity")).toHaveText("₩1,999,850");
  await expect(page.getByRole("row").filter({ hasText: "삼성전자" })).toContainText("지연");
  await expect(page.getByRole("row").filter({ hasText: "삼성전자" })).toContainText("손절 검사 불가");
  await expect(page.getByTestId("profit-chart")).toHaveCount(0);
  s.samples.push({ ...s.samples[0], timestamp: now, segment: 3 });
  await page.reload();
  await expect(page.getByTestId("performance-panel")).toHaveCount(0);
  s.segment = 4;
  await page.reload();
  await expect(page.getByTestId("profit-chart")).toHaveCount(0);
  s.lifecycle = "paused";
  await page.reload();
  await expect(page.getByTestId("performance-panel")).toHaveCount(0);
});

test("backend outage cannot create a browser session or a demo fallback", async ({ page }) => {
  await page.route("**/paper/**", route => route.abort());
  await page.goto("/");
  await expect(page.getByText("서버에 연결할 수 없습니다. 마지막으로 받은 정보를 표시합니다.")).toBeVisible();
  await expect(page.getByRole("button", { name: "모의매매 시작", exact: true })).toHaveCount(0);
  await expect(page.getByTestId("profit-chart")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "다시 연결" })).toBeVisible();
});
