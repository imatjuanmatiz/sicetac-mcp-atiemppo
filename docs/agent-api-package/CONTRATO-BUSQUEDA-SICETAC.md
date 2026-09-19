# Contrato de búsqueda SICETAC

Un solo proceso. Grok Bot, OpenClaw o el agente de otro cliente son canales.
La única pieza que cambia por cliente es la **clave** (`SICETAC_API_KEY`) y su
`consumer_id` / cuota. No se clona el cálculo ni se arma una tabla paralela de
ciudades o vehículos.

Instant no usa este contrato: allí el usuario ya eligió en listas.

## Dos oficios, dos agentes

| Agente | Oficio | Qué entrega |
|---|---|---|
| **Búsqueda** | Entender el pedido suelto y consultar el motor | Ficha: ruta + H4 + valor en plaza |
| **Cotización documento** | Tomar la ficha (y reglas comerciales del cliente) y armar la oferta | Documento / PDF / Word de cotizados |

El de búsqueda **no** cotiza en comercial, no pone margen, no arma el documento
ni promete cupo. El de documento **no** llama al catálogo a adivinar la ruta:
parte de `data.search` ya resuelta.

## Qué hace el de búsqueda

1. Entiende origen, destino, vehículo/configuración y si es carga general o contenedor.
2. Envía los términos **tal cual** los dijo el usuario. El Core homologa.
3. Una llamada: `POST /v1/prequotes` con `view=search`.
4. Presenta sólo `data.search`.

## Ficha (`data.search`)

- `ruta` — `NOMBRE_SICE`
- `configuracion` — la que usó el motor
- `sicetac_h4` + `sicetac_corte`
- `valor_plaza` + `valor_plaza_corte` (null → “sin valor en plaza”)

Fuera de la ficha: tara, PBV, H2/H8, alternativas, regla provisional. Eso es
`view=detail`, solo si alguien pide el desglose.

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
