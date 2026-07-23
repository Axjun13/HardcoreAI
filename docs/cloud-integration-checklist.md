# HardcoreAI application-side cloud integration

The `proxy_server/` directory in this checkout is reference material only. The
live gateway and its database migration are maintained in a separate private
repository.

## Implemented in this application repository

- Supabase OAuth with PKCE, persisted sessions, automatic refresh, sign-out,
  expiry recovery, and authentication-error UI.
- Every frontend-to-backend request now uses the current Supabase access token;
  the frontend contains no `TEST_TOKEN` call sites.
- Project listing/rename/delete and conversation persistence use the browser
  Supabase client directly under RLS. Project creation stays local-backend
  coordinated because it also creates workspace files and initializes Git.
- The backend validates the live access token using public Supabase
  configuration only.
- Paid LLM aliases route through `HARDCOREAI_PROXY_URL`; only llama.cpp and
  Ollama contact a provider directly.
- Paid web search routes through the authenticated `/api/search` gateway.
- One UUID is created per local agent run and reused for all of that run's
  gateway calls.
- Cloud agent context excludes environment files, credentials, keys,
  certificates, build/cache output, and `.git`. Credential-looking assignments
  in otherwise safe source files are redacted.
- The agent UI reports the number of included, excluded, and redacted files.
- Local limits cap agent steps, invalid/timed-out retries, each LLM wait, and
  total run duration in addition to gateway quotas.
- Application RLS covers projects, project components/connections, code files,
  and conversations. The public component catalogue is select-only for `anon`
  and `authenticated`.
- Release packaging excludes env files and fails its credential scan before
  creating an archive.

## Deployment checks requiring project access

1. Apply `supabase/migrations/20260723010000_complete_application_rls.sql` to
   the application Supabase project.
2. Enable the chosen OAuth provider and allow the packaged callback URL. Set
   `VITE_SUPABASE_REDIRECT_URL` to that exact stable callback.
3. Set `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `SUPABASE_URL`,
   `SUPABASE_ANON_KEY`, and `HARDCOREAI_PROXY_URL`. These are the only cloud
   values the distributed app needs.
4. Add the confirmed packaged webview origin to the private proxy's
   `ALLOWED_ORIGINS`.
5. Sign in as a real user and run one agent request tied to an owned project.
   Confirm streaming, project ownership, quota acquisition, final usage
   recording, and active-request cleanup in the private deployment.
6. Run one Research search and confirm the same agent-run UUID is used by
   subsequent paid searches within that agent run.
7. Build the release in an isolated output directory and inspect/sign the
   resulting archive before publishing it.
