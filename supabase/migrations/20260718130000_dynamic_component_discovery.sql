-- Provenance for components found by the Research agent at runtime. Product
-- images remain remote URLs; no third-party image binaries are copied into DB.

alter table public.components
    add column if not exists source_url text,
    add column if not exists source_name text,
    add column if not exists image_source_url text,
    add column if not exists discovery_query text,
    add column if not exists discovered_at timestamptz,
    add column if not exists verified_at timestamptz;
