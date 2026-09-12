-- Registro privado de consumidores y auditoría de uso de la API comercial.
-- Esta migración se versiona, pero no se aplica automáticamente desde Codex.

create table if not exists public.api_consumers (
  id uuid primary key default gen_random_uuid(),
  consumer_id text not null unique,
  name text not null,
  plan text not null default 'sandbox',
  key_prefix text not null default '',
  key_hash text not null unique,
  monthly_quota integer,
  active boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.api_usage_events (
  id bigint generated always as identity primary key,
  consumer_id text not null,
  request_id text not null,
  endpoint text not null,
  method text not null default 'POST',
  status_code integer not null,
  units integer not null default 1,
  month_key text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_api_usage_events_consumer_period
  on public.api_usage_events (consumer_id, created_at desc);
create index if not exists idx_api_usage_events_request_id
  on public.api_usage_events (request_id);

alter table public.api_consumers enable row level security;
alter table public.api_usage_events enable row level security;

-- No se crean políticas para anon/authenticated. El backend usa service role
-- para validar hashes y registrar consumo; el Data API público queda cerrado.
comment on table public.api_consumers is
  'Consumidores de la API SICETAC. key_hash nunca se expone al cliente.';
comment on table public.api_usage_events is
  'Auditoría privada de unidades consumidas por la API SICETAC.';
