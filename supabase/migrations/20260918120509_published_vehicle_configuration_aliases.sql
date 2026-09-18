-- Equivalencias comerciales y duales de configuración. El agente envía el
-- término declarado; el Core resuelve contra esta revisión publicada.
-- Patineta = C2S2/2S2, turbo = C279/2_7_9, tractomula = C3S3/3S3.
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
    'ruleset_id', 'mercado_colombia_tecnico_2026_09_17_1',
    'version', '2026.09.17-market.1',
    'status', 'published',
    'configuration_aliases', coalesce(source_definition -> 'configuration_aliases', '{}'::jsonb) || jsonb_build_object(
      '2', '2',
      '3', '3',
      '2S2', '2S2',
      '2S3', '2S3',
      '3S2', '3S2',
      '3S3', '3S3',
      'C3', '3',
      'C257', '2_5_7',
      'C279', '2_7_9',
      '2 7 9', '2_7_9',
      'C2910', '2L1 Liviano entre 9 y 10.5 Tonel.',
      'PATINETA', '2S2',
      'PATINETA 2S2', '2S2',
      'PATINETA C2S2', '2S2',
      'MINIMULA', '2S2',
      'TURBO', '2_7_9',
      'TURBO C279', '2_7_9',
      'TRACTOMULA', '3S3',
      'TRACTO MULA', '3S3',
      'TRAILER', '3S3',
      'MULA', '3S3'
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
    '2026.09.17-market.1',
    'published',
    source_snapshot,
    next_definition,
    now()
  );
end
$$;
