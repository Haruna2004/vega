const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ proxy: { server: process.env.HTTPS_PROXY }, args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 }, ignoreHTTPSErrors: true });
  for (const [n, u] of process.argv.slice(2).map(x => x.split('='))) {
    await p.goto('https://mend.harunafaruk.com' + u, { waitUntil: 'networkidle' }).catch(() => {});
    await p.waitForTimeout(3000);
    await p.screenshot({ path: `/tmp/claude-0/-home-user-vega/a003190a-7334-5e5d-bf80-bcfd1661f4c9/scratchpad/${n}.png` });
  }
  await b.close();
})();
