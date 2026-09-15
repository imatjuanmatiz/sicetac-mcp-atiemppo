-- El catálogo public.municipios conserva los códigos DANE con cero inicial
-- como número sin el cero (p. ej. 08001000 -> 8001000). El helper los
-- normaliza al consultar, pero el ruleset debe conservar la misma forma que
-- el catálogo canónico para que la trazabilidad sea directa.
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
    'ruleset_id', 'mercado_colombia_tecnico_2026_09_15_7',
    'version', '2026.09.15-market.7',
    'status', 'published',
    'location_aliases', coalesce(source_definition -> 'location_aliases', '{}'::jsonb) || jsonb_build_object(
      'ZF BARRANQUILLA', jsonb_build_object('municipality', 'Barranquilla', 'department', 'Atlántico', 'dane_code', '8001000'),
      'ZONA FRANCA BARRANQUILLA', jsonb_build_object('municipality', 'Barranquilla', 'department', 'Atlántico', 'dane_code', '8001000'),
      'ZF RIONEGRO', jsonb_build_object('municipality', 'Rionegro', 'department', 'Antioquia', 'dane_code', '5615000'),
      'ZONA FRANCA RIONEGRO', jsonb_build_object('municipality', 'Rionegro', 'department', 'Antioquia', 'dane_code', '5615000'),
      'ZONA FRANCA DE RIONEGRO', jsonb_build_object('municipality', 'Rionegro', 'department', 'Antioquia', 'dane_code', '5615000')
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
    '2026.09.15-market.7',
    'published',
    source_snapshot,
    next_definition,
    now()
  );
end
$$;
