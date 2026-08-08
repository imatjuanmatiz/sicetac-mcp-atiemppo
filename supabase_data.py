from __future__ import annotations

import os
import logging
from functools import lru_cache
from typing import Any, Dict, List

import pandas as pd
from supabase import create_client

logger = logging.getLogger("supabase_data")

# ---------------------------
# Configuración de Supabase
# ---------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    or os.getenv("SUPABASE_KEY", "")
    or os.getenv("SUPABASE_ANON_KEY", "")
).strip()

# ---------------------------
# Mapeo de tablas (editable vía ENV)
# ---------------------------
TABLES: Dict[str, str] = {
    "municipios": os.getenv("SICETAC_TABLE_MUNICIPIOS", "municipios"),
    "vehiculos": os.getenv("SICETAC_TABLE_VEHICULOS", "configuracion_vehicular"),
    "parametros": os.getenv("SICETAC_TABLE_PARAMETROS", "parametros_vigentes"),
    "costos_fijos": os.getenv("SICETAC_TABLE_COSTOS_FIJOS", "costos_fijos_vigentes"),
    "peajes": os.getenv("SICETAC_TABLE_PEAJES", "peajes_vigentes"),
    "rutas": os.getenv("SICETAC_TABLE_RUTAS", "rutas"),
    "sicetac_movilizacion": os.getenv("SICETAC_TABLE_SICETAC_MOVILIZACION", "sicetac_movilizacion_vigentes"),
    "sicetac_valorhora": os.getenv("SICETAC_TABLE_SICETAC_VALORHORA", "sicetac_valorhora_vigentes"),
    "sicetac_vacio": os.getenv("SICETAC_TABLE_SICETAC_VACIO", "sicetac_vacio_vigentes"),
    "valor_plaza": os.getenv("SICETAC_TABLE_VALOR_PLAZA", "valor_en_plaza_mensual_descriptiva"),
    "peajes_detalle": os.getenv("SICETAC_TABLE_PEAJES_DETALLE", "peajes_detalle_vigentes"),
    "peajes_resumen": os.getenv("SICETAC_TABLE_PEAJES_RESUMEN", "peajes_resumen_vigentes"),
    "peajes_inventario": os.getenv("SICETAC_TABLE_PEAJES_INVENTARIO", "peajes_inventario"),
    # Tablas mínimas para el cálculo del modelo
}


def _require_supabase() -> None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY/SUPABASE_KEY en el entorno.")


@lru_cache(maxsize=1)
def get_client():
    _require_supabase()
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def _fetch_table_all(table: str, page_size: int = 1000) -> List[Dict[str, Any]]:
    client = get_client()
    start = 0
    rows: List[Dict[str, Any]] = []
    while True:
        resp = client.table(table).select("*").range(start, start + page_size - 1).execute()
        data = resp.data or []
        rows.extend(data)
        if len(data) < page_size:
            break
        start += page_size
    return rows


def _fetch_table_filtered(
    table: str,
    *,
    select: str = "*",
    filters: list[tuple[str, str, Any]] | None = None,
    limit: int | None = None,
) -> List[Dict[str, Any]]:
    client = get_client()
    query = client.table(table).select(select)
    for column, op, value in (filters or []):
        if op == "eq":
            query = query.eq(column, value)
        elif op == "ilike":
            query = query.ilike(column, value)
        else:
            raise ValueError(f"Operador no soportado: {op}")
    if limit is not None:
        query = query.limit(limit)
    resp = query.execute()
    return resp.data or []


def _alias_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Crea alias de columnas en MAYÚSCULA y minúscula para tolerar cambios de casing.
    También normaliza espacios -> '_' en los alias.
    """
    if df is None or df.empty:
        return df

    cols = list(df.columns)
    for col in cols:
        base = str(col).strip().replace(" ", "_")
        lower = base.lower()
        upper = base.upper()

        if base not in df.columns:
            df[base] = df[col]
        if lower not in df.columns:
            df[lower] = df[col]
        if upper not in df.columns:
            df[upper] = df[col]

        # Alias con espacios (ej: COSTO FIJO)
        space_upper = base.replace("_", " ").upper()
        space_lower = base.replace("_", " ").lower()
        if space_upper not in df.columns:
            df[space_upper] = df[col]
        if space_lower not in df.columns:
            df[space_lower] = df[col]

    # Alias manuales para nombres esperados por el modelo
    manual = {
        "tipo_vehiculo": "TIPO_VEHICULO",
        "mes_codigo": "MES",
        "tipo_carroceria": "TIPO_CARROCERIA",
        "costo_fijo": "COSTO FIJO",
        "costos_variables": "COSTOS VARIABLES",
        "valor_combustible_galon_acpm": "VALOR COMBUSTIBLE GALÓN ACPM",
        "id_sice": "ID_SICE",
        "ejes_configuracion": "EJES_CONFIGURACION",
        "valor_peaje": "VALOR_PEAJE",
        "ruta": "RUTA",
        "nombre_sice": "NOMBRE_SICE",
        "km_plano": "KM_PLANO",
        "km_ondulado": "KM_ONDULADO",
        "km_montanoso": "KM_MONTAÑOSO",
        "km_urbano": "KM_URBANO",
        "km_despavimentado": "KM_DESPAVIMENTADO",
        "codigo_dane": "CODIGO_DANE",
        "codigo_dane_origen": "CODIGO_DANE_ORIGEN",
        "codigo_dane_destino": "CODIGO_DANE_DESTINO",
        "nombre_oficial": "NOMBRE_OFICIAL",
        "variacion_1": "VARIACION_1",
        "variacion_2": "VARIACION_2",
        "variacion_3": "VARIACION_3",
        "configuracion_analisis": "CONFIGURACION_ANALISIS",
        "configuracion_sicetac_lookup": "CONFIGURACION_SICETAC_LOOKUP",
        "rutasid": "RUTASID",
    }
    for src, dst in manual.items():
        if src in df.columns and dst not in df.columns:
            df[dst] = df[src]

    # Alias de acentos especiales si vienen sin tildes
    if "VALOR COMBUSTIBLE GALON ACPM" in df.columns and "VALOR COMBUSTIBLE GALÓN ACPM" not in df.columns:
        df["VALOR COMBUSTIBLE GALÓN ACPM"] = df["VALOR COMBUSTIBLE GALON ACPM"]
    return df


@lru_cache(maxsize=None)
def get_table_df(key: str) -> pd.DataFrame:
    table = TABLES.get(key, key)
    try:
        rows = _fetch_table_all(table)
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df = _alias_columns(df)
        return df
    except Exception as e:
        logger.warning(f"⚠️ No se pudo cargar tabla {table}: {e}")
        return pd.DataFrame()


@lru_cache(maxsize=512)
def get_sicetac_valorhora_df(configuracion: str, mes_codigo: int | None = None) -> pd.DataFrame:
    table = TABLES.get("sicetac_valorhora", "sicetac_valorhora_vigentes")
    configuracion_norm = str(configuracion or "").strip().upper()
    if not configuracion_norm:
        return pd.DataFrame()
    filters: list[tuple[str, str, Any]] = [("configuracion", "ilike", configuracion_norm)]
    if mes_codigo is not None:
        filters.append(("mes_codigo", "eq", int(mes_codigo)))
    try:
        rows = _fetch_table_filtered(
            table,
            filters=filters,
        )
        if not rows:
            return pd.DataFrame()
        df = _alias_columns(pd.DataFrame(rows))
        if "mes_codigo" in df.columns:
            df["mes_codigo"] = pd.to_numeric(df["mes_codigo"], errors="coerce")
            if mes_codigo is None:
                df = df[df["mes_codigo"] == df["mes_codigo"].max()]
            df = df.sort_values(by="mes_codigo", ascending=False, na_position="last")
        return df.head(1)
    except Exception as e:
        logger.warning(f"⚠️ No se pudo consultar valor hora {configuracion_norm}: {e}")
        return pd.DataFrame()


@lru_cache(maxsize=4096)
def get_sicetac_movilizacion_df(
    origen: str,
    destino: str,
    configuracion: str,
    mes_codigo: int | None = None,
) -> pd.DataFrame:
    table = TABLES.get("sicetac_movilizacion", "sicetac_movilizacion_vigentes")
    origen_norm = str(origen or "").strip()
    destino_norm = str(destino or "").strip()
    configuracion_norm = str(configuracion or "").strip().upper()
    if not origen_norm or not destino_norm or not configuracion_norm:
        return pd.DataFrame()
    filters: list[tuple[str, str, Any]] = [
        ("origen", "eq", origen_norm),
        ("destino", "eq", destino_norm),
        ("configuracion", "ilike", configuracion_norm),
    ]
    if mes_codigo is not None:
        filters.append(("mes_codigo", "eq", int(mes_codigo)))
    try:
        rows = _fetch_table_filtered(table, filters=filters)
        if not rows:
            return pd.DataFrame()
        df = _alias_columns(pd.DataFrame(rows))
        if "mes_codigo" in df.columns:
            df["mes_codigo"] = pd.to_numeric(df["mes_codigo"], errors="coerce")
            if mes_codigo is None:
                df = df[df["mes_codigo"] == df["mes_codigo"].max()]
            df = df.sort_values(by=["mes_codigo", "rutasid"], ascending=[False, True], na_position="last")
        return df
    except Exception as e:
        logger.warning(
            f"⚠️ No se pudo consultar movilización {origen_norm}->{destino_norm} / {configuracion_norm}: {e}"
        )
        return pd.DataFrame()


@lru_cache(maxsize=4096)
def get_sicetac_vacio_df(
    origen: str,
    destino: str,
    configuracion: str,
    mes_codigo: int | None = None,
) -> pd.DataFrame:
    table = TABLES.get("sicetac_vacio", "sicetac_vacio_vigentes")
    origen_norm = str(origen or "").strip()
    destino_norm = str(destino or "").strip()
    configuracion_norm = str(configuracion or "").strip().upper()
    if not origen_norm or not destino_norm or not configuracion_norm:
        return pd.DataFrame()
    filters: list[tuple[str, str, Any]] = [
        ("origen", "eq", origen_norm),
        ("destino", "eq", destino_norm),
        ("configuracion", "ilike", configuracion_norm),
    ]
    if mes_codigo is not None:
        filters.append(("mes_codigo", "eq", int(mes_codigo)))
    try:
        rows = _fetch_table_filtered(table, filters=filters)
        if not rows:
            return pd.DataFrame()
        df = _alias_columns(pd.DataFrame(rows))
        if "mes_codigo" in df.columns:
            df["mes_codigo"] = pd.to_numeric(df["mes_codigo"], errors="coerce")
            if mes_codigo is None:
                df = df[df["mes_codigo"] == df["mes_codigo"].max()]
            df = df.sort_values(by=["mes_codigo", "rutasid"], ascending=[False, True], na_position="last")
        return df
    except Exception as e:
        logger.warning(
            f"⚠️ No se pudo consultar VACIO {origen_norm}->{destino_norm} / {configuracion_norm}: {e}"
        )
        return pd.DataFrame()


@lru_cache(maxsize=4096)
def get_valor_plaza_df(route_code: str, configuracion: str) -> pd.DataFrame:
    table = TABLES.get("valor_plaza", "valor_en_plaza_mensual_descriptiva")
    route_norm = str(route_code or "").strip()
    configuracion_norm = str(configuracion or "").strip().upper()
    if not route_norm or not configuracion_norm:
        return pd.DataFrame()
    try:
        rows = _fetch_table_filtered(
            table,
            filters=[
                ("ruta", "eq", route_norm),
                ("configuracion", "ilike", configuracion_norm),
            ],
        )
        if not rows:
            return pd.DataFrame()
        df = _alias_columns(pd.DataFrame(rows))
        if "mes_codigo" in df.columns:
            df["mes_codigo"] = pd.to_numeric(df["mes_codigo"], errors="coerce")
            df = df.sort_values(by="mes_codigo", ascending=False, na_position="last")
        return df
    except Exception as e:
        logger.warning(f"⚠️ No se pudo consultar valor plaza {route_norm} / {configuracion_norm}: {e}")
        return pd.DataFrame()


@lru_cache(maxsize=4096)
def get_peajes_detalle_df(id_sice: str | int, configuracion: str | None = None) -> pd.DataFrame:
    table = TABLES.get("peajes_detalle", "peajes_detalle_vigentes")
    try:
        id_sice_int = int(float(str(id_sice).strip()))
    except Exception:
        return pd.DataFrame()

    filters: list[tuple[str, str, Any]] = [("id_sice", "eq", id_sice_int)]
    configuracion_norm = str(configuracion or "").strip().upper()
    if configuracion_norm:
        filters.append(("configuracion", "ilike", configuracion_norm))

    try:
        try:
            rows = _fetch_table_filtered(table, filters=filters)
        except Exception as filtered_error:
            if not configuracion_norm:
                raise
            # Algunas vistas de ruta solo exponen ID_SICE + ID_PEAJE + orden;
            # la configuración se resuelve después contra VALOR1..VALOR7.
            logger.info("ℹ️ Detalle de peajes sin filtro de configuración: %s", filtered_error)
            rows = []
        if not rows and configuracion_norm:
            rows = _fetch_table_filtered(table, filters=[("id_sice", "eq", id_sice_int)])
        if not rows:
            return pd.DataFrame()
        df = _alias_columns(pd.DataFrame(rows))
        if "orden" in df.columns:
            df["orden"] = pd.to_numeric(df["orden"], errors="coerce")
            sort_columns = ["orden"]
            if "configuracion" in df.columns:
                sort_columns.append("configuracion")
            df = df.sort_values(by=sort_columns, na_position="last")
        return df
    except Exception as e:
        logger.warning(f"⚠️ No se pudo consultar detalle peajes ruta {id_sice_int}: {e}")
        return pd.DataFrame()


@lru_cache(maxsize=4096)
def get_peajes_resumen_df(id_sice: str | int) -> pd.DataFrame:
    table = TABLES.get("peajes_resumen", "peajes_resumen_vigentes")
    try:
        id_sice_int = int(float(str(id_sice).strip()))
    except Exception:
        return pd.DataFrame()

    try:
        rows = _fetch_table_filtered(table, filters=[("id_sice", "eq", id_sice_int)])
        if not rows:
            return pd.DataFrame()
        df = _alias_columns(pd.DataFrame(rows))
        if "configuracion" in df.columns:
            df = df.sort_values(by="configuracion", na_position="last")
        return df
    except Exception as e:
        logger.warning(f"⚠️ No se pudo consultar resumen peajes ruta {id_sice_int}: {e}")
        return pd.DataFrame()


@lru_cache(maxsize=1)
def get_peajes_inventario_df() -> pd.DataFrame:
    """Carga el catálogo pequeño de peajes para enriquecer rutas por ID_PEAJE."""
    table = TABLES.get("peajes_inventario", "peajes_inventario")
    try:
        rows = _fetch_table_all(table)
        if not rows:
            return pd.DataFrame()
        return _alias_columns(pd.DataFrame(rows))
    except Exception as e:
        logger.warning(f"⚠️ No se pudo cargar inventario de peajes {table}: {e}")
        return pd.DataFrame()
