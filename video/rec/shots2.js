const { chromium } = require('playwright');
const path = require('path');
const R = 'https://mend.harunafaruk.com/app/runs/20261104-160433-bolonge';
const OUT = path.join(__dirname, '..', '..', 'frontend', 'public', 'shots');
(async () => {
  const b = await chromium.launch({ proxy: { server: process.env.HTTPS_PROXY } });
  const c = await b.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  const p = await c.newPage();
  await p.goto(`${R}/review`, { waitUntil: 'load' }); await p.waitForTimeout(6000);
  // video stage with masks: the region between the pipeline column and the right panel, above the controls
  await p.screenshot({ path: `${OUT}/stage.png`, clip: { x: 281, y: 196, width: 778, height: 438 } });
  await p.locator('button:visible:has-text("D001")').first().click(); await p.waitForTimeout(3500);
  const aside = await p.evaluate(() => { const r = [...document.querySelectorAll('img')].find(i => /D001\.jpg/.test(i.src))?.closest('div.h-full')?.getBoundingClientRect(); return r && { x: r.x, y: r.y, w: r.width, h: r.height }; });
  console.log('aside', aside);
  await p.screenshot({ path: `${OUT}/defect.png`, clip: { x: 1061, y: 205, width: 379, height: 695 } });
  const a = await b.newContext({ viewport: { width: 1000, height: 640 }, deviceScaleFactor: 2 });
  const q = await a.newPage();
  await q.goto(`${R}/ask`, { waitUntil: 'load' }); await q.waitForTimeout(2500);
  await q.locator('input[placeholder^="Ask"]').fill('Which site should we fix first, and what will it cost?');
  await q.keyboard.press('Enter'); await q.waitForTimeout(22000);
  await q.screenshot({ path: `${OUT}/ask.png` });
  await b.close();
})();
