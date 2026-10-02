import { test, expect } from '@playwright/test';

test.afterAll(async ({ request }) => {
  await request.post('http://127.0.0.1:8011/__test__/shutdown');
});

test('five stocks and two index inverses show native prices and closed-market readiness', async ({ page, request }) => {
  const snapshot = await (await request.get('http://127.0.0.1:8011/paper/snapshot')).json();
  const s = snapshot.session;
  const now = Date.now();
  const stocks = [['KR','005930'], ['KR','000660'], ['KR','267260'], ['US','NVDA'], ['US','AMZN']];
  const inverses = [['KR','114800'], ['US','PSQ']];
  const item = ([market, symbol]: string[]) => ({ market, symbol, name: symbol, rationale: 'Fixture only.', evidence_ids: [] });
  s.config.market = 'GLOBAL';
  s.lifecycle = 'running';
  s.evaluatedAt = now;
  s.cash = '10000000';
  s.positions = [];
  s.baseline = '10000000';
  s.mode = 'adaptive';
  s.entryBlock = 'none';
  s.condition = 'ready';
  s.policy = { playbook_id: 'adaptive-allocation', proposal_id: 'seven-ui', strategy_version: 2,
    expires_at: now+3600000, rationale: 'Fixture only.', hypothesis: 'Seven selected slots.', counterevidence: 'No return evidence.', evidence: [] };
  s.candidateGroups = ['KR','US'].map(market => ({ group_id: market, name: 'Stocks', candidates: stocks.filter(v => v[0] === market).map(item) }));
  s.standingGroups = inverses.map(v => ({ group_id: v[0]+'-inverse', name: 'Index inverse', candidates: [item(v)] }));
  s.candidateExpiresAt = now+3600000;
  s.candidateChecks = Object.fromEntries([...stocks,...inverses].map(v => [v.join(':'), null]));
  s.ready = 7; s.total = 7;
  const quote = { price: '10000', currency: 'KRW', sourceTime: now-1000, receivedAt: now, changePercent: '0' };
  const native = (market: string) => ({ market, observedAt: now, marketOpen: market === 'KR', quotes: Object.fromEntries([...stocks,...inverses].filter(v => v[0] === market).map(v => [v[1], { ...quote, currency: market === 'KR' ? 'KRW' : 'USD', price: market === 'KR' ? '10000' : '123.45' }])), minute: {}, daily: {}, fx: null, provider: 'ready' });
  s.latest = { market: 'GLOBAL', observedAt: now, quotes: {}, minute: {}, daily: {}, fx: { rate: '1350', validFrom: now-1000, validUntil: now+300000, receivedAt: now }, provider: 'ready', markets: { KR: native('KR'), US: { ...native('US'), marketOpen: true } } };
  s.globalStatus = { cashBalances: { KRW: '10000000', USD: '0' }, cashKrw: '10000000', equity: '10000000', valuationFx: null, marketEntryBlocks: {}, markets: {}, holdings: [] };
  await page.route('**/paper/snapshot', route => route.fulfill({ json: snapshot }));
  await page.goto('/');
  await expect(page.getByRole('button', { name: '개별주 5', exact: true })).toBeVisible();
  await expect(page.getByTestId('agent-candidate')).toHaveCount(5);
  await expect(page.getByTestId('agent-candidate').filter({ hasText: 'NVDA' })).toContainText('$123.45');
  s.latest.markets.US.marketOpen = false;
  for (const v of [...stocks,...inverses].filter(v => v[0] === 'US')) s.candidateChecks[v.join(':')] = 'market_closed';
  s.ready = 4;
  await page.reload();
  await expect(page.getByTestId('agent-candidate').filter({ hasText: 'NVDA' })).toContainText('유효한 가격 없음');
  await page.getByRole('button', { name: '지수 인버스 2', exact: true }).click();
  await expect(page.getByTestId('standing-candidate')).toHaveCount(2);
  await expect(page.getByTestId('standing-candidate').filter({ hasText: '114800' })).toContainText('₩10,000');
  await expect(page.getByTestId('standing-candidate').filter({ hasText: 'PSQ' })).toContainText('정규장');
  await expect(page.getByRole('heading', { name: '손익 추이' })).toHaveCount(0);
  await expect(page.getByTestId('session-cash')).toHaveText('₩10,000,000');
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});
