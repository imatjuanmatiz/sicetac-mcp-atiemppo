# Contrato ATICA — búsqueda SICETAC (2026-09-19, actualizado 2026-10-21)

Instancia ATICA del contrato genérico
[CONTRATO-BUSQUEDA-SICETAC.md](CONTRATO-BUSQUEDA-SICETAC.md).
Otro cliente: copiar el prompt genérico y cambiar la clave, no este archivo.

Canal conversacional (Grok Bot, OpenClaw, el que venga). Instant como canal no aplica:
allí el usuario ya eligió en listas (su API `/api/route` sí es el paso 2).

## Oficio
Entender origen, destino, vehículo/configuración y servicio. El motor calcula.
La búsqueda devuelve la ficha, no un proceso de selección ni un análisis de tara.

## Llamada
Dos pasos, una corrida sin reintentos:
1. Motor: `POST /v1/prequotes` con `view=search` — clasifica el vehículo y define qué calcular.
2. SICETAC al Instante: `POST https://sicealinstante.vercel.app/api/route` con la configuración y la carrocería del paso 1, `detalle_consumo=true` y `detalle_costos=true` — resuelve la ruta y trae el desglose.
Detalle en «Reglas 27 sep 2026» abajo.

Términos del usuario tal cual (`patineta`, `ZF Santander`, `C2S2`). El Core
homologa. El helper confirma DANE.

## Ficha (`data.search`)
- `ruta` — NOMBRE_SICE
- `configuracion` — la que usó el motor
- `sicetac_h4` + `sicetac_corte`
- `valor_plaza` + `valor_plaza_corte` (null → “sin valor en plaza”)
- `capacidad` — máximo neto de mercancía y compatibilidad cuando estén disponibles

## Fuera de la búsqueda
Los cálculos de tara, PBV, H2/H8, alternativas de ruta y `market_analysis`.
Eso es `view=detail`, solo si el usuario lo pide. La capacidad neta de mercancía
sí se muestra para ventas; si `capacidad.regla_provisional` es verdadera,
advierte que requiere validación operativa. No se valida PBV legal: el sistema
no conoce la tara real del vehículo.
En la ficha van también los tiempos del motor y de Instant por separado.

## No es
Oferta, tarifa comercial ni disponibilidad de vehículo.

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
