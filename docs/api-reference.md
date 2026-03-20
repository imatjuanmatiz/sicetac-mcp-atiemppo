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

Defaults importantes:

- `vehiculo`: `C3S3`
- `carroceria`: `GENERAL`
- `modo_viaje`: `CARGADO`
- `resumen`: `true`
- `tarifa_standby`: `150000`

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
  "resumen": true
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
  }
}
```

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
  "texto": "Bogotá->Barranquilla C3S3 H2 $7.077.856, H4 $7.229.067, H8 $7.531.476"
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
