# Instant y motor: helper común y correcciones verificadas

Estado: **código integrado y validado para publicación en GitHub autorizada por Juan**.
La migración municipal sigue **sin ejecutar** y el candidato de bandeja **sin instalar**.
Corte de comprobación: 27 de septiembre de 2026 UTC (26 en Bogotá).
Juan confirmó que el nombre del caso es **Puerto Antioquia**.

## Qué comparten

| Consumidor | Entrada | Resolución municipal |
| --- | --- | --- |
| SICETAC Instant web | Proxy `/api/route` → `/consulta` | `sicetac_service` → `SICETACHelper` → catálogo `municipios` |
| Agente cotizador OpenClaw | `atica_precotizar_api` → `/v1/prequotes` | Equivalencias del ruleset → mismo `sicetac_service` → mismo helper/catálogo |

Ambos repositorios están vinculados al proyecto Supabase `kpdlneddaqvkpwfbqejk`.
El adaptador instalado apunta a `https://sicetac-api-mcp.onrender.com`; ese
servicio también es el destino por defecto del proxy de Instant. No se agregó
una dependencia del motor a Instant. Esto verifica código/configuración local;
no se inspeccionaron variables privadas del despliegue web.

## Hallazgo del catálogo y del helper

La consulta de solo lectura encontró 1.271 registros y 1.271 códigos únicos.
La última actualización de catálogo es del 2 de septiembre de 2026. El ruleset
publicado es `2026.09.17-market.1` y no contiene el alias Puerto Antioquia.

| Nombre publicado | DANE formateado | Variación relevante |
| --- | --- | --- |
| NUEVA COLONIA, Antioquia | `05837002` | NUEVA COLONIA TURBO; variación 2 vacía |
| TURBO, Antioquia | `05837000` | TURBO |
| PUERTO COLOMBIA, Atlántico | `08573000` | PUERTO COLOMBIA |

La sede del puerto está en Nueva Colonia, Turbo, según su
[directorio oficial](https://puertoantioquia.com.co/es/contact).
La equivalencia propuesta se aplica al centro poblado `05837002`, conservando
Turbo cabecera y Puerto Colombia como registros distintos.

Además de faltar el alias publicado, se reprodujo un error del helper:
separaba el sufijo “Antioquia” como departamento antes de intentar una
coincidencia exacta con todo “Puerto Antioquia”. Incluso con el alias añadido
a una copia del catálogo, no lo encontraba. La corrección da prioridad al
nombre/variación completo publicado; después aplica la desambiguación por
departamento y la búsqueda aproximada existentes. No codifica nombres de
puertos ni DANE dentro de la lógica.

## Cambios guardados

- [Helper común](/Users/atiemppoia/codex/SICETAC-API-MCP/sicetac_helper.py): búsqueda
  exacta completa antes de separar departamento.
- [Pruebas compartidas](/Users/atiemppoia/codex/SICETAC-API-MCP/tests/test_shared_municipality_helper.py):
  seis regresiones, incluyendo llamadas locales por ambos endpoints al helper
  real, sin alias portuario dentro del ruleset. El caso sin tarifa usa un
  catálogo de rutas vacío deliberadamente: se valida resolución municipal y
  la brecha de cobertura, no una tarifa real.
- [Migración preparada](/Users/atiemppoia/codex/SICETAC-API-MCP/supabase/migrations/20260927020957_add_puerto_antioquia_municipality_variation.sql):
  añade `PUERTO ANTIOQUIA` en `variacion_2` de Nueva Colonia. Verifica identidad,
  campo disponible y ausencia de colisiones; no sobrescribe datos distintos.
  El preflight de solo lectura encontró exactamente un registro elegible y
  cero conflictos. **No se ejecutó la migración.**
- [Instant: formulario](/Users/atiemppoia/codex/SICETAC-INSTANT/app/page.jsx):
  invalida rutas, resultado y detalle al cambiar el pedido; descarta respuestas tardías;
  elegir contenedor vacío desactiva redondo y elegir redondo fija ida cargada.
- [Instant: proxy](/Users/atiemppoia/codex/SICETAC-INSTANT/app/api/route/route.js):
  rechaza redondo con ida vacía antes de consultar al backend.
- [Mensajes de error](/Users/atiemppoia/codex/SICETAC-INSTANT/app/lib/route-errors.js):
  transforma errores estructurados en texto, evitando el fallo de React.
- [Pruebas de Instant](/Users/atiemppoia/codex/SICETAC-INSTANT/test/route-flow.test.mjs):
  18 casos sobre handlers reales del componente, renderer React y proxy con
  HTTP simulado. Conservan el nombre Puerto Antioquia al delegar al helper,
  el contexto del detalle de costos/consumo y un único total SICETAC.

## Validación y límites

**123/123 pruebas Python, 18/18 pruebas de Instant y build Next.js 16.1.6 exitoso.**
El build final se ejecutó sobre una copia temporal de la versión integrada,
con las mismas dependencias instaladas y descarga de sus Google Fonts.
No se cambiaron las fuentes del producto.

```bash
# Desde SICETAC-API-MCP
.venv/bin/python -m unittest discover -s tests

# Desde SICETAC-INSTANT
node --test test/route-flow.test.mjs
```

Las modificaciones anteriores del catálogo vehicular de Instant se conservaron
y sus 13 códigos se contrastaron con `/opciones/vehiculos` publicado.
Se incorporaron los tres commits remotos `21f6712`, `5a8e24a` y `456306a`,
preservando distancia, detalle de costos/consumo y `sicetac_tradicional.total_viaje`
como único total. Las cinco pruebas adicionales cubren esa integración.
No hubo cambios de agentes, mensajes reales, consultas de cotización remotas
ni escrituras en Supabase en esta fase. El refuerzo de bandeja sigue sin instalarse.

`render.yaml` declara despliegue automático de la API al publicar; su arranque
ejecuta Uvicorn y no aplica migraciones. Los repositorios no tienen workflows
GitHub de migración. Subir el SQL conserva el artefacto, no activa el alias.

El respaldo y hashes de los archivos de Instant están en
[manifest-instant-fixes.json](manifest-instant-fixes.json); la evidencia remota
acotada está en [catalogo-verificado.json](catalogo-verificado.json).

Para activar la corrección común: publicar primero el helper, aplicar la
variación de catálogo y refrescar el caché municipal mediante el mecanismo
administrativo existente. Después comprobar ambos consumidores. Solo publicar
el dato no basta con el helper anterior; solo desplegar el helper tampoco
crea la variación ausente. Juan autorizó subir los cambios de código después
de revisar el borrador; la aplicación del dato y comprobación en producción
siguen pendientes y no se acreditan con las pruebas simuladas.
