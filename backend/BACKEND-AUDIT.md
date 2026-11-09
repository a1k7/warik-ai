# Warik AI — backend review of uploaded source

## Findings from the uploaded source

### Conversation creation

- `app/main.py` includes the conversations router under `/api`.
- `POST /api/conversations` accepts `{"title":"New Chat"}` and returns a
  `ConversationResponse`.
- The frontend archive sends that exact path and body.
- The route was exercised in an isolated FastAPI/SQLite test: create returned HTTP 200,
  and the subsequent list returned HTTP 200.
- Therefore, the source does not currently show a mismatch between the frontend request
  and the backend route. The Safari alert still requires the actual browser Network
  response to distinguish authentication, CORS, stale-server or runtime failures.

### Planner and orchestration

- The original `orchestrator.py` routes productivity, expenses, travel, food and hotels
  through separate deterministic/domain-specific branches; only travel uses the old
  `GoalInterpreter` workflow path.
- Unmatched requests previously went to `provider.synthesize()` with no capability
  execution. The new universal planner is inserted before this fallback.
- The new planner sees the registry's schemas and can only return registered tools.
- Legacy routes remain in place to avoid destabilizing the existing travel flow during
  the first migration.

### Workflow engine

- The engine already persisted goals/workflows and handled dependencies/failures.
- It did not centrally enforce `BaseTool.requires_confirmation` or `is_mutating`.
- It also set a step to `APPROVED` but the executor only selected `PENDING`/`READY`, which
  could strand an approved action. Both issues are addressed in Phase 1.
- The generic engine still needs an interactive selection state and general input/result
  binding before it can safely chain arbitrary search results into provider bookings.

### Booking/provider truthfulness

- Flight search produces flight results plus booking links; it does not issue a ticket.
- Hotel search produces external booking links; it does not create a hotel reservation.
- Cab functionality generates Uber/Ola handoff links; it does not request a ride.
- Food ordering explicitly hands the user to Zomato/Swiggy; Warik does not submit the order.
- `POST /api/bookings/confirm` previously wrote a database row marked CONFIRMED and
  returned "Payment successful" without a payment gateway or provider transaction. That
  endpoint now returns HTTP 501 until real integrations exist.

### Security/configuration

- `Settings.jwt_secret` has a short development fallback. Replace it with a strong random
  environment secret before deployment.
- The uploaded archive contained `token.json` and cached audio. Those files were not
  opened and are excluded from the sanitized output package. Rotate a live credential if
  that file contained one.

## Remaining work after Phase 1

1. Migrate existing domain routes onto the universal planner without losing tests.
2. Add `AWAITING_SELECTION`, validated user selection events and deterministic
   `result_bindings` from earlier task outputs.
3. Implement provider adapters for actual flight, hotel, cab and food transactions,
   including idempotency and status reconciliation.
4. Introduce a transaction/payment checkpoint with amount, provider, fees, cancellation
   terms and explicit user confirmation.
5. Add event subscriptions/polling, notifications and proactive task follow-through.
6. Add per-user timezone, preference and permission context to planning.
7. Add concurrency for independent read-only steps using isolated sessions; do not share
   a SQLAlchemy session across worker threads.
