const { chromium } = require('playwright');
const assert = require('assert/strict');
const fs = require('fs');

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  try {
    fs.mkdirSync('logs', { recursive: true });
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const at = new Date().toISOString();
    const finding = { level: 'account', target: '验收合成账户', action: 'hold', conclusion: '界面验收示例：维持现金缓冲，条件未满足不扩大风险敞口。', reasoning: '这是一条模拟模型回复，仅用于交互测试，不是实时投资分析。', confidence: 'medium', confidence_reason: '财报原文已取得，政策影响尚未核实。', trigger: '趋势与经营证据共同改善', invalidation: '出现经营反证', horizon: '未来一周', evidence_refs: ['market:600036'] };
    const report = { summary: '界面验收：账户参数与独立证据共同形成判断，非真实建议。', account_state: 'attention', findings: [finding, { ...finding, level: 'symbol', target: '600036' }], unresolved: ['部分政策消息未验证'], lessons: ['本示例仅用于UI测试'], external_sources: [] };
    const settings = { api_enabled: false, codex_model: '', web_search: true, auto_apply_verified_holdings: true };
    const data = { run: null, settings, providers: { codex: { installed: true }, api: { configured: true, enabled: false } }, account_fingerprint: 'fingerprint', confirmed: [], account_updates: [] };
    const businessStatus = { checked_at: at, target_date: at.slice(0, 10), account_snapshot_at: at, sources: [], assistants: {
      dashboard: { level: 'green', text: '就绪', reasons: ['资料与分析入口可用'] },
      portfolio: { level: 'green', text: '重点资料就绪', reasons: ['狭义覆盖有效；广义覆盖不足不参与健康判定'] },
      discovery: { level: 'red', text: '模型不可用', reasons: ['未配置分析入口'] }
    }, coverage: { narrow: { healthy: true, tracked_count: 1, covered_count: 1, missing_groups: [], boundary: 'UI fixture: narrow coverage is not market breadth.',
      items: [{ symbol: '600036', name: '验收样本', fresh: true, observed_at: at.slice(0, 10) }], references: [{ symbol: '^IXIC', name: '纳斯达克综合指数', fresh: true, observed_at: at }] },
      broad: { covered_count: 18, universe_count: 4698, coverage_pct: 0.38, as_of: at.slice(0, 10) } }, startup: { launched_at: at }, backfill: { completed_count: 20, total_symbols: 6000, remaining_count: 5980 } };
    const baseRun = () => ({ run_id: 'a'.repeat(32), status: 'awaiting_confirmation', provider: 'codex', created_at: at, updated_at: at, heartbeat_at: at, model_calls: 1, max_model_calls: 3, tool_requests: 1, max_tool_requests: 4, tokens: { input_tokens: 100, output_tokens: 200 }, context_version: 2, account_fingerprint: 'fingerprint', report_digest: 'b'.repeat(64), report, activity: '分析完成，等待确认记录', events: [{ id: 'step1', actor: 'agent1', title: '真实工具调用（测试替身）', detail: '本脚本所有写入和模型回复均被mock。', at }], data_summary: { prepared_at: at, account_snapshot_at: at, target_date: at.slice(0, 10), collection_account_matches: true, positions: [{ symbol: '600036', name: '验收样本', watchlist: false }], metrics: { total_assets: 10000, account_pnl: -100, cash_pct: 50, unpriced_holdings: [] }, source_status: [{ source: 'disclosures', status: 'partial', finished_at: at, failures: [{ symbol: '600036', reason: '测试缺口' }], coverage: [{ symbol: '600036', annual_report_found: true, index_count: 3 }] }], evidence: [{ id: 'market:600036', symbol: '600036', kind: 'market', source: 'test fixture' }] } });
    const writes = [];
    await page.route('**/api/**', async route => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      if (!path.startsWith('/api/')) return route.continue();
      if (path.startsWith('/api/investment-agents')) {
        if (request.method() !== 'GET') writes.push(path);
        if (path.endsWith('/assistant-status')) return route.fulfill({ json: { data: businessStatus } });
        if (path.endsWith('/runs') && request.method() === 'POST') {
          assert.equal(request.postDataJSON().consent, true);
          data.run = baseRun();
          return route.fulfill({ json: { data: data.run } });
        }
        if (path.endsWith('/confirm')) { data.run.status = 'confirmed'; data.confirmed = [{ ...data.run, confirmed_at: at }]; return route.fulfill({ json: { data: data.run } }); }
        if (path.endsWith('/cancel')) { data.run.status = 'cancelled'; return route.fulfill({ json: { data: data.run } }); }
        if (path.endsWith('/settings')) { Object.assign(settings, request.postDataJSON()); return route.fulfill({ json: { data: settings } }); }
        if (path.endsWith('/history')) return route.fulfill({ json: { data: data.confirmed } });
        if (path.includes('/evidence/')) return route.fulfill({ json: { data: { id: 'market:600036', facts: { price: 10, source: 'test fixture' } } } });
        return route.fulfill({ json: { data } });
      }
      assert.equal(request.method(), 'GET', `Unexpected legacy write: ${path}`);
      if (path === '/api/portfolio') return route.fulfill({ json: { data: { snapshot: { positions: [], cash_available: 0, risk_limits: {} }, metrics: { position_weights: [], missing_data: [] } } } });
      if (path === '/api/portfolio/dashboard') return route.fulfill({ json: { data: { positions: [] } } });
      if (path === '/api/portfolio/semantic-suggestions') return route.fulfill({ json: { items: [] } });
      if (path === '/api/portfolio/import/parser-providers') return route.fulfill({ json: { data: { providers: [] } } });
      if (path === '/api/rotation/summary') return route.fulfill({ json: { data: { sectors: [], summary: {}, boundary: 'UI fixture' } } });
      return route.fulfill({ json: { data: {} } });
    });
    await page.goto('http://127.0.0.1:5173/');
    await page.waitForTimeout(800);
    if (!await page.getByRole('heading', { name: '投资工作台', exact: true }).isVisible()) {
      console.log('Initial page diagnostics:', JSON.stringify(errors), (await page.locator('body').innerText()).slice(0, 2500));
      await page.screenshot({ path: 'logs/investment-agents-load-diagnostic.png' });
    }
    await page.getByRole('heading', { name: '投资工作台', exact: true }).waitFor();
    const start = page.getByRole('button', { name: '更新资料并分析', exact: true });
    await page.waitForTimeout(500);
    assert.equal(await start.isDisabled(), true);
    assert.equal(writes.length, 0, 'Opening a page must not invoke a model');
    await page.getByLabel('驾驶舱助手：就绪', { exact: true }).hover();
    await page.getByRole('tooltip').waitFor();
    assert.match(await page.getByRole('tooltip').innerText(), /工作状态/);
    await page.mouse.move(0, 150);
    await page.getByRole('checkbox', { name: /允许向所选模型发送/ }).check();
    await start.click();
    await page.getByRole('button', { name: '确认记录判断与计划', exact: true }).waitFor();
    assert.doesNotMatch(await page.locator('body').innerText(), /Agent\s*[12]/i, 'Implementation roles must not be exposed as page sections');
    const discard = page.getByRole('button', { name: '放弃本次结果', exact: true });
    assert.equal(await discard.getAttribute('type'), 'button');
    assert.equal(await discard.evaluate(element => getComputedStyle(element).borderTopStyle), 'solid');
    assert.ok((await discard.boundingBox()).width > 120);
    await page.getByRole('tab', { name: /标的计划/ }).click();
    await page.getByRole('heading', { name: '验收样本 600036', exact: true }).waitFor();
    await page.getByRole('tab', { name: /账户建议/ }).click();
    await page.getByRole('tab', { name: /账户建议/ }).press('ArrowRight');
    assert.equal(await page.getByRole('tab', { name: /行业方向/ }).getAttribute('aria-selected'), 'true');
    await page.getByRole('tab', { name: /行业方向/ }).press('Home');
    await page.getByText('判断依据、信心与反证', { exact: true }).first().click();
    await page.getByRole('button', { name: 'market:600036', exact: true }).first().click();
    await page.getByRole('heading', { name: /原始证据/ }).waitFor();
    for (const [name, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844], ['small', 320, 760]]) {
      await page.setViewportSize({ width, height });
      await page.evaluate(() => scrollTo(0, 0));
      await page.screenshot({ path: `logs/investment-agents-${name}.png`, fullPage: true });
      assert.equal(await page.locator('body').evaluate(element => element.scrollWidth > innerWidth + 1), false, name);
      const eye = await page.getByRole('button', { name: '隐藏账户信息', exact: true }).boundingBox();
      assert.ok(eye.x >= 0 && eye.x + eye.width <= width, `${name}: privacy control must stay in viewport`);
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    await discard.click();
    assert.equal(data.run.status, 'cancelled');
    await start.click();
    const writesBeforePrivacy = writes.length;
    await page.getByRole('button', { name: '隐藏账户信息', exact: true }).click();
    assert.equal(await page.getByRole('tabpanel').count(), 1);
    assert.equal(await page.getByLabel('投资分析议题').count(), 1);
    assert.match(await page.getByLabel('账户基础数据').innerText(), /\*\*\*\*/);
    assert.equal(await page.getByLabel('账户基础数据').locator('dd').filter({ hasText: /^\*\*\*\*$/ }).count(), 4);
    await page.screenshot({ path: 'logs/investment-agents-metrics-hidden.png' });
    assert.match(await page.locator('body').innerText(), /验收合成账户/, 'Analysis must remain visible when only metrics are masked');
    await page.getByRole('button', { name: '资料采集', exact: true }).click();
    await page.getByRole('heading', { name: '账户与资料状态', exact: true }).waitFor();
    await page.getByRole('heading', { name: '狭义广度 · 重点资料覆盖', exact: true }).waitFor();
    await page.getByRole('heading', { name: '广义广度 · 全市场覆盖', exact: true }).waitFor();
    assert.match(await page.getByLabel('持仓资料状态').innerText(), /数据健康/);
    assert.match(await page.getByLabel('持仓资料状态').innerText(), /0.38%/);
    await page.getByText('查看逐项时效与缺口', { exact: true }).click();
    await page.screenshot({ path: 'logs/data-coverage-desktop.png', fullPage: true });
    await page.setViewportSize({ width: 320, height: 760 });
    assert.equal(await page.locator('body').evaluate(element => element.scrollWidth > innerWidth + 1), false);
    await page.screenshot({ path: 'logs/data-coverage-mobile.png', fullPage: true });
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.getByRole('button', { name: '发现与研究', exact: true }).click();
    assert.equal(await page.getByRole('button', { name: '显示账户信息', exact: true }).getAttribute('aria-pressed'), 'true');
    await page.getByRole('button', { name: '驾驶舱', exact: true }).click();
    await page.reload();
    await page.getByRole('button', { name: '显示账户信息', exact: true }).waitFor();
    await page.getByRole('tab', { name: /账户建议/ }).waitFor();
    assert.equal(await page.getByLabel('账户基础数据').locator('dd').filter({ hasText: /^\*\*\*\*$/ }).count(), 4, 'Metric masking must survive reload');
    assert.equal(writes.length, writesBeforePrivacy, 'Privacy must not mutate account, task or model settings');
    await page.getByRole('button', { name: '显示账户信息', exact: true }).click();
    await page.getByRole('tab', { name: /账户建议/ }).waitFor();
    await page.getByRole('button', { name: '确认记录判断与计划', exact: true }).click();
    await page.getByText('已记录', { exact: true }).waitFor();
    assert.equal(data.confirmed.length, 1);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.getByText('运行设置与账户入账审计', { exact: true }).click();
    await page.getByPlaceholder('留空使用默认').fill('ui-unsaved-model');
    await page.waitForTimeout(2800);
    assert.equal(await page.getByPlaceholder('留空使用默认').inputValue(), 'ui-unsaved-model', 'Polling must not discard unsaved edits');
    await page.getByRole('button', { name: '保存运行设置', exact: true }).click();
    assert.equal(settings.codex_model, 'ui-unsaved-model');
    assert.deepEqual(errors, []);
    console.log('PASS: read-only status lights, no inference on load, consent, start/discard, structured discussion tabs, evidence, privacy across tabs/reload, human recording, settings, and 1440/390/320px layouts. All writes/model responses mocked.');

    if (process.env.REAL_READONLY === '1') {
      const actual = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
      const actualErrors = [];
      actual.on('pageerror', error => actualErrors.push(error.message));
      await actual.route('**/api/**', route => route.request().method() === 'GET' ? route.continue() : route.abort());
      await actual.goto('http://127.0.0.1:5173/');
      await actual.getByRole('heading', { name: '投资工作台', exact: true }).waitFor();
      await actual.getByRole('heading', { name: '投资判断与行动计划', exact: true }).waitFor({ timeout: 30000 });
      await actual.getByRole('tab', { name: /账户建议/ }).waitFor({ timeout: 30000 });
      await actual.screenshot({ path: 'logs/investment-agents-real-readonly.png', fullPage: true });
      assert.deepEqual(actualErrors, []);
      console.log('PASS: actual persisted Codex analysis rendered with GET-only access; no model invocation, confirmation or account mutation.');
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
