# Referencia técnica de endpoints

## Base URL

Define tu base URL según el entorno de despliegue.

Ejemplos:

- `http://localhost:8000`
- `https://sicetac-api-mcp.onrender.com`

## Modelo de entrada

El cuerpo base de consulta está definido en `ConsultaInput` dentro de `sicetac_service.py`.

Campos relevantes:

- `origen`
- `destino`
- `codigo_dane_origen`
- `codigo_dane_destino`
- `vehiculo`
- `mes`
- `carroceria`
- `tipo_contenedor`: solo para `carroceria = Portacontenedores`; admite `CARGADO` o `VACIO` y se consulta siempre con `modo_viaje = CARGADO`.
- `viaje_redondo`: calcula ida cargada y regreso con contenedor vacío; solo con `resumen = true`.
- `tipo_contenedor_regreso`: para `viaje_redondo`, debe ser `VACIO` (es el valor por defecto).
- `rutasid_ida`, `rutasid_regreso`: selección de variante SICETAC cuando un tramo tiene más de una ruta disponible.
- `modo_viaje`
- `resumen`
- `manual_mode`
- `valor_peaje_manual`
- `valor_peajes_manual`
- `horas_logisticas`
- `horas_logisticas_personalizadas`
- `tarifa_standby`
- `km_plano`
- `km_ondulado`
- `km_montañoso`
- `km_montanoso`
- `km_urbano`
- `km_despavimentado`
- `modo_tiempos_logisticos`
- `peajes`
- `incluir_peajes`
- `detalle_peajes`

Defaults importantes:

- `vehiculo`: `C3S3`
- `carroceria`: `GENERAL`
- `modo_viaje`: `CARGADO`
- `resumen`: `true`
- `tarifa_standby`: `150000`
- `peajes`, `incluir_peajes`, `detalle_peajes`: `false`

Para diferenciar la operación de contenedor vacío del viaje vacío del vehículo:

```json
{
  "modo_viaje": "CARGADO",
  "carroceria": "Portacontenedores",
  "tipo_contenedor": "VACIO"
}
```

Esta combinación usa la serie oficial `Contenedor vacío / PORTACONTENEDORES` y no devuelve `valor_plaza`.
Está disponible en la respuesta de resumen (`resumen: true`); la respuesta detallada se mantiene bloqueada para no mezclar esa serie con el cálculo genérico.

## Viaje redondo con contenedor vacío de regreso

Use `viaje_redondo: true`. La API calcula la ida con contenedor cargado e invierte automáticamente la ruta para el regreso con contenedor vacío; ambos tramos se consultan con `modo_viaje: CARGADO`.

```json
{
  "origen": "Bogotá",
  "destino": "Medellín",
  "vehiculo": "C3S3",
  "carroceria": "Portacontenedores",
  "modo_viaje": "CARGADO",
  "viaje_redondo": true,
  "tipo_contenedor": "CARGADO",
  "tipo_contenedor_regreso": "VACIO",
  "resumen": true
}
```

La respuesta conserva `ida` y `regreso`, y suma sus escenarios `H2`, `H4` y `H8` en `totales`. El regreso no incluye valor en plaza.
Si la ruta tiene variantes, la primera respuesta trae `requiere_seleccion_ruta: true` y las alternativas de cada tramo; reintenta indicando `rutasid_ida` y `rutasid_regreso`.

## `POST /consulta`

Endpoint principal.

### Uso

- resumen si `resumen = true`
- detalle si `resumen = false`

### Ejemplo

```json
{
  "origen": "Bogotá",
  "destino": "Medellín",
  "vehiculo": "C3S3",
  "mes": 202504,
  "carroceria": "GENERAL",
  "resumen": true,
  "peajes": true
}
```

### Respuesta típica

```json
{
  "origen": "Bogotá",
  "destino": "Medellín",
  "configuracion": "C3S3",
  "mes": 202504,
  "carroceria": "GENERAL",
  "modo_viaje": "CARGADO",
  "totales": {
    "H2": 123456,
    "H4": 234567,
    "H8": 345678
  },
  "resolved_route": {
    "codigo_dane_origen": "11001000",
    "codigo_dane_destino": "5001000",
    "origen_nombre": "BOGOTÁ, D.C.",
    "destino_nombre": "MEDELLIN",
    "route_code": "11001000-5001000"
  },
  "peajes_resumen": {
    "cantidad_peajes": 14,
    "total_peajes": 869600
  },
  "peajes_detalle": {
    "id_sice": 93,
    "configuracion": "C3S3",
    "detalle": []
  }
}
```

### Opción `peajes`

Si se envía `peajes: true`, `incluir_peajes: true` o `detalle_peajes: true`, la consulta adjunta el detalle normalizado de peajes para la ruta y configuración consultada.

- Si la respuesta trae una sola ruta, se agregan `peajes_resumen` y `peajes_detalle` en la raíz.
- Si la respuesta trae `variantes`, cada variante con `ID_SICE` recibe sus propios `peajes_resumen` y `peajes_detalle`.
- `peajes_resumen.total_peajes` es el total de peajes para la configuración solicitada.
- `peajes_detalle.detalle[]` contiene la lista ordenada de peajes con categoría usada y valor.

## `POST /consulta_resumen`

Versión explícita de resumen.

### Uso recomendado

- clientes que solo necesitan `H2`, `H4`, `H8`
- integraciones donde quieres un contrato más acotado

## `POST /consulta_texto`

Devuelve un texto corto listo para canales conversacionales.

### Respuesta ejemplo

```json
{
  "texto": "Bogotá->Barranquilla C3S3 H2 $7.398.537, H4 $7.571.997, H8 $7.918.917, peajes $869.600 (14 peajes)"
}
```

## `GET /peajes/detalle`

Devuelve el detalle de peajes de una ruta SICE desde la capa normalizada vigente.

Parámetros query:

- `id_sice`: ID de ruta SICE.
- `configuracion`: opcional. Acepta `2`, `3`, `C2S2`, `C2S3`, `C3S2`, `C3S3`. También normaliza `2S2`, `2S3`, `3S2`, `3S3`.

Ejemplo:

```bash
curl "http://localhost:8000/peajes/detalle?id_sice=93&configuracion=C3S3"
```

Respuesta resumida:

```json
{
  "id_sice": 93,
  "mes": 202607,
  "nombre_ruta": "BOGOTÁ _ BARRANQUILLA",
  "configuracion": "C3S3",
  "resumen": {
    "C3S3": {
      "cantidad_peajes": 14,
      "total_peajes": 869600
    }
  },
  "detalle": [
    {
      "orden": 1,
      "id_peaje": "50",
      "nombre_peaje": "SIBERIA",
      "categoria_maxima_disponible": "VII",
      "valores": {
        "C3S3": 62700
      },
      "categorias": {
        "C3S3": {
          "categoria_usada": "VII",
          "configuracion_sicetac": "3S3"
        }
      }
    }
  ]
}
```

## `GET /health`

Health check simple.

### Respuesta

```json
{
  "status": "ok"
}
```

## `POST /refresh`

Fuerza recarga de cache.

### Respuesta

```json
{
  "status": "ok",
  "refreshed": true
}
```

## `POST /snapshot/generate`

Genera un snapshot consolidado y lo publica en el bucket `snapshots`.

### Respuesta esperada

```json
{
  "ok": true,
  "file": "sicetac_snapshot_202504_all.xlsx",
  "url": "https://..."
}
```

## Códigos de error

### `404`

Usualmente asociado a:

- origen o destino no encontrado
- ruta no disponible para la combinación consultada

### `500`

Usualmente asociado a:

- tablas vacías
- problema de conexión a Supabase
- error inesperado en el cálculo o exportación

## Variables de entorno relevantes

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_KEY`
- `CORS_ORIGINS`
- `SICETAC_CACHE_TTL_SECONDS`
- `SICETAC_TABLE_MUNICIPIOS`
- `SICETAC_TABLE_VEHICULOS`
- `SICETAC_TABLE_PARAMETROS`
- `SICETAC_TABLE_COSTOS_FIJOS`
- `SICETAC_TABLE_PEAJES`
- `SICETAC_TABLE_RUTAS`
- `SICETAC_TABLE_SICETAC_VACIO`

`modo_viaje=VACIO` usa la capa `sicetac_vacio_vigentes` y responde con
`metodo=lookup_vacio_oficial` cuando existe una coincidencia oficial. La
carrocería se conserva; no se normaliza a `GENERAL`.

## MCP

Servidor:

```bash
python mcp_server.py
```

Tool disponible:

- `calcular_sicetac_tool`

Parámetros principales del tool:

- `origen`
- `destino`
- `vehiculo`
- `mes`
- `carroceria`
- `modo_viaje`
- `resumen`

Si no se envía `mes`, el tool usa el más reciente disponible en `parametros_vigentes`.
