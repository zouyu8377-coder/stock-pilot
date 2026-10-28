const { chromium } = require('playwright');
const assert = require('assert/strict');
const live = process.argv.includes('--live');
(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    if (!live) await page.route('**/api/agent/review/latest', route => route.fulfill({ json: { data: {
      run_id: 'quality-layout-only', completed_at: new Date().toISOString(), review: {
        opportunities: [], watch_items: [], risks: [{ item_id: 'layout-risk', subject: '测试标的',
          suggested_action: 'wait', action_semantics: '维持现仓，暂不新增风险，等待量价确认。',
          conclusion: '版式测试，不是正式投资建议。', target_symbols: [], evidence_refs: [],
          invalidation_conditions: ['行业相对趋势转弱'], decision_basis: ['测试事实及其影响。'],
          confidence: 'medium', confidence_reason: '量价事实可用，缺少近期公告核验。',
          technical_analysis: '测试量价事实支持等待确认。', news_analysis: '消息面证据不足，待取得近期公告。',
          counter_scenario: '测试反向情景。', trigger_condition: '下次收盘检查量价', horizon: '下一交易日' }]
      }
    } } }));
    await page.goto('http://127.0.0.1:5173/', { waitUntil: 'domcontentloaded' });
    await page.getByRole('heading', { name: '账户调整建议', exact: true }).waitFor({ timeout: 90000 });
    await page.getByText('驾驶舱加载中...', { exact: true }).waitFor({ state: 'hidden', timeout: 90000 });
    assert.equal(await page.getByText('Network Error', { exact: true }).count(), 0);
    assert.equal(await page.getByText('公告核验出现持仓逻辑反证，需确认影响是否仍然成立。', { exact: true }).count(), 0);
    const reasons = page.getByText('技术面、消息面与判断依据', { exact: true });
    await reasons.first().waitFor({ timeout: 30000 });
    await reasons.first().click();
    if (!live) {
      await page.getByText('结论信心：中', { exact: true }).waitFor();
      await page.getByText('测试量价事实支持等待确认。', { exact: false }).waitFor();
      await page.getByText('消息面证据不足，待取得近期公告。', { exact: false }).waitFor();
    } else {
      const result = await (await page.request.get('http://127.0.0.1:8000/api/agent/review/latest')).json();
      const review = result.data.review;
      const items = [...review.risks, ...review.watch_items, ...review.opportunities];
      assert(items.length > 0);
      assert(items.every(item => item.technical_analysis && item.news_analysis && item.confidence_reason));
      console.log(`Live report ${result.data.run_id}: ${items.length} items with analysis facets.`);
    }
    for (const [name, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
      await page.setViewportSize({ width, height });
      await page.getByRole('heading', { name: '账户调整建议', exact: true }).scrollIntoViewIfNeeded();
      if (name === 'mobile') await reasons.first().evaluate(el => el.scrollIntoView({ block: 'center' }));
      await page.screenshot({ path: `logs/decision-quality-${live ? 'live-' : ''}${name}.png` });
      assert.equal(await page.getByRole('heading', { name: '决策工作台', exact: true }).evaluate(el => { const s = el.closest('section'); return s.scrollWidth > s.clientWidth + 1; }), false);
    }
    assert.deepEqual(errors, []);
    console.log(`Decision rationale layout passed at desktop/mobile widths (${live ? 'existing live analysis' : 'analysis mocked'}; no model calls or portfolio writes).`);
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
