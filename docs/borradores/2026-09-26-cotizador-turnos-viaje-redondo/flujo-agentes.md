## Bandeja de cotizaciones

La cola vive en `cotizador-bandeja`. El runtime resuelve el tenant; no pases
`tenant_id` a sus herramientas. Vías, saludos y otras conversaciones no crean
jobs. Para cotizar sigue esta secuencia completa:

1. Consulta `bandeja_list` para identificar el inbox del mensaje y sus jobs.
   Conserva el texto original. `bandeja_enqueue` registra un job por escenario:
   una O-D o una ida cargada con su devolución de contenedor vacío completa.
   Dos pesos alternativos son dos jobs completos, nunca cuatro tramos sueltos.
   Transcribe los datos explícitos al registro sin homologar nombres, vehículos
   ni pesos. Si falta el dato indispensable, clasifica `missing_data` y pide
   solo ese dato. No bloquees por peso si hay un vehículo declarado.
2. `bandeja_next` reclama un job. Solo si devuelve un job nuevo y
   `already_in_flight=false`, envía una vez a `agent:atica-cotizador-api:main`
   mediante `sessions_send`, `timeoutSeconds=120`. Copia exactamente el
   `request_id` del job; no generes otro ID ni reconstruyas su fecha.
   `already_in_flight=true` significa que ya existe trabajo activo: conserva
   ese job, espera su resultado y no repitas el envío ni abras otro en el tenant.
3. El mensaje al especialista lleva el requerimiento original sin reescribir,
   seguido de metadata separada: `request_id`, tenant propio, `caller_agent`,
   `origin_channel=whatsapp`, `delivery=false`, `emitir=false` y el escenario
   concreto del job. Si hay varias alternativas, identifica solo la que debe
   calcular en esta llamada y conserva todos sus datos explícitos. Una
   aclaración incorpora únicamente los datos confirmados de esa solicitud.
   No heredes datos de otros pedidos ni incluyas información privada ajena.
4. Antes de `bandeja_attach`, verifica que el JSON recibido conserve el mismo
   `request_id`, escenario y trayectos del job. Si el sobre trae `canonical`,
   comprueba también su ID cuando exista. Un ID distinto nunca cierra el job:
   conserva el trabajo pendiente y reporta la discrepancia sin publicar cifras
   ajenas. No cambies el ID del resultado para hacerlo coincidir.
5. Adjunta el JSON intacto y su resumen visible una sola vez. Si la entrega
   devuelve `delivery.status=sent` o indica `already_sent`, no repitas el texto.
   Si devuelve `delivery.status=deferred` o `reply_required=true`, conserva el
   `visible_reply` para la respuesta normal del Gateway; eso es entrega
   pendiente por el canal normal, no un error de infraestructura. No uses
   `message` ni `sessions_yield` para cerrar una cotización.
6. Tras adjuntar, si `queued_remaining_for_request > 0`, llama de nuevo a
   `bandeja_next` con el mismo `inbox_id`. Procesa esos escenarios en serie,
   nunca en paralelo. Al cerrar el turno, reúne una sola vez los textos
   `visible_reply` diferidos de los jobs procesados, separados por escenario.
   No incluyas los que ya fueron enviados. Si falta tiempo, entrega lo obtenido,
   informa cuántos quedan y conserva la cola; no declares todo completado.

Un timeout no prueba que el especialista no recibió la solicitud. Conserva el
job `in_flight` para correlacionar la respuesta tardía; no hagas reintentos
automáticos ni liberes la cola mientras el resultado sea incierto. Solo si el
transporte confirma que no envió la solicitud cabe un reintento con el mismo
paquete e ID. Si el fallo es terminal y está confirmado, adjunta `failed` y
explica lo pendiente. JSON truncado o inválido no es un resultado cotizado ni
autoriza a dividir el viaje o inventar cifras. Si tienes `bandeja_publish`,
úsala solo para la entrega fallida del mismo resultado, nunca para el cálculo.
Si no está disponible, conserva la entrega pendiente y comunica el fallo;
no uses `message` como sustituto.

“Avanza”, “sí”, “dale” o “cotízalo” retoman el pendiente del mismo tenant;
no crean otra cotización ni saltan un job activo. Una corrección de datos
crea un escenario nuevo con su ID cuando el anterior ya fue consultado;
no reutilices el ID con parámetros distintos. Si llega un eco o respuesta
interna ya cerrada, responde `NO_REPLY` sin otra consulta, attach ni publicación.
Una respuesta tardía solo se adjunta si coincide con el job pendiente propio.

### Viaje redondo, devolución y helper

- Ida cargada + devolución de contenedor vacío: un job y una llamada con
  `origin_return`, `destination_return`,
  `viaje_redondo_con_retorno_vacio=true`, `contenedor_vacio=false`.
  Envía al especialista esos extremos como `origen_regreso`/`destino_regreso`.
  Conserva el puerto de devolución indicado; no fuerces regresar al origen
  cuando el usuario pidió otro destino. El regreso empieza en el destino de
  la ida salvo indicación expresa. Si dice volver al origen, usa ese origen.
- Devolución independiente: `contenedor_vacio=true` y
  `viaje_redondo_con_retorno_vacio=false`, sin un segundo trayecto inventado.
  Significa vehículo `CARGADO`, carrocería `Portacontenedores` y contenedor
  `VACIO`; nunca vehículo vacío ni una simulación con peso cero.
- Un viaje redondo conserva el mismo vehículo en los dos sentidos. El Core
  evalúa la ruta y modalidad de cada tramo; no dupliques la tarifa de ida,
  no sumes variantes y no selecciones otra configuración para el retorno.
  Presenta ambos tramos y el total solo si el resultado central lo entrega
  completo. Si falta uno, muestra lo disponible y la brecha sin total completo.
- “Cotizar aparte” conserva el desglose de ida/devolución en la solicitud
  combinada. Solo una petición explícita de servicios independientes permite
  jobs separados. Si “redondo” no aclara la carga del regreso, pide ese dato;
  no conviertas una segunda carga en devolución vacía.
- Conserva nombres y DANE declarados para que el helper/ruleset central los
  resuelva. No sustituyas un puerto o centro poblado por su cabecera municipal,
  ni crees aliases locales. Puerto Colombia y Puerto Antioquia son nombres
  distintos. Si el helper no confirma una equivalencia, conserva el nombre y
  pide la localidad/DANE preciso; no cambies a Turbo por tanteo ni encadenes
  consultas. Municipio resuelto sin ruta catalogada es una brecha de cobertura,
  no un municipio desconocido: no pidas kilómetros para suplir esa tarifa.
