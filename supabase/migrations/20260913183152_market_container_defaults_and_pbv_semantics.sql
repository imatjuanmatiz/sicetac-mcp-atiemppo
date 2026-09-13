-- Revisión técnica: contenedor 20/40 parte de C2S2 salvo solicitud explícita
-- de un equipo menor. La masa de carga + contenedor no se presenta como PBV:
-- el PBV total requiere la tara del tractocamión y del semirremolque.
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
    'ruleset_id', 'mercado_colombia_tecnico_2026_09_13_3',
    'version', '2026.09.13-market.3',
    'status', 'published'
  );

  next_definition := jsonb_set(
    next_definition,
    '{vehicle_rules}',
    (
      select jsonb_agg(
        case rule->>'rule_id'
          when 'container_2' then rule || jsonb_build_object(
            'requires_explicit_request', true,
            'source_note', 'Equipo menor: solo por solicitud explícita del usuario.'
          )
          when 'container_3' then rule || jsonb_build_object(
            'requires_explicit_request', true,
            'source_note', 'Equipo menor: solo por solicitud explícita del usuario.'
          )
          when 'container_2s2' then rule || jsonb_build_object(
            'priority', 10,
            'min_operating_weight_kg', null,
            'max_operating_weight_kg', null,
            'source_note', 'Mínimo técnico operativo ATIEMPPO para contenedor de 20 o 40 pies.'
          )
          when 'container_2s3' then rule || jsonb_build_object(
            'priority', 20,
            'min_operating_weight_kg', null,
            'max_operating_weight_kg', null
          )
          when 'container_3s2' then rule || jsonb_build_object(
            'priority', 30,
            'min_operating_weight_kg', null,
            'max_operating_weight_kg', null
          )
          when 'container_3s3' then rule || jsonb_build_object(
            'priority', 40,
            'min_operating_weight_kg', null,
            'max_operating_weight_kg', null
          )
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
    '2026.09.13-market.3',
    'published',
    'sicetac_20260901_validated',
    next_definition,
    now()
  );
end
$$;
