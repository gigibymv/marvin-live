#!/usr/bin/env node

const API_BASE = process.env.MARVIN_API_BASE ?? "http://127.0.0.1:8095/api/v1";
const FRONTEND_BASE = process.env.MARVIN_FRONTEND_BASE ?? "http://127.0.0.1:3003";

const ADOBE_BRIEF = `CDD — Acquisition of Adobe
[1] CLIENT AND CONTEXT
"CDD"
[2] TARGET
"Target: Adobe, software / digital media and marketing, global"
[3] DEAL ECONOMICS
"€220–250Bn implied valuation, ~$20Bn revenue FY2024, ~25–30% net margin"
[4] COMPETITIVE LANDSCAPE
"Main competitors: Canva, Figma, Salesforce, Microsoft"
[5] INVESTMENT QUESTION
"IC question: Can Adobe maintain its dominant position as creative tools become more accessible and AI-driven?"`;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`POST ${url} failed: ${response.status} ${await response.text()}`);
  }
  return response.json();
}

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`GET ${url} failed: ${response.status} ${await response.text()}`);
  }
  return response.json();
}

async function createMission() {
  return postJson(`${API_BASE}/missions`, {
    client: "MV Capital",
    target: "Adobe",
    mission_type: "cdd",
    ic_question:
      "Can Adobe maintain its dominant position as creative tools become more accessible and AI-driven?",
  });
}

async function streamChatUntilGate(missionId, text, expectedGateType, timeoutMs = 180000) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort("timeout"), timeoutMs);
  const response = await fetch(`${API_BASE}/missions/${missionId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
    signal: controller.signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`chat stream failed: ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() ?? "";
      for (const block of blocks) {
        const eventLine = block.split("\n").find((line) => line.startsWith("event:"));
        const dataLine = block.split("\n").find((line) => line.startsWith("data:"));
        if (!eventLine || !dataLine) continue;
        const event = eventLine.slice("event:".length).trim();
        const rawData = dataLine.slice("data:".length).trim();
        let payload = {};
        try {
          payload = JSON.parse(rawData);
        } catch {
          continue;
        }
        if (event === "gate_pending" && payload.gate_type === expectedGateType) {
          controller.abort("gate-reached");
          return payload;
        }
      }
    }
  } catch (error) {
    if (!String(error).includes("gate-reached") && !String(error).includes("AbortError")) {
      throw error;
    }
  } finally {
    clearTimeout(timeout);
    try {
      await reader.cancel();
    } catch {}
  }
  throw new Error(`Expected gate ${expectedGateType} not reached`);
}

async function waitForGate(missionId, gateType, timeoutMs = 240000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const progress = await getJson(`${API_BASE}/missions/${missionId}/progress`);
    const gate = (progress.gates ?? []).find(
      (entry) => entry.gate_type === gateType && (entry.lifecycle_status === "open" || entry.is_open),
    );
    if (gate) return { progress, gate };
    await sleep(2000);
  }
  throw new Error(`Timed out waiting for gate ${gateType}`);
}

async function waitForMissionComplete(missionId, timeoutMs = 240000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const progress = await getJson(`${API_BASE}/missions/${missionId}/progress`);
    if (progress.mission?.status === "complete") return progress;
    await sleep(2000);
  }
  throw new Error("Timed out waiting for mission completion");
}

async function validateGate(missionId, gateId, verdict = "APPROVED") {
  return postJson(`${API_BASE}/missions/${missionId}/gates/${gateId}/validate`, {
    verdict,
    notes: "",
  });
}

async function main() {
  const { chromium } = await import("playwright");
  const created = await createMission();
  const missionId = created.mission_id;
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1600, height: 1100 } });
  const missionUrl = `${FRONTEND_BASE}/missions/${missionId}`;
  console.log(`[live-test] mission=${missionId}`);
  await page.goto(missionUrl, { waitUntil: "networkidle" });

  await streamChatUntilGate(missionId, ADOBE_BRIEF, "hypothesis_confirmation");
  await page.reload({ waitUntil: "networkidle" });
  await page.screenshot({ path: `/private/tmp/${missionId}-g0.png`, fullPage: true });
  let gateState = await waitForGate(missionId, "hypothesis_confirmation");
  await validateGate(missionId, gateState.gate.id, "APPROVED");

  gateState = await waitForGate(missionId, "manager_review");
  await page.reload({ waitUntil: "networkidle" });
  await page.screenshot({ path: `/private/tmp/${missionId}-g1.png`, fullPage: true });
  await validateGate(missionId, gateState.gate.id, "APPROVED");

  gateState = await waitForGate(missionId, "final_review");
  await page.reload({ waitUntil: "networkidle" });
  await page.screenshot({ path: `/private/tmp/${missionId}-g3.png`, fullPage: true });
  await validateGate(missionId, gateState.gate.id, "APPROVED");

  const finalProgress = await waitForMissionComplete(missionId);
  await page.reload({ waitUntil: "networkidle" });
  await page.screenshot({ path: `/private/tmp/${missionId}-final.png`, fullPage: true });
  await browser.close();

  const readyDeliverables = (finalProgress.deliverables ?? []).filter(
    (deliverable) => deliverable.status === "ready" && deliverable.file_path,
  );
  console.log(
    JSON.stringify(
      {
        missionId,
        status: finalProgress.mission?.status,
        synthesisState: finalProgress.mission?.synthesis_state,
        readyDeliverables: readyDeliverables.map((deliverable) => deliverable.deliverable_type),
        hypotheses: (finalProgress.hypotheses ?? []).map((hypothesis) => ({
          label: hypothesis.label,
          status: hypothesis.computed?.status ?? hypothesis.status,
          rationale: hypothesis.computed?.rationale ?? null,
        })),
      },
      null,
      2,
    ),
  );
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
