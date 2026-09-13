# Paquete de producción: agente externo → Motor técnico SICETAC

Este paquete permite que un agente externo —por ejemplo un bot basado en Grok—
use el motor técnico de pre-cotización de ATIEMPPO. El agente conversa y
estructura los datos; el motor decide vehículo, PBV, SICE, tara, ruta y
referencia SICETAC.

No contiene precios comerciales, márgenes, disponibilidad de flota, secretos
de ATIEMPPO ni acceso a Supabase/OpenClaw.

## Lo que recibe el integrador

Por un canal seguro ATIEMPPO entrega únicamente:

```text
SICETAC_API_BASE_URL=https://<entorno-entregado-por-atiemppo>
SICETAC_API_KEY=<clave-piloto-individual>
```

La clave se guarda como secreto del bot o de su backend. Nunca se pone en el
prompt, repositorio, frontend, captura de pantalla o mensaje de chat. Cada bot
recibe su propio `consumer_id`, cuota y fecha de vencimiento; no reutilice la
clave del piloto ATICA ni la de otro cliente.

## Única operación necesaria en el piloto

`POST {SICETAC_API_BASE_URL}/v1/prequotes`

Header:

```http
Content-Type: application/json
X-API-Key: <SICETAC_API_KEY>
```

Solicita: origen, destino, peso, unidad y tipo de servicio. Para un contenedor
también requiere 20 o 40 pies. La operación consume una unidad de la cuota una
vez admitida para cálculo; no se debe reintentar automáticamente ante timeout.

Ejemplo de solicitud: [examples/prequote-container-40.json](examples/prequote-container-40.json).
Ejemplo de respuesta saneada: [examples/prequote-response-sanitized.json](examples/prequote-response-sanitized.json).

## Qué devuelve el motor

La respuesta tiene tres bloques:

| Bloque | Uso permitido |
| --- | --- |
| `data.technical_decision` | Recomendación técnica, PBV, capacidad SICE, tara, advertencias y versión del ruleset. |
| `data.sicetac_reference` | Referencia SICETAC, rutas/variantes, peajes y escenarios H2/H4/H8 cuando estén disponibles. |
| `data.commercial` | Confirma que no existe configuración ni emisión comercial. |

El integrador debe reportar el valor principal como `H4, 4 horas logísticas`.
Si presenta H2 u H8, debe marcarlos como escenarios alternativos, nunca
sumarlos ni presentarlos como tarifa. Rutas alternativas tampoco se suman.

## Errores y comportamiento del agente

| HTTP | Significado | Conducta del bot |
| --- | --- | --- |
| `200` | Pre-cotización técnica disponible | Explicar resultado y limitaciones. |
| `401` | Clave ausente, inválida, inactiva o vencida | Detenerse; pedir al administrador revisar acceso. |
| `422` | Faltan o no validan datos | Pedir solo el dato faltante/corregido. |
| `429` | Cuota agotada | Informar límite; no reintentar. |
| `503` | Ruleset o servicio no disponible | Informar indisponibilidad temporal; no inventar cálculo. |

`GET {SICETAC_API_BASE_URL}/v1/health` prueba disponibilidad básica y no
consume cuota. `GET /v1/usage`, autenticado, permite leer consumo y saldo.

## Archivos del paquete

- [GROK_AGENT_INSTRUCTIONS.md](GROK_AGENT_INSTRUCTIONS.md): instrucciones que
  se pueden copiar al bot.
- [tool-schema.json](tool-schema.json): esquema JSON de una herramienta HTTP
  provider-neutral.
- [ACCEPTANCE_CHECKLIST.md](ACCEPTANCE_CHECKLIST.md): prueba de recepción y
  evidencia para el piloto.

Para el contrato más amplio de clientes REST/MCP consulta
[`../third-party-integration.md`](../third-party-integration.md). Este paquete
deliberadamente no incluye `/consulta`, endpoints administrativos ni rutas
legacy.
