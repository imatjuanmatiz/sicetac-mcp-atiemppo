# API SICETAC

Esta API expone el cálculo de costos operativos bajo la metodología SICETAC y lo vuelve consumible para sistemas, integraciones y agentes.

Su foco no es solo responder una consulta puntual. Su foco es permitir que una empresa conecte comercial, operación, finanzas y asistentes internos a una misma base de referencia.

## Documentación

- [Resumen del producto y arquitectura](docs/overview.md)
- [Guía rápida de integración](docs/integration-guide.md)
- [Referencia técnica de endpoints](docs/api-reference.md)
- [Estructura interna del modelo](MODEL_STRUCTURE.md)

## Qué incluye hoy

- API HTTP con FastAPI
- Resumen y detalle de cálculo SICETAC
- Detalle de peajes por ruta y configuración
- Resolución por nombre o código DANE
- Respuesta compacta para agentes y WhatsApp
- Servidor MCP para herramientas agentic
- Generación de snapshot consolidado a Excel

## Endpoints principales

- `POST /consulta`
- `POST /consulta_resumen`
- `POST /consulta_texto`
- `GET /peajes/detalle`
- `POST /refresh`
- `POST /snapshot/generate`
- `GET /health`

## Arranque rápido

Instalación:

```bash
pip install -r requirements.txt
```

Ejecución local:

```bash
uvicorn main:app --reload
```

Health check:

```bash
curl http://localhost:8000/health
```

Consulta rápida:

```bash
curl -X POST http://localhost:8000/consulta \
  -H "Content-Type: application/json" \
  -d '{
        "origen": "Bogotá",
        "destino": "Medellín",
        "vehiculo": "C3S3",
        "mes": 202504,
        "resumen": true
      }'
```

Para comparar H4 y H8 contra diciembre de 2025, agrega `"modo_aumento": true`.
El cliente debe reenviar ese indicador mientras el modo esté activo y enviarlo
como `false` cuando el usuario indique “modo aumento off”.

Consulta rápida con detalle de peajes:

```bash
curl -X POST http://localhost:8000/consulta \
  -H "Content-Type: application/json" \
  -d '{
        "origen": "Bogotá",
        "destino": "Barranquilla",
        "vehiculo": "C3S3",
        "resumen": true,
        "peajes": true
      }'
```

## Variables mínimas de entorno

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` o `SUPABASE_KEY`

Variables útiles:

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
- `SICETAC_TABLE_SICETAC_VACIO` (por defecto `sicetac_vacio_vigentes`)

Cuando `modo_viaje=VACIO`, la API consulta la tabla oficial vigente por ruta,
configuración y carrocería. Este modo representa un vehículo sin carga; un
contenedor vacío transportado sigue siendo una operación `CARGADO`.

Para un portacontenedores, declara `tipo_contenedor` como `CARGADO` o `VACIO`.
La segunda opción usa la serie SICETAC oficial de contenedor vacío y no aplica
valor en plaza. Para un viaje redondo usa `viaje_redondo: true`: la API calcula
la ida cargada, invierte la ruta y calcula el regreso con contenedor vacío.
Cuando una dirección tiene variantes SICETAC, la respuesta solicita
`rutasid_ida` y `rutasid_regreso` para que el consumidor seleccione cada ruta.

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

## Agentes

Cliente Node de ejemplo:

```bash
SICETAC_API_URL="https://sicetac-api-mcp.onrender.com" node agent_client.js "Bogotá" "Barranquilla"
```

Servidor MCP:

```bash
python mcp_server.py
```

Tool principal:

- `calcular_sicetac_tool`

## Licencia y uso

Esta API fue desarrollada por IMETRICA para análisis y simulación de costos de transporte terrestre en Colombia, integrando fuentes oficiales y datos de operación real.
