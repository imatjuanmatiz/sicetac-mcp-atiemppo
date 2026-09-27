# Contrato propuesto para AT-COT-001 y Bruno-AT

**Referencia de diseño.** La versión operativa consolidada de este contrato
está en [flujo-agentes.md](flujo-agentes.md) y fue aplicada a los tres agentes
con autorización posterior de Juan. Las validaciones deterministas del plugin
permanecen en borrador. Véase [el manifiesto](manifest-agentes.json).

## Responsabilidad

El orquestador conserva el requerimiento, su turno y su respuesta. El
especialista común es `agent:atica-cotizador-api:main`. Solo ese especialista
usa `atica_precotizar_api`. La resolución de lugares y el cálculo pertenecen
a las fuentes centrales existentes; no se crea un catálogo dentro del prompt.

SICETAC Instant permanece independiente y fuera de este cambio.

## Turnos y trazabilidad

1. Registrar el mensaje y conservar el texto original. El runtime determina
   el tenant; el modelo no cambia la identidad del grupo.
2. Una consulta sencilla es un job. Un escenario de ida y devolución es un
   job completo. Dos escenarios de vehículo/peso son dos jobs completos;
   ninguno pierde su retorno ni se mezcla con otro mensaje.
3. Reclamar mediante `bandeja_next`. Si `already_in_flight=true`, no enviar
   otra cotización: esperar o recuperar el resultado del job ya activo.
4. Usar exactamente el `job_id` y `request_id` asignados. No reconstruir fechas,
   prefijos ni identificadores en el texto de la delegación.
5. Un solo `sessions_send` a la clave completa del especialista, con
   `timeoutSeconds=120`. El paquete conserva el texto original y los campos
   asociados a ese escenario. La clasificación en escenarios no cambia lugares,
   pesos, configuración ni cifras.
6. Comprobar la coincidencia del `request_id` devuelto antes de adjuntar o mostrar
   el resultado. Un resultado de otra solicitud nunca cierra el turno actual.
7. Adjuntar resultado y texto visible con `bandeja_attach`. Si la entrega ya
   aparece como enviada, no repetirla. Si el Gateway requiere respuesta normal,
   usar una sola vez el `visible_reply` devuelto. No precederlo de otro `message`.
8. Continuar en serie los escenarios pendientes de la misma solicitud, dentro
   del tiempo disponible. Si hay que interrumpir, informar cuántos faltan y
   conservarlos en cola. No declarar completa una solicitud con jobs pendientes.
9. Un acuse tardío o una repetición del resultado no abre una consulta nueva.
   Un timeout requiere comprobar el estado antes de repetir: no dar por hecho
   que el motor dejó de ejecutar ni que la cuota no se consumió.

## Tipos de viaje

| Pedido | Tratamiento |
| --- | --- |
| Sencillo cargado | Una ruta y configuración; modalidad declarada. |
| Ida cargada y devolución de contenedor vacío | Un job con ambos trayectos y `viaje_redondo_con_retorno_vacio=true`; `contenedor_vacio=false` para la ida. |
| Solo devolución de contenedor vacío | Un job para ese tramo con `contenedor_vacio=true`; conservar el vehículo si corresponde explícitamente al mismo escenario. |
| Vehículo sin carga ni contenedor | Modalidad distinta. No reutilizar contenedor vacío como equivalente. |

Para viaje redondo con devolución:

- La ida usa contenedor cargado; la devolución usa contenedor vacío transportado.
- Ambos tramos mantienen `modo_viaje=CARGADO` y carrocería Portacontenedores.
- La configuración del mismo equipo se conserva en ida y regreso. La ausencia
  de mercancía en la devolución no autoriza recomendar un vehículo menor.
- Conservar `origen_regreso` y `destino_regreso` si fueron declarados. El retorno
  puede ir a otro puerto; la inversión automática solo aplica cuando corresponde
  al pedido.
- Evaluar individualmente ambas rutas, sus variantes y sus referencias SICETAC.
  El agente presenta el total combinado devuelto por el motor; no suma ni
  inventa valores por su cuenta.
- Peso cero no reemplaza `tipo_contenedor=VACIO`. No llamar al motor de vehículo
  vacío para representar un contenedor vacío transportado.
- Conservar las horas logísticas solicitadas; si no se declaran, aplicar la
  convención vigente de cuatro horas. No cambiarla por el hecho de ser devolución.
- No asignar valor en plaza al contenedor vacío si la fuente lo declara no aplicable.

## Nombres, helper y cobertura

Conservar el nombre original junto con el nombre/código resuelto y su fuente.
Usar el catálogo/helper vigente para alias portuarios y centros poblados.
Una optimización o caché debe estar vinculada a la versión del catálogo y no
eliminar ese paso de resolución.

Antes de declarar que un lugar no existe, distinguir:

1. Nombre/alias no resuelto: revisar la fuente central; pedir aclaración solo
   si no hay equivalencia verificable o hay ambigüedad.
2. Lugar resuelto, ruta ausente: informar la falta de cobertura para los códigos
   concretos, conservando el centro poblado. No reemplazarlo por la cabecera.
3. Ruta existente, configuración o tarifa ausente: informar el faltante específico.

Caso de regresión: Puerto Antioquia debe contrastarse con la equivalencia
canónica de Nueva Colonia `05837002`. No trasladar esta equivalencia a
“Puerto Colombia”, y no sustituir Nueva Colonia por Turbo cabecera.

## Estado de aplicación

Las instrucciones ya se actualizaron coordinadamente y con respaldo. Las
guardas de bandeja se validaron en copia aislada, sin instalarlas. API,
catálogos y pruebas reales de canal siguen fuera de esta aplicación.
