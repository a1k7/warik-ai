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


