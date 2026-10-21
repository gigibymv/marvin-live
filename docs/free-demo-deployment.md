# Resettable free demo

The existing frontend stays on Vercel Hobby. Create only the API on Render
Free, using `render.demo.yaml` as the Blueprint Path. The default `render.yaml`
retains the original paid configuration and must not be used for this demo.

The demo uses a new service name so it does not replace an existing backend or
its disk. Check the displayed instance type is **Free** before deployment.

## Render

- Supply `OPENROUTER_API_KEY` through Render's secret environment settings.
- Add `TAVILY_API_KEY` there if live web research is needed.
- The API listens on Render's injected `PORT`; `/health` should return 200.
- Copy the actual public API URL after creation; do not assume a hostname.

## Vercel project `marvin`

Set these production environment variables, then rebuild:

```text
NEXT_PUBLIC_API_BASE_URL=<actual Render API URL>/api/v1
NEXT_PUBLIC_DEMO_MODE=1
```

The browser connects directly to the API, including SSE. Render CORS permits
`https://marvin-zeta.vercel.app`; add any other intended frontend origins
explicitly to `CORS_ORIGINS`.

## Limitations

Render Free sleeps after 15 minutes without incoming traffic. Its filesystem
is ephemeral: mission rows, graph checkpoints, uploads and generated reports
can disappear on sleep, restart or redeploy. This loss is accepted for this
demo; it is not a durable deployment. Download reports you need to retain.

The hosting free tier does not include OpenRouter or Tavily usage. Existing
API access behavior is unchanged: do not place confidential data in this
public demo. Do not set a backend API key without also configuring a client
authentication path; the existing frontend does not send `X-API-Key`.

## Verification

Check `/health`, the mission list, the demo notice, creation of a clearly named
test mission, and SSE progress. Live AI verification requires explicit use of
the configured provider credentials. Inspect the final service plan and URL.
