-- BORRADOR: no ejecutado en producción.
-- Fuente: https://puertoantioquia.com.co/es/contact (Nueva Colonia, Turbo).
-- Ambos consumidores usan SICETACHelper y este catálogo; no se agrega un
-- alias paralelo al motor ni se modifica Puerto Colombia (Atlántico).
-- Requiere el helper que busca el nombre completo antes de separar departamento.
-- Tras publicar, refrescar el caché municipal del servicio por el mecanismo
-- administrativo existente, y verificar ambos consumidores.
do $$
declare
  current_row public.municipios%rowtype;
begin
  select * into strict current_row
    from public.municipios where codigo_dane=5837002 for update;
  if current_row.nombre_oficial is distinct from 'NUEVA COLONIA'
     or current_row.departamento is distinct from 'ANTIOQUIA'
     or current_row.variacion_1 is distinct from 'NUEVA COLONIA TURBO' then
    raise exception 'El registro de Nueva Colonia cambió; revisar antes de publicar';
  end if;
  if exists (
    select 1 from public.municipios
    where codigo_dane<>5837002
      and 'PUERTO ANTIOQUIA'=any(array[
        upper(trim(nombre_oficial)), upper(trim(variacion_1)),
        upper(trim(variacion_2)), upper(trim(variacion_3))
      ])
  ) then
    raise exception 'Puerto Antioquia ya está asociado a otro DANE';
  end if;
  if current_row.variacion_2='PUERTO ANTIOQUIA' then
    return;
  end if;
  if current_row.variacion_2 is not null then
    raise exception 'variacion_2 ya tiene contenido; no se sobrescribe';
  end if;
  update public.municipios
     set variacion_2='PUERTO ANTIOQUIA', updated_at=now()
   where codigo_dane=5837002;
end
$$;
