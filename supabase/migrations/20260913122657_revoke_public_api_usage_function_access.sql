-- Defensa explícita: estas funciones las invoca solo el backend con service_role.
revoke all on function public.api_usage_for_month(text, text) from public, anon, authenticated;
revoke all on function public.reserve_api_usage(text, text, text, text) from public, anon, authenticated;
grant execute on function public.api_usage_for_month(text, text) to service_role;
grant execute on function public.reserve_api_usage(text, text, text, text) to service_role;
