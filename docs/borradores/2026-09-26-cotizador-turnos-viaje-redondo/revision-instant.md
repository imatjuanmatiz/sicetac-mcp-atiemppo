# SICETAC Instant: revisión sin cambios

Este es el diagnóstico inicial. Las tres fallas se corrigieron después en
el checkout local: [resultado y validación](helper-instant-corregido.md).
No se han desplegado esas correcciones.

Corte: 26 de septiembre de 2026, America/Bogota. Repositorio
`/Users/atiemppoia/codex/SICETAC-INSTANT`.

La [lista de issues abiertos](https://github.com/imatjuanmatiz/sicetacinstant/issues)
devolvió cero mediante `gh issue list`. No se crearon issues ni se modificó el
repositorio. El HEAD remoto se verificó con la API de GitHub:
`456306a2789c830011cad02003549ee6452d77f5`, del 23 de septiembre.
El checkout local está en `fc41a6493bebcec49d475aefffdb4503de773df2`, tres commits
atrás, y conserva cuatro modificaciones preexistentes. No se hizo pull.

## Hallazgos reproducidos

1. **P2 — Cambiar la ruta conserva RUTASID anteriores.** Después de seleccionar
   ida/regreso, cambiar el origen no limpia `rutasSeleccionadas`. El siguiente
   envío combina el nuevo origen con los IDs anteriores; el backend puede
   rechazar la selección por no pertenecer al nuevo recorrido. El mismo patrón
   existe en el cambio de destino. Reproducción ejecutada: cambiar origen y
   comprobar el payload del `onSubmit` real con fetch simulado. Ubicaciones:
   [cambio de origen](</Users/atiemppoia/codex/SICETAC-INSTANT/app/page.jsx:230>) y
   [envío de IDs](</Users/atiemppoia/codex/SICETAC-INSTANT/app/page.jsx:101>).
   Corrección propuesta: invalidar selección y resultado cuando cambie la O-D
   o los parámetros que determinan sus opciones.

2. **P2 — Ida con contenedor vacío y viaje redondo simultáneos.** El formulario
   permite escoger `tipo_contenedor=VACIO` y mantener `viaje_redondo=true`.
   El contrato de API solo acepta ida cargada + devolución vacía; por tanto
   esa combinación provoca rechazo, aunque ambos controles la permiten.
   La reproducción confirma el payload incompatible; el rechazo se sustenta
   en la validación de `sicetac_service.py:1205`, sin consultar producción.
   Ubicación: [selectores de carga y recorrido](</Users/atiemppoia/codex/SICETAC-INSTANT/app/page.jsx:296>).
   Corrección propuesta: al elegir ida vacía, pasar a sencillo o impedir
   redondo; al elegir redondo, exigir ida cargada. Validar también en el proxy.

3. **P2 — Errores estructurados no se pueden renderizar.** `setError` recibe
   directamente `data.detail`; cuando es una lista de objetos de validación,
   el JSX intenta imprimirlos y React lanza “Objects are not valid as a React
   child”. Se reprodujo con una respuesta 422 simulada y el renderer React
   instalado. No se afirma haber observado ese error en tráfico real.
   Ubicaciones: [lectura del error](</Users/atiemppoia/codex/SICETAC-INSTANT/app/page.jsx:109>) y
   [renderizado](</Users/atiemppoia/codex/SICETAC-INSTANT/app/page.jsx:344>).
   Corrección propuesta: convertir errores en texto seguro antes de mostrarlos.

Los tres casos se reproducen tanto con el árbol local como con los archivos
de `origin/main` en el SHA verificado. Son tres defectos, cada uno comprobado
en dos versiones; no seis defectos distintos.

## Casos correctos y cobertura

En ambas versiones, los handlers conservan correctamente:

- redondo válido: vehículo `CARGADO`, contenedor de ida `CARGADO`, regreso `VACIO`;
- devolución independiente: vehículo `CARGADO`, contenedor `VACIO`;
- rechazo de redondo con vehículo `VACIO` en el proxy.

[Evidencia completa](resultado-instant.json): 6 comprobaciones satisfechas y
6 brechas reproducidas (3 por versión). [Script reproducible](revisar-instant.mjs)
extrae handlers de los archivos examinados, usa HTTP simulado y React local.
No levanta un servidor, no ejecuta un navegador ni consulta el backend real.
No acredita estado del despliegue web ni revisión E2E de WhatsApp.
El flujo sigue independiente del motor OpenClaw.
