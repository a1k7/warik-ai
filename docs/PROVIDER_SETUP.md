# Warik AI — provider and deployment setup

This guide describes configuration consumed by the current codebase. A configured integration means credentials and a feature mode are present; it does not mean a provider is reachable at this moment. The authenticated Settings page exposes the same configuration snapshot at **Warik capability readiness**.

## 1. Model reasoning

For hosted use, configure a server-side Groq key:

    ENVIRONMENT=production
    LLM_PROVIDER=groq
    GROQ_API_KEY=<secret>
    GROQ_MODEL=llama-3.3-70b-versatile

The app currently supports groq and ollama. Ollama is suitable for local development when the model server is reachable from the backend. Do not place a model key in a VITE_ variable.

## 2. Live flight offers

Set:

    DUFFEL_API_KEY=<Duffel API token>

Warik calls Duffel offer-request search and can retrieve a previously displayed offer again to refresh its price and current state. The search requires a valid date, route and successfully resolved airport records. The planner supports passenger count, cabin class, stops, departure windows and arrival windows when supplied.

**Scope:** search and refresh only. The application does not currently create a Duffel order, issue a ticket, or collect payment. A refreshed offer is still not a booking.

Without Duffel, the legacy trvl command-line adapter may be used when installed and configured. Without a live adapter, the assistant provides a Google Flights handoff and marks live inventory unavailable.

## 3. Hotel search

Booking.com Demand API v3.3 is optional and requires approved partner access. Set all three:

    BOOKING_MODE=search_and_redirect
    BOOKING_API_BASE_URL=https://demandapi.booking.com/3.3
    BOOKING_API_TOKEN=<partner API token>
    BOOKING_AFFILIATE_ID=<affiliate ID>

For sandbox testing, use:

    BOOKING_API_BASE_URL=https://demandapi-sandbox.booking.com/3.3

The active adapter resolves the destination, searches current accommodation offers and requests provider details for the redirect flow. Its returned prices and URLs come from the provider. It is search-and-redirect, not a Warik-operated booking or payment.

If partner access is not configured, Warik can use the optional trvl CLI adapter. If that is not available, it creates a Booking.com search handoff and clearly marks that live inventory was not queried.

## 4. Airport transfers and rail/bus

No ride-fare provider is currently configured. The current transport capability creates Uber and Ola handoff links when pickup and drop-off are known. It does not quote live vehicle fares, guarantee vehicle availability, create a ride, or retrieve a ride confirmation.

IRCTC, RedBus and MakeMyTrip are currently external search handoffs. The app does not return live seat inventory or issue train or bus tickets.

## 5. Indian-language voice

Voice capture is disabled by default. Enable it and configure one supported speech provider:

    VOICE_ENABLED=true
    GROQ_API_KEY=<server-side Groq key>

or:

    VOICE_ENABLED=true
    GNANI_API_KEY=<server-side Gnani key>
    GNANI_ORG_ID=<Gnani organisation ID>
    GNANI_USER_ID=<Gnani user ID>

Groq is selected for STT when its key is configured; otherwise the configured Gnani provider is used. The UI supports Bengali, English (India), Gujarati, Hindi, Kannada, Malayalam, Marathi, Punjabi, Tamil and Telugu. The user reviews and can edit the transcript before sending it to the assistant.

Speech credentials must remain backend-only. Do not commit them or add them to frontend environment variables.

## 6. Swiggy

The default SWIGGY_MODE=mock means results must not be represented as live. OAuth settings can be configured using the values in the root .env.example; the account connection and supported MCP permissions are managed separately. Do not ask users to enter their Swiggy password or OTP into Warik.

## 7. Production runtime

The backend explicitly rejects SQLite in ENVIRONMENT=production. Configure a managed PostgreSQL instance and set:

    ENVIRONMENT=production
    DATABASE_URL=postgresql+psycopg://<user>:<password>@<host>:5432/<database>
    JWT_SECRET=<unique random secret, at least 32 characters>
    CORS_ORIGINS=https://<your-frontend-domain>

Use HTTPS, a restricted CORS allow-list, managed secret storage, database backups, a stable persistent database, logs/alerts, and a deployment strategy for schema changes. Do not use the development JWT secret.

The public /api/health checks database connectivity. The authenticated /api/health/capabilities endpoint reports provider configuration, never credential values. Neither endpoint is a live third-party provider health check.

## 8. Release verification

After deployment:

1. Sign in and open Settings → Warik capability readiness.
2. Confirm the expected model provider is configured.
3. Send a normal knowledge question to verify the model path.
4. Search flights with a real route/date and verify the result is marked live only when Duffel or the CLI actually returned offers.
5. Refresh a flight offer and confirm that price/expiry are re-read from Duffel.
6. Test hotel search only after partner credentials and permissions are enabled; otherwise expect a search handoff.
7. Test cab and rail/bus links as handoffs, not bookings.
8. Enable voice only after setting the speech key; verify the transcript review step.
9. Test account isolation, confirmation checkpoints, provider timeouts, retries, deletion, backup restoration and log redaction before inviting external users.

## Current product boundary

Warik combines a conversational assistant, user-scoped context, tool-driven workflows, an Action Ledger, and provider-aware search. It is not yet a universal autonomous desktop agent or a fully integrated travel booking platform. Keep this distinction explicit in demos and investor materials.
