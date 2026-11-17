# Warik AI

**Your AI companion for everyday life.**
Built by Warik Labs.

Voice-first personal AI companion. India-first, local-first, privacy-conscious.

> **Status:** Phase 4 — Gnani Prisma STT integration.
> Gnani TTS, tasks/expenses REST CRUD, travel/food UI and the React frontend arrive in later phases.

---

## Tech stack

- **Frontend:** React, TypeScript, Vite, Tailwind CSS (Phase 8)
- **Backend:** Python, FastAPI, Pydantic, SQLAlchemy
- **Database:** SQLite locally; PostgreSQL-ready via `DATABASE_URL`
- **Reasoning:** Ollama (free local model), replaceable provider layer
- **Voice:** Gnani Prisma STT (Phase 4), Gnani Timbre TTS (Phase 5) — backend-only keys
- **Auth:** bcrypt password hashing + JWT bearer tokens

---

## Backend setup


cd warik-ai/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env
uvicorn app.main:app --reload --reload-dir app

Open http://127.0.0.1:8000/docs.

Voice — Gnani Prisma STT

Voice is off by default so you never spend a Gnani credit accidentally.

To enable it:

Edit backend/.env:

dotenv
VOICE_ENABLED=true
GNANI_API_KEY=your_real_key_here
# Optional — only if your Gnani account requires them:
# GNANI_ORG_ID=...
# GNANI_USER_ID=...
Restart uvicorn.
If either flag is missing, the endpoint returns 503 without making a network call — no credit is spent.


# Credit protection

# Guard	Value
Daily per-user cap	VOICE_USAGE_LIMIT_SECONDS (default 300 s)
Max upload	VOICE_MAX_UPLOAD_BYTES (default 5 MB)
Max duration	VOICE_MAX_DURATION_SECONDS (default 30 s)
Usage ledger	voice_usage table — one row per user per day
Pre-check runs before Gnani is contacted. Post-success increments the counter. Inspect your spend:


sqlite3 backend/warik.db "SELECT usage_date, seconds_used, requests_count FROM voice_usage;"
Endpoints

Route	Purpose
POST /api/voice/transcribe	audio → {"transcript": "..."}
POST /api/voice/message	audio → transcript → agent → reply (no TTS)
Accepted audio: audio/wav, audio/mpeg, audio/flac, audio/ogg, audio/mp4, audio/x-m4a, application/octet-stream.

Supported languages: bn-IN, en-IN, gu-IN, hi-IN, kn-IN, ml-IN, mr-IN, pa-IN, ta-IN, te-IN.

# Try it (once enabled)

bash
TOKEN="paste_access_token_here"

curl -X POST http://127.0.0.1:8000/api/voice/message \
  -H "Authorization: Bearer $TOKEN" \
  -F "audio=@/path/to/clip.wav;type=audio/wav" \
  -F "language_code=en-IN" \
  -F "duration_seconds=4"
Response:

json
{
  "transcript": "remind me to study at 7 pm",
  "reply": "Reminder set: study — 31 Oct 2026, 19:00.",
  "tool_calls": [{"tool_name": "create_reminder", "success": true, ...}],
  "needs_confirmation": false
}
The agent

The agent pipeline (Phase 3) is unchanged:

Deterministic parser → 2. Ollama (if configured) → 3. tool validation → 4. confirmation card if required → 5. execution → 6. audit log.
12 tools: create_task, list_tasks, complete_task, create_reminder, list_reminders, add_expense (confirm), list_expenses, calculate_expense_summary, create_travel_plan (confirm), save_memory, retrieve_memory, delete_memory (confirm).

# Tests


cd warik-ai/backend
source .venv/bin/activate
pytest -q
The voice tests use httpx.MockTransport — no real Gnani key is required, no credit is spent.

# Security notes

.env is Git-ignored. Keys never leave the backend.
JWTs signed with JWT_SECRET; change it before any demo.
Confirmation tokens bound to user_id, 10-minute expiry.
Every tool call audited in action_logs; every voice call audited in voice_usage.
Per-user isolation enforced by get_current_user and per-tool ownership checks.
Phases

Phase	Scope	Status
1	Architecture, project structure, backend foundation	✅
2	Database models, schemas, auth	✅
3	Agent, tool registry, deterministic parser, Ollama provider	✅
4	Gnani STT + voice usage ledger	✅
5	Gnani TTS	next
6	Tasks / expenses / reminders REST CRUD	
7	Travel, food, memory	
8	React frontend	
9	Integration, testing, bug fixes	
10	Local deployment and documentation	




---

## Browser Agent demo (Instinct-style vertical slice)

This feature branch adds an authenticated browser-operating assistant at `/agent`. It launches real local Chromium against a controlled flight-search website, streams action summaries and screenshots, and pauses for human approval before a mock flight-hold action.

### Run locally

Backend (Terminal 1):

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
if [ ! -f .env ]; then cp ../.env.example .env; fi
# Preserve an existing .env. Keep AGENT_DEMO_MODE=true and localhost-only AGENT_ALLOWED_DOMAINS.
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend (Terminal 2):

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`, create an account through the existing Warik login screen, then open `/agent`. Run the prefilled task or enter another route in the same `from X to Y` format. Watch browser steps and snapshots stream in. Choose **Approve action** or **Deny** at the approval card. Task history is at `/dashboard`; open a record to inspect its replay timeline and memory files at `/tasks/{id}`.

### What the demo does

- Playwright launches Chromium locally, or connects to `AGENT_BROWSER_CDP_URL` when configured.
- The browser visits the local `/api/browser-agent/demo-site`, fills the search form, reads three sample options, and picks the lowest sample fare.
- Task, step, approval, and outcome state is persisted in the existing SQLite/SQLAlchemy database.
- Server-sent events stream task updates, action summaries, and screenshot references to the frontend.
- Screenshots are stored under `backend/data/browser-agent/shots` and served only to the authenticated task owner.
- Up to three keyword-matched markdown memory files are selected from `backend/memory` and shown on the task record.
- Approval is checked against task ownership. A pending approval expires after 10 minutes and defaults to DENY.

### Demo boundary

Flight names, fares, and holds are fictional local fixtures. No airline, marketplace, reservation service, or payment provider is contacted. A completed hold is a local UI confirmation, not a reservation. Initial navigation is restricted to the localhost allowlist. This is a vertical-slice demo, not a production general-purpose browser agent.

Set `AGENT_DEMO_MODE=false` to try the configured Warik Ollama/Groq planner. Without a reachable provider, keep `AGENT_DEMO_MODE=true`; the deterministic planner still operates the browser using the same task and approval ledger. Configure `AGENT_BROWSER_CDP_URL` only for a trusted CDP endpoint.

The Scheduler and proactive triggers remain future work.
