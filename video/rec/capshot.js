const { chromium, devices } = require('playwright');
(async () => {
  const S = process.argv[2];
  const b = await chromium.launch({ proxy: { server: process.env.HTTPS_PROXY }, args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', `--use-file-for-fake-video-capture=${S}/cam.y4m`] });
  const d = devices['iPhone 14 landscape'];
  const ctx = await b.newContext({ ...d, permissions: ['camera', 'geolocation'], geolocation: { latitude: 11.1555, longitude: 7.6505 } });
  const p = await ctx.newPage();
  await p.goto('https://mend.harunafaruk.com/capture', { waitUntil: 'load' });
  await p.waitForTimeout(5000);
  await p.screenshot({ path: '../../frontend/public/shots/capture.png' });
  await b.close();
})();
