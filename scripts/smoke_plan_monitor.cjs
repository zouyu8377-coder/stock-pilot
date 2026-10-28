const { chromium } = require('playwright');
const assert = require('assert/strict');
(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    const state = { status: 'completed', settings: { enabled: true, external_only: true }, board: { checked_at: '2026-09-22T10:00:00+08:00', research: [], plans: [{
      scope: 'symbol:603259', target: '603259', level: 'symbol', version: 1, state: 'discussion_required', reason: '计划条件成立，需要重新讨论', next_action: '核验订单与价格变化', mode: 'all', triggered_actions: ['重新评估原计划，不自动交易'],
      conditions: [{ label: '测试趋势条件', symbol: '603259', metric: 'price_vs_ma20_pct', operator: 'lt', threshold: -5, value: -8, as_of: '2026-09-22', state: 'met' }],
      operation_review: { boundary: '净变化不是逐笔成交', items: [{ symbol: '603259', before: 100, after: 200, delta: 100, assessment: '执行意图待确认' }] },
      performance_review: { price_return_pct: 2, relative_return_pct: 1, trading_days: 5, through: '2026-09-22', boundary: '价格表现不是决策成败' }
    }] } };
    await page.route('**/api/**', route => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith('/plans/monitor')) return route.fulfill({ json: { data: state } });
      if (path.endsWith('/plans')) return route.fulfill({ json: { data: { plans: {}, needs: [], memories: [], history: [] } } });
      if (route.request().method() !== 'GET') return route.abort();
      return route.continue();
    });
    await page.goto('http://127.0.0.1:5173/');
    await page.getByText('计划条件成立，需要重新讨论', { exact: true }).waitFor();
    await page.getByText('条件与证据 · 同时满足', { exact: true }).click();
    await page.getByText('执行变化与阶段复盘', { exact: true }).click();
    for (const [name, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
      await page.setViewportSize({ width, height });
      await page.getByRole('heading', { name: '计划巡检与复盘', exact: true }).scrollIntoViewIfNeeded();
      await page.screenshot({ path: `logs/plan-monitor-${name}.png` });
      assert.equal(await page.locator('body').evaluate(el => el.scrollWidth > innerWidth + 1), false);
    }
    await page.getByRole('button', { name: '讨论并修正计划', exact: true }).click();
    assert.equal(await page.getByLabel('标的代码（6位）').inputValue(), '603259');
    assert((await page.getByLabel('讨论问题').inputValue()).includes('最新检查'));
    await page.getByRole('button', { name: '立即检查（不调用模型）', exact: true }).click();
    assert.deepEqual(errors, []);
    console.log('Monitor evidence, performance, discussion handoff and desktop/mobile layout passed; API writes mocked.');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
