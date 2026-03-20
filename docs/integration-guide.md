# Guía rápida de integración

## 1. Requisitos mínimos

- acceso al endpoint base de la API
- credenciales de Supabase configuradas en el servidor
- conectividad desde la app cliente

## 2. Endpoint recomendado para empezar

Para la mayoría de integraciones, empieza con:

- `POST /consulta`

Usa `resumen: true` para obtener una respuesta compacta y estable.

## 3. Payload mínimo

### Por nombre

```json
{
  "origen": "Bogotá",
  "destino": "Medellín",
  "vehiculo": "C3S3",
  "resumen": true
}
```

### Por código DANE

```json
{
  "codigo_dane_origen": "11001000",
  "codigo_dane_destino": "5001000",
  "vehiculo": "C3S3",
  "resumen": true
}
```

## 4. Respuesta esperada

Ejemplo resumido:

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
    "route_code": "11001000-5001000"
  }
}
```

## 5. Cuándo usar cada endpoint

### `POST /consulta`

Usa este endpoint si necesitas:

- resumen por defecto
- detalle con `resumen: false`
- un endpoint único para la mayoría de clientes

### `POST /consulta_resumen`

Úsalo si quieres fijar explícitamente que siempre consumirás salida resumida.

### `POST /consulta_texto`

Úsalo para:

- agentes
- WhatsApp
- bots
- respuestas cortas para frontends conversacionales

### `POST /snapshot/generate`

Úsalo para generar un consolidado exportable a Excel y publicarlo en el bucket configurado.

## 6. Recomendación por tipo de consumidor

### Sistema transaccional

- llamar `POST /consulta`
- guardar `resolved_route`
- almacenar `mes`, `vehiculo` y `totales`

### Dashboard o BI

- consumir `POST /consulta`
- usar `resumen: true`
- normalizar `H2`, `H4`, `H8` como métricas

### Agente o asistente

- usar `POST /consulta_texto` para salida directa
- o `POST /consulta` si el agente necesita razonamiento adicional sobre el JSON

### MCP

- ejecutar `python mcp_server.py`
- invocar `calcular_sicetac_tool`

## 7. Recomendaciones de integración

- enviar siempre `vehiculo` explícito aunque exista default
- enviar `mes` explícito si quieres reproducibilidad
- usar código DANE cuando el origen y destino vengan de sistemas estructurados
- usar nombre cuando el input venga de usuarios humanos
- guardar el `route_code` resuelto para auditoría y trazabilidad

## 8. Errores comunes

- municipio no encontrado
- tablas vacías o conexión a datos no disponible
- combinación de ruta no encontrada
- payload incompleto o con tipos no compatibles

## 9. Ejemplo con cURL

```bash
curl -X POST http://localhost:8000/consulta \
  -H "Content-Type: application/json" \
  -d '{
        "origen": "Bogotá",
        "destino": "Barranquilla",
        "vehiculo": "C3S3",
        "mes": 202504,
        "resumen": true
      }'
```

## 10. Ejemplo con Node

```bash
SICETAC_API_URL="https://sicetac-api-mcp.onrender.com" node agent_client.js "Bogotá" "Barranquilla"
```
