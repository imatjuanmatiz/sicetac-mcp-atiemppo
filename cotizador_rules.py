"""Repositorio de rulesets técnicos publicados en Supabase."""

from __future__ import annotations

import os
from typing import Any

from cotizador_core import RuleSetValidationError, load_ruleset
from cotizador_core.models import RuleSet
from supabase_data import get_client


MARKET_SCOPE = "mercado_colombia_tecnico"


class PublishedRuleSetUnavailable(RuntimeError):
    """No existe una versión técnica publicada y válida para atender la API."""


def load_published_market_ruleset() -> RuleSet:
    """Lee una única revisión publicada. Nunca combina reglas entre versiones."""
    table = os.getenv("COTIZADOR_RULESETS_TABLE", "cotizador_rulesets")
    try:
        response = (
            get_client()
            .table(table)
            .select("scope_id,version,source_snapshot_id,definition")
            .eq("scope_id", MARKET_SCOPE)
            .eq("status", "published")
            .order("published_at", desc=True)
            .limit(1)
            .execute()
        )
        row = (response.data or [None])[0]
    except Exception as exc:
        raise PublishedRuleSetUnavailable("No fue posible leer el ruleset técnico publicado.") from exc
    if not isinstance(row, dict) or not isinstance(row.get("definition"), dict):
        raise PublishedRuleSetUnavailable("No hay un ruleset técnico publicado.")
    definition: dict[str, Any] = dict(row["definition"])
    definition.setdefault("scope_id", row.get("scope_id") or MARKET_SCOPE)
    definition.setdefault("version", row.get("version"))
    definition.setdefault("source_snapshot_id", row.get("source_snapshot_id"))
    try:
        return load_ruleset(definition)
    except (KeyError, TypeError, ValueError, RuleSetValidationError) as exc:
        raise PublishedRuleSetUnavailable("El ruleset técnico publicado no supera la validación.") from exc


def record_term_observation(
    *, consumer_id: str, request_id: str, raw_expression: str,
    normalized_expression: str | None, entity_type: str, suggested_value: str | None,
) -> None:
    """Registra una observación pendiente; nunca modifica reglas publicadas."""
    table = os.getenv("COTIZADOR_TERM_OBSERVATIONS_TABLE", "cotizador_term_observations")
    try:
        get_client().table(table).insert(
            {
                "scope_id": MARKET_SCOPE,
                "consumer_id": consumer_id,
                "request_id": request_id,
                "raw_expression": raw_expression,
                "normalized_expression": normalized_expression,
                "entity_type": entity_type,
                "suggested_value": suggested_value,
                "status": "pending_review",
            }
        ).execute()
    except Exception as exc:
        raise PublishedRuleSetUnavailable("No fue posible registrar la observación.") from exc
