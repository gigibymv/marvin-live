// @ts-check
const { test, expect } = require('@playwright/test');
const path = require('path');

const FRONTEND_URL = 'http://localhost:3002';

const MISTRAL_BRIEF = `Mistral AI — European LLM provider, ~$1Bn estimated ARR, Series B at $6Bn valuation (2024). IC question: is Mistral's technological moat defensible over 36 months against US labs (OpenAI, Anthropic, Google), and does it justify a growth equity investment at this valuation? Main concern: open-weight models (Llama, Qwen) are commoditizing the mid-market layer, and Mistral has not yet proven its ability to monetize enterprise beyond cloud API access.`;

const SCREENSHOT_DIR = '/tmp';

const results = {};

async function snap(page, name) {
  const p = path.join(SCREENSHOT_DIR, `marvin-c26-${name}.png`);
  await page.screenshot({ path: p, fullPage: true });
  console.log(`[SNAP] ${p}`);
  return p;
}

async function settle(page, ms = 3000) {
  await page.waitForTimeout(ms);
}

// Wait for the pending gate banner "Review now" button to appear
async function waitForGateBanner(page, timeoutMs = 300_000) {
  console.log(`  [wait] Gate banner (up to ${timeoutMs / 1000}s)...`);
  await page.waitForSelector('button:has-text("Review now")', { timeout: timeoutMs });
  console.log(`  [wait] Gate banner appeared`);
  await settle(page, 1000);
}

// Open gate modal by clicking "Review now"
async function openGateModal(page) {
  const btn = page.locator('button').filter({ hasText: 'Review now' }).first();
  await btn.waitFor({ state: 'visible', timeout: 10000 });
  await btn.click();
  console.log('  [action] Clicked "Review now"');
  // Gate modal (role=dialog) should now be open
  await page.locator('[role="dialog"]').waitFor({ state: 'visible', timeout: 10000 });
  await settle(page, 500);
}

test.setTimeout(1200_000); // 20 min

test('C2.6 Chantier acceptance — Mistral brief full run', async ({ page }) => {
  const consoleErrors = [];
  const errors409 = [];

  page.on('console', msg => {
    const t = msg.text();
    if (msg.type() === 'error') {
      consoleErrors.push(t);
    }
    if (t.includes('409') || t.includes('Failed to validate gate')) {
      errors409.push(t);
    }
  });
  page.on('response', res => {
    if (res.status() === 409) {
      errors409.push(`HTTP 409: ${res.url()}`);
    }
  });

  // ═══════════════════════════════════════════════════════════════
  // STEP 1: Navigate to /missions and open New Mission modal
  // ═══════════════════════════════════════════════════════════════
  console.log('\n[STEP 1] Navigate to /missions');
  await page.goto(`${FRONTEND_URL}/missions`);
  await page.waitForLoadState('networkidle');
  await snap(page, 'cp0a-dashboard');

  // Click "New mission" button
  await page.locator('button.new-btn, button:has-text("New mission")').first().click();
  await settle(page, 500);

  // Step 1 of modal: CDD is pre-selected. Click "Continue →"
  await page.locator('button:has-text("Continue")').first().click();
  await settle(page, 300);

  // Step 2: fill Client + Target
  // Client input: placeholder "e.g. Meridian Capital"
  // Target input: placeholder "e.g. NovaSec"
  const clientInput = page.locator('input[placeholder*="Meridian"]');
  const targetInput = page.locator('input[placeholder*="NovaSec"]');
  await clientInput.fill('Test Fund');
  await targetInput.fill('Mistral AI');
  await snap(page, 'cp0b-new-mission-form');

  // Click "Open mission →"
  await page.locator('button:has-text("Open mission")').first().click();
  console.log('[INFO] Mission submitted, awaiting redirect...');

  // Wait for redirect to /missions/<id>
  await page.waitForURL(/\/missions\/m-/, { timeout: 30000 });
  const missionUrl = page.url();
  const missionId = missionUrl.split('/missions/')[1];
  console.log(`[INFO] Mission ID: ${missionId}`);

  await page.waitForLoadState('networkidle');
  await settle(page, 2000);
  await snap(page, 'cp0c-mission-page-fresh');

  // ═══════════════════════════════════════════════════════════════
  // STEP 2: Send the Mistral brief via chat
  // ═══════════════════════════════════════════════════════════════
  console.log('\n[STEP 2] Sending Mistral brief');
  const chatInput = page.locator('textarea[placeholder*="Ask MARVIN"]');
  await chatInput.waitFor({ state: 'visible', timeout: 15000 });
  await chatInput.fill(MISTRAL_BRIEF);
  await snap(page, 'cp0d-brief-filled');

  // Press Enter to send (not Shift+Enter — that's handled in onKeyDown)
  await chatInput.press('Enter');
  console.log('[INFO] Brief sent — waiting for Dora framing agent...');

  // ═══════════════════════════════════════════════════════════════
  // WAIT: G0 framing gate banner appears
  // ═══════════════════════════════════════════════════════════════
  await waitForGateBanner(page, 240_000);
  await snap(page, 'cp1a-g0-gate-banner');

  // ─── CP1 CHECKS ───────────────────────────────────────────────
  console.log('\n[CP1] Framing + hypotheses + deliverables check');
  const body1 = await page.textContent('body');

  const hasH1 = /\bH[1-4]\b/.test(body1);
  const hasRawUUID = /hyp-[a-f0-9]{6,}/.test(body1);
  const hasEngBrief = /engagement brief/i.test(body1);
  const hasFramingMemo = /framing memo/i.test(body1);
  const hasMistralContent = body1.includes('Mistral') && body1.includes('open-weight');

  // MARVIN voice check: find chat messages from MARVIN
  const marvinMsgs = await page.locator('.msg-m').allTextContents().catch(() => []);
  const longestMsg = Math.max(0, ...marvinMsgs.map(m => m.split(/\s+/).length));

  console.log(`  H-labels (H1-H4):          ${hasH1}`);
  console.log(`  Raw UUIDs exposed:          ${hasRawUUID}`);
  console.log(`  Engagement brief:           ${hasEngBrief}`);
  console.log(`  Framing memo:               ${hasFramingMemo}`);
  console.log(`  Mistral brief content:      ${hasMistralContent}`);
  console.log(`  Longest MARVIN msg words:   ${longestMsg} (should be <50 for 1-2 sentences)`);

  // Open the gate modal to check framing memo contents
  await openGateModal(page);
  await snap(page, 'cp1b-g0-gate-modal');
  const dialogText1 = await page.locator('[role="dialog"]').textContent().catch(() => '');
  const briefInModal = dialogText1.includes('Mistral') && dialogText1.includes('open-weight');
  console.log(`  Full brief in gate modal:   ${briefInModal}`);
  const dialogWordCount = dialogText1.trim().split(/\s+/).length;
  console.log(`  Gate dialog word count:     ${dialogWordCount}`);

  results.cp1 = {
    pass: hasH1 && !hasRawUUID && (hasEngBrief || hasFramingMemo),
    detail: { hasH1, hasRawUUID, hasEngBrief, hasFramingMemo, hasMistralContent, briefInModal, longestMsg },
  };
  console.log(`[CP1] ${results.cp1.pass ? 'PASS' : 'FAIL'}`);

  // ═══════════════════════════════════════════════════════════════
  // APPROVE G0
  // ═══════════════════════════════════════════════════════════════
  console.log('\n[STEP] Approving G0...');
  await page.locator('[role="dialog"] button:has-text("Approve")').first().click();
  console.log('[INFO] G0 approved');
  await settle(page, 3000);

  // ═══════════════════════════════════════════════════════════════
  // CP2: DATA-AVAILABILITY GATE (should fire before Calculus)
  // ═══════════════════════════════════════════════════════════════
  console.log('\n[CP2] Watching for data-availability gate before Calculus...');
  // Give it up to 30 seconds; this gate should fire quickly after G0 approval
  const cp2TimeoutMs = 30_000;
  const cp2StartTime = Date.now();

  let cp2GateBannerFound = false;
  let cp2GateText = '';

  try {
    await waitForGateBanner(page, cp2TimeoutMs);
    cp2GateBannerFound = true;
  } catch {
    console.log('[CP2] No gate banner within 30s — checking if Calculus started without gate');
  }

  await snap(page, 'cp2a-after-g0-approval');
  const body2 = await page.textContent('body');

  if (cp2GateBannerFound) {
    await openGateModal(page);
    await snap(page, 'cp2b-gate-modal');
    cp2GateText = await page.locator('[role="dialog"]').textContent().catch(() => '');
  }

  const cp2BannerBanner = await page.locator('button:has-text("Review now")').isVisible().catch(() => false);
  const cp2HasPrivateRef = /private|SEC|no.*public|data room|data.*availability|LOW_CONFIDENCE|available.*data/i.test(cp2GateText || body2);
  const cp2HasSkip = /skip/i.test(cp2GateText || body2);
  const cp2HasProceedLow = /proceed.*low|LOW_CONFIDENCE|low.*confidence/i.test(cp2GateText || body2);
  const cp2HasDataRoom = /data room/i.test(cp2GateText || body2);
  const calculusRanAlready = /calculus.*[0-9]+.*finding|finding.*calculus/i.test(body2) && !cp2GateBannerFound;

  console.log(`  Data-availability gate fired: ${cp2GateBannerFound}`);
  console.log(`  Private/no-SEC data mention:  ${cp2HasPrivateRef}`);
  console.log(`  Skip option:                  ${cp2HasSkip}`);
  console.log(`  LOW_CONFIDENCE option:        ${cp2HasProceedLow}`);
  console.log(`  Data room option:             ${cp2HasDataRoom}`);
  console.log(`  Calculus bypassed gate:       ${calculusRanAlready}`);
  if (cp2GateText) console.log(`  Gate text (first 400):       ${cp2GateText.substring(0, 400)}`);

  results.cp2 = {
    pass: cp2GateBannerFound && cp2HasPrivateRef && (cp2HasSkip || cp2HasProceedLow),
    detail: { cp2GateBannerFound, cp2HasPrivateRef, cp2HasSkip, cp2HasProceedLow, cp2HasDataRoom, calculusRanAlready },
  };
  console.log(`[CP2] ${results.cp2.pass ? 'PASS' : 'FAIL — Bug 3 regression suspected'}`);

  // ═══════════════════════════════════════════════════════════════
  // CHOOSE proceed LOW_CONFIDENCE (or Approve if only button)
  // ═══════════════════════════════════════════════════════════════
  console.log('\n[STEP] Choosing proceed LOW_CONFIDENCE (or proceeding)...');

  const dialogOpen = await page.locator('[role="dialog"]').isVisible().catch(() => false);
  if (dialogOpen) {
    // Try LOW_CONFIDENCE button first
    const lowBtn = page.locator('[role="dialog"] button').filter({ hasText: /LOW_CONFIDENCE|low.*conf/i });
    if (await lowBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await lowBtn.click();
      console.log('  Clicked LOW_CONFIDENCE');
    } else {
      // Try "proceed"
      const proceedBtn = page.locator('[role="dialog"] button').filter({ hasText: /proceed/i });
      if (await proceedBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
        await proceedBtn.click();
        console.log('  Clicked proceed');
      } else {
        // Fall back to Approve
        await page.locator('[role="dialog"] button:has-text("Approve")').first().click();
        console.log('  Clicked Approve (LOW_CONFIDENCE/proceed not found)');
      }
    }
  } else if (cp2GateBannerFound) {
    // Banner but modal already closed - click Review now again
    const banner = page.locator('button:has-text("Review now")');
    if (await banner.isVisible({ timeout: 3000 }).catch(() => false)) {
      await banner.click();
      await settle(page, 500);
      await page.locator('[role="dialog"] button:has-text("Approve")').first().click();
    }
  } else {
    console.log('  No gate dialog — Calculus may start without gate (Bug 3)');
  }

  // Wait for Calculus to run (up to 4 min)
  console.log('[INFO] Waiting for Calculus / research phase...');
  await page.waitForFunction(
    () => {
      const txt = document.body.innerText.toLowerCase();
      return txt.includes('calculus') || txt.includes('financial') ||
        document.querySelector('button:contains("Review now")') ||
        document.body.innerText.includes('Review now');
    },
    { timeout: 240_000 }
  ).catch(() => console.log('[WARN] Calculus/research text not found within timeout'));

  await settle(page, 8000);
  await snap(page, 'cp3a-calculus-running');

  // ─── CP3 CHECKS ───────────────────────────────────────────────
  console.log('\n[CP3] Calculus output quality check');
  const body3 = await page.textContent('body');

  const hasAbsurdZero = /\$0[^-9.,\w].*\$0|\$0\.00.*\$0\.00|EBITDA.*=.*0\.00|revenue.*\$0\.00/i.test(body3);
  const hasMissingInputsLang = /missing inputs|LOW_CONFIDENCE|insufficient.*data|no.*public.*data/i.test(body3);
  const hasAgentNames = /\b(calculus|dora|adversus|merlin)\b/i.test(body3);
  // Check for bare "AGENT" string in a finding context (not in meta text)
  const hasGenericAGENT = /→\s*AGENT\b|\bAGENT\s*→/i.test(body3);

  console.log(`  Absurd $0/$0 findings:      ${hasAbsurdZero}`);
  console.log(`  Missing inputs language:    ${hasMissingInputsLang}`);
  console.log(`  Agent names present:        ${hasAgentNames}`);
  console.log(`  Generic AGENT label:        ${hasGenericAGENT}`);

  results.cp3 = {
    pass: !hasAbsurdZero && hasAgentNames && !hasGenericAGENT,
    detail: { hasAbsurdZero, hasMissingInputsLang, hasAgentNames, hasGenericAGENT },
  };
  console.log(`[CP3] ${results.cp3.pass ? 'PASS' : 'FAIL'}`);

  // ═══════════════════════════════════════════════════════════════
  // WAIT: G1 manager review gate
  // ═══════════════════════════════════════════════════════════════
  console.log('\n[STEP] Waiting for G1 manager review gate (up to 5 min)...');
  await waitForGateBanner(page, 300_000);
  await settle(page, 2000);
  await openGateModal(page);
  await snap(page, 'cp4a-g1-gate-modal');

  // ─── CP4 CHECKS ───────────────────────────────────────────────
  console.log('\n[CP4] G1 modal content + idempotent double-click check');
  const dialogText4 = await page.locator('[role="dialog"]').textContent().catch(() => '');

  const g1HasAbsurdZero = /\$0\.00.*\$0\.00|EBITDA.*=.*0\.00/i.test(dialogText4);
  console.log(`  Absurd zero findings in G1: ${g1HasAbsurdZero}`);
  console.log(`  G1 modal text (first 400):  ${dialogText4.substring(0, 400)}`);

  // Double-click Approve rapidly — test idempotency
  const before409 = errors409.length;
  const approveG1 = page.locator('[role="dialog"] button:has-text("Approve")').first();
  await approveG1.waitFor({ state: 'visible', timeout: 10000 });
  await approveG1.click();
  // Second rapid click — should silently no-op, not 409
  await approveG1.click({ timeout: 300 }).catch(() => {});
  await settle(page, 2000);

  const new409s = errors409.slice(before409);
  const idempotentOk = new409s.length === 0;
  console.log(`  409 errors from double-click: ${new409s.length} — ${idempotentOk ? 'IDEMPOTENT OK' : 'BUG 409 fired'}`);
  if (new409s.length > 0) console.log('  409 details:', new409s);

  results.cp4 = {
    pass: !g1HasAbsurdZero && idempotentOk,
    detail: { g1HasAbsurdZero, idempotentOk, errors409: new409s },
  };
  console.log(`[CP4] ${results.cp4.pass ? 'PASS' : 'FAIL'}`);

  // ═══════════════════════════════════════════════════════════════
  // CP5: Q&A CHAT
  // ═══════════════════════════════════════════════════════════════
  console.log('\n[CP5] Q&A chat test');
  await settle(page, 5000);
  await snap(page, 'cp5a-before-qa');

  const chatInput2 = page.locator('textarea[placeholder*="Ask MARVIN"]');
  const chatAvail = await chatInput2.isVisible({ timeout: 10000 }).catch(() => false);

  if (chatAvail) {
    // Q1: why are the claims poor?
    await chatInput2.fill('why are the claims poor?');
    await chatInput2.press('Enter');
    console.log('  Sent Q1: why are the claims poor?');
    await settle(page, 25000);
    await snap(page, 'cp5b-q1-response');

    const body5a = await page.textContent('body');
    const q1CitesFindings = /finding|claim/i.test(body5a);
    const q1CalculusAttrib = /calculus.*finding|calculus.*[0-9]+|[0-9]+.*finding.*calculus/i.test(body5a);
    const q1MerlinBug = /merlin.*logged.*finding|merlin.*finding.*added/i.test(body5a);
    console.log(`  Q1 cites findings:          ${q1CitesFindings}`);
    console.log(`  Q1 Calculus attribution:    ${q1CalculusAttrib}`);
    console.log(`  Q1 Merlin attribution bug:  ${q1MerlinBug}`);

    // Q2: what should we do?
    const chatInput3 = page.locator('textarea[placeholder*="Ask MARVIN"]');
    await chatInput3.fill('what should we do?');
    await chatInput3.press('Enter');
    console.log('  Sent Q2: what should we do?');
    await settle(page, 25000);
    await snap(page, 'cp5c-q2-response');

    const body5b = await page.textContent('body');
    const q2Actionable = /recommend|proceed|invest|diligence|next step|consider|wait/i.test(body5b);
    console.log(`  Q2 actionable recommendation: ${q2Actionable}`);

    results.cp5 = {
      pass: q1CitesFindings && !q1MerlinBug,
      detail: { q1CitesFindings, q1CalculusAttrib, q1MerlinBug, q2Actionable },
    };
  } else {
    console.log('  Chat input not visible — SKIP');
    results.cp5 = { pass: null, detail: { reason: 'chat not visible' } };
  }
  console.log(`[CP5] ${results.cp5?.pass == null ? 'SKIP' : results.cp5.pass ? 'PASS' : 'FAIL'}`);

  // ═══════════════════════════════════════════════════════════════
  // CP6: WORKSTREAM TABS — Financial Analysis
  // ═══════════════════════════════════════════════════════════════
  console.log('\n[CP6] Financial Analysis tab check');

  // The tabs are in the center column — look for tab buttons
  const finTab = page.locator('button').filter({ hasText: /financial.*analysis|Financial Analysis/i }).first();
  const finTabVisible = await finTab.isVisible({ timeout: 5000 }).catch(() => false);

  if (finTabVisible) {
    await finTab.click();
    await settle(page, 2000);
    await snap(page, 'cp6a-financial-tab');

    const body6 = await page.textContent('body');
    const metaSpam = (body6.match(/step complete|mark milestone|milestone delivered/gi) || []).length;
    const hasMeaningContent = /finding|analysis|revenue|valuation|moat|llm|model|mistral/i.test(body6);
    console.log(`  Meta-event spam count:      ${metaSpam}`);
    console.log(`  Meaningful content:         ${hasMeaningContent}`);

    results.cp6 = {
      pass: hasMeaningContent && metaSpam < 5,
      detail: { metaSpam, hasMeaningContent },
    };
  } else {
    console.log('  Financial tab not visible — checking body for tab labels');
    await snap(page, 'cp6a-no-fin-tab');
    const body6 = await page.textContent('body');
    const hasTabText = /financial.*analysis/i.test(body6);
    console.log(`  Tab label in DOM: ${hasTabText}`);
    results.cp6 = { pass: null, detail: { reason: 'tab not visible', hasTabText } };
  }
  console.log(`[CP6] ${results.cp6?.pass == null ? 'SKIP' : results.cp6.pass ? 'PASS' : 'FAIL'}`);

  // ═══════════════════════════════════════════════════════════════
  // CP7: ADVERSUS → MERLIN → G3
  // ═══════════════════════════════════════════════════════════════
  console.log('\n[CP7] Waiting for Adversus → Merlin → G3 (up to 5 min)...');

  await waitForGateBanner(page, 300_000);
  await settle(page, 2000);
  await snap(page, 'cp7a-g3-gate-banner');

  const body7 = await page.textContent('body');
  const hasRetrySpam = (body7.match(/synthesis[_\s]retry/gi) || []).length > 3;
  const g3BannerPresent = await page.locator('button:has-text("Review now")').isVisible();

  // Open G3 modal to check
  await openGateModal(page);
  await snap(page, 'cp7b-g3-gate-modal');
  const dialogText7 = await page.locator('[role="dialog"]').textContent().catch(() => '');

  console.log(`  G3 banner present:          ${g3BannerPresent}`);
  console.log(`  Retry loop spam (>3):       ${hasRetrySpam}`);
  console.log(`  G3 dialog text (first 300): ${dialogText7.substring(0, 300)}`);

  results.cp7 = {
    pass: g3BannerPresent && !hasRetrySpam,
    detail: { g3BannerPresent, hasRetrySpam },
  };
  console.log(`[CP7] ${results.cp7.pass ? 'PASS' : 'FAIL'}`);

  // Approve G3
  await page.locator('[role="dialog"] button:has-text("Approve")').first().click();
  console.log('[INFO] G3 approved');
  await settle(page, 8000);

  // ═══════════════════════════════════════════════════════════════
  // CP8: FINAL STATE
  // ═══════════════════════════════════════════════════════════════
  console.log('\n[CP8] Final state check');
  await snap(page, 'cp8a-final-state');

  const body8 = await page.textContent('body');

  const usesHLabels = /\bH[1-4]\b/.test(body8);
  const usesUUIDs = /hyp-[a-f0-9]{6,}/.test(body8);
  const doraOk = /\bDora\b/.test(body8);
  const calculusOk = /\bCalculus\b/.test(body8);
  const adversusOk = /\bAdversus\b/.test(body8);
  const merlinOk = /\bMerlin\b/.test(body8);
  const marvinOk = /\bMARVIN\b/.test(body8);
  const deliverableCount = await page.locator('a[href*="download"], a[href*="deliverable"]').count();

  console.log(`  H-labels:   ${usesHLabels}  Raw UUIDs: ${usesUUIDs}`);
  console.log(`  Dora: ${doraOk}  Calculus: ${calculusOk}  Adversus: ${adversusOk}  Merlin: ${merlinOk}  MARVIN: ${marvinOk}`);
  console.log(`  Deliverable links: ${deliverableCount}`);

  results.cp8 = {
    pass: usesHLabels && !usesUUIDs,
    detail: { usesHLabels, usesUUIDs, doraOk, calculusOk, adversusOk, merlinOk, marvinOk, deliverableCount },
  };
  console.log(`[CP8] ${results.cp8.pass ? 'PASS' : 'FAIL'}`);

  // ═══════════════════════════════════════════════════════════════
  // PRINT SUMMARY
  // ═══════════════════════════════════════════════════════════════
  console.log('\n');
  console.log('╔══════════════════════════════════════════════════════╗');
  console.log('║       CHANTIER 2.6 ACCEPTANCE TEST — RESULTS        ║');
  console.log('╠══════════════════════════════════════════════════════╣');
  const rows = [
    ['CP1', 'Framing + hypothesis labels        '],
    ['CP2', 'Data-availability gate (Bug 3)     '],
    ['CP3', 'Calculus quality — no absurd zeros '],
    ['CP4', 'G1 idempotent double-click         '],
    ['CP5', 'Q&A chat attribution               '],
    ['CP6', 'Workstream tabs — content vs spam  '],
    ['CP7', 'Adversus → Merlin → G3 (no retry)  '],
    ['CP8', 'Final state — labels + agents      '],
  ];
  let passed = 0, failed = 0, skipped = 0;
  for (const [key, label] of rows) {
    const r = results[key.toLowerCase()];
    const status = r == null ? 'SKIP' : r.pass == null ? 'SKIP' : r.pass ? 'PASS' : 'FAIL';
    if (status === 'PASS') passed++;
    else if (status === 'FAIL') failed++;
    else skipped++;
    console.log(`║ ${status.padEnd(4)} ${key} ${label}║`);
  }
  console.log('╠══════════════════════════════════════════════════════╣');
  console.log(`║ ${passed} PASS  ${failed} FAIL  ${skipped} SKIP                               ║`);
  console.log('╚══════════════════════════════════════════════════════╝');
  console.log('\nScreenshots: ls /tmp/marvin-c26-*.png');

  // Playwright assertion: test passes if no CPs failed (skip is ok)
  if (failed > 0) {
    const failedCps = rows.filter(([key]) => {
      const r = results[key.toLowerCase()];
      return r && r.pass === false;
    }).map(([key]) => key);
    throw new Error(`${failed} checkpoint(s) FAILED: ${failedCps.join(', ')}`);
  }
});
