# Contrato de búsqueda SICETAC

El API MCP y SICETAC al Instante son conexiones separadas con responsabilidades
complementarias. El agente utiliza la referencia de SICETAC al Instante como
fuente del importe publicado; consulta el API MCP/Core cuando necesita una
selección por peso, capacidad u otro análisis adicional.

Los agentes presentan valores calculados para análisis y procesos. No generan
ofertas ni textos de cotización.

## Flujo normal

1. Lee `GET /v1/agent-profile` mediante `consultar_instrucciones_vigentes` una
   vez antes de la primera operación que requiera el Core. No es un paso previo
   a una referencia directa; la lectura no consume cuota.
2. Para cada solicitud de ruta, llama directamente
   `consultar_referencia` por SICETAC al Instante con origen, destino y los
   datos que ya dio el usuario. Esa llamada entrega el importe de referencia.
3. Deja que el conector aplique sus defaults autorizados cuando falten campos:
   C3S3, CARGADO, carga general, General-Estacas, H4 y último período.
4. No hagas llamadas de precotización, catálogos o lista de variantes como
   preámbulo de una búsqueda normal. Si la referencia devuelve una ambigüedad
   no resuelta por la variante directa, pregunta solo por la decisión pendiente.

La conexión SICETAC al Instante debe estar disponible en el cliente que ejecuta
el agente. Si falta, informa que se debe habilitar; no cambies silenciosamente
a otra fuente. Su autenticación y cuota son independientes de la API comercial.

## Reconocimiento de municipios y vehículos

Envía el texto como lo escribió el usuario. El ruleset del motor resuelve
aliases, nombres de municipios, tildes y espacios. No copies ni mantengas una
tabla paralela de equivalencias.

Consulta `buscar_municipios` únicamente si hay homónimos o la búsqueda pide una
aclaración. Usa departamento o código DANE para distinguirlos. Consulta
`listar_configuraciones` o `listar_carrocerias` si el usuario solicita un
catálogo, no para cada búsqueda.

Usa `precotizar_transporte` en el API MCP cuando el usuario solicita escoger
configuración por peso, validar capacidad/tara o hacer un cálculo adicional
con el Core. No la uses como paso previo rutinario. Si el Core elige la
configuración, pasa esa configuración a SICETAC al Instante y conserva su
referencia como importe publicado.

Para contenedor sin tamaño, pregunta solo 20 o 40 pies. El ruleset publicado
define aliases, tara y capacidad. No muestres la tara ni afirmes PBV legal sin
la tara real del vehículo. Contenedor vacío transportado:
`modo_viaje=CARGADO`, `tipo_contenedor=VACIO`. Vehículo sin carga ni contenedor:
`modo_viaje=VACIO`. No sumes ida y retorno sin que lo soliciten.

## Variantes, comparaciones y detalle

- Una búsqueda normal no lista rutas. La llamada de referencia selecciona la
  variante directa cuando existe.
- Si el usuario solicita variantes o una comparación, llama `consultar_rutas`
  una vez y consulta una referencia de SICETAC al Instante por alternativa
  solicitada. Conserva vehículo, servicio, período y horas.
- Si el usuario pide componentes, combustible, peajes o detalle de ruta, llama
  `calcular_desglose` con el mismo contexto de la referencia.
- No llames `consultar_rutas` ni `calcular_desglose` en solicitudes normales.
  No repitas una consulta exitosa ni reintentes automáticamente un timeout.

Las llamadas adicionales a `precotizar_transporte`, `consultar_rutas` y
`calcular_desglose` consumen cuota de la conexión correspondiente según su
propio contrato. Una comparación puede usar una referencia por alternativa.

## Respuesta normal

Entrega directamente los datos devueltos por SICETAC al Instante: nombre de
ruta, configuración, período, horas y referencia. Presenta valor en plaza o
capacidad solo cuando la respuesta consultada los incluya. Si están ausentes,
indícalo; no inventes ni uses cero como sustituto. Conserva `request_id` para
soporte.

No muestres RUTASID, nombres internos o cálculos de tara salvo que sean
necesarios para la solicitud. No inventes margen, seguro, disponibilidad,
fecha de entrega o reglas comerciales.

## Acceso para integraciones API

El API comercial se configura por cliente, usando una clave individual en el
almacén seguro:

```text
SICETAC_API_BASE_URL=https://<api-entregada-por-atiemppo>
SICETAC_API_KEY=<clave-individual-del-consumidor>
```

Nunca escribas claves en prompts, repositorios, chats o capturas. La clave API
no autentica por sí sola SICETAC al Instante; el cliente debe habilitar ambas
conexiones de forma independiente.

Consulta [PROMPT-AGENTE-BUSQUEDA.md](PROMPT-AGENTE-BUSQUEDA.md) para el prompt
canónico y [README.md](README.md) para la configuración del paquete.
