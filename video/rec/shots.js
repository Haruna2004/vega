// Product screenshots for the landing page: node shots.js
const { chromium } = require('playwright');
const path = require('path');
const BASE = 'https://mend.harunafaruk.com';
const R = `${BASE}/app/runs/20261104-160433-bolonge`;
const OUT = path.join(__dirname, '..', '..', 'frontend', 'public', 'shots');

(async () => {
  require('fs').mkdirSync(OUT, { recursive: true });
  const b = await chromium.launch({ proxy: { server: process.env.HTTPS_PROXY }, args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, ignoreHTTPSErrors: true });
  const p = await ctx.newPage();
  const go = async (u, ms = 4000) => { await p.goto(u, { waitUntil: 'load' }).catch(() => {}); await p.waitForTimeout(ms); };
  const shot = (n, clip) => p.screenshot({ path: path.join(OUT, n + '.png'), clip });

  // 1. review: video with SAM masks, pipeline, counters
  await go(`${R}/review`, 6000);
  await shot('review');

  // 2. defect inspector
  await p.locator('button:visible:has-text("D001")').first().click();
  await p.waitForTimeout(3500);
  await shot('defect');

  // 3. map with ranked sites
  await go(`${R}/map`, 7000);
  await shot('map');

  // 4. site with field note
  await p.locator('button:visible:has-text("S04")').first().click();
  await p.waitForTimeout(4000);
  await shot('site');

  // 5. work orders
  await go(`${R}/orders`, 5000);
  await shot('orders');

  // 6. ask
  await go(`${R}/ask`, 2500);
  await p.locator('input[placeholder^="Ask"]').fill('Which site should we fix first, and what will it cost?');
  await p.keyboard.press('Enter');
  await p.waitForTimeout(20000);
  await shot('ask');

  // 7. phone capture page
  const m = await b.newContext({ ...require('playwright').devices['iPhone 14'], ignoreHTTPSErrors: true });
  const mp = await m.newPage();
  await mp.goto(`${BASE}/capture`, { waitUntil: 'load' }).catch(() => {});
  await mp.waitForTimeout(3000);
  await mp.screenshot({ path: path.join(OUT, 'capture.png') });
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
