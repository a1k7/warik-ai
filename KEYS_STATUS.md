# Keys and services status

This status is based on tracked repository configuration only. The GitHub connection does not expose the contents of local `.env` files or runtime environment variables; the developer machine's actual key presence and values have not been inspected.

| Capability | Configuration names | Tracked template status | Demo requirement |
|---|---|---|---|
| LLM / Ollama | `LLM_PROVIDER`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | Present; Ollama is the example default | Optional; scripted planner is default |
| Hosted LLM / Groq | `GROQ_API_KEY`, `GROQ_MODEL` | Names present; no key value in template | Optional |
| Browser sandbox / CDP | `AGENT_BROWSER_CDP_URL` | Added; blank by default | Not required; local Chromium is used |
| Browser runtime | Playwright Chromium | Dependency added | Required; run `playwright install chromium` |
| Database | `DATABASE_URL` | SQLite default present | No external service required |
| Authentication | `JWT_SECRET` | Name present; blank in template | Existing JWT auth is reused; set a local development secret |
| Messaging / payments | Existing integration settings | No messaging or payment integration required | Not used; final action is a local mock hold |

No secret values are stored in this file. Never commit `backend/.env`, API keys, browser session credentials, or screenshots containing private information.
