-- location_aliases sólo traduce nombres operativos a municipio/departamento.
-- El DANE se obtiene exclusivamente del catálogo municipios en el helper.
do $$
declare
  source_definition jsonb;
  source_snapshot text;
  aliases_without_dane jsonb;
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

  select coalesce(jsonb_object_agg(alias, value - 'dane_code' - 'codigo_dane'), '{}'::jsonb)
    into aliases_without_dane
    from jsonb_each(coalesce(source_definition -> 'location_aliases', '{}'::jsonb)) as item(alias, value);

  next_definition := source_definition || jsonb_build_object(
    'ruleset_id', 'mercado_colombia_tecnico_2026_09_15_8',
    'version', '2026.09.15-market.8',
    'status', 'published',
    'location_aliases', aliases_without_dane
  );

  update public.cotizador_rulesets
     set status = 'superseded'
   where scope_id = 'mercado_colombia_tecnico'
     and status = 'published';

  insert into public.cotizador_rulesets (
    scope_id, version, status, source_snapshot_id, definition, published_at
  ) values (
    'mercado_colombia_tecnico',
    '2026.09.15-market.8',
    'published',
    source_snapshot,
    next_definition,
    now()
  );
end
$$;
