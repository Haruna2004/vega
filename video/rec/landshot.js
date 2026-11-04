const { chromium, devices } = require('playwright');
(async () => {
  const S = process.argv[2];
  const b = await chromium.launch({ proxy: { server: process.env.HTTPS_PROXY } });
  for (const [n, opt] of [["land_d", { viewport: { width: 1440, height: 9000 } }], ["land_m", { viewport: { width: 390, height: 12000 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true }]]) {
    const c = await b.newContext({ ...opt, ignoreHTTPSErrors: true }); const p = await c.newPage();
    await p.goto('https://mend.harunafaruk.com/', { waitUntil: 'networkidle' });
    for (let y = 0; y < 12000; y += 600) { await p.mouse.wheel(0, 600); await p.waitForTimeout(120); }
    await p.waitForTimeout(1500);
    await p.screenshot({ path: `${S}/${n}.png`, fullPage: true });
    const w = await p.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]); console.log(n, 'scrollW/innerW', w);
  }
  await b.close();
})();
