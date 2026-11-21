# Gmail Account Hub connector

Warik uses Google's server-side OAuth flow with the single Gmail scope
`https://www.googleapis.com/auth/gmail.readonly`. Gmail is a personal-context
connector; it is not a flight, hotel, or cab inventory API.

## Google Cloud setup

1. Create/select a Google Cloud project and enable the Gmail API.
2. Configure the OAuth consent screen. During development, add your Google
   account as a test user. Public production use of Gmail restricted scopes may
   require Google's verification and security assessment; complete the process
   that Google requires for your app and deployment.
3. Create an OAuth client ID with application type **Web application**.
4. Add this exact local authorized redirect URI:
   `http://localhost:8000/api/integrations/gmail/oauth/callback`
5. For production, add the exact HTTPS callback URL used by your deployed API.

## Backend environment

Set these values in `backend/.env` (never commit this file):

```dotenv
GOOGLE_CLIENT_ID=your-web-client-id
GOOGLE_CLIENT_SECRET=your-web-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/integrations/gmail/oauth/callback
GOOGLE_FRONTEND_RETURN_URL=http://localhost:5173/settings
GOOGLE_TOKEN_ENCRYPTION_KEY=your-generated-fernet-key
```

Generate a separate encryption key:

```bash
cd ~/warik-ai/backend
source .venv/bin/activate
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Use the generated value for `GOOGLE_TOKEN_ENCRYPTION_KEY`. Keep it stable and
back it up securely: changing it makes previously encrypted tokens unreadable.
Do not reuse the JWT secret or expose this key to the frontend.

## Data and permissions

- The user authorizes Gmail directly through Google; Warik never requests a
  Google password or OTP.
- Refresh/access tokens are encrypted at rest and stored per Warik user.
- The Account Hub's travel scan searches a bounded two-year window for travel,
  ride and food confirmation messages.
- The service requests Gmail `metadata` format and does not fetch message bodies.
  A short Gmail-provided snippet and selected headers are shown to the user.
- Search results are returned on demand and are not persisted by this connector.
- Disconnect deletes the local credentials and attempts Google token revocation.
- This connector does not book, buy, send, modify, or cancel anything.

Run tests with:

```bash
cd ~/warik-ai/backend
source .venv/bin/activate
pytest -q tests/test_gmail_account_hub.py
```
