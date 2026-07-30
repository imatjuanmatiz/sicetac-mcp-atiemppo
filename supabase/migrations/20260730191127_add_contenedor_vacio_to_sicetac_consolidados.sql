alter table public.sicetac_movilizacion_vigentes
    add column if not exists contenedor_portacontenedores_vacio double precision;

alter table public.sicetac_valorhora_vigentes
    add column if not exists contenedor_portacontenedores_vacio double precision;

comment on column public.sicetac_movilizacion_vigentes.contenedor_portacontenedores_vacio is
    'SICETAC oficial: condicion CARGADO, tipo de carga Contenedor vacio, unidad PORTACONTENEDORES.';

comment on column public.sicetac_valorhora_vigentes.contenedor_portacontenedores_vacio is
    'Valor hora SICETAC oficial para condicion CARGADO, tipo de carga Contenedor vacio y unidad PORTACONTENEDORES.';
