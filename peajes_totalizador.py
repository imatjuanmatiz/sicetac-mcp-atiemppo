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


TOLL_RULE_VERSION = "sicetac-peajes-caseta-v2-relative-max"
TOLL_COLUMNS = tuple(f"VALOR{i}" for i in range(1, 8))
TOLL_CONFIGURATIONS = ("C2", "C3", "C2S2", "C2S3", "C3S2", "C3S3")
BASE_CATEGORY_AT_MAX_FIVE = {
    "C2": 2,
    "C3": 3,
    "C2S2": 3,
    "C2S3": 4,
    "C3S2": 4,
}
CATEGORY_OFFSET_BY_CONFIGURATION = {
    configuration: category - 5
    for configuration, category in BASE_CATEGORY_AT_MAX_FIVE.items()
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
        "C2M10": "C2",
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
    if normalized == "C3S3":
        nominal = maximum
    else:
        nominal = maximum + CATEGORY_OFFSET_BY_CONFIGURATION[normalized] if maximum is not None else None

    if not available:
        effective = None
        reason = "todas_categorias_cero"
        value = 0.0
    elif maximum < 2:
        # La categoría I no representa una tarifa válida para las
        # configuraciones de carga del catálogo histórico; se conserva la
        # caseta para auditoría, pero no se cobra a ningún vehículo.
        effective = None
        reason = "categoria_maxima_insuficiente"
        value = 0.0
    elif normalized == "C3S3":
        effective = maximum
        reason = "ultima_categoria_disponible_por_caseta"
        value = values[f"VALOR{effective}"]
    elif nominal is None or nominal < 1 or nominal > 7:
        effective = None
        reason = "categoria_objetivo_fuera_de_rango"
        value = 0.0
    elif values[f"VALOR{nominal}"] <= 0:
        effective = None
        reason = "categoria_objetivo_no_disponible"
        value = 0.0
    else:
        effective = nominal
        reason = "categoria_relativa_disponible"
        value = values[f"VALOR{effective}"]

    return {
        "configuracion": normalized,
        "categoria_nominal": nominal,
        "categoria_nominal_label": category_label(nominal),
        "categoria_efectiva": effective,
        "categoria_efectiva_label": category_label(effective),
        "categoria_maxima_disponible": max(available) if available else None,
        "categoria_maxima_disponible_label": category_label(max(available)) if available else None,
        "categorias_disponibles": available,
        "valor_efectivo": float(value),
        "razon": reason,
        "valores_originales": values,
    }


def _rows_from_input(rows: Any) -> list[dict[str, Any]]:
    if rows is None:
        return []
    if hasattr(rows, "to_dict"):
        return list(rows.to_dict(orient="records"))
    return [dict(row) for row in rows]


def _caseta_key(row: dict[str, Any]) -> tuple[str, str]:
    id_peaje = str(_key(row, "ID_PEAJE") or "").strip()
    if id_peaje:
        return ("id_peaje", id_peaje)
    orden = str(_key(row, "ORDEN") or _key(row, "orden") or "").strip()
    name = str(_key(row, "NOMBRE_PEAJE") or _key(row, "nombre_peaje") or "").strip().upper()
    return ("fallback", f"{orden}|{name}")


def totalize_toll_rows(rows: Any, configuration: Any) -> dict[str, Any]:
    """Totaliza filas de una ruta, una sola vez por caseta."""
    normalized = normalize_toll_configuration(configuration)
    source_rows = _rows_from_input(rows)
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    duplicates = 0
    for row in source_rows:
        key = _caseta_key(row)
        if key in unique:
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
            selection["razon"] = "valor_precalculado_legacy"
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

    return {
        "configuracion": normalized,
        "version_regla": TOLL_RULE_VERSION,
        "cantidad_filas_fuente": len(source_rows),
        "cantidad_casetas_unicas": len(details),
        "duplicados_ignorados": duplicates,
        "total_peajes": float(sum(item["valor_efectivo"] for item in details)),
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
