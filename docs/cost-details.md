# Detalles del modelo de costos

Versión API 2.5.3, puente MCP 1.2.0; publicación de septiembre de 2026.

La consulta habitual conserva la búsqueda de movilización publicada más horas
logísticas y añade `total_km` (`kilometros` en `data.search`). El modelo completo
es un cálculo independiente con sus propios componentes y total.

## Acciones

- WhatsApp: escribir **detalle de costos Bogotá a Barranquilla C3S3**, o
  después de consultar una ruta, escribir **detalle de costos** o
  **detalle de consumo**. Conserva vehículo, carrocería, modo, mes, variante y
  horas de la consulta. Sin una hora indicada, usa cuatro horas logísticas.
- Web Instant: los botones de cada ruta llaman al mismo modelo de la API.
- MCP: `detalle_costos_sicetac` y `detalle_consumo_sicetac`.
- API: `POST /consulta` o `/v1/quotes` con `detalle_costos: true` o
  `detalle_consumo: true` (también `resumen: false`).
- Agentes con homologación de términos: `POST /v1/prequotes`, `view: costs`
  o `view: consumption`. La vista `detail` conserva la consulta habitual.

El cuerpo de la solicitud conserva origen, destino, vehículo, carrocería,
modo de viaje, mes, `rutasid` cuando se seleccionó una variante y
`horas_logisticas`. No se utiliza el total publicado como entrada del modelo.

## Salida

Ambos detalles, incluso solicitados directamente sin una consulta previa,
incluyen `sicetac_tradicional`: `total_viaje`, `totales`, `horas_logisticas`,
`mes`, `rutasid`, `metodo` y `estimado`. Este total se obtiene por el proceso
habitual para la misma ruta, variante, vehículo, carrocería y horas (cuatro por
defecto). Para horas personalizadas se aplica movilización + horas × valor hora.
Se muestra como **único total del viaje**. El total del modelo se conserva
solo en la respuesta técnica para auditoría y compatibilidad; no se presenta
al usuario ni se reemplaza el total habitual por la suma del desglose. Si el
proceso habitual recurre al modelo por falta de tarifa publicada, se identifica
como estimado; los urbanos conservan el supuesto de 30 km ondulados.
En `view=costs/consumption`, `data.search.sicetac` usa este total habitual.

`detalle_costos` contiene galones, horas de recorrido/logística/totales,
rotaciones mensuales calculadas, costo fijo del viaje, costos variables y
otros costos. El subtotal variable incluye combustible, peajes, mantenimiento
e insumos, e imprevistos. Internamente, total del modelo = fijos + variables +
otros; sus componentes no se suman nuevamente. El total visible siempre es el
de `sicetac_tradicional`.

`detalle_consumo.por_terreno` incluye plano, ondulado, montaña, urbano y
despavimentado: km, velocidad (km/h), rendimiento (km/galón), horas, galones y
costo de combustible. También informa precio por galón, galones totales y
costo total de combustible. Los importes por terreno se redondean a centavos;
la suma puede diferir por centavos del total calculado antes del redondeo.

## Reglas confirmadas

1. Costos fijos: última fila aplicable a vehículo/carrocería con fecha no
   posterior al período del cálculo, vigente hasta reemplazo. La salida conserva
   `mes_costo_fijo` y `costo_fijo_mensual`. No se cambia la fecha en Supabase.
2. Sin registro de peajes: cero. Un registro existente con tarifa incompleta
   sigue produciendo un error, para no confundirlo con ausencia de peajes.
3. Origen y destino resueltos al mismo municipio: modelo con **30 km ondulados**,
   cero peajes, `estimado: true` y `tipo_estimacion: URBANO_30_KM_ONDULADO`.
   Mostrar siempre **VALOR ESTIMADO** y el supuesto de distancia.
4. Vacío sin mercancía: conserva los parámetros VACIO y cero horas logísticas.
5. El detalle de contenedor vacío transportado y el agregado de viaje redondo
   siguen fuera del modelo detallado; requieren sus series específicas. La
   consulta publicada de esos servicios continúa disponible. El contenedor
   cargado puede usar el modelo de Portacontenedores.

## Verificación

Pruebas de contrato, cálculo, consumo, selección de variante, horas cero,
vigencia por carrocería, aislamiento de la consulta publicada y transporte MCP.
Validación adicional con captura de Supabase del 22 de septiembre: 13 vehículos,
cargado/vacío, ruta 93 y recorrido urbano (52 casos), con conciliación de
componentes, kilómetros, galones y combustible.

Ejemplo C3S3 GENERAL cargado, septiembre 2026, cuatro horas logísticas:
Bogotá–Bogotá = 30 km ondulados, 6,25 galones, combustible $72.600,
0,91 h de recorrido, 46,8859 rotaciones/mes, total estimado **$602.128,68**.
