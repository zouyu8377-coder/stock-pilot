const { chromium } = require('playwright');
const assert = require('assert/strict');
(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    const state = { revision: 0, plans: {}, memories: [], needs: [], history: [] };
    let confirmed = false;
    const content = { thesis: '测试计划，不是投资建议', stance: 'wait', horizon: '季度', rationale: '测试材料',
      counter_evidence: '订单未确认', entry_condition: '取得原文', exit_condition: '逻辑失效', risk_budget: '用户设定',
      next_check: '核验订单', review_on: '2026-09-22', confidence: 'low', confidence_reason: '待核验', evidence_refs: [] };
    await page.route('**/api/**', route => {
      const req = route.request(), path = new URL(req.url()).pathname;
      if (path === '/api/agent/review/plans') return route.fulfill({ json: { data: state } });
      if (path.endsWith('/plans/export')) return route.fulfill({ json: { data: { request_id: 'test', prompt: 'TEST ONLY', expires_at: '2026-09-22' } } });
      if (path.endsWith('/plans/import')) {
        if (!req.postDataJSON().confirm) return route.fulfill({ json: { data: { status: 'preview', discussion: { level: 'symbol', target: '603259' }, before: null, after: { conclusion: '测试结论', plan: content, research: [], lesson_candidates: [] }, warning: '不会调整真实持仓' } } });
        confirmed = true;
        state.plans['symbol:603259'] = { level: 'symbol', target: '603259', version: 1, content };
        return route.fulfill({ json: { data: { status: 'confirmed' } } });
      }
      if (req.method() !== 'GET') return route.abort();
      return route.continue();
    });
    await page.goto('http://127.0.0.1:5173/');
    await page.getByRole('tab', { name: '具体标的' }).click();
    await page.getByLabel('标的代码（6位）').fill('603259');
    await page.getByLabel('讨论问题').fill('是否继续持有？');
    await page.getByRole('button', { name: '生成讨论包', exact: true }).click();
    await page.getByRole('button', { name: '复制提示词', exact: true }).waitFor();
    await page.getByLabel('讨论结果 JSON', { exact: true }).fill('{}');
    await page.getByRole('button', { name: '校验并预览草案' }).click();
    await page.getByText('新计划草案', { exact: true }).waitFor();
    assert.equal(confirmed, false);
    for (const [name, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
      await page.setViewportSize({ width, height });
      await page.getByText('待确认修改', { exact: true }).scrollIntoViewIfNeeded();
      await page.screenshot({ path: `logs/investment-plans-${name}.png` });
      assert.equal(await page.locator('body').evaluate(el => el.scrollWidth > innerWidth + 1), false);
    }
    await page.getByRole('button', { name: '确认保存计划与研究清单' }).click();
    await page.getByText('已确认保存，真实持仓未修改', { exact: true }).waitFor();
    assert(confirmed);
    await page.getByText('603259 · 等待 · 第1版', { exact: true }).waitFor();
    assert.deepEqual(errors, []);
    console.log('Plan scopes, discussion export, preview/confirmation and desktop/mobile layout passed; all writes mocked.');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
