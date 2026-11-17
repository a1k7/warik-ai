# Implementation decisions

- Work is isolated on `feat/instinct-clone`; the existing `main` branch is not modified.
- Preserve Warik's existing React/Vite frontend, FastAPI API layer, SQLAlchemy database, and JWT authentication.
- Add separate browser-agent task, step, and approval tables rather than changing the existing task model or chat workflow.
- Keep the existing home workspace and add `/agent`, `/dashboard`, and `/tasks/:id` routes.
- The demo skill is a local flight-search catalogue. It does not contact airlines, reservation sites, payment providers, or marketplaces.
- Use local Playwright Chromium by default. Connect to `AGENT_BROWSER_CDP_URL` only when a trusted CDP endpoint is explicitly configured.
- Restrict initial browser navigation to `AGENT_ALLOWED_DOMAINS`; the default allowlist contains localhost only.
- `AGENT_DEMO_MODE=true` uses a deterministic planner so a missing LLM does not block the demo. Setting it to false tries the existing configured Ollama/Groq provider.
- Require an explicit approval before the mock hold action. Approval expires after 600 seconds and defaults to DENY.
- Persist summaries, status, and screenshot filenames in SQLite. Screenshots live under `backend/data/browser-agent/shots`.
- Search up to three markdown memory files under `backend/memory` by keyword overlap and display their names on the task record.
- The Scheduler, external booking integrations, and general-purpose arbitrary-site browsing remain out of scope.
- Verification limitation: edits are committed through the GitHub API; no local clone or runnable app environment is exposed in this session. Run the documented install, build, and acceptance smoke test on the Mac before presenting.
