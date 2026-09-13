# Piloto CCL: inicio rápido con OpenClaw

Este kit permite a CCL usar la pre-cotización técnica SICETAC de ATIEMPPO desde
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

El agente debe usar `consultar_instrucciones_vigentes` una vez por sesión.
Esta operación no consume cuota y devuelve la política, reglas técnicas y
versión actuales desde ATIEMPPO; así el ZIP no se convierte en una instrucción
congelada.

## Herramienta de cotización del piloto

Después de consultar las instrucciones vigentes, el agente usa
`precotizar_transporte`. Necesita origen, destino, peso y unidad.
Si el usuario no menciona contenedor, usa carga general/suelta sin preguntar
por tara. Si declara contenedor, solicita tamaño de 20 o 40 pies; el motor
aplica la tara y la configuración técnica.

Para un contenedor vacío transportado, el agente debe enviar:

```text
modo_viaje=CARGADO
tipo_contenedor=VACIO
```

No debe utilizar `VACIO` para un contenedor vacío: ese valor significa que el
vehículo viaja sin carga ni contenedor.

## Límites del piloto

- Cada pre-cotización admitida consume una unidad de la cuota CCL.
- `consultar_consumo` muestra consumo y saldo sin gastar cuota.
- El resultado es referencia técnica SICETAC; no es tarifa, oferta,
  disponibilidad, margen ni regla comercial de CCL.
- Ante `401`, `429` o `503`, el agente informa la situación y no reintenta
  automáticamente.

## Prueba mínima de recepción

1. Ejecutar `GET /v1/health`.
2. Confirmar `consultar_consumo`.
3. Probar una pre-cotización de carga general.
4. Probar un contenedor cargado y su retorno con contenedor vacío.
5. Conservar el `request_id`, sin guardar ni compartir la clave.

La lista de validación completa está en `ACCEPTANCE_CHECKLIST.md`.
