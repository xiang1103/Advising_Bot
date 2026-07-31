-- Rebuild conversations from scratch. The original table was created by hand in
-- the dashboard and never tracked by a migration; remote data is disposable.

drop table if exists public.conversations cascade;
