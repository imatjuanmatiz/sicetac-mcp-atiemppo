-- Lote inicial de aliases operativos para zonas francas. Cada destino incluye
-- DANE cuando es conocido, para que el helper municipal resuelva por código y
-- no confunda municipios homónimos. No modifica el catálogo municipal base.
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
    'ruleset_id', 'mercado_colombia_tecnico_2026_09_15_6',
    'version', '2026.09.15-market.6',
    'status', 'published',
    'location_aliases', coalesce(source_definition -> 'location_aliases', '{}'::jsonb) || jsonb_build_object(
      'ZF SANTANDER', jsonb_build_object('municipality', 'Floridablanca', 'department', 'Santander', 'dane_code', '68276000'),
      'ZONA FRANCA SANTANDER', jsonb_build_object('municipality', 'Floridablanca', 'department', 'Santander', 'dane_code', '68276000'),
      'ZF BOGOTA', jsonb_build_object('municipality', 'Bogotá', 'department', 'Bogotá D.C.', 'dane_code', '11001000'),
      'ZONA FRANCA BOGOTA', jsonb_build_object('municipality', 'Bogotá', 'department', 'Bogotá D.C.', 'dane_code', '11001000'),
      'ZONA FRANCA DE BOGOTA', jsonb_build_object('municipality', 'Bogotá', 'department', 'Bogotá D.C.', 'dane_code', '11001000'),
      'ZFO', jsonb_build_object('municipality', 'Mosquera', 'department', 'Cundinamarca', 'dane_code', '25473000'),
      'ZF OCCIDENTE', jsonb_build_object('municipality', 'Mosquera', 'department', 'Cundinamarca', 'dane_code', '25473000'),
      'ZONA FRANCA OCCIDENTE', jsonb_build_object('municipality', 'Mosquera', 'department', 'Cundinamarca', 'dane_code', '25473000'),
      'ZONA FRANCA DE OCCIDENTE', jsonb_build_object('municipality', 'Mosquera', 'department', 'Cundinamarca', 'dane_code', '25473000'),
      'ZFP', jsonb_build_object('municipality', 'Palmira', 'department', 'Valle del Cauca', 'dane_code', '76520000'),
      'ZF PACIFICO', jsonb_build_object('municipality', 'Palmira', 'department', 'Valle del Cauca', 'dane_code', '76520000'),
      'ZONA FRANCA PACIFICO', jsonb_build_object('municipality', 'Palmira', 'department', 'Valle del Cauca', 'dane_code', '76520000'),
      'ZONA FRANCA DEL PACIFICO', jsonb_build_object('municipality', 'Palmira', 'department', 'Valle del Cauca', 'dane_code', '76520000'),
      'ZF BARRANQUILLA', jsonb_build_object('municipality', 'Barranquilla', 'department', 'Atlántico', 'dane_code', '08001000'),
      'ZONA FRANCA BARRANQUILLA', jsonb_build_object('municipality', 'Barranquilla', 'department', 'Atlántico', 'dane_code', '08001000'),
      'ZF CARTAGENA', jsonb_build_object('municipality', 'Cartagena', 'department', 'Bolívar', 'dane_code', '13001000'),
      'ZONA FRANCA CARTAGENA', jsonb_build_object('municipality', 'Cartagena', 'department', 'Bolívar', 'dane_code', '13001000'),
      'ZOFRANCA', jsonb_build_object('municipality', 'Cartagena', 'department', 'Bolívar', 'dane_code', '13001000'),
      'ZF RIONEGRO', jsonb_build_object('municipality', 'Rionegro', 'department', 'Antioquia', 'dane_code', '05615000'),
      'ZONA FRANCA RIONEGRO', jsonb_build_object('municipality', 'Rionegro', 'department', 'Antioquia', 'dane_code', '05615000'),
      'ZONA FRANCA DE RIONEGRO', jsonb_build_object('municipality', 'Rionegro', 'department', 'Antioquia', 'dane_code', '05615000')
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
    '2026.09.15-market.6',
    'published',
    source_snapshot,
    next_definition,
    now()
  );
end
$$;
