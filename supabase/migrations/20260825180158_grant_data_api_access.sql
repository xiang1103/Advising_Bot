-- threads and conversations were created without any grants to the Supabase
-- Data API roles, so a database provisioned from these migrations alone rejects
-- every backend write with:
--
--     permission denied for table threads (42501)
--
-- The remote project does not hit this because its tables were originally
-- created by hand in the dashboard, which applies the grants automatically.
-- Anything provisioned from migrations (a fresh local stack, staging, a
-- restored project) is broken without this.

-- The backend is the only writer and connects with SUPABASE_SERVICE_ROLE_KEY.
grant select, insert, update, delete on public.threads to service_role;
grant select, insert, update, delete on public.conversations to service_role;

-- anon and authenticated are deliberately granted nothing: the browser talks to
-- FastAPI, never to PostgREST. Revisit only alongside real RLS policies.

-- threads already had RLS enabled; conversations did not. service_role bypasses
-- RLS, so this is free for the backend, and it keeps the table closed by default
-- if anon/authenticated are ever granted access.
alter table public.conversations enable row level security;
