# Referencia técnica de endpoints

## Base URL

Define tu base URL según el entorno de despliegue.

Ejemplos:

- `http://localhost:8000`
- `https://sicetac-api-mcp.onrender.com`

## Modelo de entrada

El cuerpo base de consulta está definido en `ConsultaInput` dentro de `sicetac_service.py`.

Campos relevantes:

- `origen`
- `destino`
- `codigo_dane_origen`
- `codigo_dane_destino`
- `vehiculo`
- `mes`
- `carroceria`
- `tipo_contenedor`: solo para `carroceria = Portacontenedores`; admite `CARGADO` o `VACIO` y se consulta siempre con `modo_viaje = CARGADO`.
- `viaje_redondo`: calcula ida cargada y regreso con contenedor vacío; solo con `resumen = true`.
- `tipo_contenedor_regreso`: para `viaje_redondo`, debe ser `VACIO` (es el valor por defecto).
- `rutasid_ida`, `rutasid_regreso`: selección de variante SICETAC cuando un tramo tiene más de una ruta disponible.
- `modo_viaje`
- `resumen`
- `manual_mode`
- `valor_peaje_manual`
- `valor_peajes_manual`
- `horas_logisticas`
- `horas_logisticas_personalizadas`
- `tarifa_standby`
- `km_plano`
- `km_ondulado`
- `km_montañoso`
- `km_montanoso`
- `km_urbano`
- `km_despavimentado`
- `modo_tiempos_logisticos`
- `modo_aumento`: activa la comparación de H4 y H8 contra el corte SICETAC `202512`.
- `peajes`
- `incluir_peajes`
- `detalle_peajes`

Defaults importantes:

- `vehiculo`: `C3S3`
- `carroceria`: `GENERAL`
- `modo_viaje`: `CARGADO`
- `resumen`: `true`
- `modo_aumento`: `false`
- `tarifa_standby`: `150000`
- `peajes`, `incluir_peajes`, `detalle_peajes`: `false`

## Rangos livianos vigentes desde 2026-08-01

La API expone estas cuatro opciones en `GET /opciones/vehiculos`, en este orden:

| Código API | Rango PBV | Configuración oficial SICETAC |
| --- | --- | --- |
| `CA` | Camioneta: 3.500–5.000 kg | `CA_35_5` |
| `C257` | Camión dos ejes liviano: 5.001–7.000 kg | `2_5_7` |
| `C279` | Camión dos ejes liviano: 7.001–9.000 kg | `2_7_9` |
| `C2910` | Camión dos ejes liviano: 9.001–10.500 kg | `2L1 Liviano entre 9 y 10.5 Tonel.` |

Para estos rangos, `resumen: true` entrega el consolidado oficial de agosto.
El modo detallado requiere parámetros normativos por vehículo; mientras esos
parámetros no sean publicados, responde `503` con una indicación explícita en
lugar de calcular un valor no oficial.

Para diferenciar la operación de contenedor vacío del viaje vacío del vehículo:

```json
{
  "modo_viaje": "CARGADO",
  "carroceria": "Portacontenedores",
  "tipo_contenedor": "VACIO"
}
```

Esta combinación usa la serie oficial `Contenedor vacío / PORTACONTENEDORES` y no devuelve `valor_plaza`.
Está disponible en la respuesta de resumen (`resumen: true`); la respuesta detallada se mantiene bloqueada para no mezclar esa serie con el cálculo genérico.

## Viaje redondo con contenedor vacío de regreso

Use `viaje_redondo: true`. La API calcula la ida con contenedor cargado e invierte automáticamente la ruta para el regreso con contenedor vacío; ambos tramos se consultan con `modo_viaje: CARGADO`.

```json
{
  "origen": "Bogotá",
  "destino": "Medellín",
  "vehiculo": "C3S3",
  "carroceria": "Portacontenedores",
  "modo_viaje": "CARGADO",
  "viaje_redondo": true,
  "tipo_contenedor": "CARGADO",
  "tipo_contenedor_regreso": "VACIO",
  "resumen": true
}
```

La respuesta conserva `ida` y `regreso`, y suma sus escenarios `H2`, `H4` y `H8` en `totales`. El regreso no incluye valor en plaza.
Si la ruta tiene variantes, la primera respuesta trae `requiere_seleccion_ruta: true` y las alternativas de cada tramo; reintenta indicando `rutasid_ida` y `rutasid_regreso`.

## `POST /consulta`

Endpoint principal.

### Uso

- resumen si `resumen = true`
- detalle si `resumen = false`

### Modo aumento

Envíe `modo_aumento: true` para que el resumen incluya `aumento`, con los
valores actuales y de diciembre de 2025, diferencia en pesos y `aumento_pct`
para H4 y H8. Está habilitado para C2, C3, C2S2, C2S3, C3S2 y C3S3 y requiere
`resumen: true`.

La API es stateless: un cliente conversacional que quiera mantener el modo
activo debe reenviar `modo_aumento: true` en cada consulta. Para apagarlo,
envíe `modo_aumento: false` (o simplemente omita el campo en la consulta
normal). La respuesta activa incluye el mensaje de estado correspondiente.

Ejemplo:

```json
{
  "origen": "Bogotá",
  "destino": "Medellín",
  "vehiculo": "C3S3",
  "resumen": true,
  "modo_aumento": true
}
```

La respuesta agrega:

```json
{
  "aumento": {
    "activo": true,
    "periodo_base": 202512,
    "periodo_actual": 202608,
    "aumento_pct": {"H4": 12.34, "H8": 11.98},
    "horas": {
      "H4": {"valor_base": 100, "valor_actual": 112.34, "aumento_cop": 12.34, "aumento_pct": 12.34},
      "H8": {"valor_base": 120, "valor_actual": 134.38, "aumento_cop": 14.38, "aumento_pct": 11.98}
    }
  }
}
```

### Ejemplo

```json
{
  "origen": "Bogotá",
  "destino": "Medellín",
  "vehiculo": "C3S3",
  "mes": 202504,
  "carroceria": "GENERAL",
  "resumen": true,
  "peajes": true
}
```

### Respuesta típica

```json
{
  "origen": "Bogotá",
  "destino": "Medellín",
  "configuracion": "C3S3",
  "mes": 202504,
  "carroceria": "GENERAL",
  "modo_viaje": "CARGADO",
  "totales": {
    "H2": 123456,
    "H4": 234567,
    "H8": 345678
  },
  "resolved_route": {
    "codigo_dane_origen": "11001000",
    "codigo_dane_destino": "5001000",
    "origen_nombre": "BOGOTÁ, D.C.",
    "destino_nombre": "MEDELLIN",
    "route_code": "11001000-5001000"
  },
  "peajes_resumen": {
    "cantidad_peajes": 14,
    "total_peajes": 869600
  },
  "peajes_detalle": {
    "id_sice": 93,
    "configuracion": "C3S3",
    "detalle": []
  }
}
```

### Opción `peajes`

Si se envía `peajes: true`, `incluir_peajes: true` o `detalle_peajes: true`, la consulta adjunta el detalle normalizado de peajes para la ruta y configuración consultada.

- Si la respuesta trae una sola ruta, se agregan `peajes_resumen` y `peajes_detalle` en la raíz.
- Si la respuesta trae `variantes`, cada variante con `ID_SICE` recibe sus propios `peajes_resumen` y `peajes_detalle`.
- `peajes_resumen.total_peajes` es el total de peajes para la configuración solicitada.
- `peajes_detalle.detalle[]` contiene la lista ordenada de peajes con categoría
  máxima, categoría nominal, categoría efectiva, razón de selección/ausencia,
  valores originales y valor.
- `peajes_detalle.auditoria` informa la versión de regla, corte/archivo de
  fuente, filas recibidas y casetas únicas. Si existía un resumen anterior,
  informa `total_anterior`, `diferencia_vs_anterior` y `discrepante`; ese valor
  anterior no se suma ni reemplaza el total por caseta.

La regla vigente es `sicetac-peajes-caseta-v2-relative-max`. El vínculo de ruta
identifica el `ID_PEAJE` y el catálogo crudo `VALOR1` ... `VALOR7` se consulta
por caseta. Se calcula la categoría máxima disponible en cada peaje. Cuando el
máximo es V, `2`, `3`, `2S2`, `2S3`, `3S2` y `3S3` apuntan respectivamente a
II, III, III, IV, IV y V; con máximos VI o VII, el patrón se desplaza. Si la
categoría objetivo está fuera de rango o tiene valor cero, no se hace fallback
a otra categoría: el valor de esa caseta es cero y la razón queda auditada. Un
peaje cuyo máximo es únicamente I tampoco se aplica a estas configuraciones de
carga.
Las casetas duplicadas se cuentan una vez.

La validación de referencia de la ruta `12736` (Guadalajara de Buga–Funza,
corte 2026-08-01) produce `$194.800`, `$467.600`, `$467.600`, `$648.800`,
`$648.800` y `$732.900` para `2`, `3`, `2S2`, `2S3`, `3S2` y `3S3`.

## `POST /consulta_resumen`

Versión explícita de resumen.

### Uso recomendado

- clientes que solo necesitan `H2`, `H4`, `H8`
- integraciones donde quieres un contrato más acotado

## `POST /consulta_texto`

Devuelve un texto corto listo para canales conversacionales.

### Respuesta ejemplo

```json
{
  "texto": "Bogotá->Barranquilla C3S3 H2 $7.398.537, H4 $7.571.997, H8 $7.918.917, peajes $869.600 (14 peajes)"
}
```

## `GET /peajes/detalle`

Devuelve el detalle de peajes de una ruta SICE desde la capa normalizada vigente.

Parámetros query:

- `id_sice`: ID de ruta SICE.
- `configuracion`: opcional. Acepta `2`, `3`, `C2S2`, `C2S3`, `C3S2`, `C3S3`. También normaliza `2S2`, `2S3`, `3S2`, `3S3`.

Ejemplo:

```bash
curl "http://localhost:8000/peajes/detalle?id_sice=93&configuracion=C3S3"
```

Respuesta resumida:

```json
{
  "id_sice": 93,
  "mes": 202607,
  "nombre_ruta": "BOGOTÁ _ BARRANQUILLA",
  "configuracion": "C3S3",
  "resumen": {
    "C3S3": {
      "cantidad_peajes": 14,
      "total_peajes": 869600
    }
  },
  "detalle": [
    {
      "orden": 1,
      "id_peaje": "50",
      "nombre_peaje": "SIBERIA",
      "categoria_maxima_disponible": "VII",
      "valores": {
        "C3S3": 62700
      },
      "categorias": {
        "C3S3": {
          "categoria_usada": "VII",
          "configuracion_sicetac": "3S3"
        }
      }
    }
  ]
}
```

## `GET /health`

Health check simple.

### Respuesta

```json
{
  "status": "ok"
}
```

## `POST /refresh`

Fuerza recarga de cache.

### Respuesta

```json
{
  "status": "ok",
  "refreshed": true
}
```

## `POST /snapshot/generate`

Genera un snapshot consolidado y lo publica en el bucket `snapshots`.

### Respuesta esperada

```json
{
  "ok": true,
  "file": "sicetac_snapshot_202504_all.xlsx",
  "url": "https://..."
}
```

## Códigos de error

### `404`

Usualmente asociado a:

- origen o destino no encontrado
- ruta no disponible para la combinación consultada

### `500`

Usualmente asociado a:

- tablas vacías
- problema de conexión a Supabase
- error inesperado en el cálculo o exportación

## Variables de entorno relevantes

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_KEY`
- `CORS_ORIGINS`
- `SICETAC_CACHE_TTL_SECONDS`
- `SICETAC_TABLE_MUNICIPIOS`
- `SICETAC_TABLE_VEHICULOS`
- `SICETAC_TABLE_PARAMETROS`
- `SICETAC_TABLE_COSTOS_FIJOS`
- `SICETAC_TABLE_PEAJES`
- `SICETAC_TABLE_PEAJES_DETALLE`
- `SICETAC_TABLE_PEAJES_RESUMEN`
- `SICETAC_TABLE_PEAJES_INVENTARIO`
- `SICETAC_TABLE_RUTAS`
- `SICETAC_TABLE_SICETAC_VACIO`

`modo_viaje=VACIO` usa la capa `sicetac_vacio_vigentes` y responde con
`metodo=lookup_vacio_oficial` cuando existe una coincidencia oficial. La
carrocería se conserva; no se normaliza a `GENERAL`.

## MCP

Servidor:

```bash
python mcp_server.py
```

Tool disponible:

- `calcular_sicetac_tool`

Parámetros principales del tool:

- `origen`
- `destino`
- `vehiculo`
- `mes`
- `carroceria`
- `modo_viaje`
- `resumen`

Si no se envía `mes`, el tool usa el más reciente disponible en `parametros_vigentes`.
