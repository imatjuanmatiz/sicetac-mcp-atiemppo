-- Reglas técnicas compartidas para el Core de cotización.
-- Se consumen exclusivamente desde el backend con credencial secreta.
-- La regla publicada es una revisión completa e inmutable: no se mezclan filas
-- de versiones diferentes y ninguna observación de agentes se promueve sola.

create table if not exists public.cotizador_rulesets (
  id uuid primary key default gen_random_uuid(),
  scope_id text not null,
  version text not null,
  status text not null check (status in ('draft', 'published', 'superseded', 'retired')),
  source_snapshot_id text not null,
  definition jsonb not null check (jsonb_typeof(definition) = 'object'),
  created_at timestamptz not null default now(),
  published_at timestamptz,
  unique (scope_id, version)
);

create unique index if not exists uq_cotizador_rulesets_one_published_scope
  on public.cotizador_rulesets (scope_id)
  where status = 'published';

create table if not exists public.cotizador_term_observations (
  id bigint generated always as identity primary key,
  scope_id text not null,
  consumer_id text not null,
  request_id text not null,
  raw_expression text not null check (char_length(raw_expression) between 1 and 160),
  normalized_expression text,
  entity_type text not null check (char_length(entity_type) between 1 and 64),
  suggested_value text,
  status text not null default 'pending_review'
    check (status in ('pending_review', 'accepted', 'rejected')),
  reviewed_at timestamptz,
  reviewed_by text,
  created_at timestamptz not null default now()
);

create index if not exists idx_cotizador_term_observations_review
  on public.cotizador_term_observations (scope_id, status, created_at desc);

alter table public.cotizador_rulesets enable row level security;
alter table public.cotizador_term_observations enable row level security;

-- Estas tablas no forman parte de la Data API pública. El backend usa una
-- credencial secreta server-side; anon y authenticated no tienen ningún grant.
revoke all on table public.cotizador_rulesets from anon, authenticated;
revoke all on table public.cotizador_term_observations from anon, authenticated;
grant select, insert, update, delete on table public.cotizador_rulesets to service_role;
grant select, insert, update, delete on table public.cotizador_term_observations to service_role;
grant usage, select on sequence public.cotizador_term_observations_id_seq to service_role;

comment on table public.cotizador_rulesets is
  'Revisiones técnicas completas, sin precios ni políticas comerciales.';
comment on table public.cotizador_term_observations is
  'Vocabulario observado de agentes; requiere revisión antes de cambiar un ruleset.';

insert into public.cotizador_rulesets (
  scope_id, version, status, source_snapshot_id, definition, published_at
) values (
  'mercado_colombia_tecnico',
  '2026.09.12-market.1',
  'published',
  'sicetac_20260901_validated',
  $$
  {
    "schema_version": 1,
    "scope_id": "mercado_colombia_tecnico",
    "ruleset_id": "mercado_colombia_tecnico_2026_09_12_1",
    "version": "2026.09.12-market.1",
    "status": "published",
    "source_snapshot_id": "sicetac_20260901_validated",
    "knowledge_scope": "mercado_colombia_tecnico",
    "contains_commercial_rules": false,
    "emission_allowed": false,
    "container_tares_kg": {"20": 2300, "40": 4100},
    "configuration_aliases": {"C2": "2", "C2M10": "2", "C2S2": "2S2", "C2S3": "2S3", "C3S2": "3S2", "C3S3": "3S3"},
    "vehicle_equivalences": [
      {"vehicle_model_code": "CA", "sicetac_configuration": "CA_35_5", "toll_equivalence": "C2", "scope": "peajes_only"},
      {"vehicle_model_code": "C257", "sicetac_configuration": "2_5_7", "toll_equivalence": "C2", "scope": "peajes_only"},
      {"vehicle_model_code": "C279", "sicetac_configuration": "2_7_9", "toll_equivalence": "C2", "scope": "peajes_only"},
      {"vehicle_model_code": "C2910", "sicetac_configuration": "2L1 Liviano entre 9 y 10.5 Tonel.", "toll_equivalence": "C2", "scope": "peajes_only"}
    ],
    "vehicle_rules": [
      {"rule_id": "general_ca_35_5", "service_code": "carga_general", "sicetac_configuration": "CA_35_5", "commercial_label": "Rígido 2 ejes 3,5-5 t", "priority": 10, "min_operating_weight_kg": 3500, "max_operating_weight_kg": 5000, "max_cargo_kg": 1900, "axle_count": 2, "vehicle_model_code": "CA", "provisional": true},
      {"rule_id": "general_2_5_7", "service_code": "carga_general", "sicetac_configuration": "2_5_7", "commercial_label": "Rígido 2 ejes 5-7 t", "priority": 20, "min_operating_weight_kg": 5001, "max_operating_weight_kg": 7000, "max_cargo_kg": 2400, "axle_count": 2, "vehicle_model_code": "C257", "provisional": true},
      {"rule_id": "general_2_7_9", "service_code": "carga_general", "sicetac_configuration": "2_7_9", "commercial_label": "Rígido 2 ejes 7-9 t", "priority": 30, "min_operating_weight_kg": 7001, "max_operating_weight_kg": 9000, "max_cargo_kg": 4000, "axle_count": 2, "vehicle_model_code": "C279", "provisional": true},
      {"rule_id": "general_2l1", "service_code": "carga_general", "sicetac_configuration": "2L1 Liviano entre 9 y 10.5 Tonel.", "commercial_label": "Rígido 2 ejes 9-10,5 t", "priority": 40, "min_operating_weight_kg": 9001, "max_operating_weight_kg": 10500, "max_cargo_kg": 6000, "axle_count": 2, "vehicle_model_code": "C2910", "provisional": true},
      {"rule_id": "general_2", "service_code": "carga_general", "sicetac_configuration": "2", "commercial_label": "Rígido 2 ejes más de 10,5 t", "priority": 45, "min_operating_weight_kg": 10501, "max_operating_weight_kg": null, "max_cargo_kg": 9000, "axle_count": 2, "provisional": true},
      {"rule_id": "general_3", "service_code": "carga_general", "sicetac_configuration": "3", "commercial_label": "Camión rígido 3 ejes", "priority": 50, "min_operating_weight_kg": 10501, "max_operating_weight_kg": 17000, "max_cargo_kg": 16000, "axle_count": 3, "provisional": true},
      {"rule_id": "general_2s2", "service_code": "carga_general", "sicetac_configuration": "2S2", "commercial_label": "Tractocamión C2S2", "priority": 60, "min_operating_weight_kg": 17001, "max_operating_weight_kg": 28000, "max_cargo_kg": 22000, "axle_count": 4, "provisional": true},
      {"rule_id": "general_2s3", "service_code": "carga_general", "sicetac_configuration": "2S3", "commercial_label": "Tractocamión C2S3", "priority": 70, "min_operating_weight_kg": 28001, "max_operating_weight_kg": 30000, "max_cargo_kg": 27000, "axle_count": 5, "provisional": true},
      {"rule_id": "general_3s2", "service_code": "carga_general", "sicetac_configuration": "3S2", "commercial_label": "Tractocamión C3S2", "priority": 80, "min_operating_weight_kg": 30001, "max_operating_weight_kg": 32000, "max_cargo_kg": 31000, "axle_count": 5, "provisional": true},
      {"rule_id": "general_3s3", "service_code": "carga_general", "sicetac_configuration": "3S3", "commercial_label": "Tractocamión C3S3", "priority": 90, "min_operating_weight_kg": 32001, "max_operating_weight_kg": 34000, "max_cargo_kg": 34000, "axle_count": 6, "provisional": true},
      {"rule_id": "container_2", "service_code": "contenedor", "sicetac_configuration": "2", "commercial_label": "Portacontenedor C2M10", "priority": 10, "min_operating_weight_kg": 0, "max_operating_weight_kg": 10500, "max_cargo_kg": 9000, "axle_count": 2, "container_sizes_ft": [20], "provisional": true},
      {"rule_id": "container_3", "service_code": "contenedor", "sicetac_configuration": "3", "commercial_label": "Portacontenedor rígido 3 ejes", "priority": 20, "min_operating_weight_kg": 10501, "max_operating_weight_kg": 17000, "max_cargo_kg": 16000, "axle_count": 3, "container_sizes_ft": [20], "provisional": true},
      {"rule_id": "container_2s2", "service_code": "contenedor", "sicetac_configuration": "2S2", "commercial_label": "Portacontenedor C2S2", "priority": 30, "min_operating_weight_kg": 17001, "max_operating_weight_kg": 28000, "max_cargo_kg": 22000, "axle_count": 4, "container_sizes_ft": [20, 40], "provisional": true},
      {"rule_id": "container_2s3", "service_code": "contenedor", "sicetac_configuration": "2S3", "commercial_label": "Portacontenedor C2S3", "priority": 40, "min_operating_weight_kg": 28001, "max_operating_weight_kg": 30000, "max_cargo_kg": 27000, "axle_count": 5, "container_sizes_ft": [20, 40], "provisional": true},
      {"rule_id": "container_3s2", "service_code": "contenedor", "sicetac_configuration": "3S2", "commercial_label": "Portacontenedor C3S2", "priority": 50, "min_operating_weight_kg": 30001, "max_operating_weight_kg": 32000, "max_cargo_kg": 31000, "axle_count": 5, "container_sizes_ft": [20, 40], "provisional": true},
      {"rule_id": "container_3s3", "service_code": "contenedor", "sicetac_configuration": "3S3", "commercial_label": "Portacontenedor C3S3", "priority": 60, "min_operating_weight_kg": 32001, "max_operating_weight_kg": 34000, "max_cargo_kg": 34000, "axle_count": 6, "container_sizes_ft": [20, 40], "provisional": true}
    ]
  }
  $$::jsonb,
  now()
);
