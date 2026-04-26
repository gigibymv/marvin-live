# Marvin Runtime Validation Runbook

Quick reference for booting and validating Marvin on a clean Linux/VPS environment.

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- pnpm or npm
- OpenRouter API key (for LLM calls)

---

## Environment Variables

### Backend (`.env` in project root)

```bash
# Required for LLM calls
OPENROUTER_API_KEY=sk-or-v1-xxxxx
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# Optional attribution headers
OPENROUTER_HTTP_REFERER=
OPENROUTER_APP_NAME=MARVIN

# Optional web search
TAVILY_API_KEY=tvly-dev-xxxxx

# Backend server config (optional)
MARVIN_HOST=127.0.0.1      # default: 127.0.0.1
MARVIN_PORT=8091           # default: 8091
CORS_ORIGINS=http://localhost:3000  # comma-separated

# Optional API key for non-local requests
MARVIN_API_KEY=            # if set, required for non-localhost requests
```

### Frontend (`.env.local` in project root)

```bash
# Backend API base URL (for direct backend access)
NEXT_PUBLIC_API_BASE_URL=http://localhost:8095/api/v1
```

---

## Quick Start

### 1. Install Dependencies

```bash
# Python dependencies
pip install fastapi uvicorn starlette
# or with uv:
uv pip install fastapi uvicorn starlette

# Node dependencies
npm install
```

### 2. Start Backend

```bash
# From project root
uvicorn marvin_ui.server:app --host 127.0.0.1 --port 8095

# Or using the module
python -m marvin_ui.server

# Or with custom port/host
MARVIN_HOST=0.0.0.0 MARVIN_PORT=8091 uvicorn marvin_ui.server:app
```

### 3. Start Frontend

```bash
# From project root
npm run dev

# Or with custom port
PORT=3001 npm run dev
```

### 4. Health Check

```bash
# Backend health
curl http://localhost:8095/health
# Expected: {"status": "ok"}

# Frontend
curl http://localhost:3000
# Expected: HTML page
```

---

## Validation Checklist

### Phase 1: Backend API

```bash
# 1. Create mission
curl -X POST http://localhost:8095/api/v1/missions \
  -H "Content-Type: application/json" \
  -d '{"client":"Test Capital","target":"Acme Corp","ic_question":"Is this good?","mission_type":"cdd"}'
# Expected: {"mission_id":"m-acme-corp-YYYYMMDD","status":"active",...}

# 2. List missions
curl http://localhost:8095/api/v1/missions
# Expected: {"missions":[{"id":"m-acme-corp-...",...}]}

# 3. Get mission
curl http://localhost:8095/api/v1/missions/m-acme-corp-YYYYMMDD
# Expected: Full mission object

# 4. Get progress
curl http://localhost:8095/api/v1/missions/m-acme-corp-YYYYMMDD/progress
# Expected: {"mission":{...},"gates":[...],"milestones":[...],"findings":[]}
```

### Phase 2: SSE Chat Streaming

```bash
# Test SSE endpoint (requires mission_id from step 1)
curl -N -X POST http://localhost:8095/api/v1/missions/MISSION_ID/chat \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello"}'
# Expected: SSE events (run_start, text, tool_call, etc.)
```

### Phase 3: Gate Validation

```bash
# Get a gate ID from progress endpoint
GATE_ID="gate-mission-id-hyp-confirm"

# Validate gate
curl -X POST http://localhost:8095/api/v1/missions/MISSION_ID/gates/$GATE_ID/validate \
  -H "Content-Type: application/json" \
  -d '{"verdict":"APPROVED","notes":"Test approval"}'
# Expected: {"status":"resumed","mission_id":"...","gate_id":"...","resume_id":"..."}
```

### Phase 4: Full E2E via UI

1. Open http://localhost:3000 in browser
2. Click "New Mission"
3. Enter client/target and create mission
4. Open the mission
5. Send a chat message
6. Verify SSE events appear in chat panel
7. When gate_pending appears, click Approve/Reject
8. Verify graph resumes

---

## Production Deployment

### Backend

```bash
# Use gunicorn with uvicorn workers
gunicorn marvin_ui.server:app -w 4 -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8095

# Or uvicorn directly
uvicorn marvin_ui.server:app --host 0.0.0.0 --port 8095 \
  --workers 4 --proxy-headers
```

### Frontend

```bash
# Build for production
npm run build

# Start production server
npm run start

# Or with custom port
PORT=3001 npm run start
```

### Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location /api/ {
        proxy_pass http://127.0.0.1:8095/api/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        
        # SSE support
        proxy_buffering off;
        proxy_read_timeout 86400;
    }

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
    }
}
```

---

## Troubleshooting

### Backend won't start

```bash
# Check port availability
lsof -i :8095

# Check Python path
python -c "from marvin_ui.server import app; print('OK')"

# Check dependencies
pip install fastapi uvicorn starlette langgraph langchain-core langchain-openai
```

### Frontend can't reach backend

```bash
# Check CORS settings
# In backend .env:
CORS_ORIGINS=http://localhost:3000,http://localhost:3001

# Check API base URL
# In frontend .env.local:
NEXT_PUBLIC_API_BASE_URL=http://localhost:8095/api/v1
```

### SSE stream hangs

```bash
# Ensure nginx buffering is off
proxy_buffering off;

# Check LLM connectivity
curl https://openrouter.ai/api/v1/models \
  -H "Authorization: Bearer $OPENROUTER_API_KEY"
```

### Database errors

```bash
# Reset mission database
rm ~/.marvin/marvin.db

# Reset checkpoints
rm ~/.marvin/checkpoints.db
```

---

## File Structure

```
marvin/
├── marvin/
│   ├── graph/           # LangGraph orchestration
│   ├── mission/         # Mission schema/store
│   ├── tools/           # Agent tools
│   └── llm_factory.py   # LLM configuration
├── marvin_ui/
│   └── server.py        # FastAPI backend
├── lib/missions/        # Frontend mission logic
│   ├── api.ts           # API client
│   ├── repository.ts    # Repository seam
│   └── events.ts        # SSE event handling
├── components/marvin/   # Frontend components
├── app/                 # Next.js app router
├── .env                 # Backend secrets
├── .env.local          # Frontend config (create if needed)
└── RUNBOOK.md          # This file
```

---

## Known Limitations

1. **Memory-based checkpointer**: By default, uses `MemorySaver`. For persistence across restarts, configure SQLite checkpointer.

2. **No authentication**: Local trust by default. For production, set `MARVIN_API_KEY` and implement proper auth.

3. **Single-threaded gates**: Gate interrupts block until validated. Use the validate endpoint to resume.

4. **No real tool implementations**: Some tools (e.g., `search_sec_filings`) are stubs. Implement as needed.
