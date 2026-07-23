create policy "Backend service manages SICETAC VACIO"
    on public.sicetac_vacio_vigentes
    for all
    to service_role
    using (true)
    with check (true);
