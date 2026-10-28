const { chromium } = require('playwright');
const assert = require('assert/strict');
(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [], writes = [];
    page.on('pageerror', e => errors.push(e.message));
    const item = { id: '603259', symbol: '603259', name: '测试药明', version: 'v1', state: 'pending', needs_refresh: false,
      related: [], history: [], unanswered: 1, primary: { action_semantics: '维持现仓，等待订单证据更新', conclusion: '测试结论，不是投资建议',
        technical_analysis: '量价测试事实', news_analysis: '公告测试事实', confidence: 'medium', confidence_reason: '订单尚未核验',
        decision_basis: ['已取得测试公告'], trigger_condition: '下一交易日收盘', evidence_refs: [], invalidation_conditions: [] } };
    const workbench = { actions: [item], dossiers: [{ symbol: item.symbol, name: item.name, documents: [], tasks: [], questions: [
      { question: '订单是否改善？', status: 'material_found', sources: [], next_step: '核验订单原文', checked_at: new Date().toISOString() }
    ] }], needs_refresh: false };
    await page.route('**/api/**', async route => {
      const req = route.request(), url = new URL(req.url());
      if (url.pathname === '/api/agent/review/workbench') return route.fulfill({ json: { data: workbench } });
      if (req.method() === 'GET') return route.continue();
      writes.push(url.pathname);
      if (url.pathname.endsWith('/response')) {
        const body = req.postDataJSON();
        if (body.state === 'dismissed' && !body.note) return route.fulfill({ status: 409, json: { detail: '暂不采纳必须说明原因' } });
        item.state = body.state;
        return route.fulfill({ json: { data: {} } });
      }
      if (url.pathname === '/api/portfolio/simulate') return route.fulfill({ json: { data: {
        before: { cash_ratio_pct: 10, invested_ratio_pct: 90, position_weights: [{ symbol: item.symbol, weight_pct: 20 }] },
        after: { cash_ratio_pct: 15, invested_ratio_pct: 85, position_weights: [{ symbol: item.symbol, weight_pct: 15 }] }, warnings: [], risk_notes: []
      } } });
      return route.abort();
    });
    await page.goto('http://127.0.0.1:5173/', { waitUntil: 'domcontentloaded' });
    await page.getByText('当前建议：维持现仓，等待订单证据更新', { exact: true }).waitFor({ timeout: 90000 });
    await page.getByRole('button', { name: '更新账户', exact: true }).waitFor();
    await page.getByText('研究档案 · 1 个问题尚未得到原文验证', { exact: true }).click();
    await page.getByText('取得材料，问题待核验', { exact: true }).first().waitFor();
    await page.getByText('处理建议', { exact: true }).click();
    await page.getByRole('button', { name: '暂不采纳', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: '暂不采纳必须说明原因' }).waitFor();
    await page.getByLabel('测试药明处理原因').fill('等待季度订单披露');
    await page.getByRole('button', { name: '持续关注', exact: true }).click();
    await page.locator('article').filter({ hasText: '测试药明' }).getByText('持续关注', { exact: true }).first().waitFor();
    await page.getByText('调整预案（只读模拟）', { exact: true }).click();
    await page.getByLabel('数量', { exact: true }).fill('100');
    await page.getByLabel('预估成交价', { exact: true }).fill('150');
    await page.getByRole('button', { name: '计算账户影响' }).click();
    await page.getByText('该标的权重 20% → 15%', { exact: true }).waitFor();
    for (const [name, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
      await page.setViewportSize({ width, height });
      await page.getByText('当前建议：维持现仓，等待订单证据更新', { exact: true }).scrollIntoViewIfNeeded();
      await page.screenshot({ path: `logs/research-workbench-${name}.png` });
      assert.equal(await page.locator('body').evaluate(el => el.scrollWidth > innerWidth + 1), false, name + ' horizontal overflow');
    }
    assert(writes.every(p => p.endsWith('/response') || p === '/api/portfolio/simulate'));
    assert.deepEqual(errors, []);
    console.log('Research workbench desktop/mobile: dossier, disposition validation and readonly preview passed. All writes mocked; no model calls.');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
