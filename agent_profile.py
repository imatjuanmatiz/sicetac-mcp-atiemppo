"""Perfil operativo versionado para agentes integradores.

El perfil no contiene secretos ni reglas comerciales. Se consulta con una
credencial válida para que cada instalación use las mismas instrucciones
vigentes sin depender de un ZIP o prompt congelado.
"""

from __future__ import annotations

from typing import Any

from cotizador_core.models import RuleSet


CONTRACT_VERSION = "v1"
AGENT_POLICY_VERSION = "2026.10.21.3"
MINIMUM_BRIDGE_VERSION = "1.2.1"


def _automatic_container_configuration(ruleset: RuleSet, size_ft: int) -> str | None:
    candidates = [
        rule for rule in ruleset.vehicle_rules
        if rule.service_code == "contenedor"
        and not rule.requires_explicit_request
        and (rule.container_sizes_ft is None or size_ft in rule.container_sizes_ft)
    ]
    if not candidates:
        return None
    selected = min(
        candidates,
        key=lambda rule: (rule.priority, rule.max_cargo_kg or 10**12, rule.rule_id),
    )
    return selected.sicetac_configuration


def build_agent_profile(ruleset: RuleSet) -> dict[str, Any]:
    """Devuelve reglas de conversación seguras y compatibles con el contrato v1."""
    return {
        "contract_version": CONTRACT_VERSION,
        "agent_policy_version": AGENT_POLICY_VERSION,
        "minimum_bridge_version": MINIMUM_BRIDGE_VERSION,
        "ruleset": {
            "id": ruleset.ruleset_id,
            "version": ruleset.version,
            "source_snapshot_id": ruleset.source_snapshot_id,
        },
        "quota": {"consumes_units": False, "note": "Esta lectura no consume cuota."},
        "session_start": {
            "required_tool": "consultar_instrucciones_vigentes",
            "frequency": "once_per_session_before_first_core_call",
            "on_version_change": "Use el perfil devuelto para llamadas al Core; no es requisito previo para la referencia directa de SICETAC al Instante.",
        },
        "input_policy": {
            "required": ["origen", "destino"],
            "conditional": {
                "with_declared_vehicle": "Para una referencia directa, envíe la configuración declarada a SICETAC al Instante sin llamar al Core. Si el usuario pide análisis del Core, envíe requested_configuration y calcule sin exigir peso; nunca derive el peso desde la capacidad máxima.",
                "without_declared_vehicle": "Para una referencia directa use los defaults autorizados por SICETAC al Instante; no pida peso. Solo si el usuario solicita selección por capacidad, pida cargo_weight_value y cargo_weight_unit en carga_general. En contenedor solicite container_size_ft (20 o 40) solo si se requiere selección por tamaño; el peso es opcional para la referencia inicial y valida capacidad con la tara publicada si lo dieron.",
                "weight_validation": "Si se informa peso, envíe cargo_weight_value y cargo_weight_unit juntos para validar capacidad SICE.",
            },
            "default_service_code": "carga_general",
            "general_aliases": ["carga_suelta", "general", "mercancia_general", "suelta"],
            "vehicle_selection": "La referencia normal usa la configuración explícita o los defaults autorizados por SICETAC al Instante, sin selección previa del Core. Solo para análisis de selección/capacidad solicitados use el peso en carga_general o el tamaño y la tara publicada en contenedor. El peso jamás se infiere desde la capacidad máxima.",
            "published_homologation": "Envíe los términos declarados. El Core usa la tabla de equivalencias para nombrar el municipio y después el helper confirma el DANE del catálogo. No use un código SICE del alias como llave de búsqueda ni replique esa tabla en el agente.",
            "view": "Cuando use el API Core para selección o capacidad, envíe view=search. data.search incluye ruta, configuración, referencia de la hora acordada, valor en plaza cuando existe y capacidad neta/compatibilidad cuando hay regla. Para detalle de costos use view=costs; para detalle de consumo use view=consumption, solo si el usuario lo solicita. Ambos ejecutan el modelo completo, independiente de la tarifa publicada.",
            "horas_logisticas": "Default 4 (H4). No pregunte la hora si el usuario no la dijo. Si pide 2, 8 u otra, envíe horas_logisticas y recuérdela en el hilo hasta que pida otra. Presente solo esa hora.",
            "axles": "Si hay requested_configuration completa, no envíe axles: una cifra aislada puede describir sólo el tracto. Si no hay configuración completa, axles sirve como señal secundaria para selección automática.",
            "container": {
                "only_when_explicitly_named": True,
                "required_then": ["container_size_ft"],
                "sizes_ft": [20, 40],
                "tare_is_server_side": True,
                "automatic_configuration_by_size_ft": {
                    "20": _automatic_container_configuration(ruleset, 20),
                    "40": _automatic_container_configuration(ruleset, 40),
                },
                "smaller_vehicle": "Solo con requested_configuration explícita.",
            },
            "empty_container": {
                "carroceria": "Portacontenedores",
                "modo_viaje": "CARGADO",
                "tipo_contenedor": "VACIO",
                "never_use_modo_viaje_vacio_for": "Contenedor vacío transportado.",
            },
        },
        "search_workflow": {
            "canonical_reference_source": "SICETAC al Instante MCP",
            "reference_tool": "consultar_referencia",
            "reference_required_for_every_route_value": True,
            "normal_search": "Resuelva la solicitud con una llamada directa a consultar_referencia de SICETAC al Instante. Envíe los nombres o DANE y los datos que el usuario sí indicó; use los defaults autorizados del conector para los campos omitidos. No ejecute antes precotizar_transporte, listar_municipios, listar_vehiculos, listar_carrocerias, consultar_rutas ni consultar_instrucciones_vigentes.",
            "route_details": "Llame consultar_rutas solo si el usuario pide comparar variantes o conocer recorridos. Para el precio base, deje que consultar_referencia resuelva la ruta. Si la herramienta devuelve una ambigüedad que no puede resolver con la variante directa, pregunte solo por la decisión faltante.",
            "components": "Llame calcular_desglose únicamente si el usuario solicita componentes, consumo, peajes u otro detalle técnico. Conserve ruta, configuración, carrocería, modo, contenedor, mes y horas de la referencia; no repita el desglose en consultas normales.",
            "additional_analysis": "Use precotizar_transporte para selección/validación de capacidad basada en peso o análisis adicionales que requieran cotizador_core. No use su importe como reemplazo de la referencia SICETAC al Instante.",
            "comparison": "Si el usuario pide comparar rutas, consulte variantes una vez y obtenga una referencia SICETAC al Instante por variante solicitada, con el mismo vehículo, servicio, período y horas.",
            "connection_boundary": "La conexión SICETAC al Instante es independiente del API comercial. Si el cliente no la tiene disponible, informe que falta esa conexión; no simule una consulta ni la sustituya silenciosamente por otra fuente.",
        },
        "output_policy": {
            "view": "search",
            "applies_when": "Solo cuando se llamó precotizar_transporte por una selección o análisis adicional del Core.",
            "present": "Presenta los valores calculados necesarios para el análisis solicitado desde data.search: ruta (NOMBRE_SICE), configuración, referencia de la hora acordada, valor en plaza cuando exista y capacidad neta/compatibilidad cuando haya regla. La referencia publicada que se presenta como valor SICETAC siempre procede de SICETAC al Instante. No agregue datos no pedidos.",
            "omit": "No presente tara, PBV, el menú H2/H8, alternativas de ruta, capacity_only_alternatives ni el ensayo de market_analysis. No redacte textos de cotización ni añada frases de cierre; presente los datos calculados.",
            "route_name": "Use search.ruta. Nunca RUTASID, ID_SICE ni el par DANE como nombre.",
            "plaza_missing": "Si search.valor_plaza es null, diga que no hay valor en plaza. No invente ni ponga cero.",
            "toneladas_configuracion": "El valor por tonelada usa el tonelaje nominal de la configuración; no equivale al peso real transportado.",
        },
        "reference_output_policy": {
            "source": "SICETAC al Instante MCP consultar_referencia",
            "present": "Ruta, configuración, período, horas y valor devueltos por la consulta. Valor en plaza o capacidad solo si vienen en esa respuesta.",
            "omit": "No agregue avisos comerciales, listas de variantes, componentes o cálculos de tara en una búsqueda normal.",
        },
        "cost_detail_policy": {
            "when": "Solo si el usuario pide componentes, consumo, peajes o detalle técnico; no ejecutar en una búsqueda normal.",
            "total": "En ambos detalles, incluso pedidos directamente, muestre como único total del viaje sicetac_tradicional.total_viaje con sus horas_logisticas y mes: es el valor de SICETAC Instant para la misma ruta, variante y configuración. No presente detalle_costos.total_viaje ni los totales del modelo, ni recalcule el total sumando el desglose. Si estimado=true etiquete el total como estimado.",
            "preserve_context": ["origen", "destino", "requested_configuration", "carroceria", "mes", "rutasid", "horas_logisticas", "modo_viaje"],
            "costs": "Presente total_galones, horas_recorrido, horas_logisticas, rotaciones_calculadas, costo_fijo, costos_variables y otros_costos; variables incluye combustible, peajes, mantenimiento e imprevistos. No los sume dos veces.",
            "consumption": "Presente por_terreno: km, gal y costo_combustible, más total_galones y costo_combustible_total.",
            "urban": "Mismo municipio: modelo con 30 km ondulados y peajes cero. Muestre VALOR ESTIMADO y el supuesto de distancia.",
            "missing_tolls": "Sin registro de peajes: cero.",
        },
        "allowed_operations": ["GET /v1/agent-profile", "GET /v1/usage", "POST /v1/prequotes"],
        "commercial_scope": "Las reglas comerciales pertenecen al proyecto consumidor y no se configuran en esta API.",
    }
