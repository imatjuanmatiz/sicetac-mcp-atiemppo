-- Homologación de texto de carrocería: el agente conserva el término recibido;
-- el Core resuelve únicamente contra la revisión publicada en Supabase antes de
-- armar la consulta SICETAC. No modifica rutas, valores ni reglas comerciales.
do $$
declare
  source_definition jsonb;
  next_definition jsonb;
begin
  select definition
    into source_definition
    from public.cotizador_rulesets
   where scope_id = 'mercado_colombia_tecnico'
     and status = 'published'
   for update;

  if source_definition is null then
    raise exception 'No published technical market ruleset is available';
  end if;

  next_definition := source_definition || jsonb_build_object(
    'ruleset_id', 'mercado_colombia_tecnico_2026_09_14_4',
    'version', '2026.09.14-market.4',
    'status', 'published',
    'body_type_aliases', jsonb_build_object(
      'FURGON', 'General - Furgon',
      'FURGON SECO', 'General - Furgon'
    )
  );

  update public.cotizador_rulesets
     set status = 'superseded'
   where scope_id = 'mercado_colombia_tecnico'
     and status = 'published';

  insert into public.cotizador_rulesets (
    scope_id, version, status, source_snapshot_id, definition, published_at
  ) values (
    'mercado_colombia_tecnico',
    '2026.09.14-market.4',
    'published',
    'sicetac_20260901_validated',
    next_definition,
    now()
  );
end
$$;
