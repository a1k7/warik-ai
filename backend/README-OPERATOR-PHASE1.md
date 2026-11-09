# Warik AI — Operator Foundation, Phase 1

This is a migration-safe backend update for the uploaded Warik AI source tree.
It preserves the existing travel-specific interpreter and deterministic routes while
adding a registry-driven planner for requests that do not match those legacy routes.

## Included changes

1. **Capability manifest** — `registry.describe_tools()` exposes each registered tool's
   JSON input schema, capability category, confirmation requirement, mutation flag and
   declared execution status.
2. **Universal task planner** — `app/agents/universal_planner.py` can turn an unhandled
   request into a validated workflow using only registered tools. It rejects unknown
   tools, invalid arguments, unknown dependencies, cyclic dependencies and plans that
   exceed the safety limit.
3. **Planner integration** — the generic planner now runs before the plain chat fallback.
   Existing deterministic task/expense, travel, food and hotel routes are retained for
   compatibility in this first migration step.
4. **Workflow approval enforcement** — the workflow engine derives approval requirements
   from server-side tool metadata. An LLM cannot turn off confirmation for a tool marked
   `requires_confirmation` or `is_mutating`.
5. **Approval resume fix** — workflow steps in `APPROVED` state are now eligible for
   execution. Previously they were skipped by the executor after approval.
6. **Explicit approval replies** — a message must be a short, explicit approval and there
   must be an outstanding approval checkpoint. A sentence that merely contains the word
   "confirm" no longer approves a pending step.
7. **Truthful provider descriptions** — flight, hotel and cab tools are described as
   provider handoffs/search, not completed bookings.
8. **Booking safety** — `/api/bookings/confirm` now returns HTTP 501 until a real provider
   and payment integration exists. It no longer inserts a fake CONFIRMED booking or claims
   that payment succeeded.
9. **Conversation contract test** — a test covers the same `POST /api/conversations` body
   the current frontend sends.
10. **Voice configuration correction** — Gnani organization/user ID settings are defined;
    voice-disabled and Groq/Gnani configuration checks are handled before transcription.

## Apply on macOS

1. Stop the backend server.
2. Back up the current backend folder:

   ```bash
   cd ~/warik-ai
   cp -R backend backend-backup-operator-phase1
   ```

3. Extract this ZIP to a temporary folder, then copy only `app/` and `tests/` over the
   existing folders. Do not replace your local `.env`, `.venv`, database or audio cache.

   ```bash
   mkdir -p /tmp/warik-ai-operator-phase1
   unzip -q ~/Downloads/warik-ai-backend-operator-phase1.zip -d /tmp/warik-ai-operator-phase1

   cp -R /tmp/warik-ai-operator-phase1/backend/app/. ~/warik-ai/backend/app/
   cp -R /tmp/warik-ai-operator-phase1/backend/tests/. ~/warik-ai/backend/tests/
   ```

4. Activate the existing environment and validate:

   ```bash
   cd ~/warik-ai/backend
   source .venv/bin/activate

   python -m compileall -q app tests
   pytest -q
   ```

5. Restart the backend:

   ```bash
   uvicorn app.main:app --reload
   ```

The package includes the updated tests. The target is **95 passing tests**. The validation
run performed while preparing this package used test-only stubs for `bcrypt` and
`duckduckgo_search` because those packages were unavailable in the build environment.
Run the commands above inside your existing `.venv` with the real packages installed.

## Important current limitations

This is the execution foundation, not the finished all-task operator.

- The universal planner is currently the path for requests that do not match existing
  deterministic/domain routes. The next migration should move travel, food, hotel and
  productivity requests onto the same planner incrementally.
- There is not yet a general user-selection checkpoint (`AWAITING_SELECTION`) or safe
  result-binding system for chaining a user-selected flight/hotel/ride into a later
  provider transaction.
- The current flight, hotel, cab and food integrations are search/handoff capabilities.
  They do not book or charge inside Warik. The fake booking endpoint has been disabled
  deliberately until a real booking/payment adapter is integrated.
- Proactive event monitoring (flight changes, cab status, delivery events, etc.) and
  parallel execution are later phases.

## Security and local files

This ZIP deliberately excludes `token.json`, `audio_cache/`, local databases, virtual
Environments, `.env` files, `__pycache__`, and old backup copies. Keep your local data
files separate. The uploaded source archive included a `token.json`; it was not opened
or copied. If it contains a live credential, revoke/rotate that credential.

Before deployment, set a strong random `JWT_SECRET` in your local environment. The
source default is development-only and produces JWT key-length warnings.
