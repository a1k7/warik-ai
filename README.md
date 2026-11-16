# Warik AI

**An India-first personal action assistant.**

Warik helps people move everyday work forward: speak or type a request, use supported tools, keep important context, and track follow-through until the user records an outcome.

The product thesis is simple: a useful assistant should not only answer; it should help a person remember what is pending, take permitted steps, and avoid silently dropping commitments.

> **Project status: early alpha.** The current codebase includes a React application, FastAPI backend, tool-driven conversations, an Action Ledger, personal memory, and a multilingual voice capture path. Provider credentials and external integrations are required for some capabilities. This is not yet a general-purpose autonomous desktop agent.

## Product

### What is implemented

- **Conversational assistant:** chat-based requests routed through an orchestrator, tool registry, and structured workflows.
- **Action Ledger:** capture commitments with a title, context, counterparty, due date, and status (open, in progress, waiting, blocked, completed). Marking a commitment complete requires a user-entered verification note.
- **Approval checkpoints:** supported consequential tool actions can ask the user for explicit confirmation; tool activity is recorded in action logs.
- **Personal memory:** users can save, edit, and delete context that may be relevant in later conversations.
- **Everyday organisation:** tasks, reminders, expense records and summaries.
- **Travel and food discovery:** itinerary planning and map-listed restaurant candidates. Availability, live prices, menu data, and dietary suitability must not be assumed unless a provider explicitly verifies them.
- **Documents:** upload supported documents and ask questions about their contents.
- **India-first voice capture:** browser recording, ten speech-language choices, a transcript review/edit step, and an explicit send step. Voice is disabled by default and requires a configured speech provider.

### What is not implemented yet

Warik is inspired by the action-oriented assistant category, but it does **not** yet provide:

- WhatsApp or iMessage control, a dedicated phone number, or an always-on messaging channel.
- A dedicated cloud desktop or reliable general-purpose browser/phone control.
- Autonomous UPI, banking, bill payment, or credential/OTP handling.
- Automatic merchant refund retrieval, complaint filing, or guaranteed resolution.
- A guarantee that third-party inventory, prices, restaurant menus, or delivery slots are current.

These are roadmap candidates, not capabilities to claim in a demo or investor application.

## Technology

- Frontend: React, TypeScript, Vite, Tailwind CSS
- Backend: Python, FastAPI, Pydantic, SQLAlchemy
- Local database: SQLite; configure PostgreSQL through the database URL for a hosted deployment
- LLM provider layer: local Ollama or configured hosted provider
- Speech-to-text: configured Groq or Gnani provider
- Authentication: JWT bearer tokens and password hashing

## Local development

### Backend

From the repository root:

    cd backend
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    cp ../.env.example .env
    uvicorn app.main:app --reload

The API documentation is available at http://127.0.0.1:8000/docs.

### Frontend

In a second terminal:

    cd frontend
    npm ci
    printf 'VITE_API_BASE_URL=http://127.0.0.1:8000/api\n' > .env.local
    npm run dev

Open the Vite URL printed by the development server.

## Voice configuration

Voice capture is off by default. To enable it, edit backend/.env:

    VOICE_ENABLED=true
    GROQ_API_KEY=your_server_side_key

You can use a configured Gnani key instead. Keep provider keys on the backend; never put them in a VITE_ variable or commit them.

The current voice UI supports Bengali, English (India), Gujarati, Hindi, Kannada, Malayalam, Marathi, Punjabi, Tamil, and Telugu. Recordings are capped in the UI at 28 seconds; the API also enforces upload-size and duration limits. The transcript is editable and is not sent to the assistant until the user chooses to use it and then submits the chat message.

## Tests and build

Backend:

    cd backend
    pytest -q

Frontend:

    cd frontend
    npm ci
    npm run build

The speech tests should use mocked providers. Do not use a real provider key in automated tests.

## Security and release checklist

Before any external pilot:

1. Set a unique, high-entropy JWT secret and use HTTPS.
2. Use PostgreSQL or another managed database with backups; do not rely on a developer SQLite file.
3. Confirm per-user ownership checks on every record and tool.
4. Keep provider credentials server-side and rotate any key that may have been exposed.
5. Keep sensitive or irreversible actions behind a confirmation checkpoint.
6. Document which audio, document, and conversation data is sent to each external provider.
7. Add retention and deletion controls that match the data actually stored.
8. Test provider outages, retries, duplicate requests, and partial workflow failures.
9. Do not enable payments, OTP handling, or autonomous account access without explicit user authorization and a separate security review.

## India-first product direction

The near-term wedge is **personal follow-through**: refunds someone is waiting for, documents that need to be submitted, appointments to confirm, a person who owes a response, and household or work errands that otherwise disappear in chats and memory.

The Action Ledger is the first product primitive for this wedge. Voice makes capture more natural; the ledger makes pending work visible; reminders and approval checkpoints provide a safe path to action. See docs/INDIA_FIRST_PRODUCT_STRATEGY.md.

## YC / pilot narrative

Do not pitch Warik as “Instinct copied for India” or as a universal agent that can already control every app. Pitch the specific user problem, show one end-to-end workflow, disclose what is manual versus automated, and demonstrate repeat usage and completed outcomes. Investor credibility comes from real user behaviour and measured reliability, not a large feature list.
