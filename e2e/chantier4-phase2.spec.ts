import { test, expect, Page } from '@playwright/test';
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
  return p;
}

async function waitForText(page: Page, texts: string[], timeout = 480000) {
  await page.waitForFunction(
    (texts) => {
      const body = document.body.innerText;
      return texts.some(t => body.includes(t));
    },
    texts,
    { timeout }
  );
}

test('Chantier 4 Phase 2 — research to deliverables', async ({ page }) => {
  test.setTimeout(900000);

  await page.goto(`${BASE_URL}/missions/${MISSION_ID}`);
  await page.waitForLoadState('networkidle');
  await ss(page, 'p2-00-initial');

  // The graph is stuck — data_availability was approved but stream ended.
  // We need to trigger research via the UI chat.
  // Check if there's a "Review now" button for G1 or data availability
  const reviewBtn = page.locator('button').filter({ hasText: /review now/i });
  const reviewVisible = await reviewBtn.isVisible().catch(() => false);
  console.log('Review now button visible:', reviewVisible);

  // Check current state
  const pageText = await page.locator('body').textContent();
  console.log('Page contains "data availability":', pageText?.toLowerCase().includes('data availability'));
  console.log('Page contains "manager review":', pageText?.toLowerCase().includes('manager review'));
  console.log('Page contains "G1":', pageText?.includes('G1'));
  console.log('Page contains "finding":', pageText?.toLowerCase().includes('finding'));
  console.log('Page contains "hypothesis":', pageText?.toLowerCase().includes('hypothesis'));
  await ss(page, 'p2-01-current-state');

  // Scroll down to see hypotheses panel
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.waitForTimeout(500);
  await ss(page, 'p2-02-scrolled-down');

  // ── CP1.1 CAPTURE — Hypotheses before findings ────────────────────────────
  // Look for hypothesis panel in sidebar
  const hypPanel = page.locator('[class*="hypothesis"], [class*="Hypothesis"], [data-testid*="hypothesis"]');
  const hypCount = await hypPanel.count();
  console.log(`CP1.1: Hypothesis elements found: ${hypCount}`);

  // Get hypothesis statuses
  const hypTexts = await page.locator('body').evaluate(() => {
    const body = document.body.innerText;
    const lines = body.split('\n').filter(l =>
      l.includes('NOT_STARTED') || l.includes('TESTING') || l.includes('SUPPORTED') ||
      l.includes('WEAKENED') || l.includes('H1') || l.includes('H2') || l.includes('H3') || l.includes('H4')
    );
    return lines.slice(0, 20);
  });
  console.log('CP1.1 Hypothesis status lines:', hypTexts);
  await ss(page, 'cp1-01-hypotheses-before-findings');

  // If there's a "Review now" or approve button for data availability, click it
  if (reviewVisible) {
    console.log('Clicking Review now...');
    await reviewBtn.click();
    await page.waitForTimeout(2000);
    await ss(page, 'p2-03-review-modal');

    // Look for approve in modal
    const modalApprove = page.locator('[role="dialog"] button, [class*="modal"] button').filter({ hasText: /approve/i }).first();
    const modalApproveVisible = await modalApprove.isVisible().catch(() => false);
    if (modalApproveVisible) {
      await modalApprove.click();
      await ss(page, 'p2-04-approved-from-modal');
    }
  }

  // Send a message to trigger research
  console.log('Triggering research via chat...');
  const chatInput = page.locator('textarea').first();
  const chatVisible = await chatInput.isVisible().catch(() => false);
  if (chatVisible) {
    await chatInput.fill('Continue research — run full qualitative analysis on Mistral AI commercial moat, competitive positioning, and revenue model. Use available public sources.');
    await chatInput.press('Enter');
  }

  // Wait for research agents to run (up to 10 min — real LLMs)
  console.log('Waiting for research findings (up to 10 min)...');
  try {
    await waitForText(page, ['finding', 'Finding', 'TESTING', 'SUPPORTED', 'WEAKENED', 'LOW_CONFIDENCE', 'REASONED', 'KNOWN'], 600000);
    console.log('Research indicators found!');
  } catch {
    console.log('Research indicators not found after 10 min');
  }
  await ss(page, 'p2-05-after-research');

  // ── CP1.2 — After calculus ────────────────────────────────────────────────
  const hypTexts2 = await page.locator('body').evaluate(() => {
    const body = document.body.innerText;
    return body.split('\n').filter(l =>
      l.includes('NOT_STARTED') || l.includes('TESTING') || l.includes('SUPPORTED') ||
      l.includes('WEAKENED') || l.includes('H1') || l.includes('H2') || l.includes('H3') || l.includes('H4') ||
      l.includes('hyp-')
    ).slice(0, 20);
  });
  console.log('CP1.2 Hypothesis status after research:', hypTexts2);
  await ss(page, 'cp1-02-hypotheses-after-research');

  // ── CP2 — Finding cards ────────────────────────────────────────────────────
  console.log('CP2: Looking for finding cards...');
  const findingCardEl = page.locator('[class*="FindingCard"], [class*="finding-card"], [data-testid*="finding"]').first();
  const findingVisible = await findingCardEl.isVisible().catch(() => false);
  console.log('Finding cards visible:', findingVisible);

  // Look for confidence badges
  const greenBadge = await page.locator('[class*="KNOWN"], [class*="known"], :has-text("KNOWN")').count();
  const amberBadge = await page.locator('[class*="REASONED"], [class*="reasoned"], :has-text("REASONED")').count();
  const grayBadge = await page.locator('[class*="LOW_CONFIDENCE"], :has-text("LOW_CONFIDENCE")').count();
  console.log(`CP2: KNOWN=${greenBadge}, REASONED=${amberBadge}, LOW_CONFIDENCE=${grayBadge}`);
  await ss(page, 'cp2-01-finding-cards-full');

  // Look for load-bearing findings
  const loadBearing = await page.locator(':has-text("LOAD-BEARING"), :has-text("load_bearing"), [class*="load"]').count();
  console.log(`CP2.2: Load-bearing findings: ${loadBearing}`);
  await ss(page, 'cp2-02-load-bearing');

  // ── Look for G1 gate ───────────────────────────────────────────────────────
  try {
    await waitForText(page, ['manager review', 'Manager Review', 'G1', 'data decision'], 60000);
  } catch {
    console.log('G1 gate not yet visible');
  }
  await ss(page, 'p2-06-g1-gate-check');

  // Approve G1 if visible
  const g1ReviewBtn = page.locator('button').filter({ hasText: /review now/i });
  const g1ReviewVisible = await g1ReviewBtn.isVisible().catch(() => false);
  if (g1ReviewVisible) {
    console.log('G1 Review button visible, clicking...');
    await g1ReviewBtn.click();
    await page.waitForTimeout(2000);
    await ss(page, 'cp1-03-before-g1-approve');

    // ── CP1.3 — Check for WEAKENED hypothesis before approving ────────────────
    const weakened = await page.locator('body').evaluate(() => {
      return document.body.innerText.includes('WEAKENED');
    });
    console.log('CP1.3: WEAKENED hypothesis present:', weakened);

    // Click approve in modal/gate panel
    const modalApprove = page.locator('[role="dialog"] button, [class*="gate"] button').filter({ hasText: /approve/i }).first();
    if (await modalApprove.isVisible().catch(() => false)) {
      await modalApprove.click();
      await ss(page, 'p2-07-g1-approved');
    } else {
      await page.keyboard.press('Escape');
    }
  }

  // Wait for synthesis + G3 (up to 8 min)
  console.log('Waiting for synthesis and deliverables (up to 8 min)...');
  try {
    await waitForText(page, ['synthesis', 'Synthesis', 'final review', 'Final Review', 'G3', 'memo', 'Memo'], 480000);
    console.log('Synthesis indicators found!');
  } catch {
    console.log('Synthesis indicators not found after 8 min');
  }
  await ss(page, 'p2-08-synthesis-state');

  // ── CP3 — DeliverablePreview ───────────────────────────────────────────────
  console.log('CP3: Looking for Open buttons...');
  const openBtns = page.locator('button').filter({ hasText: /^open$/i });
  const openCount = await openBtns.count();
  console.log(`CP3: Found ${openCount} Open button(s)`);

  if (openCount === 0) {
    // Try clickable deliverable links
    const delivLinks = page.locator('a, button').filter({ hasText: /memo|brief|report|deliverable/i });
    const dlCount = await delivLinks.count();
    console.log(`CP3: Deliverable links: ${dlCount}`);
    await ss(page, 'cp3-01-no-open-btn');
  } else {
    // Click first Open button
    await openBtns.first().click();
    await page.waitForTimeout(2000);
    await ss(page, 'cp3-01-modal-open');

    // ── CP3.2 CRITICAL — Finding count in sidebar vs total ────────────────────
    const modalEl = page.locator('[role="dialog"], [class*="Modal"], [class*="modal"], [class*="Preview"]').first();
    const modalVisible = await modalEl.isVisible().catch(() => false);

    if (modalVisible) {
      // Count finding references in sidebar/modal
      const modalContent = await modalEl.textContent() || '';
      const findingMentions = (modalContent.match(/f-[a-z0-9]+/g) || []).length;
      const findingWordCount = (modalContent.match(/finding/gi) || []).length;
      console.log(`CP3.2: Finding ID references in modal: ${findingMentions}`);
      console.log(`CP3.2: "finding" word occurrences in modal: ${findingWordCount}`);

      // Check sidebar specifically
      const sidebar = page.locator('[class*="sidebar"], [class*="Sidebar"], [class*="side-panel"]').first();
      const sidebarVisible = await sidebar.isVisible().catch(() => false);
      if (sidebarVisible) {
        const sidebarContent = await sidebar.textContent() || '';
        const sidebarFindingCount = (sidebarContent.match(/f-[a-z0-9]+/g) || []).length;
        console.log(`CP3.2: Sidebar finding ID count: ${sidebarFindingCount}`);
      }

      // Get total finding count from DB via API
      const totalFindings = await page.evaluate(async () => {
        const r = await fetch('http://localhost:8095/api/v1/missions/m-mistral-ai-20260427-x-2a2c0b3f/findings');
        if (!r.ok) return null;
        const data = await r.json();
        return Array.isArray(data) ? data.length : (data.findings?.length ?? null);
      });
      console.log(`CP3.2: Total findings via API: ${totalFindings}`);
    }
    await ss(page, 'cp3-02-findings-sidebar');

    // Modal content check
    const preEl = page.locator('pre, [class*="markdown"], [class*="content"]').first();
    const preVisible = await preEl.isVisible().catch(() => false);
    console.log('CP3.1: Markdown/pre content visible:', preVisible);

    // ── CP3.3 — Download ─────────────────────────────────────────────────────
    const downloadBtn = page.locator('[role="dialog"] button, [class*="modal"] button').filter({ hasText: /download/i }).first();
    if (await downloadBtn.isVisible().catch(() => false)) {
      const [download] = await Promise.all([
        page.waitForEvent('download', { timeout: 10000 }).catch(() => null),
        downloadBtn.click(),
      ]);
      console.log('CP3.3: Download triggered:', download ? await download.suggestedFilename() : 'no event');
      await ss(page, 'cp3-03-download');
    } else {
      console.log('CP3.3: No download button in modal');
      await ss(page, 'cp3-03-no-download-btn');
    }

    // ── CP3.4 — Close by clicking outside ─────────────────────────────────
    await page.mouse.click(10, 10);
    await page.waitForTimeout(1000);
    const modalGone = !(await page.locator('[role="dialog"]').isVisible().catch(() => false));
    console.log('CP3.4: Modal closed:', modalGone);
    await ss(page, 'cp3-04-modal-closed');

    // ── CP3.5 — Second deliverable ────────────────────────────────────────
    if (openCount >= 2) {
      await openBtns.nth(1).click();
      await page.waitForTimeout(2000);
      await ss(page, 'cp3-05-second-deliverable');
      await page.keyboard.press('Escape');
    }
  }

  // ── CP1.4 — Expand hypothesis ─────────────────────────────────────────────
  const hypEl = page.locator('[class*="hypothesis"], [class*="Hypothesis"]').first();
  if (await hypEl.isVisible().catch(() => false)) {
    await hypEl.click();
    await page.waitForTimeout(1000);
    await ss(page, 'cp1-04-hypothesis-expanded');

    // Check for linked findings in expanded hypothesis
    const expandedContent = await hypEl.textContent() || '';
    const linkedFindings = (expandedContent.match(/f-[a-z0-9]+/g) || []).length;
    console.log('CP1.4: Linked findings in expanded hypothesis:', linkedFindings);
  } else {
    await ss(page, 'cp1-04-no-hypothesis');
  }

  console.log('Phase 2 verification complete.');
});
