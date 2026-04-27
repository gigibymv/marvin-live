const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const RESULTS_DIR = '/tmp/marvin_validation_v2';
const BASE_URL = 'http://localhost:3000';
const BACKEND_URL = 'http://localhost:8095';

async function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function shot(page, name) {
  const p = path.join(RESULTS_DIR, name + '.png');
  await page.screenshot({ path: p, fullPage: false });
  console.log('SCREENSHOT:', p);
  return p;
}

(async () => {
  fs.mkdirSync(RESULTS_DIR, { recursive: true });

  const browser = await chromium.launch({ headless: false, slowMo: 300 });
  const context = await browser.newContext({
    viewport: { width: 1400, height: 900 }
  });

  const consoleErrors = [];
  const consoleWarnings = [];

  // ---- CHECK 1: Gate modal clarity ----
  console.log('\n=== CHECK 1: Gate modal ===');
  let gatePage = await context.newPage();
  gatePage.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
    if (msg.type() === 'warning') consoleWarnings.push(msg.text());
  });

  // Try existing mission first
  await gatePage.goto(`${BASE_URL}/missions/m-vinted-20260426`, { waitUntil: 'networkidle', timeout: 15000 }).catch(() => {});
  await sleep(2000);
  await shot(gatePage, 'check1_mission_loaded');

  // Check if gate modal is visible
  let gateModal = await gatePage.$('[data-testid="gate-modal"], [class*="gate"], [class*="Gate"], [role="dialog"]');
  let modalText = '';
  if (gateModal) {
    modalText = await gateModal.innerText().catch(() => '');
    console.log('GATE MODAL FOUND on m-vinted-20260426');
    await shot(gatePage, 'check1_gate_modal');
  } else {
    console.log('No gate modal on m-vinted-20260426, checking page content...');
    const pageText = await gatePage.innerText('body').catch(() => '');
    console.log('PAGE SNIPPET:', pageText.substring(0, 500));
    await shot(gatePage, 'check1_vinted_no_gate');

    // Try second mission ID
    await gatePage.goto(`${BASE_URL}/missions/m-vinted-20260426-x-dc124983`, { waitUntil: 'networkidle', timeout: 15000 }).catch(() => {});
    await sleep(2000);
    gateModal = await gatePage.$('[data-testid="gate-modal"], [class*="gate"], [class*="Gate"], [role="dialog"]');
    if (gateModal) {
      modalText = await gateModal.innerText().catch(() => '');
      console.log('GATE MODAL FOUND on second ID');
      await shot(gatePage, 'check1_gate_modal_v2');
    } else {
      console.log('No gate modal on second ID either. Creating new mission...');
      await shot(gatePage, 'check1_second_id_no_gate');

      // Create new mission
      await gatePage.goto(`${BASE_URL}/missions`, { waitUntil: 'networkidle', timeout: 15000 }).catch(() => {});
      await sleep(2000);
      await shot(gatePage, 'check1_missions_list');

      // Look for "New mission" button
      const newBtn = await gatePage.$('button:has-text("New mission"), a:has-text("New mission"), button:has-text("New Mission"), [href*="new"]');
      if (newBtn) {
        await newBtn.click();
        await sleep(1500);
        await shot(gatePage, 'check1_new_mission_form');

        // Fill form
        const clientInput = await gatePage.$('input[name="client"], input[placeholder*="client"], input[placeholder*="Client"]');
        if (clientInput) { await clientInput.fill('Test PE'); }
        const targetInput = await gatePage.$('input[name="target"], input[placeholder*="target"], input[placeholder*="Target"]');
        if (targetInput) { await targetInput.fill('Vinted'); }

        // Look for mission type dropdown
        const missionTypeSelect = await gatePage.$('select[name="mission_type"], [name="mission_type"]');
        if (missionTypeSelect) { await missionTypeSelect.selectOption('cdd'); }

        await shot(gatePage, 'check1_form_filled');
        const submitBtn = await gatePage.$('button[type="submit"], button:has-text("Create"), button:has-text("Start")');
        if (submitBtn) {
          await submitBtn.click();
          await sleep(3000);
          await shot(gatePage, 'check1_after_create');
        }
      } else {
        console.log('No New Mission button found');
        const allButtons = await gatePage.$$eval('button', els => els.map(e => e.textContent.trim()));
        console.log('BUTTONS ON PAGE:', JSON.stringify(allButtons));
      }
    }
  }

  // Look for gate modal more broadly
  await sleep(2000);
  const dialogEls = await gatePage.$$('[role="dialog"], [class*="modal"], [class*="Modal"], [class*="Dialog"]');
  console.log('Dialog elements found:', dialogEls.length);
  for (let i = 0; i < dialogEls.length; i++) {
    const txt = await dialogEls[i].innerText().catch(() => '');
    console.log(`DIALOG[${i}]:`, txt.substring(0, 400));
  }

  // Scan for gate-related text on page
  const fullPageText = await gatePage.innerText('body').catch(() => '');
  const hasStage = fullPageText.includes('Stage') || fullPageText.includes('stage');
  const hasApprove = fullPageText.includes('Approve') || fullPageText.includes('approve');
  const hasReject = fullPageText.includes('Reject') || fullPageText.includes('reject');
  const hasHypothesis = fullPageText.includes('hypothes') || fullPageText.includes('Hypothes');
  console.log('Page text contains - Stage:', hasStage, 'Approve:', hasApprove, 'Reject:', hasReject, 'Hypothesis:', hasHypothesis);
  await shot(gatePage, 'check1_final_state');

  // Try sending chat message to trigger gate on existing mission
  await gatePage.goto(`${BASE_URL}/missions/m-vinted-20260426`, { waitUntil: 'networkidle', timeout: 15000 }).catch(() => {});
  await sleep(2000);
  const chatInput = await gatePage.$('textarea, input[type="text"][placeholder*="message"], input[type="text"][placeholder*="Message"]');
  if (chatInput) {
    console.log('Found chat input, sending trigger message...');
    await chatInput.click();
    await chatInput.fill('ok lets start');
    await chatInput.press('Enter');
    await sleep(5000);
    await shot(gatePage, 'check1_after_chat');

    // Check for gate modal again
    const gateAfterChat = await gatePage.$('[role="dialog"], [class*="gate"], [class*="Gate"]');
    if (gateAfterChat) {
      const txt = await gateAfterChat.innerText().catch(() => '');
      console.log('GATE AFTER CHAT:', txt.substring(0, 600));
      await shot(gatePage, 'check1_gate_after_chat');
    }
  }
  await gatePage.close();

  // ---- CHECK 3: Center panel per-tab content ----
  console.log('\n=== CHECK 3: Center panel tabs ===');
  const tabPage = await context.newPage();
  tabPage.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
    if (msg.type() === 'warning') consoleWarnings.push(msg.text());
  });

  await tabPage.goto(`${BASE_URL}/missions/m-jacquemus-20260426`, { waitUntil: 'networkidle', timeout: 15000 }).catch(() => {});
  await sleep(3000);
  await shot(tabPage, 'check3_mission_loaded');

  const tabs = ['Competitive', 'Market', 'Financial', 'Risk', 'Memo'];
  const tabCounts = {};

  for (const tab of tabs) {
    const tabEl = await tabPage.$(`button:has-text("${tab}"), [role="tab"]:has-text("${tab}"), a:has-text("${tab}")`);
    if (tabEl) {
      await tabEl.click();
      await sleep(1500);
      // Count finding cards
      const findings = await tabPage.$$('[class*="finding"], [class*="Finding"], [data-testid*="finding"]');
      // Also try li or article elements in center panel
      const centerCards = await tabPage.$$('[class*="card"], [class*="Card"]');
      tabCounts[tab] = findings.length;
      console.log(`TAB ${tab}: finding elements=${findings.length}, card elements=${centerCards.length}`);
      await shot(tabPage, `check3_tab_${tab.toLowerCase()}`);
    } else {
      console.log(`TAB ${tab}: NOT FOUND`);
      tabCounts[tab] = -1;
      // List all tabs/buttons
      const allTabs = await tabPage.$$eval('[role="tab"], [class*="tab"] button, nav button', els => els.map(e => e.textContent.trim()));
      console.log('Available tabs:', JSON.stringify(allTabs));
    }
  }

  // Get the full page text for last tab to check content
  const pageTextFinal = await tabPage.innerText('body').catch(() => '');
  console.log('PAGE TEXT SAMPLE (last tab):', pageTextFinal.substring(0, 300));
  await tabPage.close();

  // ---- CHECK 4: Deliverable download ----
  console.log('\n=== CHECK 4: Deliverable download ===');
  const delivPage = await context.newPage();
  delivPage.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
    if (msg.type() === 'warning') consoleWarnings.push(msg.text());
  });

  // Track network responses
  const networkStatuses = {};
  delivPage.on('response', resp => {
    if (resp.url().includes('/deliverable') || resp.url().includes('download')) {
      networkStatuses[resp.url()] = resp.status();
      console.log('NETWORK:', resp.status(), resp.url());
    }
  });

  await delivPage.goto(`${BASE_URL}/missions/m-jacquemus-20260426`, { waitUntil: 'networkidle', timeout: 15000 }).catch(() => {});
  await sleep(2000);
  await shot(delivPage, 'check4_mission_loaded');

  // Find deliverable links/buttons in left rail
  const deliverableLinks = await delivPage.$$('[class*="deliverable"], [class*="Deliverable"], [data-testid*="deliverable"]');
  console.log('Deliverable elements found:', deliverableLinks.length);

  // Look for any download buttons or links
  const downloadBtns = await delivPage.$$('a[href*="deliverable"], button:has-text("Download"), a[download], [class*="download"]');
  console.log('Download buttons found:', downloadBtns.length);

  // Get full left rail content
  const leftRail = await delivPage.$('[class*="sidebar"], [class*="Sidebar"], [class*="rail"], aside');
  if (leftRail) {
    const leftText = await leftRail.innerText().catch(() => '');
    console.log('LEFT RAIL TEXT:', leftText.substring(0, 600));
  }

  await shot(delivPage, 'check4_initial');

  // Try clicking first deliverable
  if (downloadBtns.length > 0) {
    // Listen for new page
    const [newPage] = await Promise.all([
      context.waitForEvent('page', { timeout: 5000 }).catch(() => null),
      downloadBtns[0].click()
    ]);
    if (newPage) {
      await newPage.waitForLoadState('domcontentloaded', { timeout: 8000 }).catch(() => {});
      await sleep(2000);
      const statusText = await newPage.title().catch(() => '');
      const bodyText = await newPage.innerText('body').catch(() => '');
      console.log('NEW PAGE TITLE:', statusText);
      console.log('NEW PAGE BODY:', bodyText.substring(0, 300));
      const is404 = bodyText.includes('404') || bodyText.includes('Not Found') || statusText.includes('404');
      console.log('IS 404:', is404);
      await shot(newPage, 'check4_deliverable_opened');
      await newPage.close();
    } else {
      console.log('No new page opened - may be inline or download');
      await sleep(2000);
      await shot(delivPage, 'check4_after_click');
    }

    // Try second deliverable
    if (downloadBtns.length > 1) {
      const [newPage2] = await Promise.all([
        context.waitForEvent('page', { timeout: 5000 }).catch(() => null),
        downloadBtns[1].click()
      ]);
      if (newPage2) {
        await newPage2.waitForLoadState('domcontentloaded', { timeout: 8000 }).catch(() => {});
        await sleep(1500);
        const bodyText2 = await newPage2.innerText('body').catch(() => '');
        const is404_2 = bodyText2.includes('404') || bodyText2.includes('Not Found');
        console.log('DELIVERABLE 2 IS 404:', is404_2);
        await shot(newPage2, 'check4_deliverable2_opened');
        await newPage2.close();
      }
    }
  } else {
    // Try clicking any deliverable-related element
    const allLinks = await delivPage.$$eval('a', els => els.map(e => ({ href: e.href, text: e.textContent.trim() })));
    const delivLinks = allLinks.filter(l => l.href.includes('deliverable') || l.text.toLowerCase().includes('report') || l.text.toLowerCase().includes('download'));
    console.log('DELIVERABLE LINKS:', JSON.stringify(delivLinks));
    await shot(delivPage, 'check4_no_download_btns');
  }

  await delivPage.close();

  // ---- SUMMARY ----
  console.log('\n=== CONSOLE ANOMALIES ===');
  console.log('Errors:', consoleErrors.length);
  consoleErrors.forEach(e => console.log('  ERROR:', e.substring(0, 150)));
  console.log('Warnings:', consoleWarnings.length);
  const dupKeyWarnings = consoleWarnings.filter(w => w.includes('key') || w.includes('Key'));
  console.log('Duplicate-key warnings:', dupKeyWarnings.length);

  console.log('\n=== TAB COUNTS SUMMARY ===');
  console.log(JSON.stringify(tabCounts));

  await browser.close();
  console.log('\nDONE');
})();
