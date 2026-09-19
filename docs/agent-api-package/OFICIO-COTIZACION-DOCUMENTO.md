# Oficio: cotización documento (no es la búsqueda)

Este agente **no** llama al catálogo SICETAC a resolver ciudades ni vehículos.
Recibe una ficha `data.search` (o el texto de esa ficha ya aceptada) y produce
el documento de cotizados del cliente: papel comercial, margen, condiciones,
validez, PDF/Word.

## Entrada mínima
- `ruta`, `configuracion`, `sicetac_h4`, `sicetac_corte`
- `valor_plaza`, `valor_plaza_corte` si vino
- `request_id` para trazabilidad
- reglas comerciales **del cliente** (viven en ese agente, no en SICETAC)

## No hace
- `POST /v1/prequotes` para “volver a buscar” salvo que la ficha falte o el
  usuario cambie origen, destino o vehículo.
- Homologar patineta / ZF Santander / C2S2 (eso ya lo hizo la búsqueda).
- Inventar H4 o plaza.

Si falta la ficha, pide al agente de búsqueda que la traiga. No dupliques su
prompt ni su clave a menos que el diseño del cliente lo exija; lo normal es
**otra clave o ningún acceso al motor**, y sí acceso a plantilla comercial.
