# Resettable free demo

The existing frontend stays on Vercel Hobby. The selected backend host is
Northflank Developer Sandbox. Render was rejected by the owner; neither
`render.yaml` nor `render.demo.yaml` is part of the selected deployment.

The demo uses a new service name so it does not replace an existing backend or
its disk. Keep the team on **Developer Sandbox / Free Team**. Do not upgrade
the team or add paid resources.

## Northflank

- Northflank requires card verification even for Developer Sandbox. The
  service form states the Sandbox is not charged. The owner must enter the
  card directly; do not collect or store payment details in this repository.
- Build `gigibymv/marvin-live`, branch `main`, using `/Dockerfile` and context `/`.
- Use service name `marvin-demo-api`, one instance, and the free compute option.
- Expose HTTP port `8095`; set `MARVIN_PORT=8095` and `MARVIN_HOST=0.0.0.0`.
- Set `MARVIN_DB_PATH=/data/marvin.db` and
  `MARVIN_CHECKPOINT_DB=/data/checkpoints.db` on ephemeral storage.
- Set `CORS_ORIGINS=https://marvin-zeta.vercel.app` and
  `ALLOW_LOCALHOST_ANY_PORT=0`.
- Supply `OPENROUTER_API_KEY` through Northflank's secret environment settings.
- Set `OPENROUTER_BASE_URL=https://openrouter.ai/api/v1`.
- Add `TAVILY_API_KEY` there if live web research is needed.
- `/health` should return 200.
- Copy the actual public API URL after creation; do not assume a hostname.

## Vercel project `marvin`

Set these production environment variables, then rebuild:

```text
NEXT_PUBLIC_API_BASE_URL=<actual Northflank API URL>/api/v1
NEXT_PUBLIC_DEMO_MODE=1
```

The browser connects directly to the API, including SSE. Configure CORS for
`https://marvin-zeta.vercel.app`; add any other intended frontend origins
explicitly to `CORS_ORIGINS`.

## Limitations

Northflank advertises always-on Sandbox services. Without an attached
persistent volume, mission rows, graph checkpoints, uploads and generated
reports remain ephemeral and can disappear on restart or redeploy. This loss is accepted for this
demo; it is not a durable deployment. Download reports you need to retain.

The hosting free tier does not include OpenRouter or Tavily usage. Existing
API access behavior is unchanged: do not place confidential data in this
public demo. Do not set a backend API key without also configuring a client
authentication path; the existing frontend does not send `X-API-Key`.

## Verification

Check `/health`, the mission list, the demo notice, creation of a clearly named
test mission, and SSE progress. Live AI verification requires explicit use of
the configured provider credentials. Inspect the final service plan and URL.
