"""Contrato comercial versionado para SICETAC.

Los endpoints legacy permanecen en ``main.py`` para no romper WhatsApp ni
las integraciones existentes. Esta capa agrega un contrato estable para
terceros, agentes y futuros planes de consumo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
import math
import os
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from sicetac_service import (
    ConsultaInput,
    SicetacError,
    adjuntar_peajes_a_respuesta,
    calcular_sicetac,
    calcular_sicetac_resumen,
    consulta_solicita_peajes,
    get_sice_column_options,
)
from supabase_data import get_client, get_table_df


router = APIRouter(prefix="/v1", tags=["commercial-api"])


@dataclass(frozen=True)
class ApiConsumer:
    consumer_id: str
    name: str
    plan: str
    monthly_quota: int | None
    key_prefix: str = ""
    expires_at: datetime | None = None


_memory_usage: dict[tuple[str, str], int] = {}


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except Exception:
            pass
    return value


def _month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _month_start_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


def _configured_consumers() -> list[dict[str, Any]]:
    raw = os.getenv("SICETAC_API_KEYS_JSON", "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("SICETAC_API_KEYS_JSON no contiene JSON válido.") from exc

    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        raise RuntimeError("SICETAC_API_KEYS_JSON debe ser una lista de consumidores.")
    return [item for item in parsed if isinstance(item, dict)]


def _parse_expiration(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _consumer_is_current(consumer: ApiConsumer) -> bool:
    return consumer.expires_at is None or consumer.expires_at > datetime.now(timezone.utc)


def _consumer_from_record(record: dict[str, Any]) -> ApiConsumer | None:
    key_hash = str(record.get("key_hash") or "").strip().lower()
    consumer_id = str(record.get("consumer_id") or record.get("id") or "").strip()
    if not key_hash or not consumer_id or record.get("active", True) is False:
        return None
    quota = record.get("monthly_quota")
    try:
        quota = int(quota) if quota not in (None, "") else None
    except (TypeError, ValueError):
        quota = None
    expires_at = _parse_expiration(record.get("expires_at"))
    if record.get("expires_at") not in (None, "") and expires_at is None:
        return None
    return ApiConsumer(
        consumer_id=consumer_id,
        name=str(record.get("name") or consumer_id),
        plan=str(record.get("plan") or "sandbox"),
        monthly_quota=quota,
        key_prefix=str(record.get("key_prefix") or ""),
        expires_at=expires_at,
    )


def _find_consumer(api_key: str) -> ApiConsumer | None:
    key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()

    for record in _configured_consumers():
        if str(record.get("key_hash") or "").strip().lower() == key_hash:
            return _consumer_from_record(record)

    if not _truthy(os.getenv("SICETAC_API_CONSUMERS_DB")):
        return None

    try:
        table = os.getenv("SICETAC_API_CONSUMERS_TABLE", "api_consumers")
        response = (
            get_client()
            .table(table)
            .select("consumer_id,name,plan,monthly_quota,key_prefix,key_hash,active,expires_at")
            .eq("key_hash", key_hash)
            .eq("active", True)
            .limit(1)
            .execute()
        )
        record = (response.data or [None])[0]
        return _consumer_from_record(record) if isinstance(record, dict) else None
    except Exception:
        # No filtramos detalles de Supabase al consumidor. El endpoint se
        # comporta como credencial inválida si el registro no está disponible.
        return None


def _extract_api_key(x_api_key: str | None, authorization: str | None) -> str:
    if x_api_key and x_api_key.strip():
        return x_api_key.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


def require_consumer(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> ApiConsumer:
    # La superficie /v1 es para integraciones controladas. El modo por defecto
    # debe fallar cerrado: /consulta conserva su contrato público separado.
    mode = os.getenv("SICETAC_API_ACCESS_MODE", "api_key").strip().lower()
    if mode == "public":
        return ApiConsumer(
            consumer_id="public-demo",
            name="Public demo",
            plan="demo",
            monthly_quota=None,
        )
    if mode != "api_key":
        raise HTTPException(status_code=503, detail="API comercial mal configurada.")

    api_key = _extract_api_key(x_api_key, authorization)
    if not api_key:
        raise HTTPException(status_code=401, detail="Se requiere X-API-Key o Authorization: Bearer.")
    consumer = _find_consumer(api_key)
    if consumer is None or not _consumer_is_current(consumer):
        raise HTTPException(status_code=401, detail="API key inválida o inactiva.")
    return consumer


def _persistent_usage_enabled() -> bool:
    return _truthy(os.getenv("SICETAC_USAGE_PERSISTENCE"))


def _usage_from_database(consumer_id: str) -> int | None:
    try:
        response = (
            get_client()
            .rpc("api_usage_for_month", {
                "p_consumer_id": consumer_id,
                "p_month_key": _month_key(),
            })
            .execute()
        )
        value = response.data
        if isinstance(value, int):
            return value
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, int):
                return first
            if isinstance(first, dict):
                return int(first.get("api_usage_for_month") or 0)
        return None
    except Exception:
        return None


def _current_usage(consumer: ApiConsumer) -> int:
    key = (consumer.consumer_id, _month_key())
    memory_value = _memory_usage.get(key, 0)
    if _persistent_usage_enabled():
        database_value = _usage_from_database(consumer.consumer_id)
        if database_value is None:
            raise HTTPException(status_code=503, detail="Auditoría de consumo no disponible.")
        # Supabase es la fuente de verdad cuando la persistencia está activa;
        # el evento almacenado ya incluye la unidad cobrada.
        return database_value
    return memory_value


def _reserve_unit(consumer: ApiConsumer, *, request_id: str, request: Request) -> tuple[str, int]:
    if _persistent_usage_enabled():
        try:
            response = get_client().rpc("reserve_api_usage", {
                "p_consumer_id": consumer.consumer_id,
                "p_request_id": request_id,
                "p_endpoint": request.url.path,
                "p_method": request.method,
            }).execute()
            rows = response.data or []
            row = rows[0] if isinstance(rows, list) and rows else None
            if not isinstance(row, dict):
                raise RuntimeError("La reserva de consumo no devolvió una respuesta verificable.")
            return str(row["month_key"]), int(row["monthly_usage"])
        except Exception as exc:
            # La función reserva con bloqueo de fila; no volver a la memoria
            # evitará exceder la cuota tras reinicios o llamadas concurrentes.
            detail = str(exc).lower()
            if "quota" in detail:
                raise HTTPException(status_code=429, detail="Cuota mensual agotada.") from None
            if "expired" in detail or "inactive" in detail:
                raise HTTPException(status_code=401, detail="API key inválida o inactiva.") from None
            raise HTTPException(status_code=503, detail="Auditoría de consumo no disponible.") from None
    usage = _current_usage(consumer)
    if consumer.monthly_quota is not None and usage >= consumer.monthly_quota:
        raise HTTPException(status_code=429, detail="Cuota mensual agotada.")
    month = _month_key()
    key = (consumer.consumer_id, month)
    _memory_usage[key] = _memory_usage.get(key, 0) + 1
    return month, usage + 1


def _record_usage(
    consumer: ApiConsumer,
    request: Request,
    request_id: str,
    month: str,
    status_code: int,
    units: int = 1,
) -> None:
    if not _persistent_usage_enabled():
        return
    try:
        get_client().table(os.getenv("SICETAC_USAGE_TABLE", "api_usage_events")).update(
            {
                "status_code": status_code,
                "reservation_status": "completed" if status_code < 400 else "failed",
                "metadata": {"plan": consumer.plan},
            }
        ).eq("consumer_id", consumer.consumer_id).eq("request_id", request_id).execute()
    except Exception:
        logging.getLogger(__name__).exception("No fue posible cerrar la auditoría de consumo %s", request_id)


def _response_meta(
    consumer: ApiConsumer,
    request_id: str,
    units: int,
    usage: int,
) -> dict[str, Any]:
    return {
        "api_version": "v1",
        "request_id": request_id,
        "consumer_id": consumer.consumer_id,
        "plan": consumer.plan,
        "units": units,
        "monthly_usage": usage,
        "monthly_quota": consumer.monthly_quota,
    }


def _json_response(content: Any, request_id: str, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        content=_json_safe(content),
        status_code=status_code,
        headers={"X-Request-Id": request_id},
    )


@router.get("/health", summary="Estado de la API comercial")
def commercial_health() -> dict[str, str]:
    return {"status": "ok", "api": "sicetac", "version": "v1"}


@router.get("/catalog/body-types", summary="Carrocerías SICETAC disponibles")
def commercial_body_types(consumer: ApiConsumer = Depends(require_consumer)) -> dict[str, Any]:
    del consumer
    return {"items": get_sice_column_options()}


@router.get("/catalog/vehicles", summary="Configuraciones vehiculares disponibles")
def commercial_vehicles(consumer: ApiConsumer = Depends(require_consumer)) -> dict[str, Any]:
    del consumer
    df = get_table_df("vehiculos")
    if df.empty:
        return {"items": []}
    columns = [
        column
        for column in ("tipo_vehiculo", "configuracion_analisis", "detalle_tipo_vehiculo", "ejes_configuracion")
        if column in df.columns
    ]
    if not columns:
        return {"items": []}
    return {"items": _json_safe(df[columns].fillna("").drop_duplicates().to_dict(orient="records"))}


@router.get("/catalog/municipalities", summary="Municipios y códigos para resolver origen y destino")
def commercial_municipalities(consumer: ApiConsumer = Depends(require_consumer)) -> dict[str, Any]:
    del consumer
    df = get_table_df("municipios")
    columns = [
        column for column in (
            "codigo_dane", "nombre_oficial", "departamento",
            "variacion_1", "variacion_2", "variacion_3",
        ) if column in df.columns
    ]
    if df.empty or not columns:
        return {"items": []}
    catalog = df[columns].copy()
    if "codigo_dane" in catalog:
        from sicetac_helper import SICETACHelper
        catalog["codigo_dane"] = catalog["codigo_dane"].fillna("").map(SICETACHelper(catalog)._clean_code)
    return {"items": _json_safe(catalog.fillna("").drop_duplicates().to_dict(orient="records"))}


@router.get("/usage", summary="Consumo del periodo del consumidor")
def commercial_usage(consumer: ApiConsumer = Depends(require_consumer)) -> dict[str, Any]:
    usage = _current_usage(consumer)
    return {
        "period": _month_key(),
        "consumer_id": consumer.consumer_id,
        "plan": consumer.plan,
        "used": usage,
        "quota": consumer.monthly_quota,
        "remaining": None if consumer.monthly_quota is None else max(consumer.monthly_quota - usage, 0),
    }


@router.post("/quotes", summary="Cotización SICETAC para integraciones y agentes")
def commercial_quote(
    data: ConsultaInput,
    request: Request,
    consumer: ApiConsumer = Depends(require_consumer),
) -> JSONResponse:
    request_id = str(uuid4())
    month, reserved_usage = _reserve_unit(consumer, request_id=request_id, request=request)
    status_code = 200
    try:
        if data.resumen:
            result = calcular_sicetac_resumen(data)
        else:
            result = calcular_sicetac(data)
        if consulta_solicita_peajes(data):
            result = adjuntar_peajes_a_respuesta(result, data.vehiculo)
        return _json_response(
            {
                "data": result,
                "meta": _response_meta(consumer, request_id, 1, reserved_usage),
            },
            request_id,
        )
    except SicetacError as exc:
        status_code = exc.status_code
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except HTTPException as exc:
        status_code = exc.status_code
        raise
    except Exception:
        status_code = 500
        raise HTTPException(status_code=500, detail="No fue posible calcular la cotización.")
    finally:
        _record_usage(consumer, request, request_id, month, status_code)

# La ruta pública /consulta no importa ni llama este bloque. Estas herramientas
# pertenecen exclusivamente al contrato autenticado /v1 para agentes y APIs pagas.
from pydantic import BaseModel, Field
from cotizador_core import RuleSetValidationError, evaluate_quote
from cotizador_rules import (
    MARKET_SCOPE,
    PublishedRuleSetUnavailable,
    load_published_market_ruleset,
    record_term_observation,
)


class PrequoteInput(BaseModel):
    origen: str | None = None
    destino: str | None = None
    codigo_dane_origen: str | None = None
    codigo_dane_destino: str | None = None
    cargo_weight_value: float = Field(..., ge=0, le=100000)
    cargo_weight_unit: str = Field(..., min_length=1, max_length=4)
    service_code: str = Field("carga_general", min_length=1, max_length=64)
    container_size_ft: int | None = Field(None, ge=1, le=100)
    weight_includes_tare: bool = False
    requested_configuration: str | None = Field(None, max_length=64)
    axles: int | None = Field(None, ge=1, le=12)
    carroceria: str = Field("General - Estacas", min_length=1, max_length=120)
    mes: int | None = None
    peajes: bool = True
    modo_viaje: str = "CARGADO"
    tipo_contenedor: str | None = None
    rutasid_ida: str | None = Field(None, max_length=64)


class TermObservationInput(BaseModel):
    raw_expression: str = Field(..., min_length=1, max_length=160)
    normalized_expression: str | None = Field(None, max_length=160)
    entity_type: str = Field(..., min_length=1, max_length=64)
    suggested_value: str | None = Field(None, max_length=160)


def _prequote_sicetac_input(data: PrequoteInput, configuration: str) -> ConsultaInput:
    return ConsultaInput(
        origen=data.origen,
        destino=data.destino,
        codigo_dane_origen=data.codigo_dane_origen,
        codigo_dane_destino=data.codigo_dane_destino,
        vehiculo=configuration,
        carroceria=data.carroceria,
        mes=data.mes,
        peajes=data.peajes,
        modo_viaje=data.modo_viaje,
        tipo_contenedor=data.tipo_contenedor,
        rutasid_ida=data.rutasid_ida,
        resumen=True,
    )


@router.post("/prequotes", summary="Pre-cotización técnica: Core de vehículos más SICETAC")
def market_prequote(
    data: PrequoteInput,
    request: Request,
    consumer: ApiConsumer = Depends(require_consumer),
) -> JSONResponse:
    """Ruta paga: decide técnicamente y consulta SICETAC sin regla comercial."""
    request_id = str(uuid4())
    month, reserved_usage = _reserve_unit(consumer, request_id=request_id, request=request)
    status_code = 200
    try:
        ruleset = load_published_market_ruleset()
        decision = evaluate_quote(
            {
                "scope_id": MARKET_SCOPE,
                "request_id": request_id,
                "cargo_weight_value": data.cargo_weight_value,
                "cargo_weight_unit": data.cargo_weight_unit,
                "service_code": data.service_code,
                "container_size_ft": data.container_size_ft,
                "weight_includes_tare": data.weight_includes_tare,
                "requested_configuration": data.requested_configuration,
                "axles": data.axles,
            },
            ruleset,
        )
        recommendation = decision.get("recommendation") or {}
        sicetac_reference: dict[str, Any] | None = None
        if recommendation.get("sicetac_configuration"):
            # El ruleset conserva su configuración técnica genérica (p. ej. 2S2),
            # mientras SICETAC recibe su código de catálogo (p. ej. C2S2).
            sicetac_vehicle = recommendation.get("vehicle_model_code") or recommendation["sicetac_configuration"]
            sicetac_input = _prequote_sicetac_input(data, sicetac_vehicle)
            sicetac_reference = calcular_sicetac_resumen(sicetac_input)
            if consulta_solicita_peajes(sicetac_input):
                sicetac_reference = adjuntar_peajes_a_respuesta(sicetac_reference, sicetac_input.vehiculo)
        return _json_response(
            {
                "data": {
                    "technical_decision": decision,
                    "sicetac_reference": sicetac_reference,
                    "commercial": {
                        "configured": False,
                        "emission_allowed": False,
                        "reason": "Las reglas comerciales pertenecen al proyecto consumidor.",
                    },
                },
                "meta": _response_meta(consumer, request_id, 1, reserved_usage),
            },
            request_id,
        )
    except PublishedRuleSetUnavailable as exc:
        status_code = 503
        raise HTTPException(status_code=503, detail=str(exc))
    except (RuleSetValidationError, ValueError) as exc:
        status_code = 422
        raise HTTPException(status_code=422, detail=str(exc))
    except SicetacError as exc:
        status_code = exc.status_code
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except HTTPException as exc:
        status_code = exc.status_code
        raise
    except Exception:
        status_code = 500
        raise HTTPException(status_code=500, detail="No fue posible calcular la pre-cotización técnica.")
    finally:
        _record_usage(consumer, request, request_id, month, status_code)


@router.post("/feedback/terms", summary="Registrar término para revisión técnica")
def register_term_observation(
    data: TermObservationInput,
    consumer: ApiConsumer = Depends(require_consumer),
) -> dict[str, Any]:
    """Aprendizaje gobernado: almacena candidatos, no cambia la regla publicada."""
    request_id = str(uuid4())
    record_term_observation(
        consumer_id=consumer.consumer_id,
        request_id=request_id,
        raw_expression=data.raw_expression.strip(),
        normalized_expression=(data.normalized_expression or "").strip() or None,
        entity_type=data.entity_type.strip(),
        suggested_value=(data.suggested_value or "").strip() or None,
    )
    return {
        "status": "pending_review",
        "request_id": request_id,
        "message": "La observación no altera reglas; requiere revisión y publicación de una nueva versión.",
    }
