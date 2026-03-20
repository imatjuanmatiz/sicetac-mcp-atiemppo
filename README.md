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
- Resolución por nombre o código DANE
- Respuesta compacta para agentes y WhatsApp
- Servidor MCP para herramientas agentic
- Generación de snapshot consolidado a Excel

## Endpoints principales

- `POST /consulta`
- `POST /consulta_resumen`
- `POST /consulta_texto`
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
- `SICETAC_TABLE_RUTAS`

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
