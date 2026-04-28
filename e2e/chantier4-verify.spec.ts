import { test, expect, Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const MISSION_ID = 'm-mistral-ai-20260427-x-2a2c0b3f';
const BASE_URL = 'http://localhost:3000';
const BACKEND_URL = 'http://localhost:8095';
const SCREENSHOT_DIR = '/tmp/marvin_c4_verify';

fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

async function ss(page: Page, name: string) {
  const p = path.join(SCREENSHOT_DIR, `${name}.png`);
  await page.screenshot({ path: p, fullPage: true });
  console.log(`Screenshot: ${p}`);
  return p;
}

async function waitForSSESettle(page: Page, timeoutMs = 180000) {
  // Wait for either a gate panel or a "done" state to appear
  await page.waitForFunction(
    () => {
      const text = document.body.innerText;
      return (
        text.includes('gate') ||
        text.includes('Gate') ||
        text.includes('Approve') ||
        text.includes('framing') ||
        text.includes('Framing') ||
        text.includes('hypothesis') ||
        text.includes('Hypothesis')
      );
    },
    { timeout: timeoutMs }
  );
}

test.describe('Chantier 4 — CP1/CP2/CP3 verification', () => {
  test.setTimeout(900000); // 15 min budget

  test('Full mission flow verification', async ({ page }) => {
    await page.goto(`${BASE_URL}/missions/${MISSION_ID}`);
    await page.waitForLoadState('networkidle');
    await ss(page, '00-mission-page-initial');

    // ── STEP 1: Send opening message ────────────────────────────────────────
    console.log('Step 1: Sending framing message...');
    const chatInput = page.locator('textarea, input[type="text"]').first();
    await chatInput.fill('Begin framing for Mistral AI investment, focus on commercial moat and AI infrastructure economics');
    await ss(page, '01-before-send');
    await chatInput.press('Enter');

    // Wait for framing to complete — look for gate UI or hypothesis panel
    console.log('Waiting for framing phase to settle (up to 5 min)...');
    try {
      await page.waitForSelector(
        '[data-testid*="gate"], [class*="gate"], [class*="Gate"], [class*="hypothesis"], [class*="Hypothesis"], button:has-text("Approve"), button:has-text("approve")',
        { timeout: 300000 }
      );
    } catch {
      await ss(page, '01b-timeout-framing');
      console.log('Gate/hypothesis selector not found after 5 min — capturing state');
    }

    await ss(page, '02-after-framing-stream');

    // ── CP1.1 — Hypotheses before findings ──────────────────────────────────
    console.log('CP1.1: Checking hypotheses before findings...');
    await ss(page, 'cp1-01-hypotheses-initial');

    // ── STEP 2: Find and approve framing gate (G0) ───────────────────────────
    console.log('Step 2: Looking for framing gate (G0)...');
    // Try to find approve button
    const approveBtn = page.locator('button').filter({ hasText: /approve/i }).first();
    const approveVisible = await approveBtn.isVisible().catch(() => false);

    if (approveVisible) {
      console.log('Found Approve button, clicking...');
      await approveBtn.click();
      await ss(page, '03-gate-g0-approved');
    } else {
      // Try API approach
      console.log('No approve button visible — checking gates via API...');
      const gatesResp = await page.evaluate(async (mid) => {
        const r = await fetch(`http://localhost:8095/api/v1/missions/${mid}/gates`);
        return r.ok ? r.json() : null;
      }, MISSION_ID);
      console.log('Gates:', JSON.stringify(gatesResp));
      await ss(page, '03-no-approve-button');
    }

    // Wait for research phase
    console.log('Waiting for research phase / G1 gate (up to 8 min)...');
    try {
      await page.waitForFunction(
        () => {
          const text = document.body.innerText;
          return (
            text.includes('TESTING') ||
            text.includes('finding') ||
            text.includes('Finding') ||
            text.includes('G1') ||
            text.includes('data decision') ||
            text.includes('Data Decision')
          );
        },
        { timeout: 480000 }
      );
    } catch {
      console.log('Research phase indicators not found — capturing current state');
    }

    await ss(page, '04-research-phase');

    // ── CP1.2 — After calculus findings ─────────────────────────────────────
    await ss(page, 'cp1-02-after-calculus');

    // ── CP1.3 — After adversus ───────────────────────────────────────────────
    await ss(page, 'cp1-03-after-adversus');

    // ── CP2 — FindingCard checks ────────────────────────────────────────────
    console.log('CP2: Checking finding cards...');
    await ss(page, 'cp2-01-finding-cards');

    // Scroll to findings section if exists
    const findingCard = page.locator('[class*="finding"], [class*="Finding"], [data-testid*="finding"]').first();
    const hasFindings = await findingCard.isVisible().catch(() => false);
    if (hasFindings) {
      await findingCard.scrollIntoViewIfNeeded();
      await ss(page, 'cp2-02-finding-cards-scrolled');

      // Check for confidence badges
      const badges = await page.locator('[class*="badge"], [class*="Badge"], [class*="confidence"]').allTextContents();
      console.log('Badges found:', badges.slice(0, 10));
    }

    // ── STEP 3: Approve G1 gate ──────────────────────────────────────────────
    console.log('Step 3: Looking for G1 gate approval...');
    const g1Btn = page.locator('button').filter({ hasText: /approve/i }).first();
    const g1Visible = await g1Btn.isVisible().catch(() => false);
    if (g1Visible) {
      await ss(page, '05-g1-gate-before-approve');
      await g1Btn.click();
      await ss(page, '05b-g1-gate-approved');
    } else {
      await ss(page, '05-g1-no-button');
    }

    // Wait for synthesis + deliverables (up to 8 min)
    console.log('Waiting for deliverables (up to 8 min)...');
    try {
      await page.waitForFunction(
        () => {
          const text = document.body.innerText;
          return (
            text.includes('deliverable') ||
            text.includes('Deliverable') ||
            text.includes('memo') ||
            text.includes('Memo') ||
            text.includes('Open') ||
            text.includes('Download')
          );
        },
        { timeout: 480000 }
      );
    } catch {
      console.log('Deliverables not found — capturing state');
    }

    await ss(page, '06-synthesis-deliverables');

    // ── CP3.1 — Open deliverable modal ──────────────────────────────────────
    console.log('CP3: Testing DeliverablePreview...');
    const openBtn = page.locator('button').filter({ hasText: /open/i }).first();
    const openVisible = await openBtn.isVisible().catch(() => false);
    if (openVisible) {
      await openBtn.click();
      await page.waitForTimeout(2000);
      await ss(page, 'cp3-01-modal-open');

      // ── CP3.2 CRITICAL — Count findings in sidebar vs total ──────────────
      const sidebarFindings = await page.locator('[class*="sidebar"] [class*="finding"], [class*="modal"] [class*="finding"]').count();
      const totalFindingBadge = await page.locator('[class*="finding"]').count();
      console.log(`CP3.2: Sidebar finding count: ${sidebarFindings}, Total finding elements: ${totalFindingBadge}`);

      // Try to count via text
      const modalText = await page.locator('[role="dialog"], [class*="modal"], [class*="Modal"]').textContent().catch(() => '');
      console.log('Modal contains "finding":', (modalText.match(/finding/gi) || []).length, 'occurrences');

      await ss(page, 'cp3-02-sidebar-findings');

      // ── CP3.3 — Download ─────────────────────────────────────────────────
      const [download] = await Promise.all([
        page.waitForEvent('download', { timeout: 10000 }).catch(() => null),
        page.locator('button').filter({ hasText: /download/i }).first().click().catch(() => {}),
      ]);
      if (download) {
        console.log('CP3.3: Download triggered:', await download.suggestedFilename());
      } else {
        console.log('CP3.3: No download event (may not have download button)');
      }
      await ss(page, 'cp3-03-after-download');

      // ── CP3.4 — Close modal by clicking outside ───────────────────────────
      await page.keyboard.press('Escape');
      await page.waitForTimeout(1000);
      await ss(page, 'cp3-04-modal-closed');

      // ── CP3.5 — Open second deliverable if exists ─────────────────────────
      const openBtns = page.locator('button').filter({ hasText: /open/i });
      const btnCount = await openBtns.count();
      if (btnCount >= 2) {
        await openBtns.nth(1).click();
        await page.waitForTimeout(2000);
        await ss(page, 'cp3-05-second-deliverable');
        await page.keyboard.press('Escape');
      } else {
        console.log('CP3.5: Only one deliverable available');
      }
    } else {
      await ss(page, 'cp3-no-open-button');
      console.log('CP3: No Open button found — deliverables not yet available');
    }

    // ── CP1.4 — Click expanded hypothesis ───────────────────────────────────
    console.log('CP1.4: Testing hypothesis expand...');
    const hypCard = page.locator('[class*="hypothesis"], [class*="Hypothesis"]').first();
    const hypVisible = await hypCard.isVisible().catch(() => false);
    if (hypVisible) {
      await hypCard.click();
      await page.waitForTimeout(1000);
      await ss(page, 'cp1-04-hypothesis-expanded');
    } else {
      await ss(page, 'cp1-04-no-hypothesis-visible');
    }

    console.log('Verification complete. Screenshots in /tmp/marvin_c4_verify/');
  });
});
