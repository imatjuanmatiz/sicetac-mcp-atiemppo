# Resumen del producto y arquitectura

## Qué es

La API SICETAC es una capa de servicios para consultar y distribuir valores de referencia de transporte bajo metodología SICETAC.

Está pensada para tres tipos de consumo:

- sistemas internos como TMS, CRM, ERP o dashboards
- agentes y asistentes conversacionales
- procesos de análisis, control y automatización

## Qué problema resuelve

En muchas empresas, la referencia SICETAC sigue viviendo en consultas manuales, archivos dispersos o conocimiento individual.

Esta API convierte esa consulta en una capacidad reusable:

- una misma lógica para comercial, operación y finanzas
- una misma entrada para sistemas y agentes
- una base consistente para análisis, seguimiento y automatización

## Componentes principales

### API HTTP

Archivo principal:

- `main.py`

Expone endpoints para:

- consulta resumida
- consulta detallada
- respuesta en texto corto para agentes
- health checks
- recarga de cache
- generación de snapshot consolidado

### Servicio de cálculo

Archivo principal:

- `sicetac_service.py`

Responsable de:

- validar input
- resolver municipios por nombre o código DANE
- obtener rutas, peajes, parámetros y costos
- ejecutar el cálculo SICETAC
- producir respuesta resumida o detallada

### MCP para agentes

Archivo principal:

- `mcp_server.py`

Expone la herramienta:

- `calcular_sicetac_tool`

Sirve para integrar el cálculo en asistentes o flujos agentic compatibles con MCP.

### Cliente de ejemplo

Archivo:

- `agent_client.js`

Demuestra un consumo mínimo del endpoint `/consulta`.

## Fuentes de datos esperadas

La API consume tablas con información mínima de:

- municipios
- rutas
- vehículos
- peajes
- parámetros
- costos fijos

Por defecto esas tablas se leen desde Supabase.

## Lógica general de una consulta

1. entra una solicitud con origen/destino o códigos DANE
2. se resuelve la ruta efectiva
3. se identifica la configuración vehicular y parámetros del mes
4. se obtienen peajes y distancias
5. se ejecuta el modelo
6. se devuelve resumen o detalle

## Modos de salida

### Resumen

Pensado para apps, dashboards o agentes.

Devuelve totales para escenarios logísticos típicos:

- `H2`
- `H4`
- `H8`

### Detalle

Pensado para análisis más completos.

Se obtiene enviando:

```json
{
  "resumen": false
}
```

### Texto corto

Pensado para WhatsApp o asistentes de respuesta rápida.

Se obtiene por:

- `POST /consulta_texto`

## Consideraciones operativas

- la cache de índices se refresca automáticamente según TTL
- se puede forzar con `POST /refresh`
- si no se envía `mes`, se usa el más reciente disponible
- la API soporta integración por HTTP y por MCP
