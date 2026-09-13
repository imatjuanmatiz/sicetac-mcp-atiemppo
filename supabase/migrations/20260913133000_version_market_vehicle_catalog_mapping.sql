-- La configuración técnica del motor y el código de vehículo SICETAC son
-- conceptos distintos. Esta revisión agrega la equivalencia explícita sin
-- modificar la revisión publicada que produjo trazas anteriores.
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
    'ruleset_id', 'mercado_colombia_tecnico_2026_09_13_2',
    'version', '2026.09.13-market.2',
    'status', 'published'
  );

  next_definition := jsonb_set(
    next_definition,
    '{vehicle_rules}',
    (
      select jsonb_agg(
        case rule->>'rule_id'
          when 'general_2' then rule || jsonb_build_object('vehicle_model_code', 'C2M10')
          when 'general_3' then rule || jsonb_build_object('vehicle_model_code', 'C3')
          when 'general_2s2' then rule || jsonb_build_object('vehicle_model_code', 'C2S2')
          when 'general_2s3' then rule || jsonb_build_object('vehicle_model_code', 'C2S3')
          when 'general_3s2' then rule || jsonb_build_object('vehicle_model_code', 'C3S2')
          when 'general_3s3' then rule || jsonb_build_object('vehicle_model_code', 'C3S3')
          when 'container_2' then rule || jsonb_build_object('vehicle_model_code', 'C2M10')
          when 'container_3' then rule || jsonb_build_object('vehicle_model_code', 'C3')
          when 'container_2s2' then rule || jsonb_build_object('vehicle_model_code', 'C2S2')
          when 'container_2s3' then rule || jsonb_build_object('vehicle_model_code', 'C2S3')
          when 'container_3s2' then rule || jsonb_build_object('vehicle_model_code', 'C3S2')
          when 'container_3s3' then rule || jsonb_build_object('vehicle_model_code', 'C3S3')
          else rule
        end
        order by position
      )
      from jsonb_array_elements(next_definition->'vehicle_rules') with ordinality as rules(rule, position)
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
    '2026.09.13-market.2',
    'published',
    'sicetac_20260901_validated',
    next_definition,
    now()
  );
end
$$;
