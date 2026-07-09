-- Adds board_id to projects so each project remembers which board it
-- targets. Nullable + defaulted so existing projects keep working exactly
-- as before (falls back to bluepill_f103c8 in application code).

alter table public.projects
    add column if not exists board_id text not null default 'bluepill_f103c8';

comment on column public.projects.board_id is
    'PlatformIO/Board Registry id, e.g. bluepill_f103c8, nucleo_f446re.';