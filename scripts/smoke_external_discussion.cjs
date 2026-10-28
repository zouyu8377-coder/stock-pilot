const { chromium } = require('playwright');
const assert = require('assert/strict');
(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    const change = { id: 'demo', operation: 'add', kind: 'followup', level: 'symbol', target: '603259', conclusion: '核对订单披露后继续讨论', reasoning: '尚缺原文证据', confidence: 'low', confidence_reason: '缺少最近公告', trigger: '公告更新', invalidation: '订单证据被否定', evidence_refs: [] };
    const result = { summary: '模拟外部讨论结论，仅用于界面测试', provider: 'test', changes: [change], sources: [], result_id: 'demo' };
    let data = { manifest: null, records: { entities: {}, results: [] }, incoming: { status: 'waiting' }, directory: 'C:/Project/Stock-Pilot/backend/data/external_discussion/current', stale: false };
    await page.route('**/api/**', route => {
      const path = new URL(route.request().url()).pathname;
      if (path.includes('/discussion')) {
        if (path.endsWith('/start')) data = { ...data, manifest: { context_version: 1, created_at: '2026-09-22T12:00:00+08:00' }, prompt: 'Discussion prompt' };
        if (path.endsWith('/import')) data.incoming = { status: 'preview', digest: 'checksum', result, diff: [{ before: null, after: change }], warning: '确认不会更新实际持仓' };
        if (path.endsWith('/confirm')) data = { ...data, incoming: { status: 'confirmed' }, records: { entities: { demo: { ...change, active: true } }, results: [{ ...result, confirmed_at: '2026-09-22T12:10:00+08:00' }] } };
        return route.fulfill({ json: { data } });
      }
      if (route.request().method() !== 'GET') return route.abort();
      return route.continue();
    });
    await page.goto('http://127.0.0.1:5173/');
    await page.getByRole('heading', { name: '投资讨论工作台' }).waitFor();
    await page.getByRole('button', { name: '生成讨论包', exact: true }).click();
    await page.getByText('资料版本 1', { exact: false }).waitFor();
    await page.getByText('粘贴外部模型结果', { exact: true }).click();
    await page.getByLabel('回传 JSON').fill('{}');
    await page.getByRole('button', { name: '校验并预览', exact: true }).click();
    await page.getByRole('heading', { name: '待确认结果 · test' }).waitFor();
    await page.getByRole('button', { name: '确认记录，不变更持仓' }).click();
    await page.getByText('核对订单披露后继续讨论', { exact: true }).waitFor();
    for (const [name, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
      await page.setViewportSize({ width, height });
      await page.getByRole('heading', { name: '投资讨论工作台' }).scrollIntoViewIfNeeded();
      await page.screenshot({ path: `logs/external-discussion-${name}.png` });
      assert.equal(await page.locator('body').evaluate(el => el.scrollWidth > innerWidth + 1), false);
    }
    assert.deepEqual(errors, []);
    console.log('Discussion export, preview, confirmation and desktop/mobile layouts passed. Writes mocked.');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
