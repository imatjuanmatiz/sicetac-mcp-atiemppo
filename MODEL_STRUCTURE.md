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

## 4) Lógica de Peajes (Optimizada)

- Se construye un índice en memoria por `(ID_SICE, EJES_CONFIGURACION)`.
- Se obtiene el primer valor de peaje disponible para esa combinación.
- Se pasa al modelo como `valor_peaje_override` (evita filtrar la tabla en cada request).

## 5) Archivos clave en el repo

- `sicetac_service.py`: lógica principal de cálculo y resumen.
- `modelo_sicetac.py`: modelo cargado.
- `modelo_sicetac_vacio.py`: modelo vacío.
- `main.py`: API FastAPI.
- `mcp_server.py`: herramienta MCP para agentes.

