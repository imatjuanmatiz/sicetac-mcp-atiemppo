# Estructura del Modelo SICETAC (Versión Supabase)

Este documento describe la estructura del modelo y el flujo de cálculo para futuras integraciones o mantenimiento.

## 1) Flujo General

1. **Entrada del usuario**: origen, destino, vehículo (default `C3S3`), carrocería (default `GENERAL`), mes (default último disponible).
2. **Helper de municipios**: traduce el nombre del municipio a `codigo_dane`.
3. **Rutas (SICE)**: se buscan rutas por `CODIGO_DANE_ORIGEN` y `CODIGO_DANE_DESTINO`.
4. **Selección de ruta**:
   - Si hay una sola ruta: se usa esa.
   - Si hay varias rutas: se calculan variantes por `NOMBRE_SICE` e `ID_SICE`.
5. **Peajes**: se filtran por `ID_SICE` y `EJES_CONFIGURACION` del vehículo.
6. **Parámetros y costos fijos**: se filtran por `TIPO_VEHICULO`, `MES` y `TIPO_CARROCERIA`.
7. **Cálculo SICETAC**: se ejecuta el modelo y se retorna la respuesta (resumen o detalle).

## 2) Tablas Supabase (mínimas)

### `municipios`
Columnas clave:
- `codigo_dane`
- `nombre_oficial`
- `variacion_1`, `variacion_2`, `variacion_3`

### `rutas`
Columnas clave:
- `CODIGO_DANE_ORIGEN`
- `CODIGO_DANE_DESTINO`
- `ID_SICE`
- `NOMBRE_SICE`
- `KM_PLANO`, `KM_ONDULADO`, `KM_MONTANOSO`, `KM_URBANO`, `KM_DESPAVIMENTADO`

### `configuracion_vehicular`
Columnas clave:
- `TIPO_VEHICULO`
- `EJES_CONFIGURACION`

### `peajes_vigentes`
Columnas clave:
- `ID_SICE`
- `EJES_CONFIGURACION`
- `VALOR_PEAJE`

Esta vista mantiene el contrato liviano del modelo manual: un total consolidado de peajes por ruta y configuración.

### Capa normalizada de peajes

Para entregar detalle de peajes sin repetir totales por ruta, la base usa una capa normalizada:

- `peajes_inventario`: catálogo pequeño de peajes por mes, identificado por
  `ID_PEAJE`, con tarifas crudas `VALOR1` a `VALOR7`.
- `rutas_peajes`: secuencia ordenada de peajes por `ID_SICE`.
- `peajes_detalle_vigentes`: vista que vincula ruta + `ID_PEAJE`; puede traer
  las tarifas crudas o enriquecerse desde `peajes_inventario`.
- `peajes_resumen_vigentes`: vista para totalizar peajes por ruta/configuración.

La totalización vigente usa el vínculo de ruta para identificar los
`ID_PEAJE` y aplica la regla `sicetac-peajes-caseta-v2-relative-max` sobre las
tarifas crudas de cada caseta. Para cada peaje se calcula la categoría máxima
disponible. En una caseta cuyo máximo es V, las configuraciones apuntan a
II/III/III/IV/IV/V (`2`, `3`, `2S2`, `2S3`, `3S2`, `3S3`); si el máximo es VI o
VII, ese patrón se desplaza a VI o VII. No se reemplaza una categoría ausente
por otra: si el objetivo relativo no existe, o el máximo es únicamente I, esa
caseta vale cero y queda auditada. Las casetas duplicadas se cuentan una sola
vez. El resumen legado se conserva únicamente para comparar diferencias y
nunca reemplaza el total calculado desde el detalle.

Servicio rápido:

- `GET /peajes/detalle?id_sice=93`
- `GET /peajes/detalle?id_sice=93&configuracion=C3S3`

### `parametros_vigentes`
Columnas clave:
- `TIPO_VEHICULO`
- `MES` (alias de `mes_codigo`)
- Columnas de velocidades/consumos:
  - `vel_plano_cargado`, `consumo_plano_cargado`
  - `vel_ondulado_cargado`, `consumo_ondulado_cargado`
  - `vel_montana_cargado`, `consumo_montana_cargado`
  - `vel_urbano_cargado`, `consumo_urbano_cargado`
  - `vel_afirmado_cargado`, `consumo_afirmado_cargado`
  - `vel_plano_vacio`, `consumo_plano_vacio`
  - `vel_ondulado_vacio`, `consumo_ondulado_vacio`
  - `vel_montana_vacio`, `consumo_montana_vacio`
  - `vel_urbano_vacio`, `consumo_urbano_vacio`
  - `vel_afirmado_vacio`, `consumo_afirmado_vacio`
- `COSTOS VARIABLES`
- `VALOR COMBUSTIBLE GALÓN ACPM`

### `costos_fijos_vigentes`
Columnas clave:
- `TIPO_VEHICULO`
- `TIPO_CARROCERIA`
- `MES` (alias de `mes_codigo`)
- `COSTO FIJO`

### Series oficiales SICETAC de portacontenedores

Las tablas `sicetac_movilizacion_vigentes` y `sicetac_valorhora_vigentes`
incluyen dos columnas independientes:

- `contenedor_portacontenedores_cargado`: condición `CARGADO`, tipo de carga
  `Contenedor cargado`, unidad `PORTACONTENEDORES`.
- `contenedor_portacontenedores_vacio`: condición `CARGADO`, tipo de carga
  `Contenedor vacío`, unidad `PORTACONTENEDORES`.

No se debe confundir la segunda serie con
`sicetac_vacio_vigentes.portacontenedores_vacio`, que representa el vehículo
sin carga ni contenedor.

## 3) Resumen vs Detalle

### Resumen (por defecto)
`POST /consulta` devuelve **totales para 2, 4 y 8 horas logísticas**:
```json
{
  "origen": "Bogotá",
  "destino": "Barranquilla",
  "configuracion": "C3S3",
  "mes": 202602,
  "carroceria": "GENERAL",
  "modo_viaje": "CARGADO",
  "totales": { "H2": 123, "H4": 456, "H8": 789 }
}
```

### Viaje redondo de portacontenedores

Con `viaje_redondo: true`, la capa de resumen compone dos consultas oficiales:

1. Ida: `modo_viaje=CARGADO`, `tipo_contenedor=CARGADO`.
2. Regreso: ruta invertida, `modo_viaje=CARGADO`,
   `tipo_contenedor=VACIO`.

La respuesta conserva los objetos `ida` y `regreso` y suma los escenarios
`H2`, `H4` y `H8`. El valor en plaza no aplica al tramo de contenedor vacío.
No está habilitado con `resumen: false`, para evitar mezclar las series
oficiales con el cálculo detallado genérico.

Si existen variantes en alguno de los tramos, el servicio devuelve las
alternativas y requiere `rutasid_ida` y `rutasid_regreso` antes de calcular el
total redondo. Esto evita sumar rutas elegidas implícitamente.

Si hay múltiples rutas:
```json
{
  "origen": "Bogotá",
  "destino": "Medellín",
  "variantes": [
    { "NOMBRE_SICE": "RUTA A", "ID_SICE": 106, "totales": { "H2": 1, "H4": 2, "H8": 3 } },
    { "NOMBRE_SICE": "RUTA B", "ID_SICE": 11368, "totales": { "H2": 4, "H4": 5, "H8": 6 } }
  ]
}
```

### Detalle
Envía `"resumen": false` para obtener el cálculo completo.

## 4) Lógica de Peajes (Determinística)

- Se consulta el detalle por `ID_SICE` y configuración, conservando el grano
  caseta y las tarifas originales.
- Se selecciona una categoría efectiva por caseta y se suma una sola vez por
  `ID_PEAJE`; si falta la tarifa cruda, se busca en `peajes_inventario`.
- La respuesta expone `categoria_maxima_disponible`, `categoria_nominal`,
  `categoria_usada`, razón de selección y ausencia,
  tarifas originales y `auditoria.version_regla`.
- El índice `peajes_vigentes` queda como fallback de compatibilidad solamente
  cuando el detalle no está disponible; no puede sobreescribir un total de
  detalle ni se suma junto con él.

## 5) Archivos clave en el repo

- `sicetac_service.py`: lógica principal de cálculo y resumen.
- `modelo_sicetac.py`: modelo cargado.
- `modelo_sicetac_vacio.py`: modelo vacío.
- `main.py`: API FastAPI.
- `mcp_server.py`: herramienta MCP para agentes.
