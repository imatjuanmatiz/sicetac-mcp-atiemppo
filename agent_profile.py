"""Perfil operativo versionado para agentes integradores.

El perfil no contiene secretos ni reglas comerciales. Se consulta con una
credencial válida para que cada instalación use las mismas instrucciones
vigentes sin depender de un ZIP o prompt congelado.
"""

from __future__ import annotations

from typing import Any

from cotizador_core.models import RuleSet


CONTRACT_VERSION = "v1"
AGENT_POLICY_VERSION = "2026.09.22.2"
MINIMUM_BRIDGE_VERSION = "1.2.0"


def _automatic_container_configuration(ruleset: RuleSet, size_ft: int) -> str | None:
    candidates = [
        rule for rule in ruleset.vehicle_rules
        if rule.service_code == "contenedor"
        and not rule.requires_explicit_request
        and (rule.container_sizes_ft is None or size_ft in rule.container_sizes_ft)
    ]
    if not candidates:
        return None
    selected = min(candidates, key=lambda rule: (rule.priority, rule.rule_id))
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
            "frequency": "once_per_session",
            "on_version_change": "Use el perfil devuelto y conserve las respuestas compatibles del contrato v1.",
        },
        "input_policy": {
            "required": ["origen", "destino"],
            "conditional": {
                "with_declared_vehicle": "Busque requested_configuration directo y calcule. Una recomendación o alternativa no sustituye el cálculo ni espera peso. Nunca derive el peso desde la capacidad máxima.",
                "without_declared_vehicle": "Identifique el vehículo por peso de la carga; si es contenedor, use también la tara publicada. En carga_general solicite cargo_weight_value y cargo_weight_unit.",
                "weight_validation": "Si se informa peso, envíe cargo_weight_value y cargo_weight_unit juntos para validar capacidad SICE.",
            },
            "default_service_code": "carga_general",
            "general_aliases": ["carga_suelta", "general", "mercancia_general", "suelta"],
            "vehicle_selection": "Sin vehículo, identifique por peso de la carga y tara si es contenedor. Con vehículo solicitado, búsquelo directo, calcule y, si aplica, recomiende una alternativa; el cálculo no espera peso. El peso jamás se infiere desde la capacidad máxima.",
            "published_homologation": "Envíe los términos declarados. El Core usa la tabla de equivalencias para nombrar el municipio y después el helper confirma el DANE del catálogo. No use un código SICE del alias como llave de búsqueda ni replique esa tabla en el agente.",
            "view": "Los agentes envían view=search. La ficha de búsqueda es data.search e incluye kilometros. Para detalle de costos use view=costs; para detalle de consumo use view=consumption. Ambos ejecutan el modelo completo, independiente de la tarifa publicada. view=detail conserva el detalle de la búsqueda.",
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
        "output_policy": {
            "view": "search",
            "present": "Sólo data.search: ruta (NOMBRE_SICE), configuración, kilómetros, referencia SICETAC de la hora acordada (default H4) y valor en plaza, con cortes.",
            "omit": "No presente tara, PBV, regla provisional, el menú H2/H8, alternativas de ruta, capacity_only_alternatives ni el ensayo de market_analysis. Eso es view=detail, no la búsqueda.",
            "route_name": "Use search.ruta. Nunca RUTASID, ID_SICE ni el par DANE como nombre.",
            "plaza_missing": "Si search.valor_plaza es null, diga que no hay valor en plaza. No invente ni ponga cero.",
            "disclaimer": "Es una referencia técnica SICETAC; no es una oferta, tarifa comercial ni disponibilidad de vehículo.",
        },
        "cost_detail_policy": {
            "total": "En ambos detalles, incluso pedidos directamente, presente primero sicetac_tradicional.total_viaje con sus horas_logisticas y mes. Procede de la consulta habitual para la misma ruta, variante y configuración. Conserve aparte el total del modelo; si estimado=true etiquete el total como estimado.",
            "preserve_context": ["origen", "destino", "requested_configuration", "carroceria", "mes", "rutasid", "horas_logisticas", "modo_viaje"],
            "costs": "Presente total_galones, horas_recorrido, horas_logisticas, rotaciones_calculadas, costo_fijo, costos_variables y otros_costos; variables incluye combustible, peajes, mantenimiento e imprevistos. No los sume dos veces.",
            "consumption": "Presente por_terreno: km, gal y costo_combustible, más total_galones y costo_combustible_total.",
            "urban": "Mismo municipio: modelo con 30 km ondulados y peajes cero. Muestre VALOR ESTIMADO y el supuesto de distancia.",
            "missing_tolls": "Sin registro de peajes: cero.",
        },
        "allowed_operations": ["GET /v1/agent-profile", "GET /v1/usage", "POST /v1/prequotes"],
        "commercial_scope": "Las reglas comerciales pertenecen al proyecto consumidor y no se configuran en esta API.",
    }
