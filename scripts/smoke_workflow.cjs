const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    let started = false;
    let polls = 0;
    let submissions = 0;
    await page.route('**/api/agent/review/workflow', async route => {
      if (route.request().method() === 'POST') { started = true; submissions++; }
      const status = started ? (++polls >= 3 ? 'completed' : 'running') : 'idle';
      await route.fulfill({ json: { success: true, data: {
        job_id: 'smoke-only', status,
        source: 'premarket', stage: 'inspect', detail: '测试公告取证', completed_items: 1, total_items: 3, elapsed_seconds: 30,
        steps: ['inspect', 'analyze', 'advise', 'review'].map(key => ({ key, status: status === 'completed' ? 'completed' : 'pending' })),
      } } });
    });
    await page.goto('http://127.0.0.1:5173/', { waitUntil: 'domcontentloaded' });
    const start = page.getByRole('button', { name: '巡检并分析', exact: true });
    await start.waitFor({ timeout: 90000 });
    await start.click({ timeout: 90000 });
    await page.getByRole('button', { name: '查看运行进度', exact: true }).click();
    if (submissions !== 1) throw new Error('Opening progress submitted duplicate analysis');
    await start.waitFor({ timeout: 20000 });
    await page.getByText('驾驶舱加载中...', { exact: true }).waitFor({ state: 'hidden', timeout: 90000 });
    for (const heading of ['账户概览', '账户调整建议', '潜在机会', '执行与监控清单']) {
      await page.getByRole('heading', { name: heading, exact: true }).waitFor();
    }
    await page.screenshot({ path: path.resolve('logs/workflow-desktop.png'), fullPage: false });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.resolve('logs/workflow-mobile.png'), fullPage: false });
    const panelOverflow = await page.getByText('决策工作台', { exact: true }).evaluate(el => {
      const section = el.closest('section');
      return section.scrollWidth > section.clientWidth + 1;
    });
    if (panelOverflow) throw new Error('Workflow panel overflows at mobile width');
    if (errors.length) throw new Error(errors.join('\n'));
    console.log('Desktop/mobile workflow passed; model request mocked, no account mutation.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
