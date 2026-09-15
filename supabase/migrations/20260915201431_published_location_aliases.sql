-- Homologación de localidades operativas: el Core traduce aliases publicados
-- antes de entregarlos al helper de municipios SICETAC. No modifica el catálogo
-- municipal, rutas, valores ni reglas comerciales.
do $$
declare
  source_definition jsonb;
  source_snapshot text;
  next_definition jsonb;
begin
  select definition, source_snapshot_id
    into source_definition, source_snapshot
    from public.cotizador_rulesets
   where scope_id = 'mercado_colombia_tecnico'
     and status = 'published'
   for update;

  if source_definition is null then
    raise exception 'No published technical market ruleset is available';
  end if;

  next_definition := source_definition || jsonb_build_object(
    'ruleset_id', 'mercado_colombia_tecnico_2026_09_15_5',
    'version', '2026.09.15-market.5',
    'status', 'published',
    'location_aliases', coalesce(source_definition -> 'location_aliases', '{}'::jsonb) || jsonb_build_object(
      'ZF SANTANDER', jsonb_build_object(
        'municipality', 'Floridablanca',
        'department', 'Santander'
      ),
      'ZONA FRANCA SANTANDER', jsonb_build_object(
        'municipality', 'Floridablanca',
        'department', 'Santander'
      )
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
    '2026.09.15-market.5',
    'published',
    source_snapshot,
    next_definition,
    now()
  );
end
$$;
