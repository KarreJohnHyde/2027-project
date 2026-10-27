# MedTwin Supabase setup

Project: `2027-project` (`taryyyviljuxsdtrvtof`).

On 2026-10-27 the authenticated Supabase connector reported `ACTIVE_HEALTHY`.
A read-only SQL query succeeded on PostgreSQL 17.11; the public schema had no
application tables. `supabase init` completed locally using CLI 2.122.0.

The CLI uses a separate login from the connector. Finish the local link in a
terminal in this repository:

```powershell
npm run supabase:login
npm run supabase:link
```

The link was attempted but requires a Supabase access token. Authenticate through
the CLI login flow; do not paste access tokens or a database password into source.
The owner chose to defer CLI linking after the retry still reported a missing token.
The supplied publishable key can configure a browser client, but it is not a
database password or a CLI access token.

The existing browser URL and publishable key are configured in ignored
`.env.local`. The application currently continues to use its local FastAPI/SQLite
backend. No patient records, datasets, uploads, or model artifacts were copied to
Supabase, and no remote schema was changed. A database migration needs a reviewed
schema/access policy and a real server-side connection string before switching
`DATABASE_URL`.

Local Docker services have not been started. The hosted connector works without
downloading a second local database/container stack.

Reference: https://supabase.com/docs/reference/cli/supabase-link
