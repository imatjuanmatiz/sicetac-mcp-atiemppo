# Evaluación de la articulación Core, API y MCP

Fecha del corte: 2026-09-12. La ruta `/Users/atiemppoia/Documents/GitHub/sicetac-mcp-atiemppo` es un enlace a este repositorio.

## Resultado local

Se ejecutó:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Resultado: `Ran 65 tests in 0.060s — OK`.

La suite cubre:

- regresiones del servicio SICETAC, peajes, parámetros, modo aumento y contenedor vacío;
- autenticación, expiración de claves y cuota en memoria;
- reserva persistente mediante RPC simulada y cierre de auditoría;
- catálogos y contrato HTTP del cliente comercial;
- recorrido MCP → cliente HTTP → FastAPI → `/v1/prequotes` → Core técnico → consulta SICETAC simulada;
- recorrido MCP → cliente HTTP → FastAPI → `/v1/quotes`;
- registro de vocabulario en estado `pending_review`;
- aislamiento de la ruta legacy `/consulta`, que no invoca el Core comercial;
- esquema MCP y anotaciones de operaciones que consumen cuota.

## Articulación implementada

El punto de entrada público para terceros es `commercial_api.py`, incluido por
`main.py` bajo `/v1`. El Core puro vive en `cotizador_core/`; sus reglas
publicadas se cargan desde `cotizador_rules.py`. `commercial_client.py` consume
la API y `commercial_mcp_server.py` expone las mismas capacidades por MCP
stdio. La documentación relacionada está en `docs/commercial-api.md`,
`docs/third-party-integration.md` y `docs/data-relationships.md`.

`POST /v1/prequotes` produce una decisión técnica versionada y una referencia
SICETAC. Mantiene bloqueada la emisión comercial (`emission_allowed: false`),
por lo que no convierte una recomendación técnica en precio o promesa de
servicio.

## Vencimiento y consumo

La migración `20260912161629_api_consumers_expiration_and_reservations.sql`
añade `activated_at`, `expires_at`, estados de reserva y las funciones RPC
para uso mensual y reserva atómica. El código rechaza consumidores vencidos
antes de calcular y usa la reserva persistente cuando
`SICETAC_USAGE_PERSISTENCE=true`.

La prueba local no aplica migraciones ni conecta Supabase, Render, Vercel ni un
cliente externo. Por tanto, acredita integración técnica en copia simulada,
no despliegue ni operación comercial.

## Aplicación remota en Supabase

El proyecto verificado fue `SICETAC-ATICA`
(`kpdlneddaqvkpwfbqejk`), en estado `ACTIVE_HEALTHY`. Se aplicaron las tres
migraciones en este orden:

1. `20260825120000_create_commercial_api_registry.sql` → versión remota `20260912164755`.
2. `20260912154137_cotizador_core_market_rules.sql` → versión remota `20260912164850`.
3. `20260912161629_api_consumers_expiration_and_reservations.sql` → versión remota `20260912164902`.

La primera migración creó `api_consumers` y `api_usage_events`. La segunda
creó `cotizador_rulesets` y `cotizador_term_observations` y dejó publicado el
ruleset `mercado_colombia_tecnico / 2026.09.12-market.1`. La tercera añadió
`activated_at`, `expires_at`, estados de reserva y las funciones
`api_usage_for_month` y `reserve_api_usage`.

Comprobaciones posteriores: las cuatro tablas existen con RLS activo; las dos
funciones existen; el ruleset publicado es legible; y no hay acceso público
concedido a estas tablas. El asesor de seguridad informa RLS sin políticas en
las cuatro tablas, que es el diseño intencional para mantenerlas cerradas a
`anon` y `authenticated`; el backend debe usar `service_role` server-side.

La herramienta de aplicación asignó versiones remotas con la hora de
ejecución, distintas de los prefijos de los archivos locales. Esta relación
queda registrada aquí para evitar aplicar de nuevo las mismas migraciones por
confundir el nombre local con el historial remoto.

## Aceptación pendiente

1. Aplicar las tres migraciones en Supabase en orden.
2. Registrar un consumidor de prueba con cuota, `activated_at` y `expires_at`.
3. Configurar Render con `api_key` y persistencia de uso.
4. Ejecutar la prueba externa de clave válida, vencida, revocada, cuota agotada y pre-cotización.
5. Conservar request, versión de ruleset, corte SICETAC y respuesta sin secretos.

No se creó ninguna clave de cliente ni se hizo despliegue de Render/Vercel.
Las migraciones de Supabase sí se aplicaron por autorización explícita de Juan.
