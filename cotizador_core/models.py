"""Modelos puros del núcleo; no contienen conectores ni reglas comerciales."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import re
import unicodedata


def _alias_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip().upper())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[\s_-]+", " ", text).strip()


def _location_alias(value: Any) -> dict[str, str]:
    """Valida una localidad canónica declarada en el ruleset publicado."""
    if isinstance(value, str):
        municipality = value.strip()
        department = None
    elif isinstance(value, dict):
        municipality = str(value.get("municipality") or value.get("municipio") or "").strip()
        department_value = value.get("department") or value.get("departamento")
        department = str(department_value).strip() if department_value else None
    else:
        raise ValueError("Cada location_alias debe ser texto o un objeto con municipality")
    if not municipality:
        raise ValueError("Cada location_alias debe declarar municipality")
    result = {"municipality": municipality}
    if department:
        result["department"] = department
    return result


@dataclass(frozen=True)
class QuoteInput:
    scope_id: str
    request_id: str
    cargo_weight_value: float | None = None
    cargo_weight_unit: str | None = None
    service_code: str | None = None
    container_size_ft: int | None = None
    weight_includes_tare: bool = False
    requested_configuration: str | None = None
    axles: int | None = None

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "QuoteInput":
        scope_id = raw.get("scope_id", raw.get("tenant_id"))
        required = {
            "scope_id": scope_id,
            "request_id": raw.get("request_id"),
        }
        missing = [field for field, value in required.items() if value in (None, "")]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")
        weight_value = raw.get("cargo_weight_value")
        weight_unit = raw.get("cargo_weight_unit")
        if (weight_value is None) != (weight_unit is None):
            raise ValueError("cargo_weight_value y cargo_weight_unit deben informarse juntos")
        return cls(
            scope_id=str(scope_id),
            request_id=str(raw["request_id"]),
            cargo_weight_value=(float(weight_value) if weight_value is not None else None),
            cargo_weight_unit=(str(weight_unit).lower() if weight_unit is not None else None),
            service_code=(str(raw["service_code"]).lower() if raw.get("service_code") else None),
            container_size_ft=(int(raw["container_size_ft"]) if raw.get("container_size_ft") is not None else None),
            weight_includes_tare=bool(raw.get("weight_includes_tare", False)),
            requested_configuration=(str(raw["requested_configuration"]) if raw.get("requested_configuration") else None),
            axles=(int(raw["axles"]) if raw.get("axles") is not None else None),
        )


@dataclass(frozen=True)
class VehicleEquivalence:
    vehicle_model_code: str
    sicetac_configuration: str
    toll_equivalence: str
    scope: str
    source_note: str | None = None

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "VehicleEquivalence":
        return cls(
            vehicle_model_code=str(raw["vehicle_model_code"]),
            sicetac_configuration=str(raw["sicetac_configuration"]),
            toll_equivalence=str(raw["toll_equivalence"]),
            scope=str(raw.get("scope") or "peajes_only"),
            source_note=(str(raw["source_note"]) if raw.get("source_note") else None),
        )


@dataclass(frozen=True)
class VehicleRule:
    rule_id: str
    service_code: str
    sicetac_configuration: str
    commercial_label: str
    priority: int
    min_operating_weight_kg: int | None
    max_operating_weight_kg: int | None
    max_cargo_kg: int | None
    axle_count: int | None
    provisional: bool
    requires_explicit_request: bool = False
    vehicle_model_code: str | None = None
    container_sizes_ft: tuple[int, ...] | None = None
    source_note: str | None = None

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "VehicleRule":
        return cls(
            rule_id=str(raw["rule_id"]),
            service_code=str(raw["service_code"]).lower(),
            sicetac_configuration=str(raw["sicetac_configuration"]),
            commercial_label=str(raw["commercial_label"]),
            priority=int(raw["priority"]),
            min_operating_weight_kg=(int(raw["min_operating_weight_kg"]) if raw.get("min_operating_weight_kg") is not None else None),
            max_operating_weight_kg=(int(raw["max_operating_weight_kg"]) if raw.get("max_operating_weight_kg") is not None else None),
            max_cargo_kg=(int(raw["max_cargo_kg"]) if raw.get("max_cargo_kg") is not None else None),
            axle_count=(int(raw["axle_count"]) if raw.get("axle_count") is not None else None),
            provisional=bool(raw.get("provisional", True)),
            requires_explicit_request=bool(raw.get("requires_explicit_request", False)),
            vehicle_model_code=(str(raw["vehicle_model_code"]) if raw.get("vehicle_model_code") else None),
            container_sizes_ft=(tuple(sorted(int(size) for size in raw["container_sizes_ft"])) if raw.get("container_sizes_ft") is not None else None),
            source_note=(str(raw["source_note"]) if raw.get("source_note") else None),
        )


@dataclass(frozen=True)
class RuleSet:
    scope_id: str
    ruleset_id: str
    version: str
    status: str
    source_snapshot_id: str
    emission_allowed: bool
    container_tares_kg: dict[int, int]
    configuration_aliases: dict[str, str]
    body_type_aliases: dict[str, str]
    location_aliases: dict[str, dict[str, str]]
    vehicle_equivalences: tuple[VehicleEquivalence, ...]
    vehicle_rules: tuple[VehicleRule, ...]

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "RuleSet":
        return cls(
            scope_id=str(raw.get("scope_id", raw.get("tenant_id", ""))),
            ruleset_id=str(raw["ruleset_id"]),
            version=str(raw["version"]),
            status=str(raw["status"]).lower(),
            source_snapshot_id=str(raw["source_snapshot_id"]),
            emission_allowed=bool(raw.get("emission_allowed", False)),
            container_tares_kg={int(size): int(weight) for size, weight in raw.get("container_tares_kg", {}).items()},
            configuration_aliases={_alias_key(key): str(value) for key, value in raw.get("configuration_aliases", {}).items()},
            body_type_aliases={_alias_key(key): str(value) for key, value in raw.get("body_type_aliases", {}).items()},
            location_aliases={
                _alias_key(key): _location_alias(value)
                for key, value in raw.get("location_aliases", {}).items()
            },
            vehicle_equivalences=tuple(VehicleEquivalence.from_mapping(item) for item in raw.get("vehicle_equivalences", [])),
            vehicle_rules=tuple(VehicleRule.from_mapping(item) for item in raw.get("vehicle_rules", [])),
        )

    def normalize_body_type(self, value: str) -> str:
        """Resuelve una carrocería sólo con aliases publicados en el ruleset."""
        return self.body_type_aliases.get(_alias_key(value), value)

    def normalize_configuration(self, value: str) -> str:
        """Resuelve una configuración sólo con aliases publicados en el ruleset.

        Acepta el alias exacto o un término compuesto (p. ej. «Patineta 2S2»).
        Si hay conflicto, prevalece el código SICETAC explícito sobre el
        nombre comercial.
        """
        key = _alias_key(value)
        if not key:
            return value
        exact = self.configuration_aliases.get(key)
        if exact:
            return exact
        resolved: list[tuple[str, str]] = []
        seen: set[str] = set()
        for token in [key, *key.split()]:
            if token in seen:
                continue
            seen.add(token)
            canonical = self.configuration_aliases.get(token)
            if canonical:
                resolved.append((token, canonical))
        if not resolved:
            return value
        canonicals = {item[1] for item in resolved}
        if len(canonicals) == 1:
            return next(iter(canonicals))

        def _code_like(alias: str) -> bool:
            compact = alias.replace(" ", "")
            return bool(
                re.fullmatch(r"(?:C)?\d(?:S\d)?(?:M?\d+)?", compact)
                or re.fullmatch(r"\d{3,4}", compact)
            )

        coded = [canon for alias, canon in resolved if _code_like(alias)]
        if len(set(coded)) == 1:
            return coded[0]
        return value

    def normalize_location(self, value: str | None) -> dict[str, str | None]:
        """Resuelve una localidad operativa al municipio canónico publicado.

        Esta capa sólo nombra el municipio (y el departamento, si hace falta
        para homónimos). El helper municipal confirma el DANE del catálogo;
        el código del alias no se usa como llave de búsqueda.
        """
        raw = str(value or "").strip()
        canonical = self.location_aliases.get(_alias_key(raw))
        if canonical:
            return {
                "raw": raw,
                "municipality": canonical["municipality"],
                "department": canonical.get("department"),
                "source": "published_ruleset_alias",
            }
        return {
            "raw": raw,
            "municipality": raw,
            "department": None,
            "source": "input",
        }
