const { chromium } = require('playwright');
const fs = require('fs');

async function runTest() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  // Logging utility
  const log = (msg) => {
    const text = `[${new Date().toISOString()}] ${msg}\n`;
    console.log(text.trim());
    fs.appendFileSync('report.log', text);
  };

  try {
    log("Navigating to http://localhost:3003");
    await page.goto('http://localhost:3003/missions', { waitUntil: 'networkidle' });
    
    log("Clicking 'New mission'");
    await page.click('.new-btn');
    
    log("Clicking 'Continue →'");
    await page.click('button:has-text("Continue →")');
    
    log("Filling Client and Target");
    await page.fill('input[placeholder="e.g. Meridian Capital"]', 'European PE fund');
    await page.fill('input[placeholder="e.g. NovaSec"]', 'Vinted');
    
    log("Clicking 'Open mission →'");
    await page.click('button:has-text("Open mission →")');
    
    log("Waiting for mission page to load");
    await page.waitForURL(/\/missions\/m-/, { timeout: 10000 });
    log(`Mission page loaded: ${page.url()}`);
    
    // Now look for where to enter the brief
    log("Looking for brief input...");
    // The brief input might be a textarea placeholder like "Enter your brief here" or just a textarea.
    // Let's wait for any textarea
    const textarea = page.locator('textarea');
    await textarea.waitFor({ timeout: 15000 });
    
    const brief = "CDD — Acquisition of Vinted by a European PE fund. €5Bn valuation. €813M revenue FY2024. 9.5% net margin. GMV €10.8Bn. Competitors: Depop, Vestiaire Collective. IC question: Is the €5Bn valuation justified given competitive pressure and category expansion risk? Manager: MV.";
    
    log("Entering the brief");
    await textarea.fill(brief);
    
    log("Submitting the brief");
    // Pressing Enter or clicking a send button
    await textarea.press('Enter');
    
    log("Brief submitted. Monitoring mission progress...");
    
    // Now we monitor the progress
    // Look for "approve", "confirm", "gate"
    let isFinished = false;
    let iterations = 0;
    while (!isFinished && iterations < 30) {
      await page.waitForTimeout(10000); // Check every 10s
      iterations++;
      
      const pageText = await page.evaluate(() => document.body.innerText);
      log(`Iteration ${iterations} snapshot: length=${pageText.length}`);
      
      // Look for approve buttons
      const buttons = await page.locator('button').all();
      for (const btn of buttons) {
        const text = await btn.textContent();
        if (text && (text.toLowerCase().includes('approve') || text.toLowerCase().includes('confirm'))) {
          log(`Found gate button: ${text}. Clicking it!`);
          await btn.click();
          await page.waitForTimeout(5000);
        }
      }
      
      if (pageText.includes('run_end') || pageText.toLowerCase().includes('mission complete') || pageText.includes('Papyrus')) {
        log("Mission appears to be finished.");
        isFinished = true;
      }
    }
    
    log("Taking final screenshot");
    await page.screenshot({ path: 'final_state.png', fullPage: true });

  } catch (err) {
    log(`Error: ${err.message}`);
    await page.screenshot({ path: 'error_state.png', fullPage: true });
  } finally {
    await browser.close();
  }
}

runTest();
