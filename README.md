# API SICETAC - Versión Extendida

Esta API expone un modelo de cálculo de costos operativos bajo la metodología SICETAC (Ministerio de Transporte de Colombia), y lo complementa con datos de mercado y operación real derivados del RNDC.

## 🚀 Endpoints

### POST `/consulta`
Calcula el valor del viaje bajo el modelo SICETAC. Por defecto devuelve un resumen (totales para 2/4/8h logísticas).

El endpoint acepta dos modos compatibles de identificación de ruta:
- por nombre: `origen` y `destino`
- por código DANE textual: `codigo_dane_origen` y `codigo_dane_destino`

Si llegan ambos, la API prioriza los códigos y devuelve la resolución efectiva en `resolved_route`.

#### Body (JSON)
```json
{
  "origen": "Bogotá",
  "destino": "Medellín",
  "vehiculo": "C3S3",
  "mes": 202504,
  "carroceria": "GENERAL",
  "resumen": true,
  "modo_viaje": "CARGADO",
  "valor_peaje_manual": 0,
  "horas_logisticas": null,
  "horas_logisticas_personalizadas": null,
  "tarifa_standby": 150000,
  "km_plano": 0,
  "km_ondulado": 0,
  "km_montanoso": 0,
  "km_urbano": 0,
  "km_despavimentado": 0
}
```

#### Body por código DANE
```json
{
  "codigo_dane_origen": "11001000",
  "codigo_dane_destino": "5001000",
  "vehiculo": "C3S3",
  "mes": 202504,
  "resumen": true
}
```

#### Respuesta (JSON)
```json
{
  "origen": "Bogotá",
  "destino": "Medellín",
  "configuracion": "C3S3",
  "mes": 202504,
  "carroceria": "GENERAL",
  "modo_viaje": "CARGADO",
  "totales": { "H2": 123456, "H4": 234567, "H8": 345678 },
  "resolved_route": {
    "codigo_dane_origen": "11001000",
    "codigo_dane_destino": "5001000",
    "origen_nombre": "BOGOTÁ, D.C.",
    "destino_nombre": "MEDELLIN",
    "route_code": "11001000-5001000",
    "origen_resolution_mode": "name",
    "destino_resolution_mode": "name"
  }
}
```

#### Resumen vs Detalle
- **Resumen (default):** `resumen: true`
- **Detalle completo:** `resumen: false`

---

### POST `/consulta_resumen`
Endpoint explícito de resumen (H2/H4/H8), útil para agentes.

---

### GET `/health`
Devuelve `{"status":"ok"}` para health checks.

---

### POST `/refresh`
Fuerza recarga de cache (rutas/peajes). Útil cuando actualizas tablas.

---

### POST `/consulta_texto`
Devuelve una respuesta corta para WhatsApp/agent.  
Ejemplo:
```json
{"texto":"Bogotá->Barranquilla C3S3 H2 7077856.42, H4 7229067.31, H8 7531476.19"}
```

---

## 📊 Datos utilizados

Solo se usa la información necesaria para el cálculo del modelo (rutas, vehículos, parámetros, costos, peajes, municipios).

---

## 💡 Ejemplo de uso (cURL)
```bash
curl -X POST http://localhost:8000/consulta \
  -H "Content-Type: application/json" \
  -d '{
        "origen": "Bogotá",
        "destino": "Medellín",
        "vehiculo": "3S3",
        "mes": 202504
      }'
```

```bash
curl -X POST http://localhost:8000/consulta \
  -H "Content-Type: application/json" \
  -d '{
        "codigo_dane_origen": "63001000",
        "codigo_dane_destino": "76001000",
        "vehiculo": "C3S3",
        "mes": 202504
      }'
```

---

## 🔐 Configuración Supabase

Variables mínimas:
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` (o `SUPABASE_KEY`)

## 🌐 CORS
Configura orígenes permitidos con:
- `CORS_ORIGINS` (ej: `https://miapp.com,https://otro.com`)  
Por defecto `*`.

## 🧠 Cache
La cache se recarga cada `SICETAC_CACHE_TTL_SECONDS` (default: 7 días).
Puedes forzar recarga con `POST /refresh`.

## 🤖 Cliente Node (agentes)
Ejemplo rápido:
```bash
SICETAC_API_URL="https://sicetac-api-mcp.onrender.com" node agent_client.js "Bogotá" "Barranquilla"
```

Tablas (opcional si usas nombres distintos). Ejemplo:
- `SICETAC_TABLE_MUNICIPIOS`
- `SICETAC_TABLE_VEHICULOS`
- `SICETAC_TABLE_PARAMETROS`
- `SICETAC_TABLE_COSTOS_FIJOS`
- `SICETAC_TABLE_PEAJES`
- `SICETAC_TABLE_RUTAS`

## 📦 Requisitos de entorno

- Python 3.9+
- `pandas`, `fastapi`, `uvicorn`, `supabase`, `mcp`

Instalación:
```bash
pip install -r requirements.txt
```

Ejecución local:
```bash
uvicorn main:app --reload
```

---

## 🤖 MCP (agentes)

Servidor MCP (stdio) para herramientas de agentes:
```bash
python mcp_server.py
```

Tool principal:
- `calcular_sicetac_tool`  
Si no pasas `mes`, se usa el mes más reciente disponible en `parametros_vigentes`.

---

## 📚 Licencia y uso
Esta API fue desarrollada por IMETRICA para el análisis y simulación de costos de transporte terrestre en Colombia, integrando fuentes oficiales y datos de operación real.
