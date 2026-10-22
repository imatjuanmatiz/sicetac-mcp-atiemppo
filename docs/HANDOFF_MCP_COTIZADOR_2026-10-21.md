# Handoff local: paridad SICETAC al Instante y cálculo en MCP

**Fecha:** 21 de octubre de 2026, America/Bogota.
**Owners:** SICETAC-AL-INSTANTE y SICETAC-API-MCP.
**Estado:** cambios locales revisables; no desplegados.

## Implementación

En el clon [SICETAC-AL-INSTANTE](/Users/atiemppoia/codex/SICETAC-AL-INSTANTE) se actualizaron `contract.py`, `backend.py`, `service.py`, `app.py` y `discovery.py`; el gateway local ahora permite una lectura GET filtrada del ruleset `mercado_colombia_tecnico`. Se agregó el `cotizador_core` fijado desde `imatjuanmatiz/sicetac-mcp-atiemppo` en commit `08c1c84248df3ac1844d9aadba3c7f69d8e5f5e7`, con hashes registrados en `engine/SOURCE.json`.

El MCP ahora:

- acepta `peso_carga_t`, `pies_contenedor` y `peso_incluye_tara`, valida rango/tipo y rechaza combinaciones inválidas;
- lee aliases, capacidades y taras del ruleset publicado y selecciona antes de consultar importes o ejecutar el modelo;
- usa la tara de contenedor publicada; conserva un respaldo de 20′ = 2.300 kg y 40′ = 4.100 kg, citado al SQL fuente, solo cuando falta el ruleset;
- prefiere C2S2 para 20′ y C2S3 para 40′, y escala por capacidad publicada en orden C2S2 → C2S3 → C3S2 → C3S3 para 20′ y C2S3 → C3S2 → C3S3 para 40′;
- devuelve `configuracion_elegida`, `regla_aplicada` y `pbv_assessment=requires_vehicle_tare`, sin validar PBV legal ni mostrar cálculos de tara;
- selecciona automáticamente la variante única `ORIGEN _ DESTINO`, incluye valor en plaza solo cuando está disponible y oculta versión/datos internos del payload MCP;
- instruye a resolver la referencia completa en una llamada y distingue el regreso de contenedor vacío como otra consulta en sentido inverso, `modo_viaje=CARGADO`, `tipo_contenedor=VACIO`.

El skill del complemento y `llms.txt` se alinearon con ese flujo. En SICETAC-API-MCP, `agent_profile.py` toma el default por prioridad del ruleset publicado: 2S2 para 20′ y 2S3 para 40′; `AGENT_POLICY_VERSION` es `2026.10.21.2`, y el puente local pasa a `1.2.1` (`minimum_bridge_version=1.2.1`) por los nuevos campos MCP. Se actualizaron las instrucciones Grok/ATICA que aún afirmaban C3S3 para 40′ o calculaban PBV legal a partir de taras estimadas.

Para uso de una fuerza comercial, `POST /v1/prequotes` con `view=search`
devuelve ruta, referencia SICETAC, valor en plaza cuando existe y `capacidad`
(tope neto de mercancía, peso solicitado, compatibilidad y provisionalidad).
El perfil entrega esos valores calculados para análisis y procesos, resuelve
automáticamente la configuración y solicita solo el dato crítico que falte.
La generación de textos de cotización queda para una definición posterior.

El puente `precotizar_transporte` ahora entrega `view=search` por defecto y
expone `weight_includes_tare`, ida/regreso, variante y códigos DANE de retorno.
Para carga general sin vehículo pide peso; para contenedor un tamaño 20/40 basta
para la referencia inicial, y el peso queda opcional para validar capacidad.

## Reglas publicadas y límites conocidos

La revisión `2026.10.21-market.1` tenía 32 aliases. Con la autorización posterior de Juan se publicó `2026.10.21-market.2`, con 49 aliases; `.1` quedó `superseded`. Se conserva `PATINETA`→`2S2` como nombre general, se agregan aliases de tamaño para `PATINETA 20`→`2S2` y `PATINETA 40`→`2S3`, `MINIMULA` pasa a `3S2`, y `MULA`, `TRACTOMULA` y `TRACTOCAMION DE 3 EJES` resuelven a `3S3`. La lectura de vuelta confirmó esos valores, las taras y los siete topes por configuración/tamaño. `C279` sigue descrito en SICETAC como camión liviano de dos ejes de 7.001–9.000 kg; Juan confirma que comercialmente es Turbo y `TURBO`→`2_7_9` se conserva. El ajuste de motor y pruebas está local; no se desplegó ningún canal.

Los importes de plaza no existen en las tablas públicas consultadas cuando la fila no trae `valor_en_plaza`/`valor_plaza`; no se mezclan tablas de empresa.

## Capacidades SICETAC con tara del contenedor

Lectura de solo lectura de `public.configuracion_vehicular` confirma la columna `toneladas`: C2S2 = 22, C2S3 = 27, C3S2 = 31 y C3S3 = 34. Para esta clasificación, por instrucción de Juan, el máximo de la configuración se interpreta como carga total incluyendo la tara del contenedor. Al descontar la tara publicada en el ruleset (20′ = 2.300 kg; 40′ = 4.100 kg), los máximos de mercancía quedan así:

| Configuración SICETAC | Nombre a usar en la búsqueda | Máximo de configuración | Mercancía con contenedor 20′ | Mercancía con contenedor 40′ |
|---|---|---:|---:|---:|
| C2S2 | Patineta; preferida para 20′ | 22 t | 19,7 t | 17,9 t |
| C2S3 | Patineta; preferida para 40′ | 27 t | 24,7 t | 22,9 t |
| C3S2 | Minimula, según la convención solicitada | 31 t | 28,7 t | 26,9 t |
| C3S3 | Mula, tractomula o tractocamión de 3 ejes | 34 t | 31,7 t | 29,9 t |

Las columnas de mercancía son `toneladas de configuración − tara del contenedor`; para decidir por el máximo total se compara `mercancía + tara` contra 22/27/31/34 t. No son afirmaciones de PBV legal ni incluyen la tara real del tractocamión o semirremolque. La descripción SICETAC llama “Patineta / Minimula” a C2S2 y C2S3 y “Tractomula” a C3S2 y C3S3; los nombres publicados son la convención comercial solicitada para distinguir búsquedas. La versión `.2` separa las reglas por tamaño para que C2S2 sea el inicio preferido para 20′ y C2S3 para 40′, y publica los máximos netos tras descontar tara.

Como bandas de selección propuestas por peso total (mercancía más tara del contenedor): para 20′, hasta 22 t C2S2; más de 22 y hasta 27 t C2S3; más de 27 y hasta 31 t C3S2; más de 31 y hasta 34 t C3S3. Para 40′, se prefiere C2S3 hasta 27 t; luego C3S2 hasta 31 t y C3S3 hasta 34 t. Por encima de 34 t, la tabla SICETAC consultada no ofrece otra de estas cuatro configuraciones. En peso neto de mercancía, los máximos por banda son los de la tabla anterior.

Se reprodujeron los importes de octubre con datos de solo lectura y fixture local:

- Bogotá→Buenaventura, C3S3, H4, 202610: **$4.724.726**.
- RUTASID 95 en dirección Bogotá→Buenaventura, contenedor vacío, H4: **$3.717.644**.
- La ruta inversa publicada es RUTASID 154 y da **$3.567.291**. RUTASID 95 no existe en sentido inverso; no se invirtió automáticamente ni se cambió el importe para hacerlo coincidir.

El warehouse local tiene el corte SICETAC mensual 202610, pero la tabla de parámetros del modelo encontrada conserva vigencia 202607. No se inventaron parámetros, se cargaron tablas productivas ni se afirmó que producción use ese corte. No se ejecutó una cotización en OpenClaw: la validación fue contra el `cotizador_core`, pruebas y las referencias leídas; no se encontró una herramienta de Cotizador Logística Total conectada a este turno.

## Pruebas y diferencias de suites

- MCP aislado, fixtures sintéticos, sin red/secretos/clientes: **96/96**; dependencias del motor coinciden con `engine/SOURCE.json` y cero intentos bloqueados.
- Gateway Node: **4/4**.
- API: las cuatro suites previas más las siete regresiones R01–R07: **61/61**; `tests/test_commercial_api.py`: **10/10**, incluido el perfil 40′→2S3 del ruleset publicado.
- MCP cliente, cálculo, perfil, aliases/capacidad y contrato R01–R07: suite dirigida **60/60**. Incluye selección C2S3 para 40′, peso total de 18 t con tara incluida → 13,9 t de mercancía, y ficha `view=search` con tope neto y compatibilidad.
- MCP cliente → API → Core → SICETAC: incluido en la suite del puente; se verifica `view=search`, 40′→C2S3 y normalización de 18 t con tara incluida a 13,9 t netas.
- Descubrimiento completo: **137 pruebas pasaron**; una suite opcional no se pudo importar porque `tests/test_sicetac_route_indices.py` requiere `duckdb`, ausente en `.venv`. No se instaló una dependencia nueva.
- Una copia temporal del verificador forense del 16-oct mostró R01–R06 como `NO_REPRODUCIDO`; su prueba R07 quedó `ERROR_HARNESS` porque ahora `ConsultaInput("Infinity")` produce `ValidationError` donde el probe antiguo esperaba que se aceptara. Las suites base pasaron; la regresión actual confirma rechazo con HTTP 422. Los recibos históricos no se modificaron.
- La suite MCP usa el Python 3.13 existente y emitió una advertencia de Pydantic sobre la anotación de `lifespan`; no produjo errores ni fallos.

## Archivos revisables

- [Selección, contrato y respuesta MCP](/Users/atiemppoia/codex/SICETAC-AL-INSTANTE/sicetac_instant/service.py), [backend/ruleset](/Users/atiemppoia/codex/SICETAC-AL-INSTANTE/sicetac_instant/backend.py), [entrada MCP](/Users/atiemppoia/codex/SICETAC-AL-INSTANTE/sicetac_instant/app.py).
- [Contrato de campos](/Users/atiemppoia/codex/SICETAC-AL-INSTANTE/sicetac_instant/contract.py), [gateway GET](/Users/atiemppoia/codex/SICETAC-AL-INSTANTE/supabase/functions/sicetac-instant-reference/handler.mjs), [manifiesto del motor](/Users/atiemppoia/codex/SICETAC-AL-INSTANTE/engine/SOURCE.json).
- [Regresiones de selección y octubre](/Users/atiemppoia/codex/SICETAC-AL-INSTANTE/tests/instant/test_vehicle_selection.py), [suite previa MCP](/Users/atiemppoia/codex/SICETAC-AL-INSTANTE/tests/instant/test_variant.py).
- [Perfil 40′ del motor](/Users/atiemppoia/codex/SICETAC-API-MCP/agent_profile.py), [regresión API](/Users/atiemppoia/codex/SICETAC-API-MCP/tests/test_commercial_api.py), [handoff de los siete hallazgos](/Users/atiemppoia/codex/SICETAC-API-MCP/docs/revision-api-2026-10-16/HANDOFF_IMPLEMENTACION_2026-10-21.md).
- [Ficha comercial `view=search` y capacidad](/Users/atiemppoia/codex/SICETAC-API-MCP/commercial_api.py), [entrada MCP](/Users/atiemppoia/codex/SICETAC-API-MCP/commercial_mcp_server.py), [validación del cliente](/Users/atiemppoia/codex/SICETAC-API-MCP/commercial_client.py), [regresión puente → API → Core](/Users/atiemppoia/codex/SICETAC-API-MCP/tests/test_commercial_client.py).
- [Contrato del MCP y ejemplo de salida comercial](/Users/atiemppoia/codex/SICETAC-API-MCP/docs/agent-api-package/README.md), [schema de la herramienta](/Users/atiemppoia/codex/SICETAC-API-MCP/docs/agent-api-package/tool-schema.json), [API comercial](/Users/atiemppoia/codex/SICETAC-API-MCP/docs/commercial-api.md).

## Autorización, consumo y acciones

La autorización es la petición directa de Juan para corregir localmente el MCP/API, añadir y correr regresiones, contrastar contra reglas SICETAC y publicar las revisiones de aliases/capacidades indicadas. Se conservaron los cambios preexistentes y los artefactos sin seguimiento. No se alteró Portal/CRM, autenticación, secretos, modelo configurado, tablas de parámetros ni credenciales. Las dos escrituras de reglas fueron transaccionales: publicación de `.1` (32 aliases) y luego `.2` (49 aliases, siete reglas de capacidad por tamaño), con cada versión anterior marcada `superseded`. La lógica API local ahora expone también `max_configuration_load_kg`; no se desplegó.

Se leyó el ruleset y se verificó cada publicación con lectura de vuelta. **Cotizaciones MCP/API reales: 0; cuotas de cotización descontadas: 0; publicaciones transaccionales de ruleset: 2 en este seguimiento histórico; despliegues, push y PR: 0; mensajes a otros hilos: 0; procesos persistentes y costos externos: 0.** La versión `.2` ya está publicada; el cambio de código y sus pruebas permanecen locales.
