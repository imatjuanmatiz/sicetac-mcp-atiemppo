#!/usr/bin/env python3
"""Upsert the private port value-in-plaza layer and retain a rolling window.

The input CSVs are produced by
``generar_capa_valor_plaza_puertos_desagregada_desde_202607.py``. The script
never copies RNDC manifest detail: it only uploads the derived route and
port/range aggregates. Writes require ``--execute`` and a Supabase service
role key in the environment.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import pandas as pd
from supabase import create_client


DETAIL_TABLE = "valor_en_plaza_puertos_desagregada"
SUMMARY_TABLE = "valor_en_plaza_puertos_rangos_vehiculo"
DEFAULT_DIR = Path("/Users/atiemppoia/Documents/docs de rndc/salidas/mantenimiento")

DETAIL_COLUMNS = [
    "mes_codigo", "mes_vigencia", "ruta", "codigo_puerto_origen", "puerto_origen",
    "configuracion", "tipo_carga", "valor_en_plaza", "valor_estadisticas",
    "valor_remesas", "viajes_pagados_estadisticas", "fuente_valor_en_plaza",
    "metodologia_ultimo_mes", "segmento_operativo", "tipo_contenedor_observado",
    "viajes_reportados", "viajes_total_celda", "participacion_viajes_segmento",
    "toneladas_reportadas", "toneladas_por_viaje_reportadas",
    "metodo_clasificacion_contenedor", "valor_en_plaza_unitario_observado",
    "valor_en_plaza_aporte_ponderado", "tipo_vehiculo_sicetac",
    "n_capacidades_sicetac", "capacidad_min_toneladas", "capacidad_max_toneladas",
    "proxy_peso_estado", "rango_toneladas_vehiculo", "capacidad_sicetac_estado",
]
SUMMARY_COLUMNS = [
    "mes_codigo", "mes_vigencia", "puerto_origen", "codigo_puerto_origen",
    "segmento_operativo", "tipo_contenedor_observado", "configuracion",
    "tipo_vehiculo_sicetac", "rango_toneladas_vehiculo", "proxy_peso_estado",
    "capacidad_sicetac_estado", "tipo_carga", "rutas_con_valor", "filas_ruta_valor",
    "viajes_reportados", "toneladas_reportadas",
    "valor_en_plaza_promedio_ponderado_viajes", "valor_en_plaza_mediana_rutas",
    "valor_en_plaza_min_ruta", "valor_en_plaza_max_ruta",
    "toneladas_por_viaje_reportadas",
]
DETAIL_CONFLICT = (
    "mes_codigo,ruta,codigo_puerto_origen,configuracion,tipo_carga,"
    "segmento_operativo,tipo_contenedor_observado,rango_toneladas_vehiculo"
)
SUMMARY_CONFLICT = (
    "mes_codigo,codigo_puerto_origen,segmento_operativo,tipo_contenedor_observado,"
    "configuracion,rango_toneladas_vehiculo,tipo_carga"
)


def args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input-dir", type=Path, default=DEFAULT_DIR)
    p.add_argument("--detail", help="CSV de detalle; si se omite, elige el corte con más meses")
    p.add_argument("--summary", help="CSV de resumen correspondiente al detalle")
    p.add_argument("--keep-months", type=int, default=2)
    p.add_argument("--chunk-size", type=int, default=500)
    p.add_argument("--execute", action="store_true", help="Ejecuta upsert y retención en Supabase")
    return p.parse_args()


def load(path: Path, columns: list[str]) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "mes" in df.columns:
        df = df.rename(columns={"mes": "mes_codigo"})
    df["mes_codigo"] = pd.to_numeric(df["mes_codigo"], errors="raise").astype(int)
    df["mes_vigencia"] = df["mes_codigo"].map(
        lambda x: f"{x // 100:04d}-{x % 100:02d}-01"
    )
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: faltan columnas {missing}")
    return df[columns].where(pd.notna(df[columns]), None)


def records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return df.to_dict(orient="records")


def discover_inputs(input_dir: Path) -> tuple[Path, Path]:
    candidates: list[tuple[tuple[int, int, str], Path, Path]] = []
    for detail in sorted(input_dir.glob("valor_en_plaza_puertos_desagregado_desde_*.csv")):
        suffix = detail.stem.rsplit("_desde_", 1)[-1]
        summary = input_dir / f"valor_en_plaza_puertos_rangos_vehiculo_desde_{suffix}.csv"
        if not summary.exists():
            continue
        months = pd.read_csv(detail, usecols=["mes"], encoding="utf-8-sig")["mes"].dropna().astype(int).unique()
        if len(months) == 0:
            continue
        rank = (len(months), int(max(months)), suffix)
        candidates.append((rank, detail, summary))
    if not candidates:
        raise FileNotFoundError("No hay pares de CSV de valor en plaza portuario")
    _, detail, summary = max(candidates, key=lambda item: item[0])
    return detail, summary


def upsert(client, table: str, df: pd.DataFrame, conflict: str, chunk_size: int) -> int:
    rows = records(df)
    for start in range(0, len(rows), chunk_size):
        client.table(table).upsert(rows[start : start + chunk_size], on_conflict=conflict).execute()
    return len(rows)


def main() -> None:
    a = args()
    if a.keep_months < 1:
        raise SystemExit("--keep-months debe ser positivo")
    if a.detail or a.summary:
        if not (a.detail and a.summary):
            raise SystemExit("--detail y --summary deben enviarse juntos")
        detail_path, summary_path = a.input_dir / a.detail, a.input_dir / a.summary
    else:
        detail_path, summary_path = discover_inputs(a.input_dir)
    detail = load(detail_path, DETAIL_COLUMNS)
    summary = load(summary_path, SUMMARY_COLUMNS)
    months = sorted(set(detail["mes_codigo"]) | set(summary["mes_codigo"]))
    keep = months[-a.keep_months :]
    cutoff = min(keep)
    report = {
        "detail_rows": len(detail),
        "summary_rows": len(summary),
        "source_months": months,
        "keep_months": keep,
        "cutoff_month": cutoff,
        "executed": False,
    }
    if not a.execute:
        print(report)
        return

    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        raise SystemExit("--execute requiere SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY")
    client = create_client(url, key)
    report["detail_upserted"] = upsert(client, DETAIL_TABLE, detail, DETAIL_CONFLICT, a.chunk_size)
    report["summary_upserted"] = upsert(client, SUMMARY_TABLE, summary, SUMMARY_CONFLICT, a.chunk_size)
    # La retención se ejecuta después de los upserts para no dejar un hueco si
    # el corte entrante reemplaza parcialmente el anterior.
    client.table(DETAIL_TABLE).delete().lt("mes_codigo", cutoff).execute()
    client.table(SUMMARY_TABLE).delete().lt("mes_codigo", cutoff).execute()
    report["executed"] = True
    print(report)


if __name__ == "__main__":
    main()
