// Phone-sized smoke test of GSU Compass (admin PIN 2468 expected). GPS is faked at the Main Gate.
// Usage: PLAYWRIGHT=/path/to/node_modules/playwright-core node tests/smoke.cjs [baseUrl] [screenshotDir]
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright-core');
const base = process.argv[2] || 'http://localhost:8000';
const out = process.argv[3] || require('os').tmpdir() + '/gsu-compass-shots';
require('fs').mkdirSync(out, { recursive: true });
const root = require('path').resolve(__dirname, '..');

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME || '/usr/bin/google-chrome', args: ['--headless=new', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true,
    geolocation: { latitude: 10.30402, longitude: 11.17077 }, permissions: ['geolocation'] });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
  const shot = (n) => page.screenshot({ path: `${out}/${n}.png` });
  const ok = (cond, msg) => { console.log((cond ? 'PASS ' : 'FAIL ') + msg); if (!cond) process.exitCode = 1; };

  await page.goto(base + '/');
  await page.waitForSelector('.mk-wrap', { timeout: 20000 });
  await page.waitForTimeout(2500);
  ok((await page.locator('.mk-wrap').count()) > 50, 'markers drawn: ' + (await page.locator('.mk-wrap').count()));
  await shot('01-map');

  // filter
  await page.click('.chip[data-cat="hostel"]');
  const visible = await page.$$eval('.mk-wrap', (els) => els.filter((e) => e.style.display !== 'none').length);
  ok(visible > 3 && visible < 15, 'hostel filter shows ' + visible);
  await page.click('.chip[data-cat="all"]');

  // search by name, then by question
  await page.click('#nav [data-view="search"]');
  await page.fill('#search-input', 'libary');
  await page.waitForTimeout(200);
  ok((await page.textContent('#search-results')).includes('Main Library'), 'typo "libary" finds Main Library');
  await page.fill('#search-input', 'where do I pay school fees');
  await page.press('#search-input', 'Enter');
  await page.waitForSelector('.card.hit', { timeout: 30000 });
  ok((await page.textContent('.card.hit')).includes('Bursary'), 'school fees resolves to Bursary');
  await shot('02-search');
  await page.fill('#search-input', 'I want to register my courses');
  await page.press('#search-input', 'Enter');
  await page.waitForFunction(() => document.querySelector('.card.hit h3')?.textContent && !document.querySelector('#search-status .spin'), null, { timeout: 30000 });
  console.log('     register courses ->', await page.textContent('.card.hit h3'));

  // directions
  await page.click('.card.hit [data-go]');
  await page.waitForSelector('#route:not([hidden])');
  await page.waitForTimeout(1200);
  const steps = await page.$$eval('#route-steps li', (l) => l.map((x) => x.textContent));
  ok(steps.length >= 2, 'route has steps');
  console.log('     ' + (await page.textContent('#route-dist')) + ' / ' + (await page.textContent('#route-time')));
  steps.forEach((s) => console.log('     - ' + s));
  await shot('03-route');

  // marker tap opens sheet
  await page.click('#route-close');
  await page.evaluate(() => document.querySelector('.mk-wrap').click());
  await page.waitForSelector('#sheet:not([hidden])');
  await page.waitForTimeout(800);
  await shot('04-sheet');

  // lens: stand by the library and "take" a photo of it (a photo not used as its reference)
  await ctx.setGeolocation({ latitude: 10.305069, longitude: 11.173325 });
  await page.waitForTimeout(500);
  await page.click('#nav [data-view="lens"]');
  await page.setInputFiles('#lens-camera', root + '/static/photos/commons/The_Gombe_State_University_Library_02.jpg');
  await page.waitForSelector('#lens-status .spin', { timeout: 10000 });
  await page.waitForFunction(() => !document.querySelector('#lens-status .spin'), null, { timeout: 70000 });
  await page.waitForTimeout(300);
  console.log('     lens ->', (await page.textContent('#lens-result')).slice(0, 120).replace(/\s+/g, ' '));
  await shot('05-lens');

  // gonadoc, answer in Hausa
  await page.click('#nav [data-view="gonadoc"]');
  await page.click('#gd-lang [data-lang="ha"]');
  await page.setInputFiles('#gd-camera', root + '/tests/fixtures/leaf-tomato-early-blight.jpg');
  await page.waitForSelector('#gd-status .spin', { timeout: 10000 });
  await page.waitForFunction(() => !document.querySelector('#gd-status .spin'), null, { timeout: 70000 });
  await page.waitForTimeout(300);
  console.log('     gonadoc ->', (await page.textContent('#gd-result')).slice(0, 120).replace(/\s+/g, ' '));
  await shot('06-gonadoc');

  // whole app in Hausa
  await page.click('#lang-btn');
  await page.click('#nav [data-view="map"]');
  await page.waitForTimeout(500);
  ok((await page.textContent('#nav')).includes('Taswira'), 'Hausa nav');
  await shot('07-hausa');
  await page.click('#lang-btn');

  // admin
  await page.click('#admin-btn');
  await page.fill('#admin-pin', '2468');
  await page.click('#admin-pin-form button');
  await page.waitForSelector('#admin-form:not([hidden])');
  await shot('08-admin');

  ok(!errors.length, 'no page errors' + (errors.length ? ': ' + errors.join(' | ') : ''));
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });

