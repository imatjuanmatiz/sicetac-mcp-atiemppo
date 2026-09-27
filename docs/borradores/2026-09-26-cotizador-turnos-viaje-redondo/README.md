# Borrador: turnos y viaje redondo del cotizador OpenClaw

**Actualización posterior:** Juan pidió corregir Instant y verificar el helper
común y luego autorizó subir los cambios. Véase
[correcciones verificadas y catálogo](helper-instant-corregido.md).
La versión integrada de Instant y el helper pasa 141 pruebas y build exitoso.
La migración de catálogo sigue sin ejecutar y el candidato de bandeja sin instalar.
Los manifiestos, parches y resultados anteriores se conservan como evidencia
histórica; sus hashes y estados corresponden a cada fase, no al código integrado.
El diagnóstico de abajo documenta la fase anterior de agentes/bandeja.

Estado de la fase anterior: **instrucciones de los tres agentes aplicadas; código de bandeja en
borrador probado; SICETAC Instant revisado sin cambios**.
Fecha: 26 de septiembre de 2026. API de referencia local: commit `2541f35`.

## Alcance autorizado

Juan pidió concentrarse en los turnos, la resolución de lugares por el helper
y el viaje redondo/devolución de `at_cot_001`, extendiendo el mismo comportamiento
a `bruno_at` en Alianza Team. Mantener el trabajo en borrador mientras viaja.

Después Juan autorizó expresamente tocar los agentes para completar los flujos
y revisar issues de SICETAC Instant. Se actualizaron únicamente los
`AGENTS.md` de `at_cot_001`, `bruno_at` y `atica-cotizador-api`, con respaldo.
La API, los plugins instalados, permisos, tablas operativas, servicios y
SICETAC Instant conservaron su contenido. No hubo mensajes, cotizaciones
reales, reinicios, commits, pushes ni despliegues en este refuerzo.

## Resultado del refuerzo

- **Agentes aplicados:** protocolo común de cola, ID, espera sin duplicar,
  ida/devolución completa, preservación de nombres y entrega única. Se
  sustituyeron secciones contradictorias. Véanse [flujo](flujo-agentes.md),
  [manifiesto y respaldo](manifest-agentes.json) y los tres parches `AGENTS.md`.
- **Carga de instrucciones:** AT-COT pasó de 17.899 a 15.186 caracteres;
  Bruno-AT quedó en 15.872 y ATICA en 11.419, bajo el límite configurado de
  16.000. Se comprobaron workspace, secciones de acceso/seguridad preservadas y
  contenido final. Esto no acredita una conversación nueva en producción.
- **Bandeja en borrador:** [parche](cotizador-bandeja.patch),
  [baseline](manifest-bandeja.json) y [32/32 pruebas](resultado-refuerzo.json).
  Incluye 19 pruebas existentes adaptadas al ID obligatorio y 13 regresiones.
  El diagnóstico de 8 casos queda sin brechas sobre el candidato.
- **Instant:** no hay issues abiertos en GitHub al consultar; la revisión
  encontró tres defectos reproducibles de interfaz, detallados en
  [revisión de SICETAC Instant](revision-instant.md). Su repositorio no cambió.

El backup privado está indicado en el manifiesto. Solo contiene las versiones
anteriores de los tres archivos y sus hashes; no se subió al repositorio.
Los parches guardados evitan copiar listas de participantes y transcripciones.

## Reproducir el candidato sin instalarlo

```bash
python3 docs/borradores/2026-09-26-cotizador-turnos-viaje-redondo/probar-refuerzo.py
node docs/borradores/2026-09-26-cotizador-turnos-viaje-redondo/revisar-instant.mjs
```

El primer script verifica hashes, copia el plugin a una carpeta temporal,
aplica el parche solo allí, resuelve el SDK OpenClaw instalado sin instalar
dependencias y ejecuta pruebas con SQLite temporal y transporte simulado.
El segundo es un diagnóstico histórico de Instant previo a las correcciones;
para el código actual usar `node --test test/route-flow.test.mjs` en ese repositorio. Ninguno
prueba el cálculo remoto, el Gateway ni la entrega real de WhatsApp.

El endurecimiento de código exige `request_id` en respuestas `answered`,
rechaza IDs incompatibles, cierres distintos sobre un job terminado y banderas
de viaje incoherentes. Un attach repetido no vuelve a publicar. La entrega
diferida del Gateway sigue sin recibo persistente de entrega en la bandeja;
las pruebas no prometen entrega exactamente una vez ante una caída del proceso.

## Conexión de Bruno-AT: ya existe

La configuración local actual contiene:

| Orquestador | Tenant de bandeja | Especialista |
| --- | --- | --- |
| `at_cot_001` | `AT-COT-001` | `agent:atica-cotizador-api:main` |
| `bruno_at` | `ateam` | `agent:atica-cotizador-api:main` |

Confirmado en `agents.entries`, `tools.agentToAgent.allow`, los permisos
`subagents.allowAgents`, la configuración de `cotizador-bandeja` y su tabla
`tenants`, leída con `mode=ro` y `query_only=on`.
Ambos pueden usar `sessions_send`; el especialista tiene `atica_precotizar_api`.
No se necesita crear otra conexión ni otro cotizador.
Esto acredita configuración y registro local, no una prueba nueva por WhatsApp.
La bandeja de `ateam` no contenía jobs al momento de esta lectura.

## Hallazgos del diagnóstico inicial

### Turnos

- Las 15 pruebas existentes de almacenamiento de bandeja pasaron en bases
  temporales: aislamiento por tenant, deduplicación, un job activo y conservación
  del viaje combinado, entre otras.
- `nextJob` conserva el job activo y devuelve `already_in_flight=true`. El
  orquestador debe interpretar esa marca como espera/recuperación; no como
  autorización para volver a cotizar.
- **Brecha reproducida:** `attachResult` admite un `request_id` diferente al
  asignado al job. En el caso del 25 de septiembre hay IDs con año `20260925`
  en bandeja y `20250925` en llamadas/respuestas. No se alteraron esos registros.
- **Brechas reproducidas:** la cola admite un job simultáneamente marcado como
  ida cargada más retorno y contenedor vacío, y admite dos trayectos con
  `viaje_redondo_con_retorno_vacio=false`. Las instrucciones actuales no sustituyen
  validaciones deterministas de estos campos.

### Tipos de viaje

El adaptador compilado instalado construye correctamente una sola solicitud
para el viaje combinado cuando recibe los campos correctos:

```json
{
  "modo_viaje": "CARGADO",
  "viaje_redondo": true,
  "tipo_contenedor": "CARGADO",
  "tipo_contenedor_regreso": "VACIO"
}
```

Actualmente `modo_viaje` se omite en el adaptador y el contrato existente de
la API aplica su valor por defecto `CARGADO`. El JSON anterior muestra el
significado efectivo; no es una captura literal de todos los campos enviados.
Una futura revisión del adaptador puede hacerlo explícito sin cambiar la API.

Una devolución independiente envía `tipo_contenedor=VACIO` y mantiene ese
modo vehicular `CARGADO`. En las llamadas registradas el 25 de septiembre a
Nueva Colonia → Medellín y Nueva Colonia → Cartagena sí se envió
`contenedor_vacio=true`. No corresponde afirmar que esas llamadas usaron
el vehículo sin carga.

El retorno a Medellín fue seleccionado como C2S2, mientras la ida había sido
C2S3. Fueron pedidos posteriores de retorno independiente, con configuración
sin declarar; esa evidencia no demuestra un fallo del agregado redondo.
Para un viaje redondo del mismo equipo, el criterio de aceptación exige
conservar una misma configuración en ambos trayectos.

### Helper y Puerto Antioquia / Nueva Colonia

El caso localizado es **Puerto Antioquia**, no Puerto Colombia. No se agregó
ninguna equivalencia entre Puerto Colombia y Nueva Colonia.

Secuencia observada del 25 de septiembre, en transcripciones y bandeja locales:

1. El adaptador recibió y conservó `Cali → Puerto Antioquia`.
2. La respuesta registrada no mostró un alias publicado aplicado a ese nombre;
   la resolución devolvió el nombre original y no confirmó su DANE.
3. Después se consultó `Cali → Turbo, Antioquia`, sin ruta catalogada.
4. Tras la aclaración de Juan, `Cali → Nueva Colonia, Turbo, Antioquia` sí se cotizó.
5. El helper confirmó Nueva Colonia como `05837002`. También se cotizó
   Nueva Colonia → Medellín. Nueva Colonia → Cartagena devolvió
   `OD_PAIR_NOT_IN_SICETAC_CATALOG` con los municipios ya resueltos.

El código de pre-cotización aplica equivalencias del ruleset y después llama
al helper para confirmar la localidad y su código. El adaptador no sustituye
los nombres por su cuenta. **La evidencia no demuestra que se salte el helper.**
Debe compararse la equivalencia que Juan tiene en su fuente canónica con el
catálogo/regla que el servicio estaba leyendo. No se leyó ni modificó la tabla
remota en esta revisión. No se acredita que el alias esté publicado actualmente.

### Instrucciones de Bruno-AT

`bruno-at/AGENTS.md` contenía indicaciones incompatibles entre sus secciones:

- Pide dividir el requerimiento y construir un paquete por pieza, pero después
  exige transmisión literal y conservar la solicitud completa.
- La sección de delegación indica usar `message` antes de `bandeja_attach`,
  mientras la bandeja ya gestiona entrega o devuelve `visible_reply`.
- Conserva la regla de un job por turno; `at_cot_001` indica vaciar en serie
  los escenarios de la misma solicitud cuando quedan pendientes.

La conexión estaba. Este refuerzo sustituyó los bloques contradictorios en los
agentes, en vez de añadir otra regla al final del archivo. Bruno-AT conserva
sus permisos existentes: no tiene `bandeja_publish`; ante fallo de proveedor
conserva el pendiente y lo comunica. No se habilitó una herramienta adicional.

## Borrador de solución

El [contrato propuesto](contrato-propuesto.md) define una sola secuencia para
ambos orquestadores y los campos que el especialista debe preservar.

Estado de las correcciones:

1. Coherencia de trayectos, servicio y banderas: implementada y probada en el
   candidato de bandeja, **sin instalar**.
2. ID inmutable y respuesta correlacionada: comprobación instruida en agentes y
   guarda determinista probada en candidato, **sin instalar**. Recuperaciones
   históricas requieren un procedimiento explícito; no hay reasignación silenciosa.
3. `already_in_flight`, continuidad del inbox, timeout y entrega: contrato
   **aplicado a los agentes**. `dispatch_allowed` y cierre idempotente son
   refuerzos adicionales del candidato; los agentes actuales usan la bandera
   existente y no dependen de campos nuevos.
4. Equivalencia Puerto Antioquia/Nueva Colonia: preservación de localidad
   reforzada en agentes; **publicación canónica pendiente de comprobar**.
   No se agregó ningún alias local ni se modificó el catálogo remoto.

La suite histórica de bandeja incluye una prueba que permite cambiar el
`request_id` al adjuntar un resultado de recuperación. Endurecerlo exige
actualizar de forma intencional ese procedimiento y su prueba; no se debe
aplicar un parche ciego a producción.

## Verificación local reproducible

```bash
node docs/borradores/2026-09-26-cotizador-turnos-viaje-redondo/verificar-borrador.mjs
```

[Resultado guardado](resultado-local.json): **5 comprobaciones satisfechas y
3 brechas reproducidas**. Usa SQLite temporal, transporte HTTP simulado y
auditoría sustituida. No importa/activa el plugin; extrae la función de
construcción de solicitud del adaptador compilado. No valida el cálculo
remoto, el Gateway ni la entrega real de WhatsApp. El resultado conserva hashes
del código examinado para reconocer cambios posteriores.

En el diagnóstico inicial, `test/plugin.test.mjs` no pudo iniciar por resolución
local del paquete `openclaw`. En el refuerzo se resolvió con un loader de prueba
que apunta al SDK instalado, y pasaron las 4 pruebas del plugin junto a las
de almacenamiento y regresión. No se instalaron dependencias ni se recompiló
el plugin operativo. La consulta CLI de configuración tampoco pudo leer el
directorio temporal desde el entorno restringido; la configuración indicada
arriba se verificó leyendo sus campos relevantes directamente.

## Criterios para validar operación y promover el código después

- Dos tenants simultáneos conservan sus solicitudes y respuestas separadas.
- Varias solicitudes y varios escenarios respetan su cola; no se duplican
  consultas al reclamar nuevamente un job activo ni al recibir un acuse tardío.
- Un viaje redondo mantiene ida y retorno en un solo job; cada tramo usa su
  ruta, variante, corte y modalidad. El mismo vehículo se conserva.
- Devolución: `CARGADO` + `Portacontenedores` + `tipo_contenedor=VACIO`.
  `modo_viaje=VACIO` queda reservado al vehículo sin carga ni contenedor.
- El retorno puede finalizar en otro puerto declarado. No se fuerza siempre
  la inversión al origen si el usuario pidió otro destino.
- Si falta la tarifa o ruta de un tramo, no se presenta un total redondo completo.
- Lugar no resuelto y ruta ausente son estados distintos. Una coincidencia
  de cabecera no sustituye silenciosamente un centro poblado portuario.
- `bandeja_attach` y entrega normal del Gateway producen un solo cierre visible.
- Validación controlada por canal solo cuando se autorice abandonar el borrador.

## Fuentes locales inspeccionadas

- `/Users/atiemppoia/.openclaw/openclaw.json`, campos de agentes, delegación y bandeja.
- `/Users/atiemppoia/.openclaw/workspace/at-cot-001/AGENTS.md`.
- `/Users/atiemppoia/.openclaw/workspace/bruno-at/AGENTS.md` y `SECURITY_CONTRACT.json`.
- `/Users/atiemppoia/.openclaw/workspace/atica-cotizador-api/AGENTS.md`.
- `/Users/atiemppoia/codex/openclaw/plugins/cotizador-bandeja/src/store.js` y pruebas.
- `/Users/atiemppoia/codex/openclaw/plugins/atica-cotizador-readonly/src/index.ts` y `dist/index.js`.
- Bandeja y transcripciones SQLite de los agentes, exclusivamente en lectura.
- `commercial_api.py`, `sicetac_helper.py`, `sicetac_service.py` del repositorio actual.

No se copiaron credenciales, teléfonos ni transcripciones completas a este borrador.
