-- Machine-readable evidence retained by the sequential Phase-3 verifier.
alter table public.components
    add column if not exists protocols jsonb not null default '[]'::jsonb,
    add column if not exists verification_sources jsonb not null default '[]'::jsonb;
