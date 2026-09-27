# Disponibilidad actual del modelo completo

> Evaluación previa a la implementación. La versión publicada y las reglas finales están en [Detalles de costos](cost-details.md).

Evaluación: 22 de septiembre de 2026, hora de Colombia. Repositorio: SICETAC-API-MCP. Alcance: lectura de fuentes, ejecución local de los modelos existentes y consulta del servicio publicado.

## Dictamen

**Disponemos de los insumos y de un motor capaz de calcular el detalle para la muestra probada. La entrega automática por API/MCP todavía requiere ajustes.**

El usuario confirmó la regla: **los costos fijos permanecen vigentes hasta reemplazo**. Por ello, los costos registrados en agosto son aplicables en septiembre. El diagnóstico inicial que trataba la diferencia de meses como un posible faltante queda sustituido: el error está en exigir igualdad entre mes de cálculo y mes de origen del costo.

Se ejecutaron **26 casos locales** de Bogotá–Barranquilla, RUTASID 93: 13 configuraciones en CARGADO y VACIO, con carrocería GENERAL o VOLCO según la configuración. Se usaron parámetros y peajes actuales consultados en Supabase y los costos fijos vigentes de agosto. Los 26 casos dieron resultados finitos y positivos, y sus componentes conciliaron con su propio total. La comparación con el valor publicado no fue un requisito ni un insumo.

Para esta evaluación, un adaptador en memoria comunicó al modelo que el costo era aplicable al período solicitado, conservando el mes de origen en la evidencia. No se modificaron filas, fechas ni código productivo. La selección temporal aún no está integrada en el servicio.

## Insumos comprobados

| Elemento | Evidencia | Estado |
|---|---|---|
| Parámetros por vehículo | 13 configuraciones activas, corte 202609 | Disponibles |
| Rendimientos y velocidades | Cinco terrenos, cargado/vacío; sin nulos, ceros o negativos en los campos requeridos revisados | Disponibles |
| ACPM, horas hábiles y variables por km | Valores positivos para las 13 configuraciones | Disponibles |
| Costos fijos | 138 filas de agosto, sin duplicados de mes/vehículo/carrocería ni valores inválidos; 18 pertenecen a dos códigos reemplazados fuera del catálogo activo | Vigentes hasta reemplazo, según aclaración del usuario |
| Distancias | 9.945 rutas, IDs únicos, sin terrenos nulos o negativos y suma consistente con km totales | Consistencia estructural comprobada |
| Peajes | 9.084 rutas con resumen de septiembre, seis configuraciones, 54.504 combinaciones en estado `ok` | Cobertura parcial del catálogo de rutas |
| Otras 861 rutas | Sin vínculo de peajes de septiembre | Distinguir rutas sin peajes de información faltante antes de asumir cero |
| Modelo | 26 ejecuciones con costos vigentes y cuatro pruebas unitarias existentes aprobadas | Capacidad de cálculo comprobada en la muestra |
| API publicada | Cuatro llamadas del modelo completo devolvieron 503 | Bloqueada por la validación de meses |
| MCP | Herramienta actual puede solicitar `resumen=false`, pero recibe el resultado/error del mismo servicio | Pendiente de integrar el proceso y su salida completa |

La revisión estructural no certifica actualización geográfica de todas las rutas ni soporte de todas las carrocerías. El muestreo ejecutado cubre una ruta y las combinaciones indicadas.

## Ejemplo ejecutado con los insumos existentes

Bogotá–Barranquilla, RUTASID 93, C3S3, GENERAL, CARGADO, período septiembre de 2026, cuatro horas logísticas. Costo fijo mensual de origen agosto, vigente por la regla confirmada.

| Componente | COP |
|---|---:|
| Costo fijo asignado al viaje | 1.821.084,31 |
| Combustible | 1.960.733,09 |
| Peajes | 869.600,00 |
| Otros costos variables | 1.613.418,56 |
| Imprevistos | 121.006,39 |
| Otros costos | 1.435.690,62 |
| **Total del modelo** | **7.821.532,97** |

Consumo: 168,80 galones. Recorrido: 20,31 horas. Logística: 4 horas. Total modelado de tiempo: 24,31 horas. El costo de combustible por terreno se obtiene de los galones de cada terreno multiplicados por COP 11.616/galón.

Es un resultado de prueba local con los insumos descritos; el endpoint publicado todavía no entrega este desglose. Los costos variables excluyen combustible, peajes e imprevistos para evitar doble conteo.

## Cambios concretos para entregarlo

1. **Seleccionar el costo vigente:** obtener el último costo por vehículo y carrocería con fecha no posterior a la del cálculo, independientemente de que el mes sea distinto. En ausencia de una fila aplicable, informar el faltante. Conservar mes de origen y período de aplicación.
2. **Conservar la respuesta completa:** el servicio actual ejecuta el modelo, extrae sus totales y descarta `detalle_via` y los componentes. Debe devolverlos.
3. **Completar los campos:** exponer galones totales, precio por galón, velocidad, rendimiento, combustible por terreno, tiempo total y subtotales con unidades.
4. **Conectar el proceso:** herramienta MCP y acción «detalle de costos» con la ruta y los parámetros ya resueltos, y opción de invocación directa.
5. **Delimitar cobertura:** las rutas sin información de peajes, las carrocerías sin costo aplicable y las operaciones especiales requieren un estado explícito.

La selección del último costo debe hacerse por clave de negocio. La vista actual elige el máximo mes global, lo que podría ocultar costos todavía vigentes si en el futuro solo se actualizan algunas configuraciones.

## Observaciones por resolver antes de ampliar cobertura

- **Volquetas vacías:** las capturas locales del 1 de septiembre muestran un fijo mensual menor que el agregado vigente que hoy usa la base para VOLCO. Esto puede involucrar condición de carga u otro contexto del componente; requiere revisar esa correspondencia antes de declarar validado ese segmento. La ejecución aritmética exitosa por sí sola no resuelve esta diferencia de fuente. Se conserva la regla de vigencia confirmada.
- **Pequeñas diferencias entre capturas y base:** se encontraron diferencias de COP 2, 7 y 9 en algunos fijos mensuales. Son observaciones de procedencia/calidad, no prueba de vencimiento. No se sobrescribió el canon con las capturas.
- **Captura detallada parcial:** nueve vehículos tienen captura ampliada de componentes; los cuatro restantes usan captura de subtotales para la comparación documental. Parte de los costos variables del generador local se obtuvo por derivación. La verificación de campos positivos no demuestra independencia de todas las fuentes.
- **Contenedor, redondo y aumento:** el servicio actual bloquea el modo detallado en esos casos. Deben mantenerse fuera del alcance validado hasta contar con su tratamiento específico.

## Evidencia y controles

- [Fuentes y cobertura Supabase](evidence/cost-detail-readiness-sources-2026-09-22.json).
- [26 ejecuciones con la regla de vigencia confirmada](evidence/cost-detail-readiness-asof-2026-09-22.json).
- [Cuatro respuestas del servicio publicado](evidence/cost-detail-readiness-live-2026-09-22.json).
- [Contraste independiente con capturas locales](evidence/cost-detail-readiness-model-2026-09-22.json).
- [Manifiesto de revisión de insumos](evidence/cost-detail-input-health.manifest.json) y [resultado](evidence/cost-detail-input-health.result.json): seis controles estructurales `OK`. Este estado acredita únicamente los controles del manifiesto, no disponibilidad operativa de la API.

Las capturas originales y la instantánea local conservaron sus archivos. La instantánea denominada septiembre contiene costos fijos con fecha agosto, copiados por su generador; conforme a la regla confirmada, esa fecha anterior no implica caducidad. El hash de la instantánea coincide con su manifiesto original.

Resultado operativo: **cálculo local disponible para los casos probados; entrega publicada pendiente de corregir selección de vigencia y salida del desglose**. No se realizaron despliegues ni cambios en Supabase.
