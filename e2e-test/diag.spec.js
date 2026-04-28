// @ts-check
const { test } = require('@playwright/test');
const fs = require('fs');

// Write all output to a log file for inspection
fs.writeFileSync('/tmp/marvin-diag.log', '--- DIAG RUN ---\n');
const LOG = (msg) => {
  process.stdout.write(msg + '\n');
  fs.appendFileSync('/tmp/marvin-diag.log', msg + '\n');
};

test.setTimeout(120000);

test('diagnostic — mission creation + page check', async ({ page }) => {
  const FRONTEND_URL = 'http://localhost:3002';

  LOG('\n[DIAG] Navigate to /missions');
  await page.goto(`${FRONTEND_URL}/missions`);
  await page.waitForLoadState('networkidle');
  await page.screenshot({ path: '/tmp/diag-01-dashboard.png', fullPage: true });

  // Check for "New mission" button
  const newBtn = page.locator('button.new-btn, button:has-text("New mission")').first();
  const newBtnVisible = await newBtn.isVisible({ timeout: 5000 }).catch(() => false);
  LOG(`[DIAG] "New mission" button visible: ${newBtnVisible}`);

  if (!newBtnVisible) {
    const body = await page.textContent('body');
    LOG('[DIAG] Page body (first 500): ' + body.substring(0, 500));
    throw new Error('New mission button not visible');
  }

  await newBtn.click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: '/tmp/diag-02-modal-step1.png', fullPage: true });
  const modal1Body = await page.textContent('body');
  LOG('[DIAG] Modal step1 body (first 300): ' + modal1Body.substring(0, 300));

  // Click "Continue"
  const continueBtn = page.locator('button:has-text("Continue")').first();
  const continueBtnVisible = await continueBtn.isVisible({ timeout: 5000 }).catch(() => false);
  LOG(`[DIAG] "Continue" button visible: ${continueBtnVisible}`);
  if (!continueBtnVisible) {
    throw new Error('Continue button not visible');
  }
  await continueBtn.click();
  await page.waitForTimeout(300);
  await page.screenshot({ path: '/tmp/diag-03-modal-step2.png', fullPage: true });

  // Fill form
  const clientInput = page.locator('input[placeholder*="Meridian"]');
  const targetInput = page.locator('input[placeholder*="NovaSec"]');
  const clientVisible = await clientInput.isVisible({ timeout: 5000 }).catch(() => false);
  const targetVisible = await targetInput.isVisible({ timeout: 5000 }).catch(() => false);
  LOG(`[DIAG] Client input visible: ${clientVisible}, Target input visible: ${targetVisible}`);

  if (!clientVisible || !targetVisible) {
    throw new Error('Form inputs not visible');
  }

  await clientInput.fill('Test Fund');
  await targetInput.fill('Mistral AI');

  // Click "Open mission"
  const openBtn = page.locator('button:has-text("Open mission")').first();
  const openBtnVisible = await openBtn.isVisible({ timeout: 5000 }).catch(() => false);
  LOG(`[DIAG] "Open mission" button visible: ${openBtnVisible}`);
  await openBtn.click();

  // Wait for redirect
  LOG('[DIAG] Waiting for redirect (up to 30s)...');
  await page.waitForURL(/\/missions\/m-/, { timeout: 30000 });
  const missionUrl = page.url();
  LOG(`[DIAG] Mission URL: ${missionUrl}`);

  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(3000);
  await page.screenshot({ path: '/tmp/diag-04-mission-page.png', fullPage: true });

  // Check for chat textarea
  const chatTextarea = page.locator('textarea[placeholder*="Ask MARVIN"]');
  const chatVisible = await chatTextarea.isVisible({ timeout: 15000 }).catch(() => false);
  LOG(`[DIAG] Chat textarea [placeholder*="Ask MARVIN"] visible: ${chatVisible}`);

  const allTextareas = await page.locator('textarea').all();
  LOG(`[DIAG] Total textareas on page: ${allTextareas.length}`);
  for (const ta of allTextareas) {
    const ph = await ta.getAttribute('placeholder').catch(() => 'N/A');
    const vis = await ta.isVisible().catch(() => false);
    LOG(`  textarea placeholder="${ph}" visible=${vis}`);
  }

  const body = await page.textContent('body');
  LOG('[DIAG] Mission page body (first 600): ' + body.substring(0, 600));
  LOG('[DIAG] DONE');
});
