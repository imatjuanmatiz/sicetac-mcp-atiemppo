-- Vencimiento y cuota atómica para consumidores de API, incluido el agente
-- público. Estas tablas y funciones son de backend: no se exponen por Data API.

alter table public.api_consumers
  add column if not exists activated_at timestamptz not null default now(),
  add column if not exists expires_at timestamptz;

alter table public.api_consumers
  drop constraint if exists api_consumers_expires_after_activation;
alter table public.api_consumers
  add constraint api_consumers_expires_after_activation
  check (expires_at is null or expires_at > activated_at);

alter table public.api_usage_events
  add column if not exists reservation_status text not null default 'reserved'
  check (reservation_status in ('reserved', 'completed', 'failed'));

revoke all on table public.api_consumers from anon, authenticated;
revoke all on table public.api_usage_events from anon, authenticated;
grant select, insert, update, delete on table public.api_consumers to service_role;
grant select, insert, update, delete on table public.api_usage_events to service_role;
grant usage, select on sequence public.api_usage_events_id_seq to service_role;

create or replace function public.api_usage_for_month(
  p_consumer_id text,
  p_month_key text
) returns integer
language sql
stable
security invoker
set search_path = public, pg_temp
as $$
  select coalesce(sum(units), 0)::integer
  from public.api_usage_events
  where consumer_id = p_consumer_id
    and month_key = p_month_key;
$$;

create or replace function public.reserve_api_usage(
  p_consumer_id text,
  p_request_id text,
  p_endpoint text,
  p_method text default 'POST'
) returns table(month_key text, monthly_usage integer, monthly_quota integer)
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
  v_active boolean;
  v_quota integer;
  v_expires_at timestamptz;
  v_used integer;
  v_month text := to_char(now() at time zone 'UTC', 'YYYY-MM');
begin
  select active, monthly_quota, expires_at
    into v_active, v_quota, v_expires_at
  from public.api_consumers
  where consumer_id = p_consumer_id
  for update;

  if not found or not v_active then
    raise exception 'consumer_inactive' using errcode = 'P0001';
  end if;
  if v_expires_at is not null and v_expires_at <= now() then
    raise exception 'consumer_expired' using errcode = 'P0001';
  end if;

  select coalesce(sum(units), 0)::integer
    into v_used
  from public.api_usage_events
  where consumer_id = p_consumer_id
    and month_key = v_month;
  if v_quota is not null and v_used >= v_quota then
    raise exception 'consumer_quota_exhausted' using errcode = 'P0001';
  end if;

  insert into public.api_usage_events (
    consumer_id, request_id, endpoint, method, status_code, units, month_key,
    reservation_status, metadata
  ) values (
    p_consumer_id, p_request_id, p_endpoint, p_method, 102, 1, v_month,
    'reserved', '{}'::jsonb
  );

  return query select v_month, v_used + 1, v_quota;
end;
$$;

revoke all on function public.api_usage_for_month(text, text) from public;
revoke all on function public.reserve_api_usage(text, text, text, text) from public;
grant execute on function public.api_usage_for_month(text, text) to service_role;
grant execute on function public.reserve_api_usage(text, text, text, text) to service_role;
