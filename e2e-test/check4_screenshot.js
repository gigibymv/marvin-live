const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await context.newPage();
  await page.goto('http://localhost:3000/missions/m-jacquemus-20260426', { waitUntil: 'networkidle', timeout: 15000 });
  await new Promise(r => setTimeout(r, 2000));
  await page.screenshot({ path: '/tmp/marvin_validation_v2/check4_left_rail_deliverables.png', fullPage: false });
  console.log('SCREENSHOT: /tmp/marvin_validation_v2/check4_left_rail_deliverables.png');
  await browser.close();
})();
