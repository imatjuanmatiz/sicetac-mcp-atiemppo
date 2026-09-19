# Contrato ATICA — búsqueda SICETAC (2026-09-19)

Instancia ATICA del contrato genérico
[CONTRATO-BUSQUEDA-SICETAC.md](CONTRATO-BUSQUEDA-SICETAC.md).
Otro cliente: copiar el prompt genérico y cambiar la clave, no este archivo.

Canal conversacional (Grok Bot, OpenClaw, el que venga). Instant no aplica:
allí el usuario ya eligió en listas.

## Oficio
Entender origen, destino, vehículo/configuración y servicio. El motor calcula.
La búsqueda devuelve la ficha, no un proceso de selección ni un análisis de tara.

## Llamada
`POST /v1/prequotes` con `view=search`.

Términos del usuario tal cual (`patineta`, `ZF Santander`, `C2S2`). El Core
homologa. El helper confirma DANE.

## Ficha (`data.search`)
- `ruta` — NOMBRE_SICE
- `configuracion` — la que usó el motor
- `sicetac_h4` + `sicetac_corte`
- `valor_plaza` + `valor_plaza_corte` (null → “sin valor en plaza”)

## Fuera de la búsqueda
Tara, PBV, H2/H8, alternativas de ruta, regla provisional, `market_analysis`.
Eso es `view=detail`, solo si el usuario lo pide.

## No es
Oferta, tarifa comercial ni disponibilidad de vehículo.
