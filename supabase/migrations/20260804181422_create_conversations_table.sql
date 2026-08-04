

--- the thread table points to a thread (the conversations)
create table public.threads(
    id          uuid primary key,   --- input will be a string uuid, postgres does the implicit conversion 
    title       text not null default 'New Conversation', 
    created_at  timestamptz not null default now(), 
    updated_at  timestamptz not null default now() 
); 

--- open RLS for future security proof (only useful when client side begins to access DB)
alter table public.threads enable row level security; 

-- the conversation table stores each individual conversations 
create table public.conversations(
    id      bigint generated always as identity primary key, 
    thread_id   uuid not null references public.threads(id) on delete cascade,  --- same thread id as the thread table, pinpoint to the thread
    role        text not null check(role in ('user', 'advising_bot')), 
    content     text not null,
    created_at  timestamptz not null default clock_timestamp()  
); 