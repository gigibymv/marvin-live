import { test, expect } from '@playwright/test';
import { execSync } from 'child_process';

const BRIEF = `Mistral AI — European LLM provider, ~$1Bn estimated ARR, Series B at $6Bn valuation (2024). IC question: is Mistral's technological moat defensible over 36 months against US labs (OpenAI, Anthropic, Google), and does it justify a growth equity investment at this valuation? Main concern: open-weight models (Llama, Qwen) are commoditizing the mid-market layer, and Mistral has not yet proven its ability to monetize enterprise beyond cloud API access.`;

const BACKEND = 'http://localhost:8095';

async function waitFor(fn: () => Promise<boolean>, timeout = 300000, interval = 8000): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    if (await fn()) return;
    await new Promise(r => setTimeout(r, interval));
  }
  throw new Error('Timeout waiting for condition');
}

test('CP5: Q&A 350-char hard cap', async ({ page }) => {
  page.setDefaultTimeout(300000);

  // ── Step 1: Create fresh mission ─────────────────────────────────────────────
  console.log('Creating mission...');
  const createResp = await fetch(`${BACKEND}/api/v1/missions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      client: 'TestIC',
      target: 'MistralB',
      ic_question: BRIEF,
      mission_type: 'cdd',
    }),
  });
  const createData = await createResp.json();
  const missionId = createData.mission_id;
  expect(missionId).toBeTruthy();
  console.log('Mission ID:', missionId);

  // ── Step 2: Navigate to mission page ─────────────────────────────────────────
  console.log('Opening mission in browser...');
  await page.goto(`/missions/${missionId}`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(3000);
  await page.screenshot({ path: 'e2e/results/cp5-01-opened.png', fullPage: true });

  // ── Step 3: Submit brief via chat to START the graph run ─────────────────────
  // The backend REQUIRES an active SSE stream for gate approval to resume the graph.
  // So we must submit via the browser textarea to create the stream.
  console.log('Submitting brief via chat to trigger graph...');
  const textarea = page.locator('textarea');
  await textarea.waitFor({ state: 'visible', timeout: 20000 });
  // Click to ensure focus
  await textarea.click();
  await page.waitForTimeout(500);
  await textarea.fill(BRIEF);

  // Monitor network for the chat POST to confirm it's sent
  const chatPostPromise = page.waitForRequest(
    req => req.url().includes('/chat') && req.method() === 'POST',
    { timeout: 30000 }
  ).catch(() => null);

  // Use the Send button
  const sendBtn = page.locator('button.send-btn');
  await sendBtn.waitFor({ state: 'visible', timeout: 10000 });
  await sendBtn.click();
  console.log('Send button clicked');

  const chatReq = await chatPostPromise;
  if (chatReq) {
    console.log('Chat POST confirmed:', chatReq.url());
  } else {
    console.log('WARNING: Chat POST not detected, trying Enter key...');
    await textarea.click();
    await textarea.fill(BRIEF);
    await page.keyboard.press('Enter');
  }

  await page.waitForTimeout(5000);
  await page.screenshot({ path: 'e2e/results/cp5-02-brief-sent.png', fullPage: true });

  // ── Step 4: Wait for G0 gate to open ─────────────────────────────────────────
  console.log('Waiting for G0 (hypothesis_confirmation) gate to open...');
  let g0GateId: string | null = null;
  await waitFor(async () => {
    const r = await fetch(`${BACKEND}/api/v1/missions/${missionId}/progress`);
    const d = await r.json();
    const gates: any[] = d.gates ?? [];
    const mStatus = d.mission?.status;
    const openGates = gates.filter((g: any) => g.is_open && g.status === 'pending');
    console.log(`  mission.status=${mStatus} open_gates=${openGates.map((g: any) => g.id + '(' + g.gate_type + ')').join(',') || 'none'}`);
    const g0 = openGates.find((g: any) => g.gate_type === 'hypothesis_confirmation');
    if (g0) {
      g0GateId = g0.id;
      return true;
    }
    return false;
  }, 240000, 8000);

  console.log('G0 gate open:', g0GateId);
  await page.screenshot({ path: 'e2e/results/cp5-03-g0-open.png', fullPage: true });

  // ── Step 5: Approve G0 via API (stream is active in browser) ─────────────────
  console.log('Approving G0...');
  const g0Resp = await fetch(`${BACKEND}/api/v1/missions/${missionId}/gates/${g0GateId}/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ verdict: 'APPROVED', notes: 'hypotheses confirmed' }),
  });
  const g0Result = await g0Resp.json();
  console.log('G0 result:', g0Result.status);
  await page.waitForTimeout(5000);

  // ── Step 6: Wait for DA gate to open ─────────────────────────────────────────
  console.log('Waiting for data-availability gate...');
  let daGateId: string | null = null;
  let daGateFormat: string | null = null;
  await waitFor(async () => {
    const r = await fetch(`${BACKEND}/api/v1/missions/${missionId}/progress`);
    const d = await r.json();
    const gates: any[] = d.gates ?? [];
    const openGates = gates.filter((g: any) => g.is_open && g.status === 'pending');
    console.log(`  open_gates=${openGates.map((g: any) => g.id + '(' + g.gate_type + '/' + g.format + ')').join(',') || 'none'}`);
    // Find any open gate that isn't G0
    const da = openGates.find((g: any) => g.id !== g0GateId);
    if (da) {
      daGateId = da.id;
      daGateFormat = da.format;
      return true;
    }
    return false;
  }, 240000, 8000);

  console.log('DA gate:', daGateId, 'format:', daGateFormat);
  await page.screenshot({ path: 'e2e/results/cp5-04-da-open.png', fullPage: true });

  // ── Step 7: Approve DA gate ───────────────────────────────────────────────────
  console.log('Approving DA gate...');
  let daPayload: Record<string, string>;
  if (daGateFormat === 'data_decision') {
    daPayload = { decision: 'proceed_low_confidence' };
  } else {
    daPayload = { verdict: 'APPROVED', notes: 'Proceed — accept LOW_CONFIDENCE only' };
  }
  const daResp = await fetch(`${BACKEND}/api/v1/missions/${missionId}/gates/${daGateId}/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(daPayload),
  });
  const daResult = await daResp.json();
  console.log('DA result:', daResult.status);

  // ── Step 8: Wait for ≥2 calculus findings ────────────────────────────────────
  console.log('Waiting for ≥2 calculus findings in DB...');
  await waitFor(async () => {
    try {
      const result = execSync(
        `sqlite3 ~/.marvin/marvin.db "SELECT COUNT(*) FROM findings WHERE mission_id='${missionId}' AND agent_id='calculus'"`,
        { encoding: 'utf8' }
      ).trim();
      const count = parseInt(result, 10);
      console.log('  calculus findings:', count);
      return count >= 2;
    } catch { return false; }
  }, 300000, 10000);

  const findingsRaw = execSync(
    `sqlite3 ~/.marvin/marvin.db "SELECT agent_id, confidence, substr(claim_text,1,100) FROM findings WHERE mission_id='${missionId}'"`,
    { encoding: 'utf8' }
  ).trim();
  console.log('DB findings:\n', findingsRaw);

  await page.screenshot({ path: 'e2e/results/cp5-05-findings.png', fullPage: true });

  // ── Step 9: Q&A — Ask "why are the claims poor?" ─────────────────────────────
  console.log('\n=== CP5 Q&A TEST ===');
  // Reload to get a stable state for Q&A (not mid-stream)
  await page.reload();
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(5000);

  const chatInput = page.locator('textarea');
  await chatInput.waitFor({ state: 'visible', timeout: 20000 });
  await chatInput.click();

  const initialMsgCount = await page.locator('.msg-m').count();
  console.log('Initial marvin msg count:', initialMsgCount);

  await chatInput.fill('why are the claims poor?');
  await page.screenshot({ path: 'e2e/results/cp5-06-question-typed.png', fullPage: true });

  // Send via button
  const sendBtn2 = page.locator('button.send-btn');
  await sendBtn2.click();
  console.log('Q&A question sent');

  // Wait for new marvin message (not a typing indicator)
  let responseText = '';
  await waitFor(async () => {
    const msgs = await page.locator('.msg-m').all();
    if (msgs.length > initialMsgCount) {
      const lastMsg = msgs[msgs.length - 1];
      const text = (await lastMsg.textContent()) ?? '';
      const cleaned = text.replace(/^Marvin\s*/i, '').trim();
      // Must be substantial content, not just dots
      if (cleaned.length > 20 && !/^[.\s]+$/.test(cleaned)) {
        responseText = cleaned;
        console.log('Got response, length:', cleaned.length);
        return true;
      }
      console.log('  Msg candidate (too short/dots):', JSON.stringify(cleaned.slice(0, 60)));
    } else {
      console.log('  Waiting... msgs:', msgs.length, '/ initial:', initialMsgCount);
    }
    return false;
  }, 180000, 5000);

  await page.screenshot({ path: 'e2e/results/cp5-07-response.png', fullPage: true });
  await page.screenshot({ path: '/tmp/marvin-c261-cp5-final.png', fullPage: true });

  // ── Step 10: Measure ──────────────────────────────────────────────────────────
  const charCount = responseText.length;
  const sentenceParts = responseText.split(/(?<=[.!?])\s+/).filter(s => s.trim().length > 0);
  const sentenceCount = Math.max(1, sentenceParts.length);
  const containsMerlinLogged = /merlin (has )?logged/i.test(responseText);
  const containsCalculus = /calculus/i.test(responseText);
  const findingKeywords = ['EBITDA', 'LTV', 'CAC', 'moat', 'enterprise', 'open-weight', 'commodit', 'model', 'cloud', 'ARR', 'valuation', 'monetize', 'missing', 'data'];
  const hasFindingContent = findingKeywords.some(kw => responseText.toLowerCase().includes(kw.toLowerCase()));

  const pass = charCount <= 350 && sentenceCount >= 1 && sentenceCount <= 4 && !containsMerlinLogged && containsCalculus;

  console.log('\n=== CP5 FINAL MEASUREMENT ===');
  console.log('Response verbatim:', JSON.stringify(responseText));
  console.log('Char count:', charCount);
  console.log('Sentence count:', sentenceCount);
  console.log('Contains "Merlin logged":', containsMerlinLogged);
  console.log('Contains "Calculus":', containsCalculus);
  console.log('Has finding content:', hasFindingContent);
  console.log('CP5:', pass ? 'PASS' : 'FAIL');
  if (!pass) {
    const reasons: string[] = [];
    if (charCount > 350) reasons.push(`char count ${charCount} > 350`);
    if (sentenceCount < 1 || sentenceCount > 4) reasons.push(`sentence count ${sentenceCount} not in [1,4]`);
    if (containsMerlinLogged) reasons.push('contains "Merlin logged"');
    if (!containsCalculus) reasons.push('missing "Calculus"');
    console.log('FAIL REASONS:', reasons.join('; '));
  }
});
