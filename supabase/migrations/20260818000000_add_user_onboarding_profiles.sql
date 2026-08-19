-- Product onboarding details live outside auth.users so OAuth-owned identity
-- fields remain managed by Supabase Auth.
create table if not exists public.user_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  company_name text,
  phone_number text,
  role text,
  about text,
  primary_use_case text,
  company_size text,
  referral_source text,
  willing_to_pay boolean,
  project_limit_feedback text,
  project_limit_unlocked boolean not null default false,
  completed_at timestamptz,
  updated_at timestamptz not null default now(),
  constraint user_profiles_company_name_length check (company_name is null or char_length(company_name) <= 160),
  constraint user_profiles_about_length check (about is null or char_length(about) <= 600),
  constraint user_profiles_role_valid check (role is null or role in ('Student', 'Hobbyist / Maker', 'Embedded Engineer', 'Firmware Engineer', 'Hardware Engineer', 'Researcher', 'Startup Founder', 'Product / Engineering', 'Other')),
  constraint user_profiles_primary_use_case_valid check (primary_use_case is null or primary_use_case in ('Firmware Development', 'Hardware Prototyping', 'PCB / Electronics Development', 'Debugging', 'Research', 'Learning', 'Product Development', 'Other')),
  constraint user_profiles_company_size_valid check (company_size is null or company_size in ('Individual', '2-10', '11-50', '51-200', '200+')),
  constraint user_profiles_referral_source_valid check (referral_source is null or referral_source in ('LinkedIn', 'Friend / Colleague', 'University', 'GitHub', 'Search', 'Event', 'Other'))
);

alter table public.user_profiles enable row level security;
alter table public.user_profiles
  add column if not exists phone_number text,
  add column if not exists willing_to_pay boolean,
  add column if not exists project_limit_feedback text,
  add column if not exists project_limit_unlocked boolean not null default false;
create policy "Users can manage their own onboarding profile"
  on public.user_profiles for all to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);
