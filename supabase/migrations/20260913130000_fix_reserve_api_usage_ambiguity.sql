-- Corrige la ambigüedad entre la columna de salida monthly_quota y la tabla.
-- La función sigue siendo exclusiva de service_role.
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
  select c.active, c.monthly_quota, c.expires_at
    into v_active, v_quota, v_expires_at
  from public.api_consumers as c
  where c.consumer_id = p_consumer_id
  for update;

  if not found or not v_active then
    raise exception 'consumer_inactive' using errcode = 'P0001';
  end if;
  if v_expires_at is not null and v_expires_at <= now() then
    raise exception 'consumer_expired' using errcode = 'P0001';
  end if;

  select coalesce(sum(e.units), 0)::integer
    into v_used
  from public.api_usage_events as e
  where e.consumer_id = p_consumer_id
    and e.month_key = v_month;
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

revoke all on function public.reserve_api_usage(text, text, text, text) from public, anon, authenticated;
grant execute on function public.reserve_api_usage(text, text, text, text) to service_role;
