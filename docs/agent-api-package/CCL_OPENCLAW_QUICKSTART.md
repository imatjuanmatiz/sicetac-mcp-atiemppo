# Piloto CCL: inicio rápido con OpenClaw

Este kit permite a CCL consultar los valores calculados por SICETAC de ATIEMPPO desde
su propio OpenClaw. No entrega acceso a Supabase, OpenClaw de ATIEMPPO, reglas
comerciales ni al endpoint público legado.

## Lo único que CCL recibe por separado

ATIEMPPO enviará mediante canal seguro dos valores que **no** están dentro del
ZIP:

```text
SICETAC_BASE_URL=https://<api-entregada-por-atiemppo>
SICETAC_API_KEY=<clave-individual-ccl>
```

La clave identifica a CCL, tiene una cuota y una fecha de vencimiento. Puede
revocarse o reemplazarse sin cambiar sus instrucciones ni reinstalar el kit.

## Instalación

1. Descomprimir este ZIP en una carpeta privada del servidor donde corre
   OpenClaw.
2. Crear el entorno Python e instalar el único requisito:

   ```bash
   python3 -m venv .venv
   .venv/bin/python -m pip install -r requirements-client.txt
   ```

3. Guardar `SICETAC_BASE_URL` y `SICETAC_API_KEY` como secretos del proceso
   OpenClaw. Nunca escribir la clave en la instrucción del agente, repositorio
   o canal de chat.
4. Registrar el puente MCP local usando el mecanismo habitual de su OpenClaw:

   ```json
   {
     "command": "/ruta/del/kit/.venv/bin/python",
     "args": ["/ruta/del/kit/commercial_mcp_server.py"]
   }
   ```

5. Copiar el contenido de `GROK_AGENT_INSTRUCTIONS.md` como instrucciones del
   agente. Aunque el nombre del archivo menciona Grok, el contenido es
   independiente del modelo.

6. Habilitar también la conexión MCP independiente de SICETAC al Instante en
   el cliente OpenClaw, con sus permisos de usuario. La clave del API comercial
   no habilita esa conexión. La herramienta `consultar_referencia` de Instant
   es obligatoria para cada importe de ruta; si no está conectada, el agente
   debe reportar que falta esa capacidad y no cambiar de fuente en silencio.

El agente usa `consultar_instrucciones_vigentes` una vez antes de su primera
llamada al Core. No es un paso previo a la consulta directa de SICETAC al
Instante.

## Consulta de una ruta

Para la búsqueda normal, llama directamente `consultar_referencia` de SICETAC
al Instante con origen y destino. No enumera municipios ni variantes antes de
esa llamada; usa los defaults autorizados de la conexión para los datos que el
usuario omitió.

El agente usa `precotizar_transporte` solo cuando el usuario pide selección por
peso, validación de capacidad o un análisis adicional que requiera el Core. Si
el Core elige vehículo, la referencia publicada se consulta después en SICETAC
al Instante.

Las variantes de ruta se consultan solo cuando el usuario pide comparar
recorridos. Los componentes y el consumo se consultan solo cuando pide detalle.
No se hace esa segunda consulta en una búsqueda ordinaria.

Si declara contenedor y no indicó el tamaño, se pregunta 20 o 40 pies. El
ruleset publicado resuelve la tara y configuración; no se le solicita la tara.

Para un contenedor vacío transportado, el agente debe enviar:

```text
modo_viaje=CARGADO
tipo_contenedor=VACIO
```

No debe utilizar `VACIO` para un contenedor vacío: ese valor significa que el
vehículo viaja sin carga ni contenedor.

## Límites del piloto

- Cada consulta admitida consume una unidad de la cuota CCL.
- `consultar_consumo` muestra consumo y saldo sin gastar cuota.
- El MCP entrega valores calculados para análisis y procesos; no redacta textos
  de cotización.
- Ante `401`, `429` o `503`, el agente informa la situación y no reintenta
  automáticamente.

## Prueba mínima de recepción

1. Ejecutar `GET /v1/health`.
2. Confirmar `consultar_consumo`.
3. Probar un cálculo de carga general.
4. Probar un contenedor cargado y su retorno con contenedor vacío.
5. Conservar el `request_id`, sin guardar ni compartir la clave.

La lista de validación completa está en `ACCEPTANCE_CHECKLIST.md`.
