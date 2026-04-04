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
    get_sicetac_movilizacion_df,
    get_sicetac_valorhora_df,
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

    # NUEVO: modo manual puro (sin buscar municipios/rutas)
    manual_mode: bool = False


@dataclass
class SicetacError(Exception):
    status_code: int
    detail: str


SICE_COLUMN_OPTIONS: list[dict[str, str]] = [
    {
        "column": "GENERAL_ESTACAS_CARGADO",
        "label": "General - Estacas",
        "aliases": "GENERAL|GENERAL ESTACAS|GENERAL - ESTACAS|GENERAL ESTACA|GENERAL - ESTIBA",
    },
    {
        "column": "GENERAL_FURGON_CARGADO",
        "label": "General - Furgon",
        "aliases": "FURGON GENERAL|GENERAL FURGON|GENERAL - FURGON",
    },
    {
        "column": "GENERAL_ESTIBAS_CARGADO",
        "label": "General - Estibas",
        "aliases": "ESTIBA|ESTIBAS|GENERAL ESTIBAS|GENERAL - ESTIBAS",
    },
    {
        "column": "GENERAL_PLATAFORMA_CARGADO",
        "label": "General - Plataforma",
        "aliases": "PLATAFORMA|GENERAL PLATAFORMA|GENERAL - PLATAFORMA|GENERA - PLATAFORMA",
    },
    {
        "column": "CONTENEDOR_PORTACONTENEDORES_CARGADO",
        "label": "Portacontenedores",
        "aliases": "PORTACONTENEDORES|PORTA CONTENEDORES|CONTENEDOR PORTACONTENEDORES",
    },
    {
        "column": "CARGA_REFRIGERADA_FURGON_REFRIGERADO_CARGADO",
        "label": "Furgon Refrigerado",
        "aliases": "FURGON REFRIGERADO|CARGA REFRIGERADA|REFRIGERADO",
    },
    {
        "column": "GRANEL_SOLIDO_ESTACAS_CARGADO",
        "label": "Granel Solido - Estacas",
        "aliases": "ESTACAS GRANEL SOLIDO|GRANEL SOLIDO ESTACAS|GRANEL SOLIDO - ESTACAS",
    },
    {
        "column": "GRANEL_SOLIDO_FURGON_CARGADO",
        "label": "Granel Solido - Furgon",
        "aliases": "FURGON GRANEL SOLIDO|GRANEL SOLIDO FURGON|GRANEL SOLIDO - FURGON",
    },
    {
        "column": "GRANEL_SOLIDO_VOLCO_CARGADO",
        "label": "Granel Solido - Volco",
        "aliases": "VOLCO|GRANEL SOLIDO VOLCO|GRANEL SOLIDO - VOLCO",
    },
    {
        "column": "GRANEL_SOLIDO_ESTIBAS_CARGADO",
        "label": "Granel Solido - Estibas",
        "aliases": "ESTIBAS GRANEL SOLIDO|GRANEL SOLIDO ESTIBAS|GRANEL SOLIDO - ESTIBAS",
    },
    {
        "column": "GRANEL_SOLIDO_PLATAFORMA_CARGADO",
        "label": "Granel Solido - Plataforma",
        "aliases": "PLATAFORMA GRANEL SOLIDO|GRANEL SOLIDO PLATAFORMA|GRANEL SOLIDO - PLATAFORMA",
    },
    {
        "column": "GRANEL_LIQUIDO_TANQUE_CARGADO",
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
        get_sicetac_valorhora_df.cache_clear()
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


def _carroceria_option(carroceria: str) -> dict[str, str] | None:
    return _SICE_COLUMN_MAP.get(_normalize_lookup_text(carroceria))


def _lookup_sicetac_totales(
    *,
    cod_origen_str: str,
    cod_destino_str: str,
    configuracion_lookup: str,
    carroceria: str,
) -> list[dict[str, Any]]:
    if not _USE_CONSOLIDATED_LOOKUP:
        return []

    carroceria_option = _carroceria_option(carroceria)
    if not carroceria_option:
        return []
    lookup_col = carroceria_option["column"]

    df_rows = get_sicetac_movilizacion_df(cod_origen_str, cod_destino_str, configuracion_lookup)
    if df_rows.empty:
        df_rows = get_sicetac_movilizacion_df(cod_destino_str, cod_origen_str, configuracion_lookup)
    df_valorhora = get_sicetac_valorhora_df(configuracion_lookup)

    if df_rows.empty or df_valorhora.empty:
        return []
    vh_row = df_valorhora.iloc[0]

    try:
        valor_hora = float(vh_row.get(lookup_col))
    except Exception:
        return []

    if pd.isna(valor_hora):
        return []

    resolved: list[dict[str, Any]] = []
    for _, row in df_rows.iterrows():
        try:
            movilizacion = float(row.get(lookup_col))
        except Exception:
            continue
        if pd.isna(movilizacion):
            continue
        resolved.append(
            {
                "rutasid": _clean_id(row.get("RUTASID")),
                "movilizacion": movilizacion,
                "valor_hora": valor_hora,
                "totales": {
                    "H2": round(movilizacion + (2 * valor_hora), 2),
                    "H4": round(movilizacion + (4 * valor_hora), 2),
                    "H8": round(movilizacion + (8 * valor_hora), 2),
                },
                "lookup_column": lookup_col.lower(),
                "lookup_label": carroceria_option["label"],
            }
        )
    return resolved


def calcular_sicetac(data: ConsultaInput) -> dict:
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

    vehiculo_upper = data.vehiculo.strip().upper().replace("C", "")
    vehiculos_validos = df_vehiculos["TIPO_VEHICULO"].astype(str).str.upper().str.replace("C", "").unique()
    if vehiculo_upper not in vehiculos_validos:
        raise SicetacError(
            400,
            f"Vehículo '{data.vehiculo}' no encontrado. Opciones válidas: {', '.join(vehiculos_validos)}"
        )

    fila_conf = df_vehiculos[df_vehiculos["TIPO_VEHICULO"] == data.vehiculo].iloc[0]
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
                configuracion=data.vehiculo,
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
            configuracion=data.vehiculo,
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


def calcular_sicetac_resumen(data: ConsultaInput) -> dict:
    """
    Calcula totales para 2, 4 y 8 horas logísticas con respuesta mínima.
    """
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

    vehiculo_upper = data.vehiculo.strip().upper().replace("C", "")
    vehiculos_validos = df_vehiculos["TIPO_VEHICULO"].astype(str).str.upper().str.replace("C", "").unique()
    if vehiculo_upper not in vehiculos_validos:
        raise SicetacError(
            400,
            f"Vehículo '{data.vehiculo}' no encontrado. Opciones válidas: {', '.join(vehiculos_validos)}"
        )

    meses_validos = df_parametros["MES"].unique().tolist()
    if int(mes_usar) not in meses_validos:
        raise SicetacError(400, f"Mes '{mes_usar}' no válido. Debe ser uno de: {meses_validos}")

    fila_conf = df_vehiculos[df_vehiculos["TIPO_VEHICULO"] == data.vehiculo].iloc[0]
    ejes_conf = _clean_id(fila_conf.get("EJES_CONFIGURACION"))
    configuracion_lookup = _configuracion_lookup(fila_conf, data.vehiculo)
    peajes_index = _get_peajes_index(df_peajes)

    if (
        not manual_mode
        and data.modo_viaje.upper() == "CARGADO"
        and ruta is not None
        and not ruta.empty
    ):
        lookup_rows = _lookup_sicetac_totales(
            cod_origen_str=cod_origen_str,
            cod_destino_str=cod_destino_str,
            configuracion_lookup=configuracion_lookup,
            carroceria=data.carroceria,
        )
        if lookup_rows:
            if len(lookup_rows) == 1:
                respuesta = {
                    "origen": origen_display,
                    "destino": destino_display,
                    "configuracion": data.vehiculo,
                    "configuracion_analisis": configuracion_lookup,
                    "mes": int(mes_usar),
                    "carroceria": data.carroceria,
                    "modo_viaje": data.modo_viaje.upper(),
                    "totales": lookup_rows[0]["totales"],
                    "metodo": "lookup_consolidado",
                    "detalle_lookup": {
                        "rutasid": lookup_rows[0]["rutasid"],
                        "movilizacion": lookup_rows[0]["movilizacion"],
                        "valor_hora": lookup_rows[0]["valor_hora"],
                        "columna_usada": lookup_rows[0]["lookup_column"],
                        "opcion_servicio": lookup_rows[0]["lookup_label"],
                    },
                }
                if resolved_route:
                    _attach_resolved_route(respuesta, resolved_route)
                return respuesta

            variantes = []
            for idx, item in enumerate(lookup_rows, start=1):
                variantes.append({
                    "NOMBRE_SICE": f"RUTASID {item['rutasid']}" if item["rutasid"] else f"Ruta {idx}",
                    "RUTASID": item["rutasid"],
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
                "mes": int(mes_usar),
                "carroceria": data.carroceria,
                "modo_viaje": data.modo_viaje.upper(),
                "metodo": "lookup_consolidado",
                "variantes": variantes,
            }
            if resolved_route:
                _attach_resolved_route(respuesta, resolved_route)
            return respuesta

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
                configuracion=data.vehiculo,
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
            configuracion=data.vehiculo,
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
