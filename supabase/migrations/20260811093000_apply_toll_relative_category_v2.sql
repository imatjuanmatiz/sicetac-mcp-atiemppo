-- Contrato: sicetac-toll-relative-category-v2
-- Fuente: PeajesPorRutasConTarifas_SICETAC_2026-08-01.xlsx

alter table public.peajes_tarifas_configuracion
    add column if not exists rule_id text,
    add column if not exists vehiculo_fuente text,
    add column if not exists vehiculo_canonico text,
    add column if not exists categoria_objetivo integer,
    add column if not exists categoria_efectiva integer,
    add column if not exists categoria_maxima integer,
    add column if not exists selection_status text,
    add column if not exists fallback_reason text,
    add column if not exists source_hash text,
    add column if not exists source_row_count integer;

do $$
begin
    if exists (
        select 1
        from public.peajes_inventario
        where mes_codigo = 202608
        group by mes_vigencia, id_peaje
        having count(*) > 1
    ) then
        raise exception 'conflicting_tariff_patterns: inventario duplicado para una caseta del corte 202608';
    end if;
end
$$;

delete from public.peajes_tarifas_configuracion
where mes_codigo = 202608;

with configuraciones(configuracion, configuracion_sicetac, offset_relativo) as (
    values
        ('2', 'C2', 3),
        ('3', 'C3', 2),
        ('C2S2', 'C2S2', 2),
        ('C2S3', 'C2S3', 1),
        ('C3S2', 'C3S2', 1),
        ('C3S3', 'C3S3', 0)
), calculadas as (
    select
        inv.*,
        cfg.configuracion,
        cfg.configuracion_sicetac,
        max_cat.categoria_maxima,
        max_cat.categoria_maxima - cfg.offset_relativo as categoria_objetivo,
        efectiva.categoria_efectiva
    from public.peajes_inventario inv
    cross join configuraciones cfg
    cross join lateral (
        select max(v.categoria)::integer as categoria_maxima
        from (values
            (1, inv.valor1), (2, inv.valor2), (3, inv.valor3),
            (4, inv.valor4), (5, inv.valor5), (6, inv.valor6),
            (7, inv.valor7)
        ) as v(categoria, tarifa)
        where coalesce(v.tarifa, 0) > 0
    ) max_cat
    left join lateral (
        select max(v.categoria)::integer as categoria_efectiva
        from (values
            (1, inv.valor1), (2, inv.valor2), (3, inv.valor3),
            (4, inv.valor4), (5, inv.valor5), (6, inv.valor6),
            (7, inv.valor7)
        ) as v(categoria, tarifa)
        where coalesce(v.tarifa, 0) > 0
          and v.categoria <= max_cat.categoria_maxima - cfg.offset_relativo
    ) efectiva on true
    where inv.mes_codigo = 202608
)
insert into public.peajes_tarifas_configuracion (
    mes_vigencia,
    mes_codigo,
    fecha_tarifa,
    id_peaje,
    nombre_peaje,
    configuracion,
    configuracion_sicetac,
    categoria_usada,
    categoria_maxima_disponible,
    valor_peaje,
    fuente_archivo,
    rule_id,
    vehiculo_fuente,
    vehiculo_canonico,
    categoria_objetivo,
    categoria_efectiva,
    categoria_maxima,
    selection_status,
    fallback_reason,
    source_hash,
    source_row_count
)
select
    c.mes_vigencia,
    c.mes_codigo,
    c.fecha_tarifa,
    c.id_peaje,
    c.nombre_peaje,
    c.configuracion,
    c.configuracion_sicetac,
    case c.categoria_efectiva
        when 1 then 'I' when 2 then 'II' when 3 then 'III'
        when 4 then 'IV' when 5 then 'V' when 6 then 'VI' when 7 then 'VII'
    end,
    case c.categoria_maxima
        when 1 then 'I' when 2 then 'II' when 3 then 'III'
        when 4 then 'IV' when 5 then 'V' when 6 then 'VI' when 7 then 'VII'
    end,
    case c.categoria_efectiva
        when 1 then c.valor1 when 2 then c.valor2 when 3 then c.valor3
        when 4 then c.valor4 when 5 then c.valor5 when 6 then c.valor6
        when 7 then c.valor7 else 0
    end,
    c.fuente_archivo,
    'sicetac-toll-relative-category-v2',
    c.configuracion,
    c.configuracion_sicetac,
    c.categoria_objetivo,
    c.categoria_efectiva,
    c.categoria_maxima,
    case
        when c.categoria_maxima is null then 'all_categories_zero'
        when c.categoria_efectiva is null then 'no_lower_category_available_review'
        when c.categoria_efectiva = c.categoria_objetivo then 'relative_exact'
        else 'fallback_lower'
    end,
    case
        when c.categoria_maxima is null then 'No hay categorías con tarifa positiva.'
        when c.categoria_efectiva is null then 'La categoría objetivo no existe y no hay categoría positiva inferior; se prohíbe promover.'
        when c.categoria_efectiva < c.categoria_objetivo then 'Se usa la mayor categoría positiva inferior a la categoría objetivo.'
        else null
    end,
    '351e49205db4930e57b26221fbfbdbadc065502a827f87fc774953093b6af05b',
    69957
from calculadas c;

drop view if exists public.peajes_resumen_vigentes;
drop view if exists public.peajes_detalle_vigentes;

create view public.peajes_detalle_vigentes
with (security_invoker = true)
as
with rutas_unicas as (
    select distinct on (mes_vigencia, id_sice, id_peaje, orden)
        mes_vigencia,
        mes_codigo,
        fecha_tarifa,
        id_sice,
        nombre_ruta,
        codigo_dane_origen,
        codigo_dane_destino,
        ruta,
        orden,
        id_peaje,
        ruta_peaje_orden,
        fuente_archivo
    from public.rutas_peajes
    order by mes_vigencia, id_sice, id_peaje, orden, created_at desc
)
select
    rp.mes_vigencia,
    rp.mes_codigo,
    rp.fecha_tarifa,
    rp.id_sice,
    rp.nombre_ruta,
    rp.codigo_dane_origen,
    rp.codigo_dane_destino,
    rp.ruta,
    rp.orden,
    rp.id_peaje,
    inv.nombre_peaje,
    rp.ruta_peaje_orden,
    tc.configuracion,
    tc.configuracion_sicetac,
    tc.categoria_usada,
    tc.categoria_maxima_disponible,
    tc.valor_peaje,
    inv.valor1,
    inv.valor2,
    inv.valor3,
    inv.valor4,
    inv.valor5,
    inv.valor6,
    inv.valor7,
    tc.rule_id,
    tc.vehiculo_fuente,
    tc.vehiculo_canonico,
    tc.categoria_objetivo,
    tc.categoria_efectiva,
    tc.categoria_maxima,
    tc.selection_status,
    tc.fallback_reason,
    tc.fuente_archivo,
    tc.source_hash as fuente_sha256,
    tc.source_row_count as filas_fuente
from rutas_unicas rp
join public.peajes_inventario inv
  on inv.mes_vigencia = rp.mes_vigencia
 and inv.id_peaje = rp.id_peaje
join public.peajes_tarifas_configuracion tc
  on tc.mes_vigencia = rp.mes_vigencia
 and tc.id_peaje = rp.id_peaje
where rp.mes_vigencia = (select max(mes_vigencia) from public.rutas_peajes);

create view public.peajes_resumen_vigentes
with (security_invoker = true)
as
select
    mes_vigencia,
    mes_codigo,
    id_sice,
    nombre_ruta,
    codigo_dane_origen,
    codigo_dane_destino,
    ruta,
    configuracion,
    configuracion_sicetac,
    count(*)::integer as cantidad_peajes,
    case
        when bool_or(selection_status = 'no_lower_category_available_review') then null
        else sum(valor_peaje)
    end as total_peajes,
    case
        when bool_or(selection_status = 'no_lower_category_available_review') then 'blocked_missing_effective_toll_tariff'
        else 'ok'
    end as estado,
    min(rule_id) as rule_id,
    min(fuente_sha256) as fuente_sha256,
    min(filas_fuente) as filas_fuente
from public.peajes_detalle_vigentes
group by
    mes_vigencia,
    mes_codigo,
    id_sice,
    nombre_ruta,
    codigo_dane_origen,
    codigo_dane_destino,
    ruta,
    configuracion,
    configuracion_sicetac;

revoke all on public.peajes_detalle_vigentes from anon, authenticated;
revoke all on public.peajes_resumen_vigentes from anon, authenticated;
grant select on public.peajes_detalle_vigentes to anon, authenticated, service_role;
grant select on public.peajes_resumen_vigentes to anon, authenticated, service_role;

comment on table public.peajes_tarifas_configuracion is
    'Tarifa efectiva por caseta y configuración calculada con sicetac-toll-relative-category-v2; conserva objetivo, categoría efectiva, fallback y manifiesto de fuente.';
comment on view public.peajes_detalle_vigentes is
    'Relación ruta–caseta deduplicada por corte, ruta, peaje y orden, con tarifas crudas y selección relativa v2 auditable.';
comment on view public.peajes_resumen_vigentes is
    'Total por ruta y configuración; queda NULL y bloqueado si una caseta no tiene fallback descendente.';

-- La tabla provisional provenía de inferir peajes desde totales H4 y no forma
-- parte del contrato v2. La fuente oficial ruta–caseta la reemplaza.
drop table if exists public.peajes_configuracion_especial;

notify pgrst, 'reload schema';
