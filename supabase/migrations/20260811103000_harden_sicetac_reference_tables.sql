create index if not exists rutas_peajes_mes_peaje_idx
    on public.rutas_peajes (mes_vigencia, id_peaje);

alter table public.sicetac_rutas_terreno_vigentes enable row level security;

drop policy if exists "Reference SICETAC terrain routes are readable"
    on public.sicetac_rutas_terreno_vigentes;
create policy "Reference SICETAC terrain routes are readable"
    on public.sicetac_rutas_terreno_vigentes
    for select
    to anon, authenticated
    using (true);

revoke insert, update, delete, truncate, references, trigger
    on public.sicetac_rutas_terreno_vigentes
    from anon, authenticated;
grant select on public.sicetac_rutas_terreno_vigentes
    to anon, authenticated, service_role;

notify pgrst, 'reload schema';
