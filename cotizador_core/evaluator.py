"""Evaluación explicable de reglas técnicas publicadas."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
import json

from .models import QuoteInput, RuleSet, VehicleRule


class RuleSetValidationError(ValueError):
    """La solicitud o el ruleset no puede evaluarse de forma defendible."""


SERVICE_ALIASES = {
    "general": "carga_general",
    "suelta": "carga_general",
    "carga_suelta": "carga_general",
    "mercancia_general": "carga_general",
    "homologada_carga_general": "carga_general",
}


def load_ruleset(source: str | Path | Mapping[str, Any]) -> RuleSet:
    """Carga un ruleset versionado sin otorgarle privilegios de ejecución."""
    if isinstance(source, Mapping):
        raw = dict(source)
    else:
        with Path(source).open(encoding="utf-8") as stream:
            raw = json.load(stream)
    if raw.get("schema_version") != 1:
        raise RuleSetValidationError("El ruleset no declara schema_version=1")
    ruleset = RuleSet.from_mapping(raw)
    if not ruleset.scope_id:
        raise RuleSetValidationError("El ruleset no declara scope_id")
    if not ruleset.vehicle_rules:
        raise RuleSetValidationError("El ruleset no tiene reglas vehiculares")
    model_codes = [item.vehicle_model_code for item in ruleset.vehicle_equivalences]
    if len(model_codes) != len(set(model_codes)):
        raise RuleSetValidationError("El ruleset repite un código en equivalencias")
    rules_by_model = {rule.vehicle_model_code: rule for rule in ruleset.vehicle_rules if rule.vehicle_model_code}
    for equivalence in ruleset.vehicle_equivalences:
        rule = rules_by_model.get(equivalence.vehicle_model_code)
        if rule is None or rule.sicetac_configuration != equivalence.sicetac_configuration:
            raise RuleSetValidationError("Cada equivalencia debe apuntar a una regla de la misma configuración")
    for rule in ruleset.vehicle_rules:
        if rule.container_sizes_ft is not None and rule.service_code != "contenedor":
            raise RuleSetValidationError("container_sizes_ft solo aplica a contenedor")
        if rule.requires_explicit_request and rule.service_code != "contenedor":
            raise RuleSetValidationError("requires_explicit_request solo aplica a contenedor")
    return ruleset


def _service_code(value: str | None) -> str:
    candidate = (value or "carga_general").lower()
    return SERVICE_ALIASES.get(candidate, candidate)


def _weight_kg(value: float, unit: str) -> int:
    if value < 0:
        raise RuleSetValidationError("El peso no puede ser negativo")
    if unit == "kg":
        result = value
    elif unit == "t":
        result = value * 1000
    else:
        raise RuleSetValidationError("La unidad de peso debe ser kg o t")
    if result > 100_000:
        raise RuleSetValidationError("El peso excede el límite de seguridad del motor")
    return round(result)


def _rule_trace(rule: VehicleRule, load_and_container_kg: int, cargo_kg: int) -> dict[str, Any]:
    selection_weight_ok = ((rule.min_operating_weight_kg is None or load_and_container_kg >= rule.min_operating_weight_kg) and (rule.max_operating_weight_kg is None or load_and_container_kg <= rule.max_operating_weight_kg))
    cargo_ok = rule.max_cargo_kg is None or cargo_kg <= rule.max_cargo_kg
    return {
        "rule_id": rule.rule_id,
        "sicetac_configuration": rule.sicetac_configuration,
        "container_sizes_ft": list(rule.container_sizes_ft) if rule.container_sizes_ft else None,
        "selection_weight_compatible": selection_weight_ok,
        "sice_cargo_compatible": cargo_ok,
        "eligible": selection_weight_ok and cargo_ok,
    }


def _candidate_rules(ruleset: RuleSet, service_code: str, axles: int | None, container_size_ft: int | None) -> list[VehicleRule]:
    rules = [rule for rule in ruleset.vehicle_rules if rule.service_code == service_code]
    if service_code == "contenedor":
        rules = [rule for rule in rules if rule.container_sizes_ft is None or container_size_ft in rule.container_sizes_ft]
    if axles is not None:
        axle_specific = [rule for rule in rules if rule.axle_count == axles]
        if axle_specific:
            rules = axle_specific
    if not rules:
        raise RuleSetValidationError(f"No hay reglas activas para el servicio {service_code}")
    return sorted(rules, key=lambda rule: (rule.priority, rule.max_cargo_kg or 10**12, rule.rule_id))


def _serialize_rule(ruleset: RuleSet, rule: VehicleRule, selection: str, trace: dict[str, Any]) -> dict[str, Any]:
    equivalence = next((item for item in ruleset.vehicle_equivalences if item.vehicle_model_code == rule.vehicle_model_code), None)
    is_container = rule.service_code == "contenedor"
    return {
        "rule_id": rule.rule_id,
        "commercial_label": rule.commercial_label,
        "sicetac_configuration": rule.sicetac_configuration,
        "vehicle_model_code": rule.vehicle_model_code,
        "vehicle_equivalence": ({"toll_equivalence": equivalence.toll_equivalence, "scope": equivalence.scope, "source_note": equivalence.source_note} if equivalence else None),
        "container_sizes_ft": list(rule.container_sizes_ft) if rule.container_sizes_ft else None,
        "max_cargo_kg": rule.max_cargo_kg,
        "provisional": rule.provisional,
        "requires_explicit_request": rule.requires_explicit_request,
        "selection": selection,
        "selection_weight_compatible": trace["selection_weight_compatible"],
        "pbv_compatible": None if is_container else trace["selection_weight_compatible"],
        "pbv_assessment": "requires_vehicle_tare" if is_container else "evaluated_from_published_range",
        "sice_cargo_compatible": trace["sice_cargo_compatible"],
        "source_note": rule.source_note,
    }


def evaluate_quote(raw_request: dict[str, Any], ruleset: RuleSet) -> dict[str, Any]:
    """Devuelve una decisión reproducible; la emisión comercial queda bloqueada."""
    request = QuoteInput.from_mapping(raw_request)
    if ruleset.status != "published":
        raise RuleSetValidationError("Solo un ruleset publicado puede atender cotizaciones")
    if request.scope_id != ruleset.scope_id:
        raise RuleSetValidationError("El request no corresponde al alcance técnico publicado")
    if request.axles is not None and request.axles <= 0:
        raise RuleSetValidationError("El número de ejes debe ser positivo")
    service_code = _service_code(request.service_code)
    reported_kg = _weight_kg(request.cargo_weight_value, request.cargo_weight_unit)
    tare_kg = 0
    if service_code == "contenedor":
        if request.container_size_ft not in ruleset.container_tares_kg:
            raise RuleSetValidationError("El tamaño de contenedor debe tener una tara publicada")
        tare_kg = ruleset.container_tares_kg[request.container_size_ft]
    if request.weight_includes_tare:
        if service_code != "contenedor":
            raise RuleSetValidationError("weight_includes_tare solo aplica a contenedor")
        if reported_kg < tare_kg:
            raise RuleSetValidationError("El peso total no puede ser inferior a la tara")
        cargo_kg, operating_kg = reported_kg - tare_kg, reported_kg
    else:
        cargo_kg, operating_kg = reported_kg, reported_kg + tare_kg
    candidates = _candidate_rules(ruleset, service_code, request.axles, request.container_size_ft)
    traces = [_rule_trace(rule, operating_kg, cargo_kg) for rule in candidates]
    trace_by_id = {item["rule_id"]: item for item in traces}
    explicit = request.requested_configuration
    if explicit:
        configuration = ruleset.configuration_aliases.get(explicit.upper(), explicit)
        selected = next((rule for rule in candidates if rule.sicetac_configuration == configuration), None)
        if selected is None:
            return {"engine_version": "1.0.0", "request_id": request.request_id, "scope_id": request.scope_id, "ruleset": {"id": ruleset.ruleset_id, "version": ruleset.version, "source_snapshot_id": ruleset.source_snapshot_id}, "status": "requires_catalog_entry", "normalized_input": {"service_code": service_code, "cargo_kg": cargo_kg, "tare_kg": tare_kg, "operating_gross_weight_kg": operating_kg}, "requested_configuration": explicit, "recommendation": None, "rule_trace": traces, "warnings": ["La configuración explícita no existe en la regla técnica publicada."], "emission": {"allowed": False, "reason": "La emisión depende de reglas comerciales externas."}}
        selected_trace, selection = trace_by_id[selected.rule_id], "explicit"
    else:
        automatic_candidates = candidates
        if service_code == "contenedor":
            automatic_candidates = [rule for rule in candidates if not rule.requires_explicit_request]
            if not automatic_candidates:
                raise RuleSetValidationError("No hay una configuración automática publicada para este contenedor")
            selected = next((rule for rule in automatic_candidates if trace_by_id[rule.rule_id]["sice_cargo_compatible"]), None)
        else:
            selected = next((rule for rule in automatic_candidates if trace_by_id[rule.rule_id]["eligible"]), None)
        if selected:
            selected_trace = trace_by_id[selected.rule_id]
            selection = "automatic_operational_default" if service_code == "contenedor" else "automatic"
        else:
            cargo_capable = [rule for rule in automatic_candidates if trace_by_id[rule.rule_id]["sice_cargo_compatible"]]
            if cargo_capable:
                selected = min(cargo_capable, key=lambda rule: (rule.max_cargo_kg or 10**12, rule.priority))
                selected_trace = trace_by_id[selected.rule_id]
                selection = "nearest_available_pbv_pending" if service_code != "contenedor" else "nearest_available_sice_candidate"
            else:
                selected = max(automatic_candidates, key=lambda rule: (rule.max_cargo_kg or -1, -rule.priority))
                selected_trace, selection = trace_by_id[selected.rule_id], "nearest_available_sice_exceeded"
    recommendation = _serialize_rule(ruleset, selected, selection, selected_trace)
    warnings: list[str] = []
    if recommendation["provisional"]:
        warnings.append("La regla seleccionada está marcada como provisional.")
    if service_code == "contenedor":
        warnings.append("El PBV total requiere la tara del tractocamión y semirremolque; carga y contenedor no bastan para validarlo.")
        if selection == "automatic_operational_default":
            warnings.append("Portacontenedor C2S2 es el mínimo técnico operativo por defecto; un equipo menor exige solicitud expresa.")
    elif not recommendation["pbv_compatible"]:
        warnings.append("El peso operativo reportado no encaja en el rango publicado.")
    if not recommendation["sice_cargo_compatible"]:
        warnings.append("La carga supera el máximo SICE publicado.")
    return {"engine_version": "1.0.0", "request_id": request.request_id, "scope_id": request.scope_id, "ruleset": {"id": ruleset.ruleset_id, "version": ruleset.version, "source_snapshot_id": ruleset.source_snapshot_id}, "status": "recommended" if not warnings else "provisional", "normalized_input": {"service_code": service_code, "cargo_kg": cargo_kg, "tare_kg": tare_kg, "load_and_container_weight_kg": operating_kg, "weight_includes_tare": request.weight_includes_tare}, "requested_configuration": explicit, "recommendation": recommendation, "rule_trace": traces, "warnings": warnings, "emission": {"allowed": False, "reason": "La emisión depende de reglas comerciales externas."}}
