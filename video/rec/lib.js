// Shared helpers for recording scenes from the live site.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const BASE = 'https://mend.harunafaruk.com';
const RUN = '20261104-143311-bolonge';
const OUT = path.join(__dirname, '..', 'public', 'rec');

const CURSOR = `
(() => {
  if (window.__cur) return;
  const c = document.createElement('div');
  c.style.cssText = 'position:fixed;left:0;top:0;width:22px;height:22px;z-index:2147483647;pointer-events:none;transform:translate(-3px,-2px);transition:transform 0.08s';
  c.innerHTML = '<svg width="22" height="22" viewBox="0 0 24 24"><path d="M3 2l7 19 2.5-7.5L20 11z" fill="#0f0e12" stroke="#fff" stroke-width="1.5"/></svg>';
  const put = () => document.body && !c.isConnected && document.body.appendChild(c);
  put(); new MutationObserver(put).observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener('mousemove', (e) => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
  window.addEventListener('mousedown', () => { c.style.transform = 'translate(-3px,-2px) scale(0.85)'; }, true);
  window.addEventListener('mouseup', () => { c.style.transform = 'translate(-3px,-2px)'; }, true);
  window.__cur = c;
})();`;

async function open(name, { audio } = {}) {
  const args = ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--autoplay-policy=no-user-gesture-required'];
  if (audio) args.push('--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', `--use-file-for-fake-audio-capture=${audio}`);
  const browser = await chromium.launch({ proxy: { server: process.env.HTTPS_PROXY }, args });
  const dir = path.join(OUT, '_' + name);
  fs.rmSync(dir, { recursive: true, force: true });
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, ignoreHTTPSErrors: true, recordVideo: { dir, size: { width: 1920, height: 1080 } }, permissions: ['microphone'] });
  await ctx.addInitScript(CURSOR);
  const page = await ctx.newPage();
  const t0 = Date.now();
  const mark = {};
  let mx = 960, my = 600;
  const h = {
    page, ctx,
    mark: (k) => { mark[k] = (Date.now() - t0) / 1000; },
    wait: (ms) => page.waitForTimeout(ms),
    async move(x, y, ms = 700) {
      const steps = Math.max(8, Math.round(ms / 16));
      for (let i = 1; i <= steps; i++) {
        const t = i / steps, e = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
        await page.mouse.move(mx + (x - mx) * e, my + (y - my) * e);
        await page.waitForTimeout(ms / steps);
      }
      mx = x; my = y;
    },
    async to(sel, ms) {
      const el = typeof sel === 'string' ? page.locator(sel).first() : sel;
      await el.scrollIntoViewIfNeeded();
      const b = await el.boundingBox();
      await h.move(b.x + b.width / 2, b.y + b.height / 2, ms);
      return el;
    },
    async click(sel, ms) { await h.to(sel, ms); await page.waitForTimeout(150); await page.mouse.down(); await page.waitForTimeout(90); await page.mouse.up(); },
    async type(text, delay = 55) { await page.keyboard.type(text, { delay }); },
    async done() {
      const v = page.video();
      await ctx.close(); await browser.close();
      const src = await v.path();
      fs.renameSync(src, path.join(OUT, name + '.webm'));
      fs.rmSync(dir, { recursive: true, force: true });
      fs.writeFileSync(path.join(OUT, name + '.marks.json'), JSON.stringify(mark, null, 1));
      console.log(name, mark);
    },
  };
  return h;
}
module.exports = { open, BASE, RUN };
