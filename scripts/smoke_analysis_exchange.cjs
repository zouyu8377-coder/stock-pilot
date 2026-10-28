const { chromium } = require('playwright');
const assert = require('assert/strict');
(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    const item = { item_id: 'i1', subject: '保险板块潜在机会', conclusion: '测试机会', confidence: 'medium', evidence_refs: ['rotation:insurance'], counter_evidence_refs: [], action_semantics: '核查份额', invalidation_conditions: ['量能下降'], target_symbols: ['512070'], suggested_action: 'watch', trigger_condition: '份额增加' };
    const review = { headline: '测试分析', summary: '测试摘要', opportunities: [item], risks: [], watch_items: [], data_status: { usable: true }, verification_tasks: [] };
    const task = { task_id: 'test-task', subject: item.subject, task: '补查保险ETF份额', target_symbols: ['512070'], success_criteria: '取得近5日份额', missing_evidence: ['ETF份额'], status: 'pending', attempt_count: 0, tool: { auto_executable: true, mapping_reason: '', label: '取证' } };
    await page.route('**/api/agent/review/latest', r => r.fulfill({ json: { data: { run_id: 'test', completed_at: new Date().toISOString(), review } } }));
    await page.route('**/api/rotation/summary', r => r.fulfill({ json: { data: { as_of: new Date().toISOString().slice(0, 10), potential_opportunities: [{ sector_id: 'insurance', name: '保险', data_quality: 'complete' }], early_turning: [], wait_pullback: [] } } }));
    await page.route('**/api/agent/review/tasks', r => r.fulfill({ json: { items: [task] } }));
    await page.route('**/api/agent/review/tasks/test-task/execute', r => { task.status = 'completed'; return r.fulfill({ json: { data: task } }); });
    await page.route('**/api/agent/review/workflow', r => r.fulfill({ json: { data: { status: 'idle', steps: [] } } }));
    await page.route('**/api/agent/review/exchange/export', r => r.fulfill({ json: { data: { request_id: 'test', prompt: 'test-prompt', local_path: 'test-only.json' } } }));
    let imports = 0;
    await page.route('**/api/agent/review/exchange/import', r => {
      const body = r.request().postDataJSON(); imports++;
      return r.fulfill({ json: { data: body.confirm ? { status: 'imported' } : { status: 'preview', review, warnings: [] } } });
    });
    await page.goto('http://127.0.0.1:5173/', { waitUntil: 'domcontentloaded' });
    await page.getByText('补查保险ETF份额', { exact: true }).waitFor({ timeout: 90000 });
    const opportunities = page.getByRole('heading', { name: '潜在机会', exact: true }).locator('xpath=ancestor::section[1]');
    assert.equal(await opportunities.getByText('保险', { exact: true }).count(), 0);
    await page.getByRole('button', { name: '立即核查', exact: true }).click();
    await page.getByText('保险板块潜在机会 · 已取得证据', { exact: true }).waitFor();
    await page.getByText('外部分析 · 导出与回传', { exact: true }).click();
    await page.getByRole('button', { name: '生成分析请求', exact: true }).click();
    await page.getByText('本地请求：test-only.json', { exact: true }).waitFor();
    await page.getByRole('textbox', { name: '分析结果 JSON', exact: true }).fill('{}');
    await page.getByRole('button', { name: '校验并预览', exact: true }).click();
    await page.getByRole('button', { name: '确认导入分析与任务', exact: true }).click();
    await page.getByText('分析结果已导入，持仓未修改', { exact: true }).waitFor();
    assert.equal(imports, 2);
    for (const [name, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
      await page.setViewportSize({ width, height });
      await page.getByText('外部分析 · 导出与回传', { exact: true }).scrollIntoViewIfNeeded();
      await page.screenshot({ path: `logs/exchange-${name}.png` });
      const overflow = await page.getByRole('heading', { name: '决策工作台', exact: true }).evaluate(el => { const s = el.closest('section'); return s.scrollWidth > s.clientWidth + 1; });
      assert.equal(overflow, false);
    }
    assert.deepEqual(errors, []);
    console.log('Task action, deduplication, preview/confirm and responsive exchange tests passed (mocked, no model or account writes).');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
