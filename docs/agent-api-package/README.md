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

## Operaciones del piloto

Al inicio de cada sesión el agente consulta el perfil autenticado vigente:

`GET {SICETAC_API_BASE_URL}/v1/agent-profile`


No consume cuota. Devuelve la versión de contrato, la política del agente, el
ruleset publicado y las instrucciones que deben prevalecer sobre esta copia
del paquete. Así las mejoras compatibles del motor se reflejan sin reemplazar
el ZIP ni el prompt del cliente.

La única operación que consume cuota en el flujo de pre-cotización es:

`POST {SICETAC_API_BASE_URL}/v1/prequotes`

Header:

```http
Content-Type: application/json
X-API-Key: <SICETAC_API_KEY>
```

Solicita: origen, destino, peso y unidad. Si no se menciona un contenedor, el
servicio es `carga_general` por defecto (incluye “carga suelta”) y no se debe
preguntar por tara. Solo para un contenedor declarado expresamente requiere 20
o 40 pies; el motor incorpora la tara técnica publicada. La operación consume
una unidad de la cuota una vez admitida para cálculo; no se debe reintentar
automáticamente ante timeout.

El motor inicia contenedores de 20 y 40 pies en Portacontenedor C2S2 como
regla técnica operativa. Un equipo menor solo se consulta cuando el usuario lo
solicita expresamente mediante `requested_configuration`. Para el retorno con
contenedor vacío, se mantiene `modo_viaje: "CARGADO"` y se envía
`tipo_contenedor: "VACIO"`; `modo_viaje: "VACIO"` corresponde a un vehículo
sin carga ni contenedor. Para una ida cargada y un vacío que no regresa al
origen, envía `viaje_redondo: true`, `tipo_contenedor: "CARGADO"`,
`tipo_contenedor_regreso: "VACIO"`, `origen_regreso` y `destino_regreso` en la
misma solicitud. Si esos dos últimos campos se omiten, el motor invierte la
ruta automáticamente.

Ejemplo de solicitud: [examples/prequote-container-40.json](examples/prequote-container-40.json).
Ejemplo de respuesta saneada: [examples/prequote-response-sanitized.json](examples/prequote-response-sanitized.json).

## Qué devuelve el motor

La respuesta tiene tres bloques:

| Bloque | Uso permitido |
| --- | --- |
| `data.technical_decision` | Recomendación técnica, capacidad SICE, tara, estado verificable del PBV, advertencias y versión del ruleset. |
| `data.sicetac_reference` | Referencia SICETAC, rutas/variantes, peajes y escenarios H2/H4/H8 cuando estén disponibles. |
| `data.market_analysis` | Valor de mercado observado/proxy RNDC por ruta y configuración, con corte y brecha analítica frente a H4. No es tarifa comercial. |
| `data.commercial` | Confirma que no existe configuración ni emisión comercial. |

El integrador debe reportar el valor principal como `H4, 4 horas logísticas`.
Si presenta H2 u H8, debe marcarlos como escenarios alternativos, nunca
sumarlos ni presentarlos como tarifa. Rutas alternativas tampoco se suman. Si
hay `market_analysis`, reporta siempre su corte: su valor observado puede ser
de un mes distinto al SICETAC y únicamente sirve como contraste analítico.

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
`GET /v1/agent-profile`, autenticado, entrega las instrucciones vigentes y no
consume cuota.

## Archivos del paquete

- [GROK_AGENT_INSTRUCTIONS.md](GROK_AGENT_INSTRUCTIONS.md): instrucciones que
  se pueden copiar al bot; el agente primero consulta el perfil vigente.
- [CCL_OPENCLAW_QUICKSTART.md](CCL_OPENCLAW_QUICKSTART.md): instalación y
  prueba mínima para un OpenClaw externo.
- [CCL_ENV.example](CCL_ENV.example): nombres de secretos, sin incluir valores.
- [tool-schema.json](tool-schema.json): esquema JSON de una herramienta HTTP
  provider-neutral.
- [ACCEPTANCE_CHECKLIST.md](ACCEPTANCE_CHECKLIST.md): prueba de recepción y
  evidencia para el piloto.

Para el contrato más amplio de clientes REST/MCP consulta
[`../third-party-integration.md`](../third-party-integration.md). Este paquete
deliberadamente no incluye `/consulta`, endpoints administrativos ni rutas
legacy.
