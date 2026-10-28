const { chromium } = require('playwright');
const assert = require('assert/strict');
const fs = require('fs');
const path = require('path');

const base = process.env.DEMO_URL || 'http://127.0.0.1:8010';
const prefix = '/api/demo/collaboration';

(async () => {
  fs.mkdirSync(path.resolve('logs'), { recursive: true });
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const page = await context.newPage();
    const errors = [];
    const privateCalls = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {
      const url = new URL(request.url());
      if (url.pathname.startsWith('/api/') && !url.pathname.startsWith(prefix)) privateCalls.push(url.pathname);
    });
    async function state() {
      const id = await page.evaluate(() => localStorage.getItem('stock-pilot-collaboration-demo-run'));
      const response = await context.request.get(`${base}${prefix}/runs/${id}`);
      assert.equal(response.status(), 200);
      return (await response.json()).data;
    }
    await page.goto(`${base}/demo.html`);
    await page.getByRole('heading', { name: '证据协作工作台' }).waitFor();
    await page.getByRole('button', { name: '新建演示', exact: true }).waitFor({ state: 'visible' });

    for (const scenario of ['evidence_gap', 'sufficient', 'stale_handoff', 'conflicting_evidence', 'tool_failure', 'unavailable', 'permission_blocked']) {
      await page.getByLabel('演示场景').selectOption(scenario);
      await page.getByRole('button', { name: '新建演示', exact: true }).click();
      await page.getByRole('button', { name: '运行至待确认', exact: true }).click();
      const confirm = page.getByRole('button', { name: '确认演示结论，不变更持仓', exact: true });
      await confirm.waitFor();
      const run = await state();
      assert.equal(run.phase, 'awaiting_confirmation');
      assert.equal(run.model_calls, 0);
      assert.equal(run.confirmed_report, null);
      assert.equal(run.context.payload.account.synthetic, true);
      if (scenario === 'stale_handoff') assert.ok(run.events.some(event => event.kind === 'rejected'));
      if (scenario === 'conflicting_evidence') assert.match(run.pending_report.report.summary, /现金流下降/);
      if (scenario === 'unavailable') assert.ok(run.events.some(event => event.kind === 'tool_exhausted'));
      if (scenario === 'evidence_gap') {
        for (const [name, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844], ['small', 320, 760]]) {
          await page.setViewportSize({ width, height });
          await page.evaluate(() => scrollTo(0, 0));
          await page.screenshot({ path: `logs/agent-demo-${name}.png`, fullPage: true });
          assert.equal(await page.locator('body').evaluate(element => element.scrollWidth > innerWidth + 1), false, name);
        }
        await page.setViewportSize({ width: 1440, height: 1000 });
      }
      await confirm.click();
      await page.getByRole('heading', { name: '已确认演示结论', exact: true }).waitFor();
      assert.equal((await state()).phase, 'confirmed');
    }
    await page.reload();
    await page.getByRole('heading', { name: '已确认演示结论', exact: true }).waitFor();

    // A human-pasted response exercises the same schema without calling an LLM.
    await page.getByRole('radio', { name: '手动外部模型', exact: true }).check();
    await page.getByLabel('演示场景').selectOption('evidence_gap');
    await page.getByRole('button', { name: '新建演示', exact: true }).click();
    await page.getByRole('heading', { name: '外部模型交接', exact: true }).waitFor();
    let run = await state();
    const envelope = current => ({ run_id: current.run_id, context_version: current.context.version, context_fingerprint: current.context.fingerprint, response_id: `browser-${current.revision}`, provider: 'manual-ui-test-not-a-model' });
    await page.getByLabel('外部分析侧 JSON 回传').fill(JSON.stringify({ ...envelope(run), action: 'request_evidence', requests: [{ tool: 'market', symbols: ['600519', '600036', '510300'], reason: 'Verify deterministic demo weights' }] }));
    await page.getByRole('button', { name: '校验回传', exact: true }).click();
    await page.getByRole('button', { name: '运行至待确认', exact: true }).click();
    await page.getByText('等待外部模型回传', { exact: true }).waitFor();
    run = await state();
    assert.equal(run.context.version, 2);
    await page.getByLabel('外部分析侧 JSON 回传').fill(JSON.stringify({ ...envelope(run), action: 'final', report: { summary: 'Manual UI test, synthetic portfolio only', findings: [{ title: 'Weight arithmetic', conclusion: 'The sample position is 36.14% of the synthetic account', reasoning: '120000 / 332000, not a real investment conclusion', confidence: 'low', evidence_refs: ['E1'] }], unresolved: ['No real financial disclosure collected'] } }));
    await page.getByRole('button', { name: '校验回传', exact: true }).click();
    await page.getByRole('heading', { name: '待校验分析稿', exact: true }).waitFor();
    await page.getByRole('button', { name: '下一步', exact: true }).click();
    await page.getByRole('button', { name: '确认演示结论，不变更持仓', exact: true }).waitFor();
    assert.equal((await state()).pending_report.provider, 'manual-ui-test-not-a-model');
    await page.getByRole('button', { name: '确认演示结论，不变更持仓', exact: true }).click();
    await page.getByRole('heading', { name: '已确认演示结论', exact: true }).waitFor();
    if (process.env.DEMO_PUBLIC === '1') {
      await page.getByRole('radio', { name: '响应样本', exact: true }).check();
      await page.getByRole('checkbox', { name: '联网获取公开行情', exact: true }).check();
      await page.getByRole('button', { name: '新建演示', exact: true }).click();
      await page.getByRole('button', { name: '运行至待确认', exact: true }).click();
      await page.getByRole('button', { name: '确认演示结论，不变更持仓', exact: true }).waitFor();
      const live = await state();
      const quote = live.context.payload.evidence.find(item => item.tool === 'market');
      assert.equal(quote?.data.synthetic, false, 'Optional public quote must not silently fall back to synthetic data');
      assert.equal(quote?.data.source, 'tencent_public_quote');
      assert.equal(live.context.payload.evidence.find(item => item.tool === 'disclosure').data.synthetic, true);
      console.log('PASS: optional public quote collected through the UI; financial evidence remains synthetic.');
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(privateCalls, []);
    console.log('PASS: seven scenarios, manual evidence/final handoff, persistence, human gate, 1440/390/320px layouts. Real isolated API; zero LLM/private-account calls.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
