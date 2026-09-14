"""Perfil operativo versionado para agentes integradores.

El perfil no contiene secretos ni reglas comerciales. Se consulta con una
credencial válida para que cada instalación use las mismas instrucciones
vigentes sin depender de un ZIP o prompt congelado.
"""

from __future__ import annotations

from typing import Any

from cotizador_core.models import RuleSet


CONTRACT_VERSION = "v1"
AGENT_POLICY_VERSION = "2026.09.14.1"
MINIMUM_BRIDGE_VERSION = "1.1.0"


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
                "with_declared_vehicle": "requested_configuration y carroceria permiten solicitar la referencia sin peso; nunca derive el peso desde la capacidad máxima.",
                "without_declared_vehicle": "Para carga_general, solicite cargo_weight_value y cargo_weight_unit antes de seleccionar automáticamente.",
                "weight_validation": "Si se informa peso, envíe cargo_weight_value y cargo_weight_unit juntos para validar capacidad SICE.",
            },
            "default_service_code": "carga_general",
            "general_aliases": ["carga_suelta", "general", "mercancia_general", "suelta"],
            "vehicle_selection": "Con vehículo explícito, use esa configuración y la carrocería declarada para la referencia SICETAC; el peso sólo valida capacidad SICE y jamás se infiere desde la capacidad. Sin vehículo y sin contenedor, sugiera la configuración cuya banda inclusiva contiene la carga y cumple capacidad SICE.",
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
            "primary_reference": "H4, 4 horas logísticas",
            "alternatives": "H2, H8 y rutas alternativas son escenarios; no se suman.",
            "market_analysis": "Presente market_analysis como valor de mercado observado RNDC/proxy, con su corte y brecha frente a H4. Nunca lo trate como tarifa comercial.",
            "capacity_and_pbv": "Seleccione por capacidad SICE igual o superior a la carga reportada. Si pbv_assessment=requires_vehicle_tare, no declare incompatibilidad: el PBV total requiere las taras del equipo.",
            "declared_vehicle_without_weight": "Si weight_validation=not_provided, informe que se usaron el vehículo y la carrocería declarados, y que la capacidad SICE no fue validada por falta de peso.",
            "capacity_only_alternatives": "Si el motor devuelve capacity_only_alternatives, preséntelas sólo como sugerencias por peso. No reducen ni invalidan el vehículo programado: valide volumen, dimensiones y operación.",
            "disclaimer": "Es una referencia técnica SICETAC; no es una oferta, tarifa comercial ni disponibilidad de vehículo.",
        },
        "allowed_operations": ["GET /v1/agent-profile", "GET /v1/usage", "POST /v1/prequotes"],
        "commercial_scope": "Las reglas comerciales pertenecen al proyecto consumidor y no se configuran en esta API.",
    }
