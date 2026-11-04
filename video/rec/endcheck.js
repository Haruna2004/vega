const { chromium, devices } = require('playwright');
(async () => {
  const b = await chromium.launch({ proxy: { server: process.env.HTTPS_PROXY } });
  const c = await b.newContext({ ...devices['iPhone 14'] }); const p = await c.newPage();
  await p.goto('https://mend.harunafaruk.com/', { waitUntil: 'networkidle' });
  const r = await p.evaluate(() => {
    const els = [document.documentElement, document.body, document.getElementById('root')];
    const scroller = els.find(e => e.scrollHeight > e.clientHeight + 5 && getComputedStyle(e).overflowY !== 'visible') || document.scrollingElement;
    const f = document.querySelector('footer').getBoundingClientRect();
    return { scroller: scroller.tagName + '#' + scroller.id, sh: scroller.scrollHeight, ch: scroller.clientHeight, footerBottomDoc: f.bottom + scroller.scrollTop, docSH: document.documentElement.scrollHeight, bodyBg: getComputedStyle(document.body).backgroundColor };
  });
  console.log(r); await b.close();
})();
