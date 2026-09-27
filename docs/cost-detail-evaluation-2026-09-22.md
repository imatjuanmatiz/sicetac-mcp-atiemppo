# Evaluación del proceso «Detalle de costos»

> Evaluación previa a la implementación. La versión publicada y las reglas finales están en [Detalles de costos](cost-details.md).

Fecha: 22 de septiembre de 2026. Estado: evaluación y propuesta; funcionalidad pendiente de implementación.

Actualización tras validación y aclaración del usuario: los costos fijos continúan vigentes hasta que sean reemplazados. La fecha agosto no significa vencimiento. La prueba con esta regla y los insumos existentes calculó 26 casos locales; el servicio publicado sigue rechazándolos por exigir igualdad de meses. Véase [evaluación de disponibilidad actual](cost-detail-readiness-2026-09-22.md).

## Resultado

El proceso solicitado ejecuta el modelo completo y obtiene su propio total de viaje y desglose. El motor existente calcula kilómetros, horas y galones por terreno y los principales rubros; la integración todavía no entrega ese resultado al consumidor.

La aclaración del usuario establece dos procesos independientes:

| Proceso | Operación | Resultado |
|---|---|---|
| Consulta del valor publicado | Busca movilización y valor por hora para la ruta/configuración y aplica las horas logísticas | Valor de referencia publicado con su escenario de horas |
| Detalle de costos | Toma distancias, rendimientos, velocidades, combustible, peajes, costos fijos y variables; ejecuta el modelo completo | Consumos, tiempos, componentes y total calculado por el modelo |

Ambos pueden compartir el contexto de la ruta. El detalle no depende de obtener primero el valor publicado ni de coincidir con él. Su validación comprueba fórmulas, insumos y suma de sus propios componentes. Una comparación entre procesos es un análisis adicional opcional.

Hay dos cambios de integración necesarios: seleccionar los costos fijos vigentes hasta reemplazo, aunque su fecha de origen sea anterior al mes calculado, y conservar el desglose en la respuesta del servicio. Agregar solamente una instrucción al agente o enviar `resumen=false` no resuelve el proceso.

## Proyecto y publicación comprobados

- Carpeta real: `/Users/atiemppoia/codex/SICETAC-API-MCP`.
- `/Users/atiemppoia/Documents/GitHub/sicetac-mcp-atiemppo` es un enlace simbólico a esa misma carpeta.
- Remoto registrado: `https://github.com/imatjuanmatiz/sicetac-mcp-atiemppo.git`.
- Revisión local: `5d179c28420cb1da82806674dd97e45cbf3a3fc1`; árbol limpio antes de esta evaluación.
- Render: `https://sicetac-api-mcp.onrender.com`; `GET /health` devuelve versión 2.4.0. OpenAPI publica `/consulta`, `/v1/quotes` y `/v1/prequotes`.
- Supabase: proyecto SICETAC-ATICA; se consultaron esquema, vistas y parámetros por lectura.
- WhatsApp: se revisó el puente local `/Users/atiemppoia/Documents/GitHub/atica-whatsapp-bridge/main.py`. Usa HTTP contra `/consulta`, con la URL anterior como valor por defecto. Conserva `last_route` y `last_result` para consultas posteriores de peajes. Esto acredita el código local, no la revisión exacta desplegada del puente.
- Vercel: se listaron los proyectos `atica`, `sicetac-lab` y `sicealinstante`. El conector de detalle de proyecto falló con un error de validación `idOrName`; queda pendiente verificar el repositorio y la revisión de cada despliegue.
- `api/atica.ts` contiene un ejemplo con mes 202510 y referencias antiguas. Su presencia en este repositorio no acredita que sea el código vigente de Vercel.
- La versión 2.4.0 y el contrato publicado no acreditan por sí solos un SHA de despliegue idéntico al local.

## Evidencia del bloqueo actual

Prueba contra Render, misma entrada para ambas salidas:

| Campo | Valor |
|---|---|
| Ruta | Bogotá–Barranquilla |
| RUTASID | 93, devuelto por el resumen |
| Vehículo / carrocería | C3S3 / GENERAL |
| Mes | 202609 |
| Horas logísticas | 4 |
| Resumen | HTTP 200; H4 = COP 7.821.531 |
| Detalle (`resumen=false`) | HTTP 503 |

Mensaje recibido: «No hay parámetros normativos publicados para este vehículo en el modo detallado. Use resumen=true, que entrega el consolidado oficial SICETAC vigente.»

Las vistas consultadas muestran:

| Fuente | Mes expuesto | Filas |
|---|---:|---:|
| `parametros_vigentes` | 202609 | 13 |
| `costos_fijos_vigentes` | 202608 | 138 |
| `sicetac_valorhora_vigentes` | 202609 | — |

Cada vista selecciona el último mes disponible de su propia tabla. El servicio exige parámetros y costos fijos con el mismo `MES`; septiembre no encuentra filas de costos fijos fechadas en septiembre. El usuario confirmó que los costos no se han modificado y permanecen vigentes: debe seleccionarse el último costo aplicable por vehículo y carrocería, con fecha no posterior al período solicitado. Se conserva agosto como mes de origen; septiembre es el período de cálculo. El bloqueo observado es técnico, no una prueba de vencimiento del costo.

La consulta del valor publicado usa movilización más valor por hora logística. Para el caso comprobado: COP 7.454.479 + 4 × COP 91.763 = COP 7.821.531. El detalle ejecuta el modelo completo con otra cadena de insumos y entrega su propio total. La igualdad con el valor publicado no es un requisito de este proceso.

## Qué existe y qué falta

| Información pedida | Estado comprobado | Trabajo requerido |
|---|---|---|
| Kilómetros por terreno | Disponible en la ruta | Exponer con RUTASID y corte |
| Galones por terreno | Calculados en `detalle_via` | Conservar en la respuesta |
| Consumo total | Se calcula internamente | Exponer suma en galones |
| Rendimiento y velocidad | Presentes en parámetros | Exponer km/gal y km/h |
| Combustible total | Calculado en COP | Conservar y mostrar precio COP/gal |
| Combustible por terreno | Derivable con los insumos existentes | Calcular en el motor: galones × COP/gal |
| Horas de recorrido por terreno | Calculadas | Conservar en la respuesta |
| Horas logísticas y totales | Disponibles/derivables | Mantener las horas de la consulta original |
| Costos fijos del viaje | Agregado mensual vigente hasta reemplazo | Aplicar selección temporal y exponer mes de origen, base y asignación |
| Otros costos variables | Calculados con COP/km | Mostrar concepto real; el campo legado se llama `mantenimiento` |
| Peajes | Totalizador y detalle existentes | Mantener una sola totalización y su trazabilidad |
| Imprevistos y otros costos | Calculados como agregados | Exponer base, tasa y resultado |
| Llantas, lubricantes, salarios, seguros por separado | Sin ese desglose en las vistas consumidas | Incorporar fuentes por concepto antes de ofrecerlo |

Los modelos cargado y vacío devuelven `detalle_via`, combustible, fijo, peajes, mantenimiento, imprevistos y otros costos. Sin embargo, `sicetac_service.calcular_sicetac` extrae solamente `total_viaje` para H2/H4/H8 y descarta el resto en las ramas de ruta manual, ruta única y variantes.

Una reproducción local con insumos sintéticos confirmó que el modelo devuelve `detalle_via`, el servicio lo pierde y H4 conserva el mismo total. Se aisló el SDK de red ausente; no se modificó la lógica de cálculo para la prueba. Pasaron además las cuatro pruebas existentes de `test_modelo_parametros_202608.py`.

`/v1/prequotes` siempre construye una consulta con `resumen=True`. Su `view=detail` añade información técnica, homologación y mercado; no solicita el desglose operativo.

## Ejemplo de información que se puede obtener

Ejemplo parcial derivado de la ruta 93 y los parámetros C3S3 cargado de septiembre consultados en Supabase. ACPM: COP 11.616 por galón. Se aplican las fórmulas ya usadas por el modelo: galones = km ÷ rendimiento; horas = km ÷ velocidad; combustible = galones × precio.

Este ejemplo ilustra los componentes de combustible y recorrido del modelo. El total completo requiere calcular también los demás componentes con sus insumos válidos.

| Terreno | km | km/gal | Galones | Combustible COP | Horas de recorrido |
|---|---:|---:|---:|---:|---:|
| Plano | 879,75 | 6,48 | 135,76 | 1.577.033,33 | 15,64 |
| Ondulado | 72,08 | 4,80 | 15,02 | 174.433,60 | 2,18 |
| Montañoso | 37,73 | 3,26 | 11,57 | 134.439,17 | 1,60 |
| Urbano | 21,00 | 3,26 | 6,44 | 74.826,99 | 0,89 |
| Despavimentado | 0,00 | 2,07 | 0,00 | 0,00 | 0,00 |
| **Total** | **1.010,56** | — | **168,80** | **1.960.733,09** | **20,31** |

Con 4 horas logísticas, el tiempo total modelado sería 24,31 horas. Son tiempos estimados del modelo, no una promesa de llegada. Se suman valores sin redondear; el redondeo de filas puede producir diferencias de centavos al sumar la presentación.

## Proceso propuesto

1. El usuario solicita **«detalle de costos»**, indicando una ruta o utilizando la que ya tiene en contexto.
2. Si existe una ficha previa, el canal recupera sus datos de operación; también debe admitir iniciar el detalle directamente, sin consultar primero un valor publicado.
3. Resuelve ruta, RUTASID, vehículo homologado, carrocería, condición cargado/vacío, período y horas. Obtiene las distancias y parámetros necesarios para el modelo.
4. Si la consulta está incompleta o hay varias rutas en contexto, solicita únicamente la selección que falta.
5. El agente llama a una herramienta MCP dedicada, propuesta como `detalle_costos_sicetac`.
6. La herramienta consume la API comercial y esta ejecuta el modelo completo existente con los insumos de esa ruta, sin tomar el valor publicado como base del cálculo.
7. La respuesta presenta total calculado por el modelo, componentes de costos, tabla por terreno, tiempos y fuentes.
8. Si faltan insumos del modelo, devuelve un estado explícito de detalle no disponible e identifica el faltante. Una referencia publicada previa permanece en su ficha y no sustituye el resultado del modelo.

Para una ruta de catálogo se usa `manual_mode=false`: permite tomar sus distancias y peajes. En este código, `manual_mode=true` significa omitir la búsqueda de municipios/rutas y usar distancias ingresadas. Ejecutar el modelo manual para una ruta oficial no exige activar ese indicador.

H4 se usa cuando no existe otra selección. Si la ficha previa fue H2, H6, H8 u otra hora, el detalle conserva ese escenario. Para VACIO, el modelo actual aplica horas logísticas cero; debe comunicarlo.

## Contrato técnico recomendado, aún no implementado

- Conservar `/v1/quotes` para clientes/MCP y `/consulta` para el consumidor legado.
- Crear en el servicio una operación explícita de cálculo completo, accesible mediante la herramienta `detalle_costos_sicetac`. Puede conectarse a los endpoints existentes mediante `resumen=false`, pero debe ejecutar y devolver el modelo, independientemente de la consulta del valor publicado.
- Añadir una selección explícita `rutasid` para el detalle de una ruta. Hoy no existe ese campo de selección para un trayecto sencillo.
- Agregar `detalle_costos` y declarar `metodo=modelo_completo`. Si se mantienen campos de compatibilidad como `totales`, deben corresponder al modelo ejecutado.
- Mantener el cálculo en el servidor; los canales formatean los valores.
- La herramienta MCP nueva debe reenviar los campos resueltos y conservar la política de cuotas/auditoría de la API comercial. No reintentar automáticamente.
- WhatsApp hoy usa HTTP directo. Puede invocar el mismo servicio de detalle desde su puente; el agente MCP invoca ese servicio mediante su herramienta. Ambos comparten contrato y cálculo.
- No reutilizar `view=detail` como sinónimo tácito de esta nueva acción: el contrato actual tiene otro contenido.

Salida propuesta:

| Bloque | Contenido |
|---|---|
| `contexto` | RUTASID, nombres y DANE, vehículo, carrocería, modo, mes, horas |
| `terrenos[]` | Tipo, km, km/h, km/gal, horas, galones, combustible COP |
| `combustible` | COP/gal, galones y costo total |
| `tiempos` | Recorrido, logística, total, horas hábiles y recorridos mensuales |
| `costos` | Fijos, combustible, peajes, otros variables, imprevistos, otros y total |
| `metodo` | `modelo_completo`, con identificación de la versión utilizada |
| `fuentes` | Mes efectivo y mes de origen de cada insumo, versión y fecha de cálculo |
| `disponibilidad` | Completo, parcial o no disponible, con motivo |

Los subtotales no se suman otra vez como componentes. La suma de componentes debe explicar el total del modelo. La consulta de valores publicados y su comparación quedan fuera del recorrido obligatorio de «detalle de costos»; se pueden ofrecer como análisis separado cuando el usuario lo solicite.

## Alcance y límites

La primera entrega completa puede cubrir carga general cargada y vehículo vacío con parámetros válidos. El código bloquea expresamente el detalle para `tipo_contenedor`, viajes redondos y `modo_aumento`. Esos casos necesitan tratamiento por serie/tramo y validación antes de declararlos soportados.

Contenedor vacío transportado sigue siendo operación cargada con su serie particular; no se puede sustituir por el modelo de vehículo vacío.

Las fuentes históricas requieren resolución por período: cambiar solamente `mes` no recupera registros históricos si la carga usa exclusivamente vistas del último mes.

## Orden de implementación y aceptación

1. **Vigencia:** aplicar la regla confirmada por el usuario: último costo fijo aplicable por vehículo y carrocería, vigente hasta reemplazo y nunca posterior al período solicitado. Conservar las fechas originales; no exigir una nueva fila cada mes.
2. **Motor/servicio:** devolver el desglose, precio y rendimiento; generar combustible por terreno; seleccionar la misma RUTASID; validar datos finitos y positivos cuando el terreno tenga distancia.
3. **API/MCP:** incorporar el bloque y la herramienta; conservar compatibilidad, cuotas y trazabilidad.
4. **Canales:** reconocer el comando en WhatsApp usando el contexto existente y preparar la acción visual en el proyecto Vercel correcto.
5. **Verificación:** demostrar el recorrido herramienta → API → modelo con fixtures controlados, y después validar una ruta real con fuentes completas.

Criterios de aceptación:

- Conservar RUTASID, vehículo, carrocería, período solicitado y horas cuando se parte de una ficha; permitir también una solicitud directa del modelo completo.
- Suma de km y galones consistente; suma del combustible por terreno concilia con el total según una política documentada de redondeo.
- Suma de componentes concilia con el total modelado.
- Tiempos por terreno concilian con recorrido; logística se presenta por separado.
- Cortes de datos y restricciones visibles; insumos faltantes o inválidos no se convierten en cero.
- Pruebas de ruta única, variantes, dirección, cargado, vacío, H4 y horas personalizadas.
- Casos de contenedor y viaje redondo conservan un error explícito hasta tener soporte validado.
- La respuesta normal de búsqueda permanece compatible.
- En WhatsApp, «detalle de costos» reutiliza el contexto y pide la ruta solamente cuando no existe o es ambigua.
- El detalle funciona con insumos completos aunque la consulta de valores publicados no esté disponible; una prueba debe comprobar esa independencia.
- El total del detalle procede de sus componentes y no se ajusta al valor publicado. La comparación entre procesos es opcional y no condiciona la aceptación.

## Archivos que concentran el cambio

- `modelo_sicetac.py` y `modelo_sicetac_vacio.py`: ampliar salida auditable.
- `sicetac_service.py`: vigencias, conservación del desglose y selección de ruta.
- `main.py` y `commercial_api.py`: contratos y respuesta.
- `commercial_client.py`, `commercial_mcp_server.py`, `mcp_server.py`: acceso al proceso.
- Puente WhatsApp externo: reconocimiento, contexto y presentación.
- Proyecto frontend Vercel: identificar primero el despliegue y repositorio correspondiente.
- Documentación: actualizar la promesa actual de «detalle con resumen=false» cuando esté implementada.

## Fuentes y evidencia

Documentación revisada: README, MODEL_STRUCTURE, overview, referencia API, integración y contratos de búsqueda/ATICA. Contraste con código de modelos, servicio, API comercial, MCP y puente WhatsApp.

Referencias locales clave:

- `modelo_sicetac.py:30–130`: cálculo y devolución del desglose.
- `modelo_sicetac_vacio.py:30–134`: modelo vacío.
- `sicetac_service.py:973–995`: validación de coincidencia de períodos.
- `sicetac_service.py:1374–1389`: límites de detalle.
- `sicetac_service.py:1546–1636`: descarte del desglose.
- `commercial_api.py:523–525`: consulta siempre resumida desde precotización.
- `commercial_api.py:891–909`: diferencia entre las vistas search/detail.
- Puente WhatsApp `main.py:1769` y `main.py:2206`: consulta HTTP y detalle de peajes desde contexto.

Evidencia estructurada: [cost-detail-2026-09-22.json](evidence/cost-detail-2026-09-22.json).

Se prepararon únicamente esta evaluación y su evidencia. La funcionalidad, los datos, los despliegues y los canales no fueron modificados.
