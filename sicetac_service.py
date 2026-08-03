from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import Any
import unicodedata

import pandas as pd
from pydantic import BaseModel
import time

from supabase_data import (
    get_peajes_detalle_df,
    get_peajes_resumen_df,
    get_sicetac_movilizacion_df,
    get_sicetac_vacio_df,
    get_sicetac_valorhora_df,
    get_valor_plaza_df,
    get_table_df,
)
from sicetac_helper import SICETACHelper
from modelo_sicetac import calcular_modelo_sicetac_extendido
from modelo_sicetac_vacio import calcular_modelo_sicetac_extendido_vacio


class ConsultaInput(BaseModel):
    origen: str | None = None
    destino: str | None = None
    codigo_dane_origen: str | None = None
    codigo_dane_destino: str | None = None
    vehiculo: str = "C3S3"
    mes: int | None = None
    carroceria: str = "GENERAL"
    tipo_contenedor: str | None = None
    viaje_redondo: bool = False
    tipo_contenedor_regreso: str | None = None
    rutasid_ida: str | None = None
    rutasid_regreso: str | None = None
    valor_peaje_manual: float = 0.0
    valor_peajes_manual: float = 0.0

    # LEGACY: sigue existiendo para no romper nada
    horas_logisticas: float | None = None

    # NUEVO: tiempo logístico que pide el usuario (cargue/descargue total)
    horas_logisticas_personalizadas: float | None = None

    # NUEVO: tarifa de stand by por hora > 8h
    tarifa_standby: float = 150000.0

    km_plano: float = 0
    km_ondulado: float = 0
    km_montañoso: float = 0
    km_montanoso: float = 0
    km_urbano: float = 0
    km_despavimentado: float = 0
    modo_viaje: str = "CARGADO"

    # NUEVO: modo escenarios de tiempos logísticos
    modo_tiempos_logisticos: bool = False

    # NUEVO: respuesta resumida (por defecto True)
    resumen: bool = True

    # NUEVO: compara los totales oficiales contra diciembre de 2025.
    # Se mantiene apagado por defecto para preservar el contrato existente.
    modo_aumento: bool = False

    # NUEVO: modo manual puro (sin buscar municipios/rutas)
    manual_mode: bool = False

    # NUEVO: incluir detalle de peajes en la respuesta de consulta.
    peajes: bool = False
    incluir_peajes: bool = False
    detalle_peajes: bool = False


@dataclass
class SicetacError(Exception):
    status_code: int
    detail: str


SICE_COLUMN_OPTIONS: list[dict[str, str]] = [
    {
        "column": "GENERAL_ESTACAS_CARGADO",
        "vacio_column": "ESTACAS_VACIO",
        "label": "General - Estacas",
        "aliases": "GENERAL|GENERAL ESTACAS|GENERAL - ESTACAS|GENERAL ESTACA|GENERAL - ESTIBA",
    },
    {
        "column": "GENERAL_FURGON_CARGADO",
        "vacio_column": "FURGON_VACIO",
        "label": "General - Furgon",
        "aliases": "FURGON GENERAL|GENERAL FURGON|GENERAL - FURGON",
    },
    {
        "column": "GENERAL_ESTIBAS_CARGADO",
        "vacio_column": "ESTIBAS_VACIO",
        "label": "General - Estibas",
        "aliases": "ESTIBA|ESTIBAS|GENERAL ESTIBAS|GENERAL - ESTIBAS",
    },
    {
        "column": "GENERAL_PLATAFORMA_CARGADO",
        "vacio_column": "PLATAFORMA_VACIO",
        "label": "General - Plataforma",
        "aliases": "PLATAFORMA|GENERAL PLATAFORMA|GENERAL - PLATAFORMA|GENERA - PLATAFORMA",
    },
    {
        "column": "CONTENEDOR_PORTACONTENEDORES_CARGADO",
        "contenedor_vacio_column": "CONTENEDOR_PORTACONTENEDORES_VACIO",
        "vacio_column": "PORTACONTENEDORES_VACIO",
        "label": "Portacontenedores",
        "aliases": "PORTACONTENEDORES|PORTA CONTENEDORES|CONTENEDOR PORTACONTENEDORES",
    },
    {
        "column": "CARGA_REFRIGERADA_FURGON_REFRIGERADO_CARGADO",
        "vacio_column": "FURGON_REFRIGERADO_VACIO",
        "label": "Furgon Refrigerado",
        "aliases": "FURGON REFRIGERADO|CARGA REFRIGERADA|REFRIGERADO",
    },
    {
        "column": "GRANEL_SOLIDO_ESTACAS_CARGADO",
        "vacio_column": "ESTACAS_VACIO",
        "label": "Granel Solido - Estacas",
        "aliases": "ESTACAS GRANEL SOLIDO|GRANEL SOLIDO ESTACAS|GRANEL SOLIDO - ESTACAS",
    },
    {
        "column": "GRANEL_SOLIDO_FURGON_CARGADO",
        "vacio_column": "FURGON_VACIO",
        "label": "Granel Solido - Furgon",
        "aliases": "FURGON GRANEL SOLIDO|GRANEL SOLIDO FURGON|GRANEL SOLIDO - FURGON",
    },
    {
        "column": "GRANEL_SOLIDO_VOLCO_CARGADO",
        "vacio_column": "VOLCO_VACIO",
        "label": "Granel Solido - Volco",
        "aliases": "VOLCO|GRANEL SOLIDO VOLCO|GRANEL SOLIDO - VOLCO",
    },
    {
        "column": "GRANEL_SOLIDO_ESTIBAS_CARGADO",
        "vacio_column": "ESTIBAS_VACIO",
        "label": "Granel Solido - Estibas",
        "aliases": "ESTIBAS GRANEL SOLIDO|GRANEL SOLIDO ESTIBAS|GRANEL SOLIDO - ESTIBAS",
    },
    {
        "column": "GRANEL_SOLIDO_PLATAFORMA_CARGADO",
        "vacio_column": "PLATAFORMA_VACIO",
        "label": "Granel Solido - Plataforma",
        "aliases": "PLATAFORMA GRANEL SOLIDO|GRANEL SOLIDO PLATAFORMA|GRANEL SOLIDO - PLATAFORMA",
    },
    {
        "column": "GRANEL_LIQUIDO_TANQUE_CARGADO",
        "vacio_column": "TANQUE_VACIO",
        "label": "Granel Liquido - Tanque",
        "aliases": "TANQUE - GRANEL LIQUIDO|TANQUE GRANEL LIQUIDO|GRANEL LIQUIDO TANQUE|GRANEL LQUIDO TANQUE",
    },
]


def _normalize_lookup_text(value: str | None) -> str:
    text = str(value or "").strip().upper()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\s+", " ", text)
    return text


_SICE_COLUMN_MAP: dict[str, dict[str, str]] = {}
for item in SICE_COLUMN_OPTIONS:
    _SICE_COLUMN_MAP[item["column"]] = item
    _SICE_COLUMN_MAP[_normalize_lookup_text(item["label"])] = item
    for alias in item["aliases"].split("|"):
        _SICE_COLUMN_MAP[_normalize_lookup_text(alias)] = item


def get_sice_column_options() -> list[dict[str, str]]:
    return [
        {"column": item["column"].lower(), "label": item["label"]}
        for item in SICE_COLUMN_OPTIONS
    ]


def _convertir_nativos(d: Any):
    if isinstance(d, dict):
        return {k: _convertir_nativos(v) for k, v in d.items()}
    if isinstance(d, list):
        return [_convertir_nativos(v) for v in d]
    if hasattr(d, "item"):
        return d.item()
    return d


def _normalizar_configuracion_peaje(configuracion: str | None) -> str | None:
    raw = str(configuracion or "").strip().upper().replace(" ", "")
    if not raw:
        return None
    return {
        "2S2": "C2S2",
        "2S3": "C2S3",
        "3S2": "C3S2",
        "3S3": "C3S3",
    }.get(raw, raw)


def obtener_peajes_detalle(id_sice: int, configuracion: str | None = None) -> dict[str, Any]:
    configuracion_norm = _normalizar_configuracion_peaje(configuracion)
    df_detalle = get_peajes_detalle_df(id_sice, configuracion_norm)
    df_resumen = get_peajes_resumen_df(id_sice)

    if df_detalle.empty:
        raise SicetacError(404, f"No hay detalle de peajes para ID_SICE {id_sice}")

    if configuracion_norm and not df_resumen.empty and "configuracion" in df_resumen.columns:
        df_resumen = df_resumen[
            df_resumen["configuracion"].astype(str).str.upper() == configuracion_norm
        ]

    first = df_detalle.iloc[0]

    def _num(value: Any) -> float:
        try:
            if pd.isna(value):
                return 0.0
            return float(value)
        except Exception:
            return 0.0

    resumen: dict[str, dict[str, Any]] = {}
    if not df_resumen.empty:
        for _, row in df_resumen.iterrows():
            cfg = str(row.get("configuracion") or "").strip()
            if not cfg:
                continue
            resumen[cfg] = {
                "cantidad_peajes": int(_num(row.get("cantidad_peajes"))),
                "total_peajes": _num(row.get("total_peajes")),
            }
    else:
        for cfg, group in df_detalle.groupby("configuracion"):
            resumen[str(cfg)] = {
                "cantidad_peajes": int(group["id_peaje"].nunique()),
                "total_peajes": float(group["valor_peaje"].sum()),
            }

    detalle: list[dict[str, Any]] = []
    for (orden, id_peaje), group in df_detalle.groupby(["orden", "id_peaje"], sort=True):
        group_sorted = group.sort_values(by="configuracion")
        base = group_sorted.iloc[0]
        valores = {}
        categorias = {}
        for _, row in group_sorted.iterrows():
            cfg = str(row.get("configuracion") or "").strip()
            if not cfg:
                continue
            valores[cfg] = _num(row.get("valor_peaje"))
            categorias[cfg] = {
                "categoria_usada": row.get("categoria_usada"),
                "configuracion_sicetac": row.get("configuracion_sicetac"),
            }

        detalle.append({
            "orden": int(_num(orden)),
            "id_peaje": str(id_peaje),
            "nombre_peaje": base.get("nombre_peaje"),
            "categoria_maxima_disponible": base.get("categoria_maxima_disponible"),
            "valores": valores,
            "categorias": categorias,
        })

    return _convertir_nativos({
        "id_sice": int(id_sice),
        "mes": int(first.get("mes_codigo")) if first.get("mes_codigo") is not None else None,
        "mes_vigencia": first.get("mes_vigencia"),
        "nombre_ruta": first.get("nombre_ruta"),
        "ruta": first.get("ruta"),
        "codigo_dane_origen": first.get("codigo_dane_origen"),
        "codigo_dane_destino": first.get("codigo_dane_destino"),
        "configuracion": configuracion_norm,
        "resumen": resumen,
        "detalle": detalle,
    })


def consulta_solicita_peajes(data: ConsultaInput) -> bool:
    return bool(
        getattr(data, "peajes", False)
        or getattr(data, "incluir_peajes", False)
        or getattr(data, "detalle_peajes", False)
    )


def _extraer_id_sice(payload: dict[str, Any]) -> int | None:
    candidates = [
        payload.get("ID_SICE"),
        payload.get("id_sice"),
        payload.get("RUTASID"),
        payload.get("rutasid"),
        (payload.get("detalle_lookup") or {}).get("rutasid")
        if isinstance(payload.get("detalle_lookup"), dict)
        else None,
        (payload.get("detalle_lookup") or {}).get("id_sice")
        if isinstance(payload.get("detalle_lookup"), dict)
        else None,
    ]
    for value in candidates:
        try:
            if value is None or str(value).strip() == "":
                continue
            return int(float(str(value).strip()))
        except Exception:
            continue
    return None


def _resumen_peajes_config(detalle: dict[str, Any], configuracion: str | None) -> dict[str, Any] | None:
    resumen = detalle.get("resumen") if isinstance(detalle, dict) else None
    if not isinstance(resumen, dict):
        return None
    config_norm = _normalizar_configuracion_peaje(configuracion)
    if config_norm and config_norm in resumen:
        return resumen[config_norm]
    first = next(iter(resumen.values()), None)
    return first if isinstance(first, dict) else None


def adjuntar_peajes_a_respuesta(respuesta: dict[str, Any], configuracion: str | None = None) -> dict[str, Any]:
    if not isinstance(respuesta, dict):
        return respuesta

    config_norm = _normalizar_configuracion_peaje(configuracion or respuesta.get("configuracion"))
    variantes = respuesta.get("variantes")
    targets = variantes if isinstance(variantes, list) and variantes else [respuesta]

    cache: dict[int, dict[str, Any]] = {}
    errores: list[dict[str, Any]] = []
    incluidos = 0

    for target in targets:
        if not isinstance(target, dict):
            continue
        id_sice = _extraer_id_sice(target)
        if id_sice is None:
            continue
        try:
            if id_sice not in cache:
                cache[id_sice] = obtener_peajes_detalle(id_sice, config_norm)
            detalle = cache[id_sice]
            target["peajes_detalle"] = detalle
            target["peajes_resumen"] = _resumen_peajes_config(detalle, config_norm)
            incluidos += 1
        except SicetacError as ex:
            errores.append({"id_sice": id_sice, "error": ex.detail, "status_code": ex.status_code})

    respuesta["peajes_consulta"] = {
        "solicitado": True,
        "configuracion": config_norm,
        "rutas_con_peajes": incluidos,
        "errores": errores,
    }
    return respuesta


def _clean_id(x) -> str:
    s = str(x or "").strip()
    if not s:
        return ""
    digits = re.sub(r"\D", "", s)
    if digits:
        return digits
    if s.endswith(".0") and s[:-2].isdigit():
        return s[:-2]
    return s


def _display_name(input_value: str | None, resolved_name: str | None) -> str:
    text = str(input_value or "").strip()
    if text:
        return text
    return str(resolved_name or "").strip()


def _resolved_route_payload(
    *,
    origen_input: str | None,
    destino_input: str | None,
    origen_info: dict[str, Any] | None,
    destino_info: dict[str, Any] | None,
) -> dict[str, Any]:
    cod_origen = _clean_id(origen_info.get("codigo_dane")) if origen_info else ""
    cod_destino = _clean_id(destino_info.get("codigo_dane")) if destino_info else ""
    return {
        "input_origen": str(origen_input or "").strip() or None,
        "input_destino": str(destino_input or "").strip() or None,
        "codigo_dane_origen": cod_origen or None,
        "codigo_dane_destino": cod_destino or None,
        "origen_nombre": origen_info.get("nombre_oficial") if origen_info else None,
        "destino_nombre": destino_info.get("nombre_oficial") if destino_info else None,
        "origen_departamento": origen_info.get("departamento") if origen_info else None,
        "destino_departamento": destino_info.get("departamento") if destino_info else None,
        "origen_resolution_mode": origen_info.get("resolution_mode") if origen_info else None,
        "destino_resolution_mode": destino_info.get("resolution_mode") if destino_info else None,
        "route_code": f"{cod_origen}-{cod_destino}" if cod_origen and cod_destino else None,
    }


def _resolve_route_inputs(data: ConsultaInput, helper: SICETACHelper) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str, str]:
    origen_info = helper.resolver_municipio_input(data.origen, data.codigo_dane_origen)
    destino_info = helper.resolver_municipio_input(data.destino, data.codigo_dane_destino)

    if not origen_info or not destino_info:
        raise SicetacError(404, "Origen o destino no encontrado")

    resolved_route = _resolved_route_payload(
        origen_input=data.origen,
        destino_input=data.destino,
        origen_info=origen_info,
        destino_info=destino_info,
    )
    origen_display = _display_name(data.origen, origen_info.get("nombre_oficial"))
    destino_display = _display_name(data.destino, destino_info.get("nombre_oficial"))
    return origen_info, destino_info, resolved_route, origen_display, destino_display


def _attach_resolved_route(payload: dict[str, Any], resolved_route: dict[str, Any]) -> dict[str, Any]:
    payload["resolved_route"] = resolved_route
    return payload


def _valor_plaza_selector(carroceria: str | None) -> tuple[str, str, str | None]:
    normalized = _normalize_lookup_text(carroceria)
    if "REFRIGERADO" in normalized or "FRIO" in normalized:
        return ("valor_en_plaza_refrigerada", "Refrigerada", "fuente_refrigerada")
    return ("valor_en_plaza_carga_normal", "Carga normal", "fuente_carga_normal")


def _mes_label(mes_codigo: Any) -> str:
    digits = re.sub(r"\D", "", str(mes_codigo or ""))
    if len(digits) >= 6:
        return f"{digits[:4]}-{digits[4:6]}"
    return str(mes_codigo or "")


def _build_valor_plaza_summary(
    *,
    route_code: str | None,
    configuracion_lookup: str | None,
    carroceria: str | None,
    max_months: int = 3,
) -> dict[str, Any] | None:
    route_norm = str(route_code or "").strip()
    configuracion_norm = str(configuracion_lookup or "").strip().upper()
    if not route_norm or not configuracion_norm:
        return None

    df_plaza = get_valor_plaza_df(route_norm, configuracion_norm)
    if df_plaza.empty:
        return None

    preferred_column, label, preferred_source_column = _valor_plaza_selector(carroceria)
    fallback_column = "valor_en_plaza_carga_normal"
    fallback_source_column = "fuente_carga_normal"

    meses: list[dict[str, Any]] = []
    valores: list[float] = []
    fallback_used = False

    for _, row in df_plaza.iterrows():
        valor = row.get(preferred_column)
        fuente = row.get(preferred_source_column)
        tipo_utilizado = label

        if pd.isna(valor) or valor in (None, ""):
            if preferred_column != fallback_column:
                valor = row.get(fallback_column)
                fuente = row.get(fallback_source_column)
                tipo_utilizado = "Carga normal"
                fallback_used = True

        try:
            valor_float = float(valor)
        except Exception:
            continue
        if pd.isna(valor_float):
            continue

        meses.append(
            {
                "mes_codigo": int(row.get("mes_codigo")) if not pd.isna(row.get("mes_codigo")) else row.get("mes_codigo"),
                "mes_label": _mes_label(row.get("mes_codigo")),
                "valor": valor_float,
                "fuente": str(fuente).strip() or None,
                "tipo_carga_usado": tipo_utilizado,
            }
        )
        valores.append(valor_float)
        if len(meses) >= max_months:
            break

    if not meses:
        return None

    promedio = sum(valores) / len(valores)
    return {
        "route_code": route_norm,
        "configuracion_analisis": configuracion_norm,
        "tipo_carga_label": label,
        "tipo_carga_column": preferred_column,
        "fallback_to_carga_normal": fallback_used,
        "meses": meses,
        "promedio_ultimos_meses": promedio,
    }


def _attach_valor_plaza(
    payload: dict[str, Any],
    *,
    resolved_route: dict[str, Any] | None,
    configuracion_lookup: str | None,
    carroceria: str | None,
    tipo_contenedor: str | None = None,
) -> dict[str, Any]:
    # SICETAC no define Valor en Plaza para la operación de contenedor vacío.
    if _es_contenedor_vacio(carroceria or "", tipo_contenedor):
        payload["valor_plaza_no_aplica"] = "CONTENEDOR_VACIO"
        return payload
    if not resolved_route:
        return payload
    route_code = resolved_route.get("route_code")
    plaza = _build_valor_plaza_summary(
        route_code=route_code,
        configuracion_lookup=configuracion_lookup,
        carroceria=carroceria,
    )
    if plaza:
        payload["valor_plaza"] = plaza
    return payload


def _get_dataframes():
    df_municipios = get_table_df("municipios")
    df_vehiculos = get_table_df("vehiculos")
    df_parametros = get_table_df("parametros")
    df_costos_fijos = get_table_df("costos_fijos")
    df_peajes = get_table_df("peajes")
    df_rutas = get_table_df("rutas")
    # SICETAC consolidado se consulta por lookup puntual para no cargar 116k filas en memoria.
    df_sicetac_movilizacion = pd.DataFrame()
    df_sicetac_valorhora = pd.DataFrame()
    return (
        df_municipios,
        df_vehiculos,
        df_parametros,
        df_costos_fijos,
        df_peajes,
        df_rutas,
        df_sicetac_movilizacion,
        df_sicetac_valorhora,
    )


_RUTAS_INDEX: dict[tuple[str, str], list[pd.Series]] | None = None
_PEAJES_INDEX: dict[tuple[str, str], list[float]] | None = None
_LAST_REFRESH_TS: float | None = None
_CACHE_TTL_SECONDS = int(float(
    (os.getenv("SICETAC_CACHE_TTL_SECONDS") or str(7 * 24 * 3600))
))
_USE_CONSOLIDATED_LOOKUP = (os.getenv("SICETAC_USE_CONSOLIDATED_LOOKUP", "true").strip().lower() != "false")


def _get_rutas_index(df_rutas: pd.DataFrame) -> dict[tuple[str, str], list[pd.Series]]:
    global _RUTAS_INDEX
    if _RUTAS_INDEX is not None:
        return _RUTAS_INDEX
    if df_rutas is None or df_rutas.empty:
        _RUTAS_INDEX = {}
        return _RUTAS_INDEX

    if "CODIGO_DANE_ORIGEN" not in df_rutas.columns or "CODIGO_DANE_DESTINO" not in df_rutas.columns:
        _RUTAS_INDEX = {}
        return _RUTAS_INDEX

    index: dict[tuple[str, str], list[pd.Series]] = {}
    for _, row in df_rutas.iterrows():
        key = (_clean_id(row["CODIGO_DANE_ORIGEN"]), _clean_id(row["CODIGO_DANE_DESTINO"]))
        index.setdefault(key, []).append(row)
    _RUTAS_INDEX = index
    return _RUTAS_INDEX


def _get_peajes_index(df_peajes: pd.DataFrame) -> dict[tuple[str, str], list[float]]:
    global _PEAJES_INDEX
    if _PEAJES_INDEX is not None:
        return _PEAJES_INDEX
    if df_peajes is None or df_peajes.empty:
        _PEAJES_INDEX = {}
        return _PEAJES_INDEX

    if "ID_SICE" not in df_peajes.columns or "EJES_CONFIGURACION" not in df_peajes.columns:
        _PEAJES_INDEX = {}
        return _PEAJES_INDEX

    index: dict[tuple[str, str], list[float]] = {}
    for _, row in df_peajes.iterrows():
        key = (_clean_id(row["ID_SICE"]), _clean_id(row["EJES_CONFIGURACION"]))
        try:
            valor = float(row.get("VALOR_PEAJE", 0))
        except Exception:
            valor = 0.0
        index.setdefault(key, []).append(valor)
    _PEAJES_INDEX = index
    return _PEAJES_INDEX


def _refresh_cache(force: bool = False) -> None:
    global _LAST_REFRESH_TS, _RUTAS_INDEX, _PEAJES_INDEX
    now = time.time()
    if not force and _LAST_REFRESH_TS is not None:
        if (now - _LAST_REFRESH_TS) < _CACHE_TTL_SECONDS:
            return

    # Limpiar cache de tablas Supabase
    try:
        get_table_df.cache_clear()
    except Exception:
        pass
    try:
        get_sicetac_movilizacion_df.cache_clear()
    except Exception:
        pass
    try:
        get_sicetac_vacio_df.cache_clear()
    except Exception:
        pass
    try:
        get_sicetac_valorhora_df.cache_clear()
    except Exception:
        pass
    try:
        get_peajes_detalle_df.cache_clear()
    except Exception:
        pass
    try:
        get_peajes_resumen_df.cache_clear()
    except Exception:
        pass

    # Limpiar índices
    _RUTAS_INDEX = None
    _PEAJES_INDEX = None
    _LAST_REFRESH_TS = now


def _latest_mes(df_parametros: pd.DataFrame) -> int | None:
    if df_parametros is None or df_parametros.empty or "MES" not in df_parametros.columns:
        return None
    try:
        return int(pd.to_numeric(df_parametros["MES"], errors="coerce").max())
    except Exception:
        return None


def _manual_km_montanoso(data: ConsultaInput) -> float:
    # Compatibilidad de nombres: km_montañoso (legacy) y km_montanoso (nuevo).
    return float(getattr(data, "km_montanoso", 0) or getattr(data, "km_montañoso", 0) or 0)


def _manual_valor_peaje(data: ConsultaInput) -> float:
    # Compatibilidad de nombres: valor_peaje_manual (legacy) y valor_peajes_manual (nuevo).
    return float(getattr(data, "valor_peajes_manual", 0) or getattr(data, "valor_peaje_manual", 0) or 0)


def _has_manual_distances(data: ConsultaInput) -> bool:
    return any([
        float(getattr(data, "km_plano", 0) or 0),
        float(getattr(data, "km_ondulado", 0) or 0),
        float(_manual_km_montanoso(data) or 0),
        float(getattr(data, "km_urbano", 0) or 0),
        float(getattr(data, "km_despavimentado", 0) or 0),
    ])


def _configuracion_lookup(fila_conf: pd.Series, vehiculo: str) -> str:
    value = (
        fila_conf.get("CONFIGURACION_SICETAC_LOOKUP")
        or fila_conf.get("configuracion_sicetac_lookup")
        or fila_conf.get("CONFIGURACION_ANALISIS")
        or fila_conf.get("EJES_CONFIGURACION")
        or vehiculo
    )
    return str(value).strip().upper()


def _fila_vehiculo(df_vehiculos: pd.DataFrame, vehiculo: str) -> pd.Series:
    """Resuelve un vehículo sin depender de mayúsculas ni del prefijo ``C``."""
    input_norm = str(vehiculo or "").strip().upper().replace("C", "")
    catalogo = df_vehiculos["TIPO_VEHICULO"].astype(str).str.upper()
    coincidencias = df_vehiculos[catalogo.str.replace("C", "", regex=False) == input_norm]
    if coincidencias.empty:
        opciones = ", ".join(catalogo.tolist())
        raise SicetacError(400, f"Vehículo '{vehiculo}' no encontrado. Opciones válidas: {opciones}")
    return coincidencias.iloc[0]


def _verificar_parametros_modelo(
    df_parametros: pd.DataFrame,
    df_costos_fijos: pd.DataFrame,
    fila_conf: pd.Series,
    mes: int,
) -> str:
    """Confirma que el modo manual tiene insumos normativos para el vehículo."""
    tipo = str(fila_conf.get("TIPO_VEHICULO") or "").strip().upper()
    params = df_parametros[
        (df_parametros["TIPO_VEHICULO"].astype(str).str.upper() == tipo)
        & (pd.to_numeric(df_parametros["MES"], errors="coerce") == int(mes))
    ]
    costos = df_costos_fijos[
        (df_costos_fijos["TIPO_VEHICULO"].astype(str).str.upper() == tipo)
        & (pd.to_numeric(df_costos_fijos["MES"], errors="coerce") == int(mes))
    ]
    if params.empty or costos.empty:
        raise SicetacError(
            503,
            "No hay parámetros normativos publicados para este vehículo en el modo detallado. "
            "Use resumen=true, que entrega el consolidado oficial SICETAC vigente.",
        )
    return tipo


def _carroceria_option(carroceria: str) -> dict[str, str] | None:
    return _SICE_COLUMN_MAP.get(_normalize_lookup_text(carroceria))


def _tipo_contenedor(value: str | None) -> str | None:
    normalized = _normalize_lookup_text(value)
    if not normalized:
        return None
    if normalized in {"VACIO", "CONTENEDOR VACIO"}:
        return "VACIO"
    if normalized in {"CARGADO", "CONTENEDOR CARGADO"}:
        return "CARGADO"
    raise SicetacError(400, "tipo_contenedor debe ser CARGADO o VACIO.")


def _es_contenedor_vacio(carroceria: str, tipo_contenedor: str | None) -> bool:
    option = _carroceria_option(carroceria)
    return bool(option and option["label"] == "Portacontenedores" and _tipo_contenedor(tipo_contenedor) == "VACIO")


def _validar_contexto_tipo_contenedor(data: ConsultaInput) -> str | None:
    if data.tipo_contenedor_regreso is not None:
        raise SicetacError(400, "tipo_contenedor_regreso solo aplica con viaje_redondo=true.")
    tipo = _tipo_contenedor(data.tipo_contenedor)
    if tipo is None:
        return None
    option = _carroceria_option(data.carroceria)
    if not option or option["label"] != "Portacontenedores":
        raise SicetacError(400, "tipo_contenedor solo aplica con carroceria=Portacontenedores.")
    if str(data.modo_viaje or "").strip().upper() != "CARGADO":
        raise SicetacError(400, "tipo_contenedor se consulta con modo_viaje=CARGADO.")
    return tipo


def _copiar_consulta(data: ConsultaInput, **updates: Any) -> ConsultaInput:
    if hasattr(data, "model_copy"):
        return data.model_copy(update=updates)
    return data.copy(update=updates)


def _seleccionar_variante_tramo(
    respuesta: dict[str, Any], rutasid: str | None, nombre_tramo: str
) -> dict[str, Any] | None:
    if "totales" in respuesta:
        rutasid_actual = _clean_id(respuesta.get("detalle_lookup", {}).get("rutasid"))
        if rutasid and rutasid_actual and _clean_id(rutasid) != rutasid_actual:
            raise SicetacError(400, f"rutasid_{nombre_tramo} no corresponde a la ruta resuelta.")
        return respuesta

    variantes = respuesta.get("variantes", [])
    if not variantes:
        raise SicetacError(404, f"No hay una tarifa oficial para el tramo de {nombre_tramo}.")
    if not rutasid:
        return None

    rutasid_normalizado = _clean_id(rutasid)
    variante = next(
        (
            item
            for item in variantes
            if _clean_id(item.get("RUTASID") or item.get("ID_SICE")) == rutasid_normalizado
        ),
        None,
    )
    if not variante:
        opciones = ", ".join(
            _clean_id(item.get("RUTASID") or item.get("ID_SICE"))
            for item in variantes
        )
        raise SicetacError(
            400,
            f"rutasid_{nombre_tramo}={rutasid} no es válido. Opciones: {opciones}.",
        )

    seleccionado = {key: value for key, value in respuesta.items() if key != "variantes"}
    seleccionado.update(
        {
            "rutasid": _clean_id(variante.get("RUTASID") or variante.get("ID_SICE")),
            "nombre_sice": variante.get("NOMBRE_SICE"),
            "ruta": variante.get("RUTA"),
            "totales": variante["totales"],
            "detalle_lookup": variante.get("detalle_lookup", {}),
        }
    )
    return seleccionado


AUMENTO_MES_BASE = 202512
AUMENTO_CONFIGURACIONES_DICIEMBRE = {
    "C2",
    "C3",
    "C2S2",
    "C2S3",
    "C3S2",
    "C3S3",
}


def _normalizar_configuracion_aumento(value: Any) -> str:
    """Normaliza las etiquetas C2/2, C2S2/2S2 usadas por las tablas SICETAC."""
    normalized = re.sub(r"\s+", "", str(value or "").strip().upper())
    if normalized in {"2", "3"}:
        return f"C{normalized}"
    if normalized in {"2S2", "2S3", "3S2", "3S3"}:
        return f"C{normalized}"
    return normalized


def _variacion_total_sicetac(
    valor_actual: Any,
    valor_base: Any,
    *,
    hora: str,
) -> dict[str, Any]:
    """Devuelve diferencia COP y porcentaje, sin dividir por cero."""
    try:
        actual = float(valor_actual) if valor_actual is not None else None
        base = float(valor_base) if valor_base is not None else None
    except (TypeError, ValueError):
        actual = None
        base = None

    if actual is None or base is None or pd.isna(actual) or pd.isna(base):
        return {
            "hora": hora,
            "disponible": False,
            "valor_actual": actual,
            "valor_base": base,
            "aumento_cop": None,
            "aumento_pct": None,
            "motivo": "No hay valor comparable para el periodo actual o diciembre de 2025.",
        }

    diferencia = round(actual - base, 2)
    porcentaje = round((diferencia / base) * 100, 2) if base != 0 else None
    return {
        "hora": hora,
        "disponible": porcentaje is not None,
        "valor_actual": round(actual, 2),
        "valor_base": round(base, 2),
        "aumento_cop": diferencia,
        "aumento_pct": porcentaje,
        "motivo": None if porcentaje is not None else "El valor base de diciembre de 2025 es cero.",
    }


def _calcular_viaje_redondo_contenedor(data: ConsultaInput) -> dict[str, Any]:
    if bool(getattr(data, "manual_mode", False)):
        raise SicetacError(400, "viaje_redondo con contenedor vacío requiere una ruta oficial, no manual_mode.")

    option = _carroceria_option(data.carroceria)
    if not option or option["label"] != "Portacontenedores":
        raise SicetacError(400, "viaje_redondo con contenedor vacío solo aplica con carroceria=Portacontenedores.")
    if str(data.modo_viaje or "").strip().upper() != "CARGADO":
        raise SicetacError(400, "viaje_redondo con contenedor vacío requiere modo_viaje=CARGADO.")

    tipo_ida = _tipo_contenedor(data.tipo_contenedor) or "CARGADO"
    tipo_regreso = _tipo_contenedor(data.tipo_contenedor_regreso) or "VACIO"
    if tipo_ida != "CARGADO" or tipo_regreso != "VACIO":
        raise SicetacError(
            400,
            "viaje_redondo de portacontenedores se compone de ida CARGADO y regreso VACIO.",
        )

    ida_data = _copiar_consulta(
        data,
        viaje_redondo=False,
        tipo_contenedor="CARGADO",
        tipo_contenedor_regreso=None,
    )
    regreso_data = _copiar_consulta(
        data,
        viaje_redondo=False,
        origen=data.destino,
        destino=data.origen,
        codigo_dane_origen=data.codigo_dane_destino,
        codigo_dane_destino=data.codigo_dane_origen,
        modo_viaje="CARGADO",
        tipo_contenedor="VACIO",
        tipo_contenedor_regreso=None,
    )
    ida = calcular_sicetac_resumen(ida_data)
    regreso = calcular_sicetac_resumen(regreso_data)
    ida_seleccionada = _seleccionar_variante_tramo(ida, data.rutasid_ida, "ida")
    regreso_seleccionada = _seleccionar_variante_tramo(
        regreso, data.rutasid_regreso, "regreso"
    )
    if ida_seleccionada is None or regreso_seleccionada is None:
        return {
            "tipo_consulta": "VIAJE_REDONDO_CONTENEDOR",
            "requiere_seleccion_ruta": True,
            "ida": ida,
            "regreso": regreso,
            "instruccion": (
                "Seleccione una ruta SICETAC para cada tramo y reintente con "
                "rutasid_ida y rutasid_regreso."
            ),
            "valor_plaza_regreso_no_aplica": "CONTENEDOR_VACIO",
        }

    totales = {
        hora: round(
            float(ida_seleccionada["totales"][hora])
            + float(regreso_seleccionada["totales"][hora]),
            2,
        )
        for hora in ("H2", "H4", "H8")
    }
    return {
        "tipo_consulta": "VIAJE_REDONDO_CONTENEDOR",
        "configuracion": data.vehiculo,
        "carroceria": "Portacontenedores",
        "ida": ida_seleccionada,
        "regreso": regreso_seleccionada,
        "totales": totales,
        "valor_plaza_regreso_no_aplica": "CONTENEDOR_VACIO",
    }


def _lookup_sicetac_totales(
    *,
    cod_origen_str: str,
    cod_destino_str: str,
    configuracion_lookup: str,
    carroceria: str,
    modo_viaje: str = "CARGADO",
    tipo_contenedor: str | None = None,
    mes_codigo: int | None = None,
) -> list[dict[str, Any]]:
    if not _USE_CONSOLIDATED_LOOKUP:
        return []

    carroceria_option = _carroceria_option(carroceria)
    if not carroceria_option:
        return []
    es_vacio = str(modo_viaje or "").strip().upper() == "VACIO"
    contenedor_vacio = _es_contenedor_vacio(carroceria, tipo_contenedor)
    if es_vacio and contenedor_vacio:
        raise SicetacError(400, "Un contenedor vacío se consulta con modo_viaje=CARGADO.")
    lookup_col = carroceria_option["vacio_column"] if es_vacio else carroceria_option["column"]
    if contenedor_vacio:
        lookup_col = carroceria_option["contenedor_vacio_column"]

    if es_vacio:
        df_rows = get_sicetac_vacio_df(
            cod_origen_str, cod_destino_str, configuracion_lookup, mes_codigo
        )
        if df_rows.empty:
            df_rows = get_sicetac_vacio_df(
                cod_destino_str, cod_origen_str, configuracion_lookup, mes_codigo
            )
        if df_rows.empty:
            return []
        valor_hora_global = None
    else:
        df_rows = get_sicetac_movilizacion_df(
            cod_origen_str, cod_destino_str, configuracion_lookup, mes_codigo
        )
        if df_rows.empty:
            df_rows = get_sicetac_movilizacion_df(
                cod_destino_str, cod_origen_str, configuracion_lookup, mes_codigo
            )
        df_valorhora = get_sicetac_valorhora_df(configuracion_lookup, mes_codigo)
        if df_rows.empty or df_valorhora.empty:
            return []
        try:
            valor_hora_global = float(df_valorhora.iloc[0].get(lookup_col))
        except Exception:
            return []
        if pd.isna(valor_hora_global):
            return []

    resolved: list[dict[str, Any]] = []
    for _, row in df_rows.iterrows():
        try:
            movilizacion = float(row.get(lookup_col))
        except Exception:
            continue
        if pd.isna(movilizacion):
            continue
        try:
            valor_hora = (
                float(row.get("VALORHORA_VACIO"))
                if es_vacio
                else float(valor_hora_global)
            )
        except Exception:
            continue
        if pd.isna(valor_hora):
            continue
        resolved.append(
            {
                "rutasid": _clean_id(row.get("RUTASID")),
                "mes_codigo": int(row.get("MES_CODIGO")) if pd.notna(row.get("MES_CODIGO")) else None,
                "movilizacion": movilizacion,
                "valor_hora": valor_hora,
                "totales": {
                    "H2": round(movilizacion + (2 * valor_hora), 2),
                    "H4": round(movilizacion + (4 * valor_hora), 2),
                    "H8": round(movilizacion + (8 * valor_hora), 2),
                },
                "lookup_column": lookup_col.lower(),
                "lookup_label": carroceria_option["label"],
                "lookup_method": (
                    "lookup_vacio_oficial"
                    if es_vacio
                    else "lookup_contenedor_vacio_oficial"
                    if contenedor_vacio
                    else "lookup_consolidado"
                ),
            }
        )
    return resolved


def _route_metadata_map(ruta: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if ruta is None or ruta.empty:
        return {}
    metadata: dict[str, dict[str, Any]] = {}
    for _, row in ruta.iterrows():
        rutasid = _clean_id(row.get("ID_SICE"))
        if not rutasid:
            continue
        metadata[rutasid] = {
            "nombre_sice": row.get("NOMBRE_SICE"),
            "ruta": row.get("RUTA"),
            "id_sice": row.get("ID_SICE"),
        }
    return metadata


def calcular_sicetac(data: ConsultaInput) -> dict:
    if bool(getattr(data, "modo_aumento", False)):
        raise SicetacError(
            400,
            "modo_aumento requiere resumen=true para comparar los totales oficiales H4 y H8.",
        )
    if data.viaje_redondo:
        raise SicetacError(
            400,
            "viaje_redondo está disponible con resumen=true; el detalle por tramo aún no está habilitado.",
        )
    tipo_contenedor = _validar_contexto_tipo_contenedor(data)
    if tipo_contenedor is not None:
        raise SicetacError(
            400,
            "tipo_contenedor está disponible con resumen=true; el detalle del modelo aún no incorpora esta serie oficial.",
        )
    _refresh_cache()
    (
        df_municipios,
        df_vehiculos,
        df_parametros,
        df_costos_fijos,
        df_peajes,
        df_rutas,
        df_sicetac_movilizacion,
        df_sicetac_valorhora,
    ) = _get_dataframes()

    if df_municipios.empty or df_vehiculos.empty or df_parametros.empty or df_costos_fijos.empty or df_peajes.empty or df_rutas.empty:
        raise SicetacError(500, "Tablas de Supabase no disponibles o vacías. Verifica conexión y datos.")

    helper = SICETACHelper(df_municipios)

    mes_usar = data.mes
    if mes_usar is None:
        mes_usar = _latest_mes(df_parametros)
    if mes_usar is None:
        raise SicetacError(500, "No se pudo determinar el MES más reciente.")

    manual_mode = bool(getattr(data, "manual_mode", False))
    manual_distancias = {
        "km_plano": float(getattr(data, "km_plano", 0) or 0),
        "km_ondulado": float(getattr(data, "km_ondulado", 0) or 0),
        "km_montanoso": float(_manual_km_montanoso(data) or 0),
        "km_urbano": float(getattr(data, "km_urbano", 0) or 0),
        "km_despavimentado": float(getattr(data, "km_despavimentado", 0) or 0),
    }

    for _k, _v in manual_distancias.items():
        if _v < 0:
            raise SicetacError(400, f"Distancia manual inválida en {_k}: no puede ser negativa")

    manual_peaje = _manual_valor_peaje(data)
    if manual_peaje < 0:
        raise SicetacError(400, "valor_peaje_manual/valor_peajes_manual no puede ser negativo")

    if manual_mode:
        ruta = pd.DataFrame()
        fila_ruta = None
        resolved_route = None
        origen_display = _display_name(data.origen, None)
        destino_display = _display_name(data.destino, None)
    else:
        origen_info, destino_info, resolved_route, origen_display, destino_display = _resolve_route_inputs(data, helper)
        cod_origen_str = _clean_id(origen_info["codigo_dane"])
        cod_destino_str = _clean_id(destino_info["codigo_dane"])

        rutas_index = _get_rutas_index(df_rutas)
        ruta_rows = rutas_index.get((cod_origen_str, cod_destino_str), [])
        if not ruta_rows:
            ruta_rows = rutas_index.get((cod_destino_str, cod_origen_str), [])
        ruta = pd.DataFrame(ruta_rows) if ruta_rows else pd.DataFrame()

        if ruta.empty:
            if not _has_manual_distances(data):
                raise SicetacError(404, "Ruta no registrada y no se proporcionaron distancias manuales")
            fila_ruta = None
        else:
            fila_ruta = ruta.iloc[0]

    def _distancias_from_ruta(row):
        if row is None:
            return manual_distancias
        return {
            "km_plano": row.get("KM_PLANO", 0),
            "km_ondulado": row.get("KM_ONDULADO", 0),
            "km_montanoso": row.get("KM_MONTAÑOSO", 0),
            "km_urbano": row.get("KM_URBANO", 0),
            "km_despavimentado": row.get("KM_DESPAVIMENTADO", 0),
        }

    fila_conf = _fila_vehiculo(df_vehiculos, data.vehiculo)
    vehiculo_modelo = _verificar_parametros_modelo(
        df_parametros, df_costos_fijos, fila_conf, int(mes_usar)
    )
    ejes_conf = _clean_id(fila_conf.get("EJES_CONFIGURACION"))

    peajes_index = _get_peajes_index(df_peajes)

    meses_validos = df_parametros["MES"].unique().tolist()
    if int(mes_usar) not in meses_validos:
        raise SicetacError(400, f"Mes '{mes_usar}' no válido. Debe ser uno de: {meses_validos}")

    def _peaje_for_ruta(ruta_row) -> float:
        if ruta_row is None:
            return float(manual_peaje or 0)
        id_sice = _clean_id(ruta_row.get("ID_SICE"))
        valores = peajes_index.get((id_sice, ejes_conf), [])
        if not valores:
            return float(manual_peaje or 0)
        # Si hay múltiples, tomamos el primero (si quieres, puedo cambiar a suma)
        return float(valores[0])

    def _ejecutar_modelo(horas_logisticas_modelo: float | None, ruta_row=None):
        distancias = _distancias_from_ruta(ruta_row)
        valor_peaje_override = _peaje_for_ruta(ruta_row)
        if data.modo_viaje.upper() == "VACIO":
            return calcular_modelo_sicetac_extendido_vacio(
                origen=origen_display,
                destino=destino_display,
                configuracion=vehiculo_modelo,
                serie=int(mes_usar),
                distancias=distancias,
                valor_peaje_manual=data.valor_peaje_manual,
                matriz_parametros=df_parametros,
                matriz_costos_fijos=df_costos_fijos,
                matriz_vehicular=df_vehiculos,
                rutas_df=df_rutas,
                peajes_df=df_peajes,
                carroceria_especial=data.carroceria,
                ruta_oficial=ruta_row,
                horas_logisticas=horas_logisticas_modelo,
                valor_peaje_override=valor_peaje_override,
            )
        return calcular_modelo_sicetac_extendido(
            origen=origen_display,
            destino=destino_display,
            configuracion=vehiculo_modelo,
            serie=int(mes_usar),
            distancias=distancias,
            valor_peaje_manual=data.valor_peaje_manual,
            matriz_parametros=df_parametros,
            matriz_costos_fijos=df_costos_fijos,
            matriz_vehicular=df_vehiculos,
            rutas_df=df_rutas,
            peajes_df=df_peajes,
            carroceria_especial=data.carroceria,
            ruta_oficial=ruta_row,
            horas_logisticas=horas_logisticas_modelo,
            valor_peaje_override=valor_peaje_override,
        )

    def _normalizar_total(res: dict | None):
        if res is None:
            return None
        if "total_viaje" not in res and "total_viaje_vacio" in res:
            res["total_viaje"] = res["total_viaje_vacio"]
        return res

    horas_objetivo = [2, 4, 8]

    def _totales_para_ruta(ruta_row):
        tot = {}
        for h in horas_objetivo:
            res = _normalizar_total(_ejecutar_modelo(h, ruta_row=ruta_row))
            tot[f"H{h}"] = float(res.get("total_viaje", 0)) if res else None
        return tot

    if ruta.empty:
        totales = _totales_para_ruta(None)
        respuesta = {
            "origen": origen_display,
            "destino": destino_display,
            "configuracion": data.vehiculo,
            "mes": int(mes_usar),
            "carroceria": data.carroceria,
            "modo_viaje": data.modo_viaje.upper(),
            "totales": totales,
        }
        if manual_mode:
            respuesta["manual_mode_applied"] = True
            respuesta["manual_input"] = {
                "total_km": round(sum(manual_distancias.values()), 2),
                "km_plano": manual_distancias["km_plano"],
                "km_ondulado": manual_distancias["km_ondulado"],
                "km_montanoso": manual_distancias["km_montanoso"],
                "km_urbano": manual_distancias["km_urbano"],
                "km_despavimentado": manual_distancias["km_despavimentado"],
                "valor_peajes_manual": float(manual_peaje),
            }
        if resolved_route:
            _attach_resolved_route(respuesta, resolved_route)
        return respuesta

    if len(ruta) == 1:
        totales = _totales_para_ruta(fila_ruta)
        respuesta = {
            "origen": origen_display,
            "destino": destino_display,
            "configuracion": data.vehiculo,
            "mes": int(mes_usar),
            "carroceria": data.carroceria,
            "modo_viaje": data.modo_viaje.upper(),
            "totales": totales,
        }
        if manual_mode:
            respuesta["manual_mode_applied"] = True
            respuesta["manual_input"] = {
                "total_km": round(sum(manual_distancias.values()), 2),
                "km_plano": manual_distancias["km_plano"],
                "km_ondulado": manual_distancias["km_ondulado"],
                "km_montanoso": manual_distancias["km_montanoso"],
                "km_urbano": manual_distancias["km_urbano"],
                "km_despavimentado": manual_distancias["km_despavimentado"],
                "valor_peajes_manual": float(manual_peaje),
            }
        if resolved_route:
            _attach_resolved_route(respuesta, resolved_route)
        return respuesta

    variantes = []
    for _, r in ruta.iterrows():
        variantes.append({
            "NOMBRE_SICE": r.get("NOMBRE_SICE"),
            "ID_SICE": r.get("ID_SICE"),
            "totales": _totales_para_ruta(r),
        })

    respuesta = {
        "origen": origen_display,
        "destino": destino_display,
        "configuracion": data.vehiculo,
        "mes": int(mes_usar),
        "carroceria": data.carroceria,
        "modo_viaje": data.modo_viaje.upper(),
        "variantes": variantes,
    }
    if manual_mode:
        respuesta["manual_mode_applied"] = True
        respuesta["manual_input"] = {
            "total_km": round(sum(manual_distancias.values()), 2),
            "km_plano": manual_distancias["km_plano"],
            "km_ondulado": manual_distancias["km_ondulado"],
            "km_montanoso": manual_distancias["km_montanoso"],
            "km_urbano": manual_distancias["km_urbano"],
            "km_despavimentado": manual_distancias["km_despavimentado"],
            "valor_peajes_manual": float(manual_peaje),
        }
    if resolved_route:
        _attach_resolved_route(respuesta, resolved_route)
    return respuesta


def _calcular_sicetac_resumen_base(data: ConsultaInput) -> dict:
    """
    Calcula totales para 2, 4 y 8 horas logísticas con respuesta mínima.
    """
    if data.viaje_redondo:
        return _calcular_viaje_redondo_contenedor(data)
    _validar_contexto_tipo_contenedor(data)
    _refresh_cache()
    (
        df_municipios,
        df_vehiculos,
        df_parametros,
        df_costos_fijos,
        df_peajes,
        df_rutas,
        df_sicetac_movilizacion,
        df_sicetac_valorhora,
    ) = _get_dataframes()

    if df_municipios.empty or df_vehiculos.empty or df_parametros.empty or df_costos_fijos.empty or df_peajes.empty or df_rutas.empty:
        raise SicetacError(500, "Tablas de Supabase no disponibles o vacías. Verifica conexión y datos.")

    helper = SICETACHelper(df_municipios)

    mes_usar = data.mes
    if mes_usar is None:
        mes_usar = _latest_mes(df_parametros)
    if mes_usar is None:
        raise SicetacError(500, "No se pudo determinar el MES más reciente.")

    manual_mode = bool(getattr(data, "manual_mode", False))
    manual_distancias = {
        "km_plano": float(getattr(data, "km_plano", 0) or 0),
        "km_ondulado": float(getattr(data, "km_ondulado", 0) or 0),
        "km_montanoso": float(_manual_km_montanoso(data) or 0),
        "km_urbano": float(getattr(data, "km_urbano", 0) or 0),
        "km_despavimentado": float(getattr(data, "km_despavimentado", 0) or 0),
    }

    for _k, _v in manual_distancias.items():
        if _v < 0:
            raise SicetacError(400, f"Distancia manual inválida en {_k}: no puede ser negativa")

    manual_peaje = _manual_valor_peaje(data)
    if manual_peaje < 0:
        raise SicetacError(400, "valor_peaje_manual/valor_peajes_manual no puede ser negativo")

    if manual_mode:
        ruta = pd.DataFrame()
        fila_ruta = None
        resolved_route = None
        origen_display = _display_name(data.origen, None)
        destino_display = _display_name(data.destino, None)
    else:
        origen_info, destino_info, resolved_route, origen_display, destino_display = _resolve_route_inputs(data, helper)
        cod_origen_str = _clean_id(origen_info["codigo_dane"])
        cod_destino_str = _clean_id(destino_info["codigo_dane"])

        rutas_index = _get_rutas_index(df_rutas)
        ruta_rows = rutas_index.get((cod_origen_str, cod_destino_str), [])
        if not ruta_rows:
            ruta_rows = rutas_index.get((cod_destino_str, cod_origen_str), [])
        ruta = pd.DataFrame(ruta_rows) if ruta_rows else pd.DataFrame()

        if ruta.empty:
            if not _has_manual_distances(data):
                raise SicetacError(404, "Ruta no registrada y no se proporcionaron distancias manuales")
            fila_ruta = None
        else:
            fila_ruta = ruta.iloc[0]

    def _distancias_from_ruta(row):
        if row is None:
            return manual_distancias
        return {
            "km_plano": row.get("KM_PLANO", 0),
            "km_ondulado": row.get("KM_ONDULADO", 0),
            "km_montanoso": row.get("KM_MONTAÑOSO", 0),
            "km_urbano": row.get("KM_URBANO", 0),
            "km_despavimentado": row.get("KM_DESPAVIMENTADO", 0),
        }

    fila_conf = _fila_vehiculo(df_vehiculos, data.vehiculo)
    ejes_conf = _clean_id(fila_conf.get("EJES_CONFIGURACION"))
    configuracion_lookup = _configuracion_lookup(fila_conf, data.vehiculo)
    peajes_index = _get_peajes_index(df_peajes)

    if (
        not manual_mode
        and data.modo_viaje.upper() in {"CARGADO", "VACIO"}
        and ruta is not None
        and not ruta.empty
    ):
        route_metadata = _route_metadata_map(ruta)
        lookup_rows = _lookup_sicetac_totales(
            cod_origen_str=cod_origen_str,
            cod_destino_str=cod_destino_str,
            configuracion_lookup=configuracion_lookup,
            carroceria=data.carroceria,
            modo_viaje=data.modo_viaje,
            tipo_contenedor=data.tipo_contenedor,
            # Sin un mes explícito, el consolidado oficial debe resolver al
            # último corte publicado, aun si los parámetros normativos tienen
            # una vigencia anterior.
            mes_codigo=int(mes_usar) if data.mes is not None else None,
        )
        if lookup_rows:
            if len(lookup_rows) == 1:
                respuesta = {
                    "origen": origen_display,
                    "destino": destino_display,
                    "configuracion": data.vehiculo,
                    "configuracion_analisis": configuracion_lookup,
                    "mes": lookup_rows[0]["mes_codigo"] or int(mes_usar),
                    "mes_parametros": int(mes_usar),
                    "carroceria": data.carroceria,
                    "modo_viaje": data.modo_viaje.upper(),
                    "tipo_contenedor": _tipo_contenedor(data.tipo_contenedor),
                    "totales": lookup_rows[0]["totales"],
                    "metodo": lookup_rows[0]["lookup_method"],
                    "detalle_lookup": {
                        "rutasid": lookup_rows[0]["rutasid"],
                        "nombre_sice": route_metadata.get(lookup_rows[0]["rutasid"], {}).get("nombre_sice"),
                        "ruta": route_metadata.get(lookup_rows[0]["rutasid"], {}).get("ruta"),
                        "movilizacion": lookup_rows[0]["movilizacion"],
                        "valor_hora": lookup_rows[0]["valor_hora"],
                        "columna_usada": lookup_rows[0]["lookup_column"],
                        "opcion_servicio": lookup_rows[0]["lookup_label"],
                    },
                }
                if resolved_route:
                    _attach_resolved_route(respuesta, resolved_route)
                _attach_valor_plaza(
                    respuesta,
                    resolved_route=resolved_route,
                    configuracion_lookup=configuracion_lookup,
                    carroceria=data.carroceria,
                    tipo_contenedor=data.tipo_contenedor,
                )
                return respuesta

            variantes = []
            for idx, item in enumerate(lookup_rows, start=1):
                route_info = route_metadata.get(item["rutasid"], {})
                variantes.append({
                    "NOMBRE_SICE": route_info.get("nombre_sice") or (f"RUTASID {item['rutasid']}" if item["rutasid"] else f"Ruta {idx}"),
                    "RUTASID": item["rutasid"],
                    "RUTA": route_info.get("ruta"),
                    "ID_SICE": route_info.get("id_sice") or item["rutasid"],
                    "totales": item["totales"],
                    "detalle_lookup": {
                        "movilizacion": item["movilizacion"],
                        "valor_hora": item["valor_hora"],
                        "columna_usada": item["lookup_column"],
                        "opcion_servicio": item["lookup_label"],
                    },
                })

            respuesta = {
                "origen": origen_display,
                "destino": destino_display,
                "configuracion": data.vehiculo,
                "configuracion_analisis": configuracion_lookup,
                "mes": lookup_rows[0]["mes_codigo"] or int(mes_usar),
                "mes_parametros": int(mes_usar),
                "carroceria": data.carroceria,
                "modo_viaje": data.modo_viaje.upper(),
                "tipo_contenedor": _tipo_contenedor(data.tipo_contenedor),
                "metodo": lookup_rows[0]["lookup_method"],
                "variantes": variantes,
            }
            if resolved_route:
                _attach_resolved_route(respuesta, resolved_route)
            _attach_valor_plaza(
                respuesta,
                resolved_route=resolved_route,
                configuracion_lookup=configuracion_lookup,
                carroceria=data.carroceria,
                tipo_contenedor=data.tipo_contenedor,
            )
            return respuesta

    vehiculo_modelo = _verificar_parametros_modelo(
        df_parametros, df_costos_fijos, fila_conf, int(mes_usar)
    )

    if _es_contenedor_vacio(data.carroceria, data.tipo_contenedor):
        raise SicetacError(
            503,
            "No hay consolidado oficial vigente para Contenedor vacío en esta ruta/configuración.",
        )

    def _peaje_for_ruta(ruta_row) -> float:
        if ruta_row is None:
            return float(manual_peaje or 0)
        id_sice = _clean_id(ruta_row.get("ID_SICE"))
        valores = peajes_index.get((id_sice, ejes_conf), [])
        if not valores:
            return float(manual_peaje or 0)
        return float(valores[0])

    def _ejecutar_modelo(horas_logisticas_modelo: float | None, ruta_row=None):
        distancias = _distancias_from_ruta(ruta_row)
        valor_peaje_override = _peaje_for_ruta(ruta_row)
        if data.modo_viaje.upper() == "VACIO":
            return calcular_modelo_sicetac_extendido_vacio(
                origen=origen_display,
                destino=destino_display,
                configuracion=vehiculo_modelo,
                serie=int(mes_usar),
                distancias=distancias,
                valor_peaje_manual=data.valor_peaje_manual,
                matriz_parametros=df_parametros,
                matriz_costos_fijos=df_costos_fijos,
                matriz_vehicular=df_vehiculos,
                rutas_df=df_rutas,
                peajes_df=df_peajes,
                carroceria_especial=data.carroceria,
                ruta_oficial=ruta_row,
                horas_logisticas=horas_logisticas_modelo,
                valor_peaje_override=valor_peaje_override,
            )
        return calcular_modelo_sicetac_extendido(
            origen=origen_display,
            destino=destino_display,
            configuracion=vehiculo_modelo,
            serie=int(mes_usar),
            distancias=distancias,
            valor_peaje_manual=data.valor_peaje_manual,
            matriz_parametros=df_parametros,
            matriz_costos_fijos=df_costos_fijos,
            matriz_vehicular=df_vehiculos,
            rutas_df=df_rutas,
            peajes_df=df_peajes,
            carroceria_especial=data.carroceria,
            ruta_oficial=ruta_row,
            horas_logisticas=horas_logisticas_modelo,
            valor_peaje_override=valor_peaje_override,
        )

    def _normalizar_total(res: dict | None):
        if res is None:
            return None
        if "total_viaje" not in res and "total_viaje_vacio" in res:
            res["total_viaje"] = res["total_viaje_vacio"]
        return res

    horas_objetivo = [2, 4, 8]

    def _totales_para_ruta(ruta_row):
        tot = {}
        for h in horas_objetivo:
            res = _normalizar_total(_ejecutar_modelo(h, ruta_row=ruta_row))
            tot[f"H{h}"] = float(res.get("total_viaje", 0)) if res else None
        return tot

    if ruta.empty:
        totales = _totales_para_ruta(None)
        respuesta = {
            "origen": origen_display,
            "destino": destino_display,
            "configuracion": data.vehiculo,
            "mes": int(mes_usar),
            "carroceria": data.carroceria,
            "modo_viaje": data.modo_viaje.upper(),
            "totales": totales,
        }
        if manual_mode:
            respuesta["manual_mode_applied"] = True
            respuesta["manual_input"] = {
                "total_km": round(sum(manual_distancias.values()), 2),
                "km_plano": manual_distancias["km_plano"],
                "km_ondulado": manual_distancias["km_ondulado"],
                "km_montanoso": manual_distancias["km_montanoso"],
                "km_urbano": manual_distancias["km_urbano"],
                "km_despavimentado": manual_distancias["km_despavimentado"],
                "valor_peajes_manual": float(manual_peaje),
            }
        if resolved_route:
            _attach_resolved_route(respuesta, resolved_route)
        _attach_valor_plaza(
            respuesta,
            resolved_route=resolved_route,
            configuracion_lookup=configuracion_lookup,
            carroceria=data.carroceria,
            tipo_contenedor=data.tipo_contenedor,
        )
        return respuesta

    if len(ruta) == 1:
        totales = _totales_para_ruta(fila_ruta)
        respuesta = {
            "origen": origen_display,
            "destino": destino_display,
            "configuracion": data.vehiculo,
            "mes": int(mes_usar),
            "carroceria": data.carroceria,
            "modo_viaje": data.modo_viaje.upper(),
            "totales": totales,
        }
        if manual_mode:
            respuesta["manual_mode_applied"] = True
            respuesta["manual_input"] = {
                "total_km": round(sum(manual_distancias.values()), 2),
                "km_plano": manual_distancias["km_plano"],
                "km_ondulado": manual_distancias["km_ondulado"],
                "km_montanoso": manual_distancias["km_montanoso"],
                "km_urbano": manual_distancias["km_urbano"],
                "km_despavimentado": manual_distancias["km_despavimentado"],
                "valor_peajes_manual": float(manual_peaje),
        }
        if resolved_route:
            _attach_resolved_route(respuesta, resolved_route)
        _attach_valor_plaza(
            respuesta,
            resolved_route=resolved_route,
            configuracion_lookup=configuracion_lookup,
            carroceria=data.carroceria,
            tipo_contenedor=data.tipo_contenedor,
        )
        return respuesta

    variantes = []
    for _, r in ruta.iterrows():
        variantes.append({
            "NOMBRE_SICE": r.get("NOMBRE_SICE"),
            "ID_SICE": r.get("ID_SICE"),
            "totales": _totales_para_ruta(r),
        })

    respuesta = {
        "origen": origen_display,
        "destino": destino_display,
        "configuracion": data.vehiculo,
        "mes": int(mes_usar),
        "carroceria": data.carroceria,
        "modo_viaje": data.modo_viaje.upper(),
        "variantes": variantes,
    }
    if manual_mode:
        respuesta["manual_mode_applied"] = True
        respuesta["manual_input"] = {
            "total_km": round(sum(manual_distancias.values()), 2),
            "km_plano": manual_distancias["km_plano"],
            "km_ondulado": manual_distancias["km_ondulado"],
            "km_montanoso": manual_distancias["km_montanoso"],
            "km_urbano": manual_distancias["km_urbano"],
            "km_despavimentado": manual_distancias["km_despavimentado"],
            "valor_peajes_manual": float(manual_peaje),
        }
    if resolved_route:
        _attach_resolved_route(respuesta, resolved_route)
    _attach_valor_plaza(
        respuesta,
        resolved_route=resolved_route,
        configuracion_lookup=configuracion_lookup,
        carroceria=data.carroceria,
        tipo_contenedor=data.tipo_contenedor,
    )
    return respuesta


def _totales_de_respuesta(respuesta: dict[str, Any], rutasid: str | None = None) -> dict[str, Any] | None:
    """Obtiene los totales de una respuesta única o de una variante concreta."""
    totales = respuesta.get("totales")
    if isinstance(totales, dict):
        if rutasid is None:
            return totales
        detalle = respuesta.get("detalle_lookup") or {}
        if _clean_id(detalle.get("rutasid")) == _clean_id(rutasid):
            return totales

    variantes = respuesta.get("variantes")
    if not isinstance(variantes, list):
        return None
    if rutasid is None and len(variantes) == 1:
        return variantes[0].get("totales")
    for variante in variantes:
        candidato = variante.get("RUTASID") or variante.get("ID_SICE")
        if rutasid is not None and _clean_id(candidato) == _clean_id(rutasid):
            return variante.get("totales")
    return None


def _bloque_aumento(
    *,
    totales_actuales: dict[str, Any] | None,
    totales_base: dict[str, Any] | None,
    periodo_actual: Any,
    metodo_actual: Any = None,
    metodo_base: Any = None,
) -> dict[str, Any]:
    horas = {
        hora: _variacion_total_sicetac(
            (totales_actuales or {}).get(hora),
            (totales_base or {}).get(hora),
            hora=hora,
        )
        for hora in ("H4", "H8")
    }
    return {
        "activo": True,
        "estado": "ACTIVO",
        "periodo_base": AUMENTO_MES_BASE,
        "periodo_actual": int(periodo_actual) if periodo_actual is not None else None,
        "metodo_actual": metodo_actual,
        "metodo_base": metodo_base,
        "horas": horas,
        "aumento_pct": {
            "H4": horas["H4"]["aumento_pct"],
            "H8": horas["H8"]["aumento_pct"],
        },
        "mensaje": "Modo aumento activo: las próximas consultas deben conservar modo_aumento=true hasta recibir modo_aumento=false.",
    }


def _adjuntar_modo_aumento(data: ConsultaInput, respuesta: dict[str, Any]) -> dict[str, Any]:
    """Adjunta la comparación H4/H8 con diciembre de 2025 al resumen oficial."""
    configuracion = _normalizar_configuracion_aumento(
        respuesta.get("configuracion_analisis") or data.vehiculo
    )
    estado_base = {
        "activo": True,
        "estado": "ACTIVO",
        "periodo_base": AUMENTO_MES_BASE,
        "periodo_actual": respuesta.get("mes"),
        "configuracion": configuracion,
        "mensaje": "Modo aumento activo: las próximas consultas deben conservar modo_aumento=true hasta recibir modo_aumento=false.",
    }

    if configuracion not in AUMENTO_CONFIGURACIONES_DICIEMBRE:
        estado_base.update({
            "disponible": False,
            "motivo": "La comparación histórica está definida para C2, C3, C2S2, C2S3, C3S2 y C3S3.",
        })
        respuesta["aumento"] = estado_base
        return respuesta

    if not respuesta.get("metodo"):
        estado_base.update({
            "disponible": False,
            "motivo": "El modo aumento solo compara valores del consolidado oficial SICETAC; esta consulta no devolvió ese consolidado.",
        })
        respuesta["aumento"] = estado_base
        return respuesta

    try:
        datos_base = _copiar_consulta(data, mes=AUMENTO_MES_BASE, modo_aumento=False)
        respuesta_base = _calcular_sicetac_resumen_base(datos_base)
    except SicetacError as ex:
        estado_base.update({
            "disponible": False,
            "motivo": f"No fue posible obtener el corte base {AUMENTO_MES_BASE}: {ex.detail}",
        })
        respuesta["aumento"] = estado_base
        return respuesta

    if not respuesta_base.get("metodo"):
        estado_base.update({
            "disponible": False,
            "motivo": f"El corte base {AUMENTO_MES_BASE} no devolvió un valor del consolidado oficial SICETAC.",
        })
        respuesta["aumento"] = estado_base
        return respuesta

    periodo_actual = respuesta.get("mes") or data.mes
    metodo_actual = respuesta.get("metodo")
    metodo_base = respuesta_base.get("metodo")
    variantes_actuales = respuesta.get("variantes")

    if isinstance(variantes_actuales, list):
        por_ruta: dict[str, Any] = {}
        for variante in variantes_actuales:
            rutasid = _clean_id(variante.get("RUTASID") or variante.get("ID_SICE"))
            aumento = _bloque_aumento(
                totales_actuales=variante.get("totales"),
                totales_base=_totales_de_respuesta(respuesta_base, rutasid),
                periodo_actual=periodo_actual,
                metodo_actual=metodo_actual,
                metodo_base=metodo_base,
            )
            variante["aumento"] = aumento
            por_ruta[rutasid or str(len(por_ruta) + 1)] = aumento
        estado_base["por_ruta"] = por_ruta
        estado_base["disponible"] = any(
            bool(item.get("horas", {}).get("H4", {}).get("disponible"))
            and bool(item.get("horas", {}).get("H8", {}).get("disponible"))
            for item in por_ruta.values()
        )
    else:
        bloque = _bloque_aumento(
            totales_actuales=respuesta.get("totales"),
            totales_base=_totales_de_respuesta(respuesta_base),
            periodo_actual=periodo_actual,
            metodo_actual=metodo_actual,
            metodo_base=metodo_base,
        )
        estado_base.update(bloque)
        estado_base["disponible"] = all(
            bool(bloque["horas"][hora].get("disponible")) for hora in ("H4", "H8")
        )
    respuesta["aumento"] = estado_base
    return respuesta


def calcular_sicetac_resumen(data: ConsultaInput) -> dict:
    """Calcula el resumen y, opcionalmente, la variación frente a diciembre de 2025."""
    if bool(getattr(data, "modo_aumento", False)):
        if data.viaje_redondo:
            raise SicetacError(400, "modo_aumento aún no está habilitado para viaje_redondo.")
        respuesta = _calcular_sicetac_resumen_base(data)
        return _adjuntar_modo_aumento(data, respuesta)
    return _calcular_sicetac_resumen_base(data)


def generar_snapshot(
    horas: list[int] | None = None,
    carroceria: str = "GENERAL",
    modo_viaje: str = "CARGADO",
) -> pd.DataFrame:
    """
    Genera snapshot para todas las rutas y vehículos.
    """
    _refresh_cache()
    (
        df_municipios,
        df_vehiculos,
        df_parametros,
        df_costos_fijos,
        df_peajes,
        df_rutas,
        _df_sicetac_movilizacion,
        _df_sicetac_valorhora,
    ) = _get_dataframes()

    if df_municipios.empty or df_vehiculos.empty or df_parametros.empty or df_costos_fijos.empty or df_peajes.empty or df_rutas.empty:
        raise SicetacError(500, "Tablas de Supabase no disponibles o vacías. Verifica conexión y datos.")

    if horas is None:
        horas = [0, 2, 4, 8]

    mes_usar = _latest_mes(df_parametros)
    if mes_usar is None:
        raise SicetacError(500, "No se pudo determinar el MES más reciente.")

    peajes_index = _get_peajes_index(df_peajes)

    nombre_mpio = {}
    if "CODIGO_DANE" in df_municipios.columns and "NOMBRE_OFICIAL" in df_municipios.columns:
        for _, row in df_municipios.iterrows():
            nombre_mpio[_clean_id(row["CODIGO_DANE"])] = str(row["NOMBRE_OFICIAL"]).strip()

    vehiculos = df_vehiculos["TIPO_VEHICULO"].astype(str).unique().tolist()
    vehiculos = [v for v in vehiculos if str(v).strip().upper() != "V3"]

    def _peaje_for(ruta_row, ejes_conf: str) -> float:
        id_sice = _clean_id(ruta_row.get("ID_SICE"))
        valores = peajes_index.get((id_sice, ejes_conf), [])
        return float(valores[0]) if valores else 0.0

    rows = []
    for _, ruta_row in df_rutas.iterrows():
        cod_origen = _clean_id(ruta_row.get("CODIGO_DANE_ORIGEN"))
        cod_destino = _clean_id(ruta_row.get("CODIGO_DANE_DESTINO"))

        distancias = {
            "km_plano": ruta_row.get("KM_PLANO", 0),
            "km_ondulado": ruta_row.get("KM_ONDULADO", 0),
            "km_montanoso": ruta_row.get("KM_MONTAÑOSO", 0),
            "km_urbano": ruta_row.get("KM_URBANO", 0),
            "km_despavimentado": ruta_row.get("KM_DESPAVIMENTADO", 0),
        }

        for vehiculo in vehiculos:
            fila_conf = df_vehiculos[df_vehiculos["TIPO_VEHICULO"] == vehiculo].iloc[0]
            ejes_conf = _clean_id(fila_conf.get("EJES_CONFIGURACION"))
            valor_peaje = _peaje_for(ruta_row, ejes_conf)

            totales = {}
            for h in horas:
                if modo_viaje.upper() == "VACIO":
                    res = calcular_modelo_sicetac_extendido_vacio(
                        origen=nombre_mpio.get(cod_origen, cod_origen),
                        destino=nombre_mpio.get(cod_destino, cod_destino),
                        configuracion=vehiculo,
                        serie=int(mes_usar),
                        distancias=distancias,
                        valor_peaje_manual=0,
                        matriz_parametros=df_parametros,
                        matriz_costos_fijos=df_costos_fijos,
                        matriz_vehicular=df_vehiculos,
                        rutas_df=df_rutas,
                        peajes_df=df_peajes,
                        carroceria_especial=carroceria,
                        ruta_oficial=ruta_row,
                        horas_logisticas=h,
                        valor_peaje_override=valor_peaje,
                    )
                else:
                    res = calcular_modelo_sicetac_extendido(
                        origen=nombre_mpio.get(cod_origen, cod_origen),
                        destino=nombre_mpio.get(cod_destino, cod_destino),
                        configuracion=vehiculo,
                        serie=int(mes_usar),
                        distancias=distancias,
                        valor_peaje_manual=0,
                        matriz_parametros=df_parametros,
                        matriz_costos_fijos=df_costos_fijos,
                        matriz_vehicular=df_vehiculos,
                        rutas_df=df_rutas,
                        peajes_df=df_peajes,
                        carroceria_especial=carroceria,
                        ruta_oficial=ruta_row,
                        horas_logisticas=h,
                        valor_peaje_override=valor_peaje,
                    )
                total = res.get("total_viaje") or res.get("total_viaje_vacio")
                totales[f"H{h}"] = float(total) if total is not None else None

            rows.append({
                "mes": int(mes_usar),
                "codigo_origen": cod_origen,
                "codigo_destino": cod_destino,
                "origen_nombre": nombre_mpio.get(cod_origen),
                "destino_nombre": nombre_mpio.get(cod_destino),
                "vehiculo": vehiculo,
                "id_sice": ruta_row.get("ID_SICE"),
                "nombre_sice": ruta_row.get("NOMBRE_SICE"),
                "valor_peaje": valor_peaje,
                **totales,
            })

    return pd.DataFrame(rows)
