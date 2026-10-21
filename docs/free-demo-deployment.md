# Resettable free demo

The existing frontend stays on Vercel Hobby. The selected backend host is
FastAPI Cloud Hobby ($0/month, explicitly no credit card required).
Render was rejected by the owner, and Northflank was rejected because it
requires a card. Neither `render.yaml` nor `render.demo.yaml` is part of the
selected deployment.

The demo uses a new service name so it does not replace an existing backend or
its disk. Keep the team on **Hobby**. Do not upgrade
the team or add paid resources.

## FastAPI Cloud

- Sign in to the free Hobby account. Do not enter a payment method or
  upgrade to Pro. If deployment asks for a card, stop and report the conflict
  with the published no-card offering.
- Deploy the Python project with `fastapi deploy` from the repository root.
  `pyproject.toml` declares `marvin_ui.server:app`; `.python-version` selects
  Python 3.11. `.fastapicloudignore` excludes frontend and local files.
- Use service name `marvin-demo-api`. Set the maximum replicas to **1**:
  each SQLite instance has its own local state and cannot serve a shared mission.
- Leave the database paths unset to use the default writable home directory,
  or configure both paths within a writable temporary directory. Do not use
  Docker's `/data` path, which is not created by this deployment method.
- Set `CORS_ORIGINS=https://marvin-zeta.vercel.app` and
  `ALLOW_LOCALHOST_ANY_PORT=0`.
- Supply `OPENROUTER_API_KEY` through FastAPI Cloud's secret environment settings.
- Set `OPENROUTER_BASE_URL=https://openrouter.ai/api/v1`.
- Add `TAVILY_API_KEY` there if live web research is needed.
- `/health` should return 200.
- Copy the actual public API URL after creation; do not assume a hostname.

## Vercel project `marvin`

Set these production environment variables, then rebuild:

```text
NEXT_PUBLIC_API_BASE_URL=<actual FastAPI Cloud API URL>/api/v1
NEXT_PUBLIC_DEMO_MODE=1
```

The browser connects directly to the API, including SSE. Configure CORS for
`https://marvin-zeta.vercel.app`; add any other intended frontend origins
explicitly to `CORS_ORIGINS`.

## Limitations

All seven LLM roles use `minimax/minimax-m3.1-flash:free`, verified in the
OpenRouter catalogue on 2026-10-20. The request also caps prompt, completion
and per-request provider pricing at zero. There is no paid fallback. Free
capacity and daily request quotas can interrupt a multi-agent mission.

Hobby apps scale to zero when idle. Mission rows, graph checkpoints, uploads
and generated reports use local storage and must be treated as ephemeral:
they can disappear when instances stop or are replaced. This loss is accepted for this
demo; it is not a durable deployment. Download reports you need to retain.

The hosting free tier does not include OpenRouter or Tavily usage. Existing
API access behavior is unchanged: do not place confidential data in this
public demo. Do not set a backend API key without also configuring a client
authentication path; the existing frontend does not send `X-API-Key`.

## Verification

Check `/health`, the mission list, the demo notice, creation of a clearly named
test mission, and SSE progress. Live AI verification requires explicit use of
the configured provider credentials. Inspect the final service plan and URL.

When provider keys exist only on the deployed demo, run the same runtime smoke
without copying them locally:

```bash
MARVIN_SMOKE_BASE_URL=https://marvin-demo-api.fastapicloud.dev MARVIN_SMOKE_DURATION=120 make smoke
```

This mode is restricted to that exact resettable demo. It creates a uniquely
named smoke mission, checks that `hi` returns an onboarding reply without
starting agents or creating a brief, then checks up to 120 seconds of a
substantive brief (25 seconds by default without the duration override) for SSE progress and errors. It does not verify an entire
research mission. Without this variable, the smoke still uses a local server
and temporary databases; the full local run requires a configured provider key.
