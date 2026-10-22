# Contrato de búsqueda SICETAC

Un solo proceso. Grok Bot, OpenClaw o el agente de otro cliente son canales.
La única pieza que cambia por cliente es la **clave** (`SICETAC_API_KEY`) y su
`consumer_id` / cuota. No se clona el cálculo ni se arma una tabla paralela de
ciudades o vehículos.

Instant no usa este contrato: allí el usuario ya eligió en listas. Su API
(`/api/route`) sí es el paso 2 del agente de búsqueda (ver abajo).

## Dos oficios, dos agentes

| Agente | Oficio | Qué entrega |
|---|---|---|
| **Búsqueda** | Entender el pedido suelto y consultar el motor | Ficha: ruta + H4 + valor en plaza |
| **Cotización documento** | Tomar la ficha (y reglas comerciales del cliente) y armar la oferta | Documento / PDF / Word de cotizados |

El de búsqueda **no** calcula precio de venta, no pone margen, no arma el documento
ni promete cupo. Sí devuelve una base de precotización técnica y de mercado
para que ventas aplique reglas aprobadas del cliente. El de documento **no** llama al catálogo a adivinar la ruta:
parte de `data.search` ya resuelta.

## Qué hace el de búsqueda

1. Entiende origen, destino, vehículo/configuración y si es carga general o contenedor.
2. Envía los términos **tal cual** los dijo el usuario. El Core homologa.
   En contenedor, si no hay configuración declarada, deja que las reglas
   publicadas elijan: 20 pies inicia C2S2; 40 pies inicia C2S3.
3. Paso 1, motor: `POST /v1/prequotes` con `view=search`. Clasifica el vehículo
   y define qué calcular.
4. Paso 2, SICETAC al Instante: `POST https://sicealinstante.vercel.app/api/route`
   con esa configuración y carrocería, `detalle_consumo=true` y `detalle_costos=true`.
5. Presenta `data.search` y, cuando lo pidan o se comparen rutas, el desglose de Instant.
Una corrida por solicitud (una llamada a cada uno por escenario), sin reintentos.

## Horas
Default 4 (H4). El usuario puede pedir 2, 8 u otra cifra; el agente la envía
en `horas_logisticas` y la **conserva en el hilo** hasta que pida otra.
La ficha presenta solo esa hora, no el menú H2/H4/H8.

## Ficha (`data.search`)

- `ruta` — `NOMBRE_SICE`
- `configuracion` — la que usó el motor
- `kilometros` — distancia de la ruta seleccionada
- `estimado` y `supuestos` — mostrar explícitamente en rutas urbanas
- `horas_logisticas` + `horas_etiqueta` + `sicetac` (valor de esa hora)
- `sicetac_corte`
- `valor_plaza` + `valor_plaza_corte` (null → “sin valor en plaza”; contenedor vacío → siempre sin valor en plaza)
- `capacidad` — máximo de mercancía y compatibilidad SICE cuando haya regla y peso
- tiempos: motor y SICETAC al Instante, por separado

Fuera de la ficha: cálculos de tara, PBV, H2/H8 y alternativas. La capacidad
neta de mercancía sí está disponible para ventas; `capacidad.regla_provisional`
debe comunicarse cuando sea verdadera. No se valida PBV legal porque no se
conoce la tara real del vehículo.

**Detalle de costos y de consumo (27 sep 2026):** siempre por SICETAC al Instante
con `detalle_consumo=true` y `detalle_costos=true` (ver D abajo). Reemplaza el uso
anterior de `view=costs` / `view=consumption` del motor para el desglose. Nunca
`/consulta` directo, `/consulta_resumen` ni `/consulta_texto`. Se muestra un único
total del viaje (la referencia de la hora acordada, H4 por defecto); nunca la suma
de los componentes. Si la referencia es estimada, mostrarlo explícitamente.
Ver [contrato del detalle](../cost-details.md) para los campos del desglose.

## Qué cambia al crear otro agente

| Cambia | No cambia |
|---|---|
| Clave en el almacén secreto | Prompt de búsqueda (esta plantilla) |
| Nombre visible / a quién reporta | `view=search` y el formato de ficha |
| Cuota y vencimiento del consumidor | Equivalencias (viven en el Core) |
| | El oficio: no se vuelve cotizador-documento |

## Secretos

```text
SICETAC_API_BASE_URL=https://sicetac-api-mcp.onrender.com
SICETAC_API_KEY=<clave-individual-de-ese-consumidor>
```

Nunca en el prompt, el repo, el chat ni una captura. Cada cliente o canal
tiene su clave. No reutilizar la de ATICA.

## Prompt canónico

Copiar [PROMPT-AGENTE-BUSQUEDA.md](PROMPT-AGENTE-BUSQUEDA.md). Rellenar nombre
y cliente. No editar el bloque de herramienta ni el formato de éxito.

## Reglas 27 sep 2026 (ajustadas el 21 oct 2026) — prevalecen si algo anterior choca

### A. Flujo de dos pasos
1. **Motor** (`POST /v1/prequotes`): clasifica el vehículo (configuración + carrocería), aplica la capacidad de carga publicada y define qué calcular. Da la referencia H4.
2. **SICETAC al Instante** (`POST https://sicealinstante.vercel.app/api/route`): resuelve la ruta con esa configuración (`vehiculo`) y esa carrocería (`carroceria`) y trae el desglose.
Una corrida por solicitud: una llamada al motor y una a Instant por escenario; sin reintentos. Instant se ejecuta sin pedir autorización cada vez.

### B. Clasificación del vehículo con contenedor
- El perfil vigente calcula `automatic_configuration_by_size_ft` desde las reglas publicadas: **20 pies → 2S2; 40 pies → 2S3**.
- Si el usuario declara una configuración, se conserva; no se pregunta su peso.
- Sin configuración declarada, 20 pies inicia en 2S2 y escala por capacidad publicada: 2S2 → 2S3 → 3S2 → 3S3. 40 pies inicia en 2S3 y escala: 2S3 → 3S2 → 3S3.
- En contenedor sin peso usa el default por tamaño y deja capacidad sin validar; no preguntes peso para obtener la referencia inicial. En carga general sin configuración, el peso sí es necesario.
- Carrocería `Portacontenedores` en toda operación con contenedor (motor e Instant).

### C. Peso y tara
- Usa `peso_carga_t`, `pies_contenedor` y `peso_incluye_tara` cuando estén disponibles; el motor aplica la tara publicada del contenedor al seleccionar configuración.
- Devuelve `pbv_assessment=requires_vehicle_tare`. El peso de carga no es el PBV y el sistema no conoce la tara real del vehículo: **no valides ni afirmes cumplimiento de PBV legal**.
- Las reglas y capacidades de selección son provisionales; comunica la capacidad neta y el estado de compatibilidad que entregue el motor, advirtiendo cuando la regla sea provisional. No muestres cálculos de tara salvo que el usuario los pida.

### D. Detalle de consumo y costos (siempre por SICETAC al Instante)
- `POST https://sicealinstante.vercel.app/api/route` con `origen`, `destino`, `vehiculo` (configuración del paso 1), `carroceria`, `detalle_consumo=true` y `detalle_costos=true`.
- Reportar: precio del ACPM por galón, galones totales, rendimiento y km por terreno (plano, ondulado, montaña, urbano, despavimentado), combustible, mantenimiento, costo fijo, peajes, otros e imprevistos.
- Total visible del viaje = la referencia H4 (o la hora acordada); nunca la suma de los componentes del desglose.
- **Nunca** usar la consulta antigua de cálculo completo (`/consulta`) directo, ni `/consulta_resumen` ni `/consulta_texto`. Para el desglose tampoco se usa `view=costs` / `view=consumption` del motor: lo reemplaza Instant.
- Viaje vacío (`tipo_contenedor=VACIO`): Instant responde 400 «tipo_contenedor está disponible con resumen=true; el detalle del modelo aún no incorpora esta serie oficial». Entonces reportar el total del motor y avisar que el consumo del vacío solo está en resumen. **No** hacer pasar el desglose en cargado por el del vacío.

### E. Regreso de contenedor vacío = viaje redondo
- Contenedor que regresa VACIO: viaje redondo (ida cargada + regreso vacío), `viaje_redondo=true`, `tipo_contenedor_regreso=VACIO`; ida en `CARGADO`, nunca `modo_viaje VACIO`.
- El contenedor vacío **no tiene valor en plaza**: decir «sin valor en plaza (contenedor vacío)»; no buscarlo ni poner cero.
- El desglose de Instant cubre solo la ida cargada y se etiqueta así; para el regreso vacío aplica la regla del 400 (punto D).

### F. Eficiencia al comparar rutas
- Por ruta: **costo H4 por km** (H4 ÷ km), **galones por km** (galones ÷ km, del detalle Instant) y **peajes por km** (peajes ÷ km); no solo el costo absoluto.
- Si hay valor en plaza: **prima frente al H4** = (plaza − H4) ÷ H4, en %.
- Advertencia obligatoria: el costo fijo y las horas logísticas repartidos en más km bajan el costo por km sin que la ruta sea más eficiente; mirar también galones/km y peajes/km.

### G. Tiempos de respuesta
En cada caso, reportar por separado el tiempo del motor y el de SICETAC al Instante (en segundos). No sumarlos en un solo tiempo.
