# Prueba de aceptación: bot externo

No active un bot de producción con una clave compartida. ATIEMPPO crea un
consumidor piloto dedicado, con cuota y vencimiento; la clave se entrega por
un canal seguro y se guarda como secreto del bot.

## Antes de probar

- [ ] URL HTTPS de entorno configurada sin `/v1` duplicado.
- [ ] Clave piloto guardada como secreto; no aparece en prompt, repositorio ni log.
- [ ] Bot limitado a `POST /v1/prequotes` y `GET /v1/usage`.
- [ ] Sin acceso a `/consulta`, Supabase, panel administrativo u OpenClaw ATIEMPPO.

## Casos obligatorios

1. `GET /v1/health` devuelve `200`.
2. Una clave inválida recibe `401` y no incrementa el uso.
3. Solicitud completa de contenedor: Bogotá → Buenaventura, 15 t, 40 pies.
4. El bot reporta por defecto `H4, 4 horas logísticas` junto al valor principal.
5. El bot separa rutas y escenarios alternativos; no suma sus valores.
6. Datos incompletos: el bot pide solo el campo faltante y no llama el API.
   Si ya hay vehículo/configuración declarada, la falta de peso neto no es
   un dato faltante: debe cotizar.
7. `GET /v1/usage` confirma que la prueba admitida consumió una unidad.
8. Error `429` o clave revocada: el bot informa límite/acceso, sin reintento.

## Evidencia que conserva ATIEMPPO

- fecha/hora de prueba;
- versión del paquete;
- `request_id` y `consumer_id` sin exponer la clave;
- petición saneada, respuesta saneada y resultado esperado/obtenido;
- confirmación de cuota y vencimiento del consumidor piloto.

Al aprobar la prueba se mantiene el mismo contrato y se cambia solo la URL o
la clave del entorno siguiente. Las reglas comerciales permanecen fuera de
este paquete y pertenecen al integrador/cliente.
