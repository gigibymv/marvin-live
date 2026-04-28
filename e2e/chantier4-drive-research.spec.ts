import { test, Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const MISSION_ID = 'm-mistral-ai-20260427-x-2a2c0b3f';
const BASE_URL = 'http://localhost:3000';
const SCREENSHOT_DIR = '/tmp/marvin_c4_verify';

fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

async function ss(page: Page, name: string) {
  const p = path.join(SCREENSHOT_DIR, `${name}.png`);
  await page.screenshot({ path: p, fullPage: true });
  console.log(`Screenshot: ${p}`);
}

async function waitForAny(page: Page, texts: string[], timeout: number) {
  try {
    await page.waitForFunction(
      (t) => t.some(s => document.body.innerText.includes(s)),
      texts,
      { timeout }
    );
    return true;
  } catch {
    return false;
  }
}

test('Drive research to completion', async ({ page }) => {
  test.setTimeout(900000); // 15 min

  // Intercept SSE to monitor events
  const events: string[] = [];
  page.on('response', async (resp) => {
    if (resp.url().includes('/chat') || resp.url().includes('/stream')) {
      console.log('SSE response:', resp.url(), resp.status());
    }
  });

  await page.goto(`${BASE_URL}/missions/${MISSION_ID}`);
  await page.waitForLoadState('networkidle');
  await ss(page, 'r-00-start');

  // Send message to kick the graph
  const chatInput = page.locator('textarea').first();
  await chatInput.waitFor({ timeout: 10000 });
  await chatInput.fill('Run all research workstreams now: market analysis, competitive positioning, revenue model, and risk assessment for Mistral AI Series C investment decision.');
  await ss(page, 'r-01-before-send');
  await chatInput.press('Enter');

  // Wait for the graph to start running — look for agent activity indicators
  console.log('Waiting for agents to activate (up to 5 min)...');
  const agentsActive = await waitForAny(page, [
    'RUNNING', 'Running', 'running',
    'dora\nMar', // agent name followed by state
    'finding', 'Finding',
    'TESTING', 'SUPPORTED', 'WEAKENED',
    'K 0', 'R 0', 'L 0', // counts changing
    'Gate pending', 'gate_pending',
  ], 300000);
  console.log('Agents activated:', agentsActive);
  await ss(page, 'r-02-agents-running');

  // Keep waiting for research to complete (findings + hypotheses updating)
  console.log('Waiting for research findings (up to 8 more min)...');
  const researchDone = await waitForAny(page, [
    'TESTING', 'SUPPORTED', 'WEAKENED',
    'manager review', 'Manager Review',
    'G1', 'data decision',
    'KNOWN', 'REASONED', 'LOW_CONFIDENCE',
  ], 480000);
  console.log('Research done indicators:', researchDone);
  await ss(page, 'r-03-research-done');

  // ── CP1.1 — Hypotheses status before G1 approval ─────────────────────────
  const hypSection = page.locator('#hypotheses, [class*="hypothesis"], [class*="Hypothesis"]');
  const hypText = await page.locator('aside, [class*="sidebar"]').first().textContent().catch(() => '');
  console.log('Hypothesis section text:', hypText?.substring(0, 500));
  await ss(page, 'cp1-01-hypothesis-status');

  // Scroll sidebar to show all hypotheses
  await page.evaluate(() => {
    const sidebar = document.querySelector('aside') || document.querySelector('[class*="sidebar"]');
    if (sidebar) sidebar.scrollTop = 500;
  });
  await page.waitForTimeout(500);
  await ss(page, 'cp1-01b-hypothesis-scrolled');

  // ── CP2 — Find finding cards ───────────────────────────────────────────────
  // Switch to Market and Competitive Analysis tab if not already there
  const marketTab = page.locator('button, [role="tab"]').filter({ hasText: /market/i }).first();
  if (await marketTab.isVisible().catch(() => false)) {
    await marketTab.click();
    await page.waitForTimeout(500);
  }
  await ss(page, 'cp2-01-market-tab');

  // Check if G1 Review button appeared
  const reviewBtn = page.locator('button').filter({ hasText: /review now/i });
  const hasReview = await reviewBtn.isVisible().catch(() => false);
  console.log('G1 Review Now visible:', hasReview);

  if (hasReview) {
    await ss(page, 'cp1-03-before-g1');

    // ── CP1.3 — Check for WEAKENED before approving ───────────────────────
    const bodyText = await page.locator('body').textContent() || '';
    console.log('CP1.3 WEAKENED present:', bodyText.includes('WEAKENED'));
    console.log('CP1.3 TESTING present:', bodyText.includes('TESTING'));
    console.log('CP1.3 SUPPORTED present:', bodyText.includes('SUPPORTED'));

    // Approve G1
    await reviewBtn.click();
    await page.waitForTimeout(1500);
    await ss(page, 'r-04-g1-modal');

    // Find approve in modal
    const approveInModal = page.locator('[role="dialog"] button, [class*="modal"] button, [class*="gate"] button').filter({ hasText: /approve/i }).first();
    if (await approveInModal.isVisible().catch(() => false)) {
      await approveInModal.click();
      console.log('G1 approved via modal');
      await ss(page, 'r-05-g1-approved');
    } else {
      // Try direct API
      console.log('No modal approve btn — trying API approve of G1');
      await page.keyboard.press('Escape');
    }
  }

  // Wait for synthesis (up to 8 min)
  console.log('Waiting for synthesis/deliverables (up to 8 min)...');
  const synthDone = await waitForAny(page, [
    'final review', 'Final Review', 'G3',
    'synthesis', 'Synthesis',
    'Download', 'download',
  ], 480000);
  console.log('Synthesis done:', synthDone);
  await ss(page, 'r-06-synthesis');

  // ── CP1.4 — Click hypothesis to expand ────────────────────────────────────
  const hypCard = page.locator('[class*="HypothesisCard"], [class*="hypothesis-card"]').first();
  const hypCardVis = await hypCard.isVisible().catch(() => false);
  if (!hypCardVis) {
    // Try clicking H1 label in sidebar
    const h1Label = page.locator('text=H1').first();
    if (await h1Label.isVisible().catch(() => false)) {
      await h1Label.click();
      await page.waitForTimeout(1000);
      await ss(page, 'cp1-04-h1-clicked');
    }
  } else {
    await hypCard.click();
    await page.waitForTimeout(1000);
    await ss(page, 'cp1-04-hypothesis-expanded');
  }

  // ── CP3 — DeliverablePreview ───────────────────────────────────────────────
  // Navigate to Brief tab which should show deliverables
  const briefTab = page.locator('[role="tab"], button, a').filter({ hasText: /brief/i }).first();
  if (await briefTab.isVisible().catch(() => false)) {
    await briefTab.click();
    await page.waitForTimeout(500);
  }
  await ss(page, 'cp3-00-brief-tab');

  // Look for Open buttons
  const openBtns = page.locator('button').filter({ hasText: /^open$/i });
  const openCount = await openBtns.count();
  console.log(`CP3: Open button count: ${openCount}`);

  // Also check for clickable deliverable items
  const delivLinks = page.locator('a[href*="deliverable"], [class*="deliverable"] button, [class*="Deliverable"] button').filter({ hasText: /open|view/i });
  const delivCount = await delivLinks.count();
  console.log(`CP3: Deliverable action links: ${delivCount}`);

  // Click "framing memo" link if visible
  const framingLink = page.locator('text=framing memo, text=Deliverable ready · framing memo').first();
  const framingVisible = await framingLink.isVisible().catch(() => false);
  console.log('Framing memo link visible:', framingVisible);

  if (openCount > 0) {
    await openBtns.first().click();
    await page.waitForTimeout(2000);
    await ss(page, 'cp3-01-modal');

    // Check modal size ~1100x800
    const modalEl = page.locator('[role="dialog"]').first();
    if (await modalEl.isVisible().catch(() => false)) {
      const box = await modalEl.boundingBox();
      console.log('CP3.1: Modal dimensions:', box?.width, 'x', box?.height);

      // Count findings in sidebar
      const totalFindingsApi = await page.evaluate(async () => {
        const r = await fetch('http://localhost:8095/api/v1/missions/m-mistral-ai-20260427-x-2a2c0b3f/findings');
        if (!r.ok) return -1;
        const d = await r.json();
        return Array.isArray(d) ? d.length : (d.findings?.length ?? -1);
      });
      console.log(`CP3.2: Total findings in DB: ${totalFindingsApi}`);

      const sidebarFindCount = await page.locator('[role="dialog"] [class*="finding"], [role="dialog"] [class*="Finding"]').count();
      console.log(`CP3.2: Finding elements in modal sidebar: ${sidebarFindCount}`);

      const preVisible = await page.locator('[role="dialog"] pre, [role="dialog"] [class*="markdown"]').isVisible().catch(() => false);
      console.log('CP3.1: Markdown content visible:', preVisible);
      await ss(page, 'cp3-02-sidebar-detail');

      // Download
      const dlBtn = page.locator('[role="dialog"] button').filter({ hasText: /download/i }).first();
      if (await dlBtn.isVisible().catch(() => false)) {
        const [dl] = await Promise.all([
          page.waitForEvent('download', { timeout: 10000 }).catch(() => null),
          dlBtn.click(),
        ]);
        console.log('CP3.3: Download file:', dl ? await dl.suggestedFilename() : 'none');
        await ss(page, 'cp3-03-download');
      }

      // Close by clicking outside
      await page.mouse.click(5, 5);
      await page.waitForTimeout(800);
      const modalClosed = !(await page.locator('[role="dialog"]').isVisible().catch(() => true));
      console.log('CP3.4: Modal closed by outside click:', modalClosed);
      await ss(page, 'cp3-04-closed');

      // Open second deliverable
      if (openCount >= 2) {
        await openBtns.nth(1).click();
        await page.waitForTimeout(1500);
        await ss(page, 'cp3-05-second-deliverable');
        await page.keyboard.press('Escape');
      }
    }
  } else {
    // Try clicking on deliverable items in the activity feed
    const delivItem = page.locator('text=framing memo').first();
    if (await delivItem.isVisible().catch(() => false)) {
      await delivItem.click();
      await page.waitForTimeout(1500);
      await ss(page, 'cp3-01-via-feed-click');
    } else {
      await ss(page, 'cp3-no-open-available');
      console.log('CP3: No deliverable open mechanism found yet');
    }
  }

  console.log('All verification steps complete.');
});
