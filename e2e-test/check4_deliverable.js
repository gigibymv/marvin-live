const { chromium } = require('playwright');

(async () => {
  const RESULTS_DIR = '/tmp/marvin_validation_v2';
  const browser = await chromium.launch({ headless: false, slowMo: 200 });
  const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });

  const networkStatuses = {};
  const page = await context.newPage();

  page.on('response', resp => {
    if (resp.url().includes('deliverable') || resp.url().includes('download')) {
      networkStatuses[resp.url()] = resp.status();
      console.log('NETWORK:', resp.status(), resp.url().substring(0, 120));
    }
  });

  await page.goto('http://localhost:3000/missions/m-jacquemus-20260426', { waitUntil: 'networkidle', timeout: 15000 });
  await new Promise(r => setTimeout(r, 2000));

  // Find all Open links (deliverables)
  const openLinks = await page.$$('a:has-text("Open"), [class*="deliverable"] a, [class*="Deliverable"] a');
  console.log('Open links found:', openLinks.length);

  // Get hrefs
  const hrefs = await page.$$eval('a', els =>
    els.filter(e => e.textContent.trim().includes('Open') || (e.href && e.href.includes('deliverable')))
       .map(e => ({ text: e.textContent.trim(), href: e.href }))
  );
  console.log('DELIVERABLE HREFS:', JSON.stringify(hrefs, null, 2));

  if (openLinks.length > 0) {
    // Click first Open link — expect new tab
    const [newPage] = await Promise.all([
      context.waitForEvent('page', { timeout: 8000 }).catch(() => null),
      openLinks[0].click()
    ]);

    if (newPage) {
      await newPage.waitForLoadState('domcontentloaded', { timeout: 8000 }).catch(() => {});
      await new Promise(r => setTimeout(r, 2000));
      const title = await newPage.title();
      const bodyText = await newPage.innerText('body').catch(() => '');
      const url = newPage.url();
      console.log('NEW TAB URL:', url);
      console.log('NEW TAB TITLE:', title);
      console.log('NEW TAB BODY (first 300):', bodyText.substring(0, 300));
      const is404 = bodyText.includes('404') || bodyText.includes('Not Found') || bodyText.includes('not found');
      console.log('IS 404:', is404);
      await newPage.screenshot({ path: `${RESULTS_DIR}/check4_deliverable1_newtab.png` });
      console.log('SCREENSHOT:', `${RESULTS_DIR}/check4_deliverable1_newtab.png`);
      await newPage.close();
    } else {
      console.log('No new tab — may be same-page or download');
      await new Promise(r => setTimeout(r, 2000));
      await page.screenshot({ path: `${RESULTS_DIR}/check4_deliverable1_samepage.png` });
      console.log('SCREENSHOT:', `${RESULTS_DIR}/check4_deliverable1_samepage.png`);
    }

    // Try second link
    if (openLinks.length > 1) {
      const [newPage2] = await Promise.all([
        context.waitForEvent('page', { timeout: 8000 }).catch(() => null),
        openLinks[1].click()
      ]);
      if (newPage2) {
        await newPage2.waitForLoadState('domcontentloaded', { timeout: 8000 }).catch(() => {});
        await new Promise(r => setTimeout(r, 1500));
        const body2 = await newPage2.innerText('body').catch(() => '');
        const url2 = newPage2.url();
        const is404_2 = body2.includes('404') || body2.includes('Not Found');
        console.log('DELIVERABLE 2 URL:', url2);
        console.log('DELIVERABLE 2 IS 404:', is404_2);
        console.log('DELIVERABLE 2 BODY:', body2.substring(0, 200));
        await newPage2.screenshot({ path: `${RESULTS_DIR}/check4_deliverable2_newtab.png` }).catch(() => {});
        console.log('SCREENSHOT:', `${RESULTS_DIR}/check4_deliverable2_newtab.png`);
        await newPage2.close().catch(() => {});
      }
    }
  }

  console.log('NETWORK STATUSES:', JSON.stringify(networkStatuses));
  await browser.close();
  console.log('DONE');
})();
