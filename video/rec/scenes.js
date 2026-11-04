// node scenes.js s2 s3 ...  records each scene from the live site
const { open, BASE, RUN } = require('./lib');
const path = require('path');
const R = `${BASE}/app/runs/${RUN}`;
const go = async (h, url) => { await h.page.goto(url, { waitUntil: "load" }).catch(() => {}); await h.wait(1500); };

const S = {
  // landing, then the survey list, then open bolonge
  async s2() {
    const h = await open('s2');
    await go(h, BASE + '/');
    h.mark('start');
    await h.move(900, 500, 800);
    for (let i = 0; i < 6; i++) { await h.page.mouse.wheel(0, 260); await h.wait(700); }
    await h.wait(800);
    await go(h, BASE + '/app');
    h.mark('app');
    await h.wait(1500);
    await h.to('text=bolonge', 1200);
    await h.wait(1200);
    await h.click('text=bolonge', 400);
    await h.wait(4000);
    await h.done();
  },
  // processing replay at 4x
  async s3() {
    const h = await open('s3');
    await go(h, `${R}/review`);
    await h.wait(2500);
    h.mark('start');
    await h.page.locator('select').first().selectOption('8').catch(() => {});
    await h.click('text=Replay processing', 1000);
    h.mark('replay');
    await h.wait(56000);
    await h.done();
  },
  // click a clear pothole, read the inspector
  async s4() {
    const h = await open('s4');
    await go(h, `${R}/review`);
    await h.wait(2500);
    h.mark('start');
    const id = process.env.DEFECT || 'D005';
    const row = h.page.locator(`button:visible:has-text("${id}")`).first();
    await h.click(row, 1200);
    h.mark('open');
    await h.wait(2500);
    await h.move(1730, 520, 900); await h.wait(2500);
    await h.move(1730, 700, 900); await h.wait(3000);
    await h.move(1730, 860, 900); await h.wait(4000);
    const raw = h.page.locator('button:visible:has-text("Raw pixels")').first();
    await h.click(raw, 800); await h.wait(2200);
    await h.click(h.page.locator('button:visible:has-text("SAM mask")').first(), 600); await h.wait(4000);
    await h.done();
  },
  // map with ranked sites, open #1
  async s5() {
    const h = await open('s5');
    await go(h, `${R}/map`);
    await h.wait(6000);
    h.mark('start');
    await h.move(800, 500, 1200); await h.wait(2500);
    await h.move(1200, 600, 1200); await h.wait(2000);
    const first = h.page.locator('text=/^#?1$/').first();
    const site = h.page.locator('button:visible:has-text("S01")').first();
    await h.click((await site.count()) ? site : first, 1200);
    h.mark('open');
    await h.wait(9000);
    await h.done();
  },
  // voice note on the #1 site
  async s6() {
    const h = await open('s6', { audio: path.join(__dirname, '..', 'public', 'rec', 'note.wav') });
    await go(h, `${R}/map`);
    await h.wait(5000);
    const site = h.page.locator(`button:visible:has-text("${process.env.SITE || "S01"}")`).first();
    await h.click(site, 900);
    await h.wait(1500);
    h.mark('start');
    const btn = h.page.locator('button:visible:has-text("Hold to record")').first();
    await h.to(btn, 1000);
    await h.wait(400);
    await h.page.mouse.down();
    h.mark('rec');
    await h.wait(9000);
    await h.page.mouse.up();
    h.mark('sent');
    await h.wait(52000);
    await h.done();
  },
  // work orders: edit a rate, download pdf
  async s7() {
    const h = await open('s7');
    await go(h, `${R}/orders`);
    await h.wait(2500);
    h.mark('start');
    await h.move(700, 500, 1000); await h.wait(2000);
    const rate = h.page.locator('input[type=number].w-20').first();
    await h.click(rate, 1200);
    await h.page.keyboard.press('Control+A');
    await h.type(process.env.RATE || '95', 180);
    h.mark('rate');
    await h.wait(3500);
    const dl = h.page.locator('button:visible:has-text("Download PDF")').first();
    await h.to(dl, 1000);
    h.mark('pdf');
    await h.wait(1000);
    await h.done();
  },
  async s8() {
    const h = await open('s8');
    await go(h, `${R}/ask`);
    await h.wait(2000);
    h.mark('start');
    await h.click('input[placeholder^="Ask"]', 1000);
    await h.type(process.env.Q || 'Which site should we fix first, and what will it cost?', 45);
    await h.wait(500);
    await h.page.keyboard.press('Enter');
    h.mark('asked');
    await h.wait(16000);
    await h.done();
  },
};

(async () => { for (const n of process.argv.slice(2)) await S[n](); })().catch((e) => { console.error(e); process.exit(1); });
