# Debug Log

Bugs found and fixed during development. Most recent first.

---

## 2026-05-02 — `ic_question` required field breaks mission creation

**Symptom:** "Failed to fetch" on "Open mission" button in the New Mission modal.

**Root cause:** Codex commit `847365d` made `ic_question` a required field in `CreateMissionRequest` (`marvin_ui/server.py:715`). The frontend never sends it at creation time — the IC question is asked later in chat, then persisted via `persist_framing` → `_derive_ic_question`. The contract was always `ic_question: ""` at creation (see `lib/missions/repository.ts` comment: `// Will be asked in chat`).

**Fix:** `marvin_ui/server.py` — changed `ic_question: str` → `ic_question: str = ""` in `CreateMissionRequest`.

**Files touched:** `marvin_ui/server.py`

---

## 2026-05-02 — Render webhook disconnected, auto-deploy not triggering

**Symptom:** Push to `main` did not trigger Render redeploy.

**Root cause:** GitHub → Render webhook was disconnected (`gh api repos/.../hooks` returned `[]`).

**Fix:** Triggered manual deploys via Render CLI:
```bash
render deploys create srv-d7p2l53bc2fs73c3lu80  # backend
render deploys create srv-d7p2l8vavr4c73d1gnvg  # frontend
```

**Permanent fix needed:** Reconnect repo in Render dashboard → Settings → Build & Deploy for both services.

---
