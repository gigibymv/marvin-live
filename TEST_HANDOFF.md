# MARVIN — End-to-End Live Test Handoff

For an independent coding agent running a full mission test against this commit.

---

## 1. Readiness verdict

**Ready** with one noted caveat (see §8). All readiness checks pass at the handoff commit.

---

## 2. Exact commit and branch

- **Branch**: `main`
- **Commit**: `0fdaf5e0ddb7141b674df032fa2ed815256ac1d4` (`main` HEAD at handoff). Note: the immediately prior commit `95b2d3a` is the source-snapshot commit; this commit only updates `TEST_HANDOFF.md` to pin the SHA. Either is a valid checkout for testing — they are product-identical.
- **Repo root** (on the original machine): `/Users/mv/Desktop/AI/PROJECTS/marvin`

If working from a fresh clone elsewhere, `git checkout 0fdaf5e`.

---

## 3. Environment requirements

- Python 3.11+ with venv
- Node.js 18+ with npm
- Network access to `openrouter.ai` (and `tavily.com` if `TAVILY_API_KEY` is set)
- macOS or Linux (only one shell-quirk noted in §8)

### `.env` at repo root (REQUIRED)

```bash
OPENROUTER_API_KEY=sk-or-v1-...                    # REQUIRED
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1   # REQUIRED
OPENROUTER_APP_NAME=MARVIN                         # optional
TAVILY_API_KEY=                                    # optional; tools tolerate empty
MARVIN_HOST=127.0.0.1                              # optional, default 127.0.0.1
MARVIN_PORT=8095                                   # optional, default 8095
CORS_ORIGINS=http://localhost:3000                 # optional
```

**Do NOT set `MARVIN_DB_PATH`** for this test (see §8).

### `.env.local` at repo root (REQUIRED for the frontend dev server)

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8095/api/v1
```

Both `.env.example` and `.env.local.example` are committed; copy them to `.env` and `.env.local` respectively.

---

## 4. Backend startup commands

From the repo root:

```bash
# 1. Create venv and install deps
python3.11 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"

# 2. Load env into current shell (must be `set -a; source; set +a`,
#    NOT --env-file; uvicorn/dotenv interplay with this stack is brittle)
set -a; source .env; set +a

# 3. Start backend
PYTHONPATH=$PWD .venv/bin/python -m uvicorn marvin_ui.server:app --port 8095
```

Verify:
```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8095/health   # expect 200
curl -s http://127.0.0.1:8095/api/v1/missions                            # expect {"missions":[]}
```

---

## 5. Frontend startup commands

From the repo root, in a separate shell:

```bash
npm install
npm run dev      # http://localhost:3000
```

Optional smoke checks:
```bash
npm run typecheck   # tsc clean
npm test            # vitest, 21 tests pass
npm run build       # production build
```

---

## 6. DB / migration / init commands

There are no separate migration commands. SQLite at `~/.marvin/marvin.db` is created on first `MissionStore()` call by `marvin/mission/store.py::_initialize_schema` from `marvin/mission/001_init.sql` plus `_apply_additive_migrations` (idempotent).

To start from a clean DB:
```bash
rm -f ~/.marvin/marvin.db
# then start backend; schema is recreated on first request
```

---

## 7. Smoke validation performed at this commit

Performed against `0fdaf5e`:

| Check | Result |
|---|---|
| `pytest tests/` | 154 passed, 3 skipped, 0 failed |
| `npm run typecheck` | clean |
| `npm test` (vitest) | 21 passed |
| Clean-DB backend boot | `/health` → 200; `GET /api/v1/missions` → `{"missions":[]}`; DB file created at `~/.marvin/marvin.db` |
| Mission creation | `POST /api/v1/missions` → 200 with `mission_id` |
| First SSE checkpoint | `POST /api/v1/missions/{id}/chat` produces `run_start` + `deliverable_ready` + `gate_pending` (hyp_confirm) within ~25 s |
| Prior full-run evidence (different mission, same commit's tools) | `run_start → hyp_confirm → G1 → G3 → run_end`, 6 deliverables, 4 milestones delivered, 27 findings persisted with valid `hypothesis_id`, no `KeyError: 'merlin'` |

---

## 8. Known caveats that do not block testing

1. **`MARVIN_DB_PATH` partial honoring.** The FastAPI server's `_get_store()` reads `MARVIN_DB_PATH`, but the deterministic graph code in `marvin/graph/runner.py` and `marvin/graph/gates.py` calls `MissionStore()` directly with no args, which always uses `~/.marvin/marvin.db`. With the env var unset (default), both paths agree. **Leave `MARVIN_DB_PATH` unset for this test.**
2. **rtk-wrapped `curl` buffering.** On the original developer machine, `curl` is wrapped by `rtk` and buffers SSE streams. Use `/usr/bin/curl -s -N` for SSE. Generic Linux machines should have no such wrapper.
3. **Existing `HANDOFF.md` and `RUNBOOK.md`** are partially stale — they predate several recent fixes (gate_entry node, merlin retry phase, persistence-chokepoint events, hypothesis_id normalization). Treat **this file** and `CLAUDE.md` as authoritative; consult the others only for additional context.
4. **Adversus may produce one tool-validation error per mission** as a graceful surfaced rejection of malformed `hypothesis_id`. The run continues; this is expected behavior, not a regression.

---

## 9. Known blockers, if any

**None.** The smoke run reproduces a clean live path from clean DB through the first interrupt.

---

## 10. Exact instructions for the second agent

```bash
# 0. Fresh shell
cd <repo-root>
git checkout 0fdaf5e

# 1. Backend
python3.11 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"
cp .env.example .env
# edit .env: set OPENROUTER_API_KEY=sk-or-v1-...  (TAVILY_API_KEY optional)

set -a; source .env; set +a
rm -f ~/.marvin/marvin.db   # ensure clean DB
PYTHONPATH=$PWD .venv/bin/python -m uvicorn marvin_ui.server:app --port 8095 &
sleep 5
curl -s http://127.0.0.1:8095/health   # expect {"status":"ok"} or 200

# 2. Frontend (separate shell)
cd <repo-root>
npm install
cp .env.local.example .env.local
npm run dev    # http://localhost:3000

# 3. Run a mission via UI
#    - open http://localhost:3000
#    - create mission (any client/target)
#    - send chat: "Analyze <Target> Corp."
#    - approve hypothesis_confirmation gate when modal appears
#    - approve G1 (manager_review) gate
#    - approve G3 (final_review) gate
#    - confirm run reaches run_end and shows 6 deliverables

# 4. Or via API only:
MID=$(curl -s -X POST http://127.0.0.1:8095/api/v1/missions \
  -H "Content-Type: application/json" \
  -d '{"client":"Acme","target":"Acme","ic_question":"Is Acme attractive?"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['mission_id'])")
echo "$MID"

curl -s -N -X POST "http://127.0.0.1:8095/api/v1/missions/$MID/chat" \
  -H "Content-Type: application/json" \
  -d '{"text":"Analyze Acme Corp."}'   # streams SSE; ^C after gate_pending

# Approve a gate (for each of: gate-$MID-hyp-confirm, gate-$MID-G1, gate-$MID-G3):
curl -s -X POST "http://127.0.0.1:8095/api/v1/missions/$MID/gates/<gate-id>/validate" \
  -H "Content-Type: application/json" \
  -d '{"verdict":"APPROVED","notes":"ok"}'
# then re-attach to chat to continue receiving SSE for that mission
```

### Expected pass criteria for the live test

- All three gates (`hyp-confirm`, `G1`, `G3`) reachable and approvable
- SSE event types observed across the run (cumulative): `run_start`, `agent_active`, `agent_done`, `text`, `tool_result`, `finding_added` (≥10), `milestone_done` (≥4), `deliverable_ready` (≥6), `gate_pending` (3), `run_end`
- No `KeyError`, no Python tracebacks in server log
- DB end state for that mission: ≥3 hypotheses, ≥10 findings (most with `hypothesis_id` set), 4 delivered milestones, 6 deliverables

---

## 11. Files changed at this commit and why

Modified (this session, on top of prior session's H2 + slice work):

- `pyproject.toml` — declare langgraph/langchain-core/langchain-openai/python-dotenv as actual deps so `pip install -e .[dev]` produces a working install.
- `.env.local.example` — `NEXT_PUBLIC_API_BASE_URL` port 8091 → 8095 to match backend default.
- `.gitignore` — ignore `.claude/`; whitelist `.env.local.example`.
- `UI Marvin/MissionControl.jsx` — `Feed` component referenced `props.findings` without destructuring `props`; passed `findings` from parent. Without this, the live UI raises `ReferenceError` once findings start populating.

Newly tracked (previously untracked, not a code change but a packaging fix):

- All frontend (`app/`, `components/`, `lib/`, `UI Marvin/`)
- All schemas/store (`marvin/mission/`)
- All subgraphs and prompts (`marvin/graph/subgraphs/`, `marvin/subagents/prompts/`)
- `marvin/llm_factory.py`, `marvin/events.py`, `marvin/graph/state.py`, `marvin/graph/gates.py`
- `marvin/tools/common.py`, `marvin/tools/arbiter_tools.py`, `marvin/tools/merlin_tools.py`
- `marvin_ui/__init__.py`
- `pyproject.toml`, `package.json`, `package-lock.json`, `tsconfig.json`, `vitest.config.ts`, `next.config.ts`
- All tests (`tests/test_*.py`, `tests/*.test.ts`, `tests/setup.ts`)
- `CLAUDE.md`, `HANDOFF.md`, `RUNBOOK.md`, `.env.example`, `.env.local.example`, `.gitignore`

---

## 12. Why the product is now fresh and reproducible

- **One fixed commit holds everything required to run.** Before this commit only 13 files were tracked; a fresh clone could not have run. Now `git clone` + `git checkout 0fdaf5e` + the §10 commands give a working system.
- **No build artifacts in the tree.** `.next/`, `__pycache__/`, `output/`, `*.db`, `node_modules/`, `.venv/`, `.claude/` are all in `.gitignore` and not committed. The handoff state is independent of any prior local build.
- **Dependencies are declarative.** `pyproject.toml` and `package-lock.json` pin/declare every runtime dependency; `pip install -e ".[dev]"` and `npm install` are sufficient.
- **DB is reproducible from schema.** No DB file is committed; first `MissionStore()` call rebuilds the schema from `marvin/mission/001_init.sql` plus idempotent additive migrations. Deleting `~/.marvin/marvin.db` before running guarantees a clean test bed.
- **Env contract is documented and enforced.** `.env.example` and `.env.local.example` cover every variable the code reads. Frontend now points to the same port the backend defaults to.
- **No reliance on session shell state.** All commands above are explicit; no aliases, no hidden `PATH` quirks. The only shell-specific note is `set -a; source .env; set +a` for env loading, which is in §4.
- **Tests are green at this commit** (pytest 154, vitest 21, typecheck clean) and one clean-DB smoke run reproduces the first runtime checkpoint.

---

## 13. Runbook — reproducing late-phase backend crashes (e.g. `Exit 137`)

`Exit 137` (SIGKILL) was reported once during Adversus by an independent tester. It did **not** reproduce locally on macOS / Python 3.14 after fixing an upstream calculus null-input crash. The instrumentation below is left in tree (gated, off by default) so any future repro attempt produces the curves needed to rank the cause.

**Enable instrumentation and start the backend:**

```bash
set -a; source .env; set +a
MARVIN_DEBUG_RUNTIME=1 PYTHONPATH=$PWD nohup .venv/bin/python -m uvicorn marvin_ui.server:app --host 127.0.0.1 --port 8095 > /tmp/marvin.stderr 2>&1 &
echo $! > /tmp/marvin.pid
```

`MARVIN_DEBUG_RUNTIME=1` activates `marvin.runtime_debug`, which logs `node_entry` and `agent_io` lines for `research_join`, `adversus`, and `merlin` (message count, content bytes, accumulated tool_calls, RSS, monotonic time). With the env var unset there is zero behavior change and zero log output.

**Start the RSS / VSZ sampler against the backend PID:**

```bash
nohup tools/devops/mem_sampler.sh $(cat /tmp/marvin.pid) /tmp/marvin.rss.csv > /tmp/marvin.sampler.log 2>&1 &
```

**On crash, capture:**

- backend exit code: `wait $(cat /tmp/marvin.pid); echo $?` — `137` = SIGKILL
- `tail -200 /tmp/marvin.stderr` — Python tracebacks and runtime_debug timeline
- `/tmp/marvin.rss.csv` — full memory curve at 1 Hz
- macOS jetsam evidence: `log show --last 30m --predicate 'eventMessage CONTAINS[c] "memorystatus" OR eventMessage CONTAINS[c] "jetsam"'`
- Linux OOM evidence (when applicable): `dmesg | tail -200`, `journalctl -k --since "30 min ago"`
- ancestry: `ps -o pid,ppid,pgid,command -p <pid>` — confirm no `--reload`, IDE, or supervisor parent

**Files (all gated / removable in one commit):**

- `marvin/runtime_debug.py` — gated logger
- `tools/devops/mem_sampler.sh` — RSS/VSZ sampler
- single-line `log_node_entry` / `log_agent_io` calls in `marvin/graph/runner.py`, `marvin/graph/subgraphs/adversus.py`, `marvin/graph/subgraphs/merlin.py`
