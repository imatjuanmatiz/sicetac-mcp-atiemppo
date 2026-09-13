# API comercial SICETAC v1

La API comercial es la superficie versionada para empresas, integraciones y
agentes. Los endpoints legacy (`/consulta`, `/peajes/detalle`, etc.) siguen
operando para WhatsApp y SICETAC-LAB.

## Endpoints

- `GET /v1/health`: estado público, no consume unidades.
- `POST /v1/quotes`: cotiza una ruta y consume una unidad.
- `POST /v1/prequotes`: aplica el Core técnico, consulta SICETAC y consume una unidad.
- `POST /v1/feedback/terms`: registra vocabulario para revisión; no cambia reglas ni consume una cotización.
- `GET /v1/catalog/body-types`: catálogo de carrocerías.
- `GET /v1/catalog/vehicles`: catálogo de vehículos.
- `GET /v1/catalog/municipalities`: municipios, departamentos, aliases y códigos normalizados como texto.
- `GET /v1/usage`: consumo del periodo del consumidor.

## Acceso

Los endpoints `/v1` fallan cerrados y exigen API key de forma predeterminada.
Para una demo aislada se puede declarar explícitamente
`SICETAC_API_ACCESS_MODE=public`; para integraciones reales conserva
`SICETAC_API_ACCESS_MODE=api_key`.

Las claves no se guardan en el repositorio. El backend acepta:

- `X-API-Key: <clave>`
- `Authorization: Bearer <clave>`

La configuración inicial puede usar `SICETAC_API_KEYS_JSON` con hashes SHA-256.

Un consumidor puede incluir `activated_at` y `expires_at` en formato ISO 8601.
La API rechaza la clave después de `expires_at`; la migración de operación
también valida el vencimiento dentro de la reserva persistente. Para una clave
de seis meses, calcula la fecha exacta desde la activación y conserva ambas
fechas en el registro privado. El generador actual crea la clave y el hash;
las fechas de vigencia se agregan al registro antes de guardarlo en Supabase o
en el gestor de secretos.

Genera una clave fuera del repositorio con:

```bash
python scripts/generate_api_key.py cliente-demo "Cliente demo" --plan sandbox --monthly-quota 1000
```

El programa muestra la clave una sola vez y un registro que puede copiarse a
un gestor de secretos o a `api_consumers`:

```json
[
  {
    "consumer_id": "cliente-demo",
    "name": "Cliente demo",
    "plan": "sandbox",
    "key_prefix": "sk_live_",
    "key_hash": "<sha256-de-la-clave>",
    "monthly_quota": 1000,
    "active": true
  }
]
```

Para operación comercial, la migración
`20260825120000_create_commercial_api_registry.sql` crea `api_consumers` y
`api_usage_events`. Con `SICETAC_API_CONSUMERS_DB=true`, el backend valida las
claves contra `api_consumers`; con `SICETAC_USAGE_PERSISTENCE=true`, registra
las unidades en `api_usage_events`. Ambas tablas quedan cerradas por RLS.

## Ejemplo

```bash
curl -X POST "$SICETAC_BASE_URL/v1/quotes" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $SICETAC_API_KEY" \
  -d '{
    "origen": "Bogotá",
    "destino": "Medellín",
    "vehiculo": "C3S3",
    "carroceria": "GENERAL",
    "resumen": true,
    "peajes": true
  }'
```

La respuesta tiene contrato estable:

```json
{
  "data": { "totales": { "H2": 0, "H4": 0, "H8": 0 } },
  "meta": {
    "api_version": "v1",
    "request_id": "uuid",
    "consumer_id": "cliente-demo",
    "plan": "sandbox",
    "units": 1,
    "monthly_usage": 1,
    "monthly_quota": 1000
  }
}
```

## Core técnico de pre-cotización

`POST /v1/prequotes` es la superficie para agentes y procesos pagos que
necesitan elegir una configuración antes de consultar SICETAC. Recibe origen,
destino, peso, unidad, servicio, contenedor, ejes y, si aplica, una
configuración solicitada. La API responde tres bloques:

- `technical_decision`: configuración recomendada, PBV, SICE, tara,
  advertencias y versión exacta del ruleset.
- `sicetac_reference`: resultado SICETAC con la configuración resultante.
- `commercial`: siempre indica `configured: false` y
  `emission_allowed: false`. Márgenes, disponibilidad, precio y aprobación
  pertenecen al proyecto consumidor.

El ruleset publicado se obtiene server-side desde Supabase bajo el alcance
`mercado_colombia_tecnico`. No se aceptan reglas ni un alcance elegido por el
cliente en la solicitud. Una respuesta conserva su versión y corte de fuente.

Para aportar vocabulario, un agente autenticado puede llamar
`POST /v1/feedback/terms` con `raw_expression` y `entity_type`. El registro
queda `pending_review`: una revisión humana, pruebas y una nueva versión
publicada son obligatorias antes de modificar equivalencias o reglas.

## Orden de puesta en producción

1. Aplicar `20260825120000_create_commercial_api_registry.sql`, seguido de
   `20260912154137_cotizador_core_market_rules.sql` y
   `20260912161629_api_consumers_expiration_and_reservations.sql`, en una
   ventana controlada de Supabase.
2. Crear un consumidor de prueba con una clave fuera del repositorio.
3. Configurar `api_key`, registro de consumidores y persistencia de uso en
   Render.
4. Configurar `SICETAC_COMMERCIAL_API_URL` y la clave server-side en Vercel.
5. Probar health, una cotización, pre-cotización, cuota, clave inválida,
   vencimiento y revocación.

No se debe publicar `SUPABASE_SERVICE_ROLE_KEY`, API keys ni secretos en
Vercel client-side, el frontend o documentación pública.

Las operaciones administrativas legacy `/refresh` y `/snapshot/generate` ahora
requieren `X-Admin-Token` y `SICETAC_ADMIN_TOKEN`. Si el token no está
configurado, permanecen cerradas con `503`.

## Integración del consumidor

El [paquete para terceros](third-party-integration.md) incluye cliente HTTP,
puente MCP por stdio, ejemplos y aceptación. El [mapa de relaciones](data-relationships.md)
explica cómo se conectan municipios, variantes, vehículos, carrocerías y periodos.

Consulta la sección de aceptación y operación de esa guía antes de ofrecer
garantías comerciales. La reserva persistente y la expiración están
implementadas en código y migración, pero requieren aplicación y verificación
en el entorno real. El catálogo de municipios comparte autenticación de
consumidor y no reserva unidades de cotización.
