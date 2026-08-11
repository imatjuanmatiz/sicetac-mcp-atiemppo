"""Totalización determinística de peajes SICETAC por caseta.

El libro oficial publica una fila por ``RUTA_ID + caseta`` y las tarifas
``VALOR1`` ... ``VALOR7``. Esta capa conserva ese grano y selecciona la
categoría efectiva antes de sumar. No depende de Supabase ni escribe fuentes.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import re
from typing import Any


TOLL_RULE_VERSION = "sicetac-toll-relative-category-v2"
TOLL_COLUMNS = tuple(f"VALOR{i}" for i in range(1, 8))
TOLL_CONFIGURATIONS = ("C2", "C3", "C2S2", "C2S3", "C3S2", "C3S3")
TOLL_CATEGORY_OFFSET = {
    "C2": 3,
    "C3": 2,
    "C2S2": 2,
    "C2S3": 1,
    "C3S2": 1,
    "C3S3": 0,
}
CATEGORY_LABELS = {index: label for index, label in enumerate(("I", "II", "III", "IV", "V", "VI", "VII"), start=1)}


class TollTotalizationError(ValueError):
    """La entrada de peajes no cumple el contrato determinístico."""


def normalize_toll_configuration(value: Any) -> str:
    """Normaliza las etiquetas usadas por la API, Supabase y el Excel."""
    raw = re.sub(r"\s+", "", str(value or "").strip().upper())
    aliases = {
        "2": "C2",
        "3": "C3",
        "CA": "C2",
        "C257": "C2",
        "C279": "C2",
        "C2910": "C2",
        "C2M10": "C2",
        "V2": "C2",
        "V3": "C3",
        "V4": "C3",
        "2S2": "C2S2",
        "2S3": "C2S3",
        "3S2": "C3S2",
        "3S3": "C3S3",
    }
    normalized = aliases.get(raw, raw)
    if normalized not in TOLL_CONFIGURATIONS:
        raise TollTotalizationError(f"Configuración sin regla de peajes: {value}")
    return normalized


def category_label(category: int | None) -> str | None:
    return CATEGORY_LABELS.get(int(category)) if category is not None else None


def _key(row: Any, name: str) -> Any:
    """Obtiene una columna tolerando casing, espacios y guiones bajos."""
    if hasattr(row, "get"):
        direct = row.get(name)
        if direct is not None:
            return direct
        wanted = re.sub(r"[^A-Z0-9]", "", name.upper())
        for candidate, value in row.items():
            if re.sub(r"[^A-Z0-9]", "", str(candidate).upper()) == wanted:
                return value
    return None


def _number(value: Any) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return number if number > 0 else 0.0


def _category_from_label(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    reverse = {label: index for index, label in CATEGORY_LABELS.items()}
    if text in reverse:
        return reverse[text]
    try:
        number = int(float(text))
    except (TypeError, ValueError):
        return None
    return number if 1 <= number <= 7 else None


def select_effective_toll(row: Any, configuration: Any) -> dict[str, Any]:
    """Selecciona una categoría efectiva para una caseta.

    La respuesta incluye las tarifas originales para que el API pueda auditar
    la decisión y no tenga que reconstruirlas desde un total agregado.
    """
    normalized = normalize_toll_configuration(configuration)
    values = {column: _number(_key(row, column)) for column in TOLL_COLUMNS}
    available = [index for index in range(1, 8) if values[f"VALOR{index}"] > 0]
    maximum = max(available) if available else None
    target = maximum - TOLL_CATEGORY_OFFSET[normalized] if maximum is not None else None

    if not available:
        effective = None
        status = "all_categories_zero"
        fallback_reason = "No hay categorías con tarifa positiva."
        value = 0.0
    elif target is not None and target >= 1 and values[f"VALOR{target}"] > 0:
        effective = target
        status = "relative_exact"
        fallback_reason = None
        value = values[f"VALOR{effective}"]
    else:
        lower = [index for index in available if target is not None and index < target]
        if lower:
            effective = max(lower)
            status = "fallback_lower"
            fallback_reason = (
                f"VALOR{target} no está disponible; se usa la mayor categoría "
                f"positiva inferior."
            )
            value = values[f"VALOR{effective}"]
        else:
            effective = None
            status = "no_lower_category_available_review"
            fallback_reason = (
                "La categoría objetivo no está disponible y no existe una "
                "categoría positiva inferior; no se permite promover."
            )
            value = 0.0

    return {
        "configuracion": normalized,
        "rule_id": TOLL_RULE_VERSION,
        "categoria_objetivo": target,
        "categoria_objetivo_label": category_label(target),
        # Alias transitorio para consumidores de la respuesta v1.
        "categoria_nominal": target,
        "categoria_nominal_label": category_label(target),
        "categoria_efectiva": effective,
        "categoria_efectiva_label": category_label(effective),
        "categoria_maxima_disponible": maximum,
        "categoria_maxima_disponible_label": category_label(maximum),
        "categorias_disponibles": available,
        "valor_efectivo": float(value),
        "selection_status": status,
        "fallback_reason": fallback_reason,
        # Alias transitorio para consumidores de la respuesta v1.
        "razon": status,
        "valores_originales": values,
    }


def _rows_from_input(rows: Any) -> list[dict[str, Any]]:
    if rows is None:
        return []
    if hasattr(rows, "to_dict"):
        return list(rows.to_dict(orient="records"))
    return [dict(row) for row in rows]


def _caseta_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    source_cut = str(
        _key(row, "SOURCE_CUT")
        or _key(row, "MES_VIGENCIA")
        or _key(row, "FECHA_TARIFA")
        or ""
    ).strip()
    route = str(_key(row, "RUTA_ID") or _key(row, "ID_SICE") or "").strip()
    id_peaje = str(_key(row, "ID_PEAJE") or "").strip()
    orden = str(_key(row, "ORDEN") or "").strip()
    if id_peaje:
        return (source_cut, route, id_peaje, orden)
    name = str(_key(row, "NOMBRE_PEAJE") or _key(row, "nombre_peaje") or "").strip().upper()
    return (source_cut, route, name, orden)


def _tariff_pattern(row: dict[str, Any]) -> tuple[float, ...]:
    return tuple(_number(_key(row, column)) for column in TOLL_COLUMNS)


def totalize_toll_rows(rows: Any, configuration: Any) -> dict[str, Any]:
    """Totaliza filas de una ruta, una sola vez por caseta."""
    normalized = normalize_toll_configuration(configuration)
    source_rows = _rows_from_input(rows)
    unique: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    duplicates = 0
    for row in source_rows:
        key = _caseta_key(row)
        if key in unique:
            if _tariff_pattern(unique[key]) != _tariff_pattern(row):
                raise TollTotalizationError(
                    "conflicting_tariff_patterns: una misma ocurrencia "
                    "ruta-peaje-orden tiene patrones VALOR1..VALOR7 distintos"
                )
            duplicates += 1
            continue
        unique[key] = row

    details: list[dict[str, Any]] = []
    def _order_key(item: dict[str, Any]) -> tuple[int, float | str]:
        raw_order = _key(item, "ORDEN") or _key(item, "orden")
        try:
            return (0, float(raw_order))
        except (TypeError, ValueError):
            return (1, str(raw_order or ""))

    for row in sorted(unique.values(), key=lambda item: (_order_key(item), str(_key(item, "ID_PEAJE") or ""))):
        selection = select_effective_toll(row, normalized)
        # A normalized legacy view may contain only the already selected value.
        # It is accepted as a compatibility fallback but is marked explicitly.
        has_raw_values = any(_key(row, column) is not None for column in TOLL_COLUMNS)
        if not has_raw_values and _key(row, "VALOR_PEAJE") is not None:
            selection["valor_efectivo"] = _number(_key(row, "VALOR_PEAJE"))
            selection["categoria_efectiva"] = _category_from_label(
                _key(row, "CATEGORIA_USADA")
            )
            selection["categoria_efectiva_label"] = category_label(selection["categoria_efectiva"])
            selection["selection_status"] = "legacy_precalculated_value"
            selection["fallback_reason"] = (
                "La fuente no expone VALOR1..VALOR7; no puede auditarse con la regla relativa."
            )
            selection["razon"] = "legacy_precalculated_value"
            selection["valores_originales"] = {}
        details.append(
            {
                "ruta_id": _key(row, "RUTA_ID") or _key(row, "ID_SICE") or _key(row, "id_sice"),
                "orden": _key(row, "ORDEN") or _key(row, "orden"),
                "id_peaje": str(_key(row, "ID_PEAJE") or _key(row, "id_peaje") or "").strip() or None,
                "nombre_peaje": _key(row, "NOMBRE_PEAJE") or _key(row, "nombre_peaje"),
                **selection,
            }
        )

    blocked = any(
        item["selection_status"] == "no_lower_category_available_review"
        for item in details
    )
    return {
        "configuracion": normalized,
        "version_regla": TOLL_RULE_VERSION,
        "estado": "blocked_missing_effective_toll_tariff" if blocked else (
            "no_toll_rows" if not source_rows else "ok"
        ),
        "cantidad_filas_fuente": len(source_rows),
        "cantidad_casetas_unicas": len(details),
        "duplicados_ignorados": duplicates,
        "total_peajes": None if blocked else float(sum(item["valor_efectivo"] for item in details)),
        "detalle": details,
    }


def source_manifest(path: Path | str, row_count: int | None = None) -> dict[str, Any]:
    """Construye el manifiesto mínimo del corte oficial sin copiar el libro."""
    source = Path(path)
    digest = sha256()
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    match = re.search(r"(20\d{2})[-_](\d{2})[-_](\d{2})", source.name)
    cutoff = "-".join(match.groups()) if match else None
    return {
        "fuente_archivo": source.name,
        "fuente_corte": cutoff,
        "fuente_sha256": digest.hexdigest(),
        "filas_fuente": row_count,
        "version_regla": TOLL_RULE_VERSION,
    }
