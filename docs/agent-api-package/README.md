# Paquete: agente de búsqueda → motor SICETAC

Un proceso, muchos canales. Grok Bot, OpenClaw o el agente de otro cliente
llaman el mismo API. **Al crear otro agente de búsqueda solo cambia la clave.**

Hay dos oficios. Este paquete es el de **búsqueda** (entender el pedido suelto
y devolver ruta + H4 + valor en plaza). El documento comercial de cotizados es
**otro** agente: [OFICIO-COTIZACION-DOCUMENTO.md](OFICIO-COTIZACION-DOCUMENTO.md).

No contiene precios comerciales, márgenes, disponibilidad de flota, secretos
de ATIEMPPO ni acceso a Supabase/OpenClaw.

## Cómo clonar un agente de búsqueda

1. Copiar [PROMPT-AGENTE-BUSQUEDA.md](PROMPT-AGENTE-BUSQUEDA.md). Rellenar
   `{{CLIENTE}}` y `{{LINEA_REPORTE}}`. No editar herramienta ni ficha.
2. Guardar una **clave nueva** en el almacén secreto del bot. Nunca en el prompt.
3. Canon: [CONTRATO-BUSQUEDA-SICETAC.md](CONTRATO-BUSQUEDA-SICETAC.md).
4. Probar con [ACCEPTANCE_CHECKLIST.md](ACCEPTANCE_CHECKLIST.md).

Por un canal seguro ATIEMPPO entrega únicamente:

```text
SICETAC_API_BASE_URL=https://<entorno-entregado-por-atiemppo>
SICETAC_API_KEY=<clave-individual-de-ese-consumidor>
```

Cada bot recibe su propio `consumer_id`, cuota y vencimiento. No reutilizar la
clave de ATICA ni la de otro cliente.

## Operaciones del piloto

Al inicio de cada sesión el agente consulta el perfil autenticado vigente:

`GET {SICETAC_API_BASE_URL}/v1/agent-profile`


No consume cuota. Devuelve la versión de contrato, la política del agente, el
ruleset publicado y las instrucciones que deben prevalecer sobre esta copia
del paquete. Así las mejoras compatibles del motor se reflejan sin reemplazar
el ZIP ni el prompt del cliente.

La única operación que consume cuota en el flujo de pre-cotización es:

`POST {SICETAC_API_BASE_URL}/v1/prequotes`

Los agentes envían `view=search`. La ficha de búsqueda es `data.search`:
ruta (`NOMBRE_SICE`), configuración, SICETAC de la hora acordada, valor en
plaza cuando exista y capacidad máxima de mercancía cuando haya regla. La
capacidad indica si el peso declarado cabe y si la regla es provisional; el
motor no valida PBV legal porque no conoce la tara del vehículo.

Header:

```http
Content-Type: application/json
X-API-Key: <SICETAC_API_KEY>
```

Solicita origen y destino. En carga general, si no hay vehículo/configuración,
solicita peso y unidad. Para un contenedor declarado, solicita 20 o 40 pies si
falta el tamaño; el motor aplica el default por tamaño aunque no den el peso y
marca capacidad como no validada. Si informan peso, envía unidad y marca
`weight_includes_tare` cuando ya incluya la tara del contenedor. El servicio
`carga_general` es el default (incluye “carga suelta”). La operación consume una
unidad de cuota una vez admitida para cálculo; no la reintentes ante timeout.

Para contenedores, solicita 20 o 40 pies solo si el usuario no lo indicó y usa
carrocería `Portacontenedores`. El motor inicia 20′ en C2S2 Patineta y 40′ en
C2S3 Patineta, y escala por el máximo SICETAC publicado: para 20′ C2S2 → C2S3
→ C3S2 → C3S3; para 40′ C2S3 → C3S2 → C3S3. La capacidad de mercancía ya
descuenta la tara del contenedor del tonelaje de configuración. La selección
y los topes son técnicos y provisionales; no representan PBV legal.

Una fuerza comercial puede usar la ficha como base de precotización: referencia
SICETAC + contraste de valor en plaza + capacidad. No es el precio que se ofrece
al cliente. Margen, disponibilidad, condiciones, vigencia y aprobación se
configuran en el proyecto consumidor, nunca se inventan en el motor.

Para el retorno con
contenedor vacío, se mantiene `modo_viaje: "CARGADO"` y se envía
`tipo_contenedor: "VACIO"`; `modo_viaje: "VACIO"` corresponde a un vehículo
sin carga ni contenedor. Para una ida cargada y un vacío que no regresa al
origen, envía `viaje_redondo: true`, `tipo_contenedor: "CARGADO"`,
`tipo_contenedor_regreso: "VACIO"`, `origen_regreso` y `destino_regreso` en la
misma solicitud. Si esos dos últimos campos se omiten, el motor invierte la
ruta automáticamente.

Ejemplo de solicitud: [examples/prequote-container-40.json](examples/prequote-container-40.json).
Ejemplo de respuesta saneada: [examples/prequote-response-sanitized.json](examples/prequote-response-sanitized.json).

## Qué presenta el agente de búsqueda

Con `view=search` el cuerpo útil es `data.search`:

| Campo | Qué es |
| --- | --- |
| `ruta` | Nombre SICETAC (`NOMBRE_SICE`) |
| `configuracion` | La que usó el motor |
| `sicetac_h4` + `sicetac_corte` | Referencia principal |
| `valor_plaza` + `valor_plaza_corte` | Último valor en plaza; null → “sin valor en plaza” |
| `capacidad.max_mercancia_t` | Tope neto de mercancía publicado para esa configuración |
| `capacidad.max_configuracion_sicetac_t` | Toneladas nominales de la configuración cuando la regla las publica |
| `capacidad.cumple_maximo_sice` | Si el peso informado cabe en el tope técnico; null si no se informó peso |
| `capacidad.regla_provisional` | Indica que el tope requiere validación operativa |

`view=detail` conserva el detalle de modelo y análisis de mercado. El agente de
búsqueda no necesita ese detalle para responder una consulta normal. Instant y
el agente de documento no sustituyen esta ficha.

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

- [CONTRATO-BUSQUEDA-SICETAC.md](CONTRATO-BUSQUEDA-SICETAC.md): proceso único.
- [PROMPT-AGENTE-BUSQUEDA.md](PROMPT-AGENTE-BUSQUEDA.md): prompt para clonar.
- [GROK_BOT_ATICA.md](GROK_BOT_ATICA.md): instancia ATICA de ese prompt.
- [OFICIO-COTIZACION-DOCUMENTO.md](OFICIO-COTIZACION-DOCUMENTO.md): el otro agente.
- [GROK_AGENT_INSTRUCTIONS.md](GROK_AGENT_INSTRUCTIONS.md): notas extendidas.
- [CCL_OPENCLAW_QUICKSTART.md](CCL_OPENCLAW_QUICKSTART.md): OpenClaw externo.
- [CCL_ENV.example](CCL_ENV.example): nombres de secretos, sin valores.
- [tool-schema.json](tool-schema.json): esquema de la herramienta HTTP.
- [ACCEPTANCE_CHECKLIST.md](ACCEPTANCE_CHECKLIST.md): prueba de recepción.

Para el contrato más amplio de clientes REST/MCP consulta
[`../third-party-integration.md`](../third-party-integration.md). Este paquete
deliberadamente no incluye `/consulta`, endpoints administrativos ni rutas
legacy.
