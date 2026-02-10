from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from pydantic import BaseModel

from supabase_data import get_table_df
from sicetac_helper import SICETACHelper
from modelo_sicetac import calcular_modelo_sicetac_extendido
from modelo_sicetac_vacio import calcular_modelo_sicetac_extendido_vacio


class ConsultaInput(BaseModel):
    origen: str
    destino: str
    vehiculo: str = "C3S3"
    mes: int | None = None
    carroceria: str = "GENERAL"
    valor_peaje_manual: float = 0.0

    # LEGACY: sigue existiendo para no romper nada
    horas_logisticas: float | None = None

    # NUEVO: tiempo logístico que pide el usuario (cargue/descargue total)
    horas_logisticas_personalizadas: float | None = None

    # NUEVO: tarifa de stand by por hora > 8h
    tarifa_standby: float = 150000.0

    km_plano: float = 0
    km_ondulado: float = 0
    km_montañoso: float = 0
    km_urbano: float = 0
    km_despavimentado: float = 0
    modo_viaje: str = "CARGADO"

    # NUEVO: modo escenarios de tiempos logísticos
    modo_tiempos_logisticos: bool = False


@dataclass
class SicetacError(Exception):
    status_code: int
    detail: str


def _convertir_nativos(d: Any):
    if isinstance(d, dict):
        return {k: _convertir_nativos(v) for k, v in d.items()}
    if isinstance(d, list):
        return [_convertir_nativos(v) for v in d]
    if hasattr(d, "item"):
        return d.item()
    return d


def _clean_id(x) -> str:
    s = str(x).strip()
    # Si viene como float entero (ej: 5001000.0), conviértelo a int sin ceros añadidos
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
    except Exception:
        pass
    if s.endswith(".0") and s[:-2].isdigit():
        return s[:-2]
    return s


def _get_dataframes():
    df_municipios = get_table_df("municipios")
    df_vehiculos = get_table_df("vehiculos")
    df_parametros = get_table_df("parametros")
    df_costos_fijos = get_table_df("costos_fijos")
    df_peajes = get_table_df("peajes")
    df_rutas = get_table_df("rutas")
    return df_municipios, df_vehiculos, df_parametros, df_costos_fijos, df_peajes, df_rutas


_RUTAS_INDEX: dict[tuple[str, str], list[pd.Series]] | None = None


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


def _latest_mes(df_parametros: pd.DataFrame) -> int | None:
    if df_parametros is None or df_parametros.empty or "MES" not in df_parametros.columns:
        return None
    try:
        return int(pd.to_numeric(df_parametros["MES"], errors="coerce").max())
    except Exception:
        return None


def calcular_sicetac(data: ConsultaInput) -> dict:
    df_municipios, df_vehiculos, df_parametros, df_costos_fijos, df_peajes, df_rutas = _get_dataframes()

    if df_municipios.empty or df_vehiculos.empty or df_parametros.empty or df_costos_fijos.empty or df_peajes.empty or df_rutas.empty:
        raise SicetacError(500, "Tablas de Supabase no disponibles o vacías. Verifica conexión y datos.")

    helper = SICETACHelper(df_municipios)

    mes_usar = data.mes
    if mes_usar is None:
        mes_usar = _latest_mes(df_parametros)
    if mes_usar is None:
        raise SicetacError(500, "No se pudo determinar el MES más reciente.")

    origen_info = helper.buscar_municipio(data.origen)
    destino_info = helper.buscar_municipio(data.destino)

    if not origen_info or not destino_info:
        raise SicetacError(404, "Origen o destino no encontrado")

    cod_origen = origen_info["codigo_dane"]
    cod_destino = destino_info["codigo_dane"]

    cod_origen_str = _clean_id(cod_origen)
    cod_destino_str = _clean_id(cod_destino)

    rutas_index = _get_rutas_index(df_rutas)
    ruta_rows = rutas_index.get((cod_origen_str, cod_destino_str), [])
    if not ruta_rows:
        ruta_rows = rutas_index.get((cod_destino_str, cod_origen_str), [])
    ruta = pd.DataFrame(ruta_rows) if ruta_rows else pd.DataFrame()

    manual_distancias = None
    if ruta.empty:
        if any([data.km_plano, data.km_ondulado, data.km_montañoso, data.km_urbano, data.km_despavimentado]):
            manual_distancias = {
                "km_plano": data.km_plano,
                "km_ondulado": data.km_ondulado,
                "km_montanoso": data.km_montañoso,
                "km_urbano": data.km_urbano,
                "km_despavimentado": data.km_despavimentado,
            }
        else:
            raise SicetacError(404, "Ruta no registrada y no se proporcionaron distancias manuales")
        fila_ruta = None
    else:
        fila_ruta = ruta.iloc[0]

    def _distancias_from_ruta(row):
        if row is None:
            return manual_distancias or {
                "km_plano": 0,
                "km_ondulado": 0,
                "km_montanoso": 0,
                "km_urbano": 0,
                "km_despavimentado": 0,
            }
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

    def _ejecutar_modelo(horas_logisticas_modelo: float | None, ruta_row=None):
        distancias = _distancias_from_ruta(ruta_row)
        if data.modo_viaje.upper() == "VACIO":
            return calcular_modelo_sicetac_extendido_vacio(
                origen=data.origen,
                destino=data.destino,
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
            )
        return calcular_modelo_sicetac_extendido(
            origen=data.origen,
            destino=data.destino,
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
        )

    def _normalizar_total(res: dict | None):
        if res is None:
            return None
        if "total_viaje" not in res and "total_viaje_vacio" in res:
            res["total_viaje"] = res["total_viaje_vacio"]
        return res

    resultado = None
    escenarios_tiempos = None

    if data.modo_tiempos_logisticos:
        res_movilizacion = _normalizar_total(_ejecutar_modelo(0, ruta_row=fila_ruta))
        res_sicetac = _normalizar_total(_ejecutar_modelo(None, ruta_row=fila_ruta))

        res_personalizado = None
        if data.horas_logisticas_personalizadas is not None:
            horas_usuario = float(data.horas_logisticas_personalizadas)
            horas_base = min(horas_usuario, 8.0)
            horas_extra = max(horas_usuario - 8.0, 0.0)

            res_base = _normalizar_total(_ejecutar_modelo(horas_base, ruta_row=fila_ruta))
            if res_base is not None:
                res_personalizado = _convertir_nativos(res_base)
                costo_standby = round(horas_extra * float(data.tarifa_standby), 2)
                total_viaje = float(res_personalizado.get("total_viaje", 0))
                res_personalizado.update({
                    "horas_logisticas_usuario": horas_usuario,
                    "horas_logisticas_base": horas_base,
                    "horas_standby_adicionales": horas_extra,
                    "tarifa_standby": float(data.tarifa_standby),
                    "costo_standby": costo_standby,
                    "total_viaje_ajustado": round(total_viaje + costo_standby, 2),
                })

        escenarios_tiempos = {
            "MOVILIZACION": _convertir_nativos(res_movilizacion) if res_movilizacion else None,
            "SICETAC_DEFECTO": _convertir_nativos(res_sicetac) if res_sicetac else None,
            "PERSONALIZADO": res_personalizado,
        }
        resultado = res_sicetac or res_movilizacion or res_personalizado
    else:
        if data.horas_logisticas_personalizadas is not None:
            horas_usuario = float(data.horas_logisticas_personalizadas)
            horas_base = min(horas_usuario, 8.0)
            horas_extra = max(horas_usuario - 8.0, 0.0)

            res_base = _normalizar_total(_ejecutar_modelo(horas_base, ruta_row=fila_ruta))
            resultado = res_base

            if resultado is not None and horas_extra > 0:
                resultado = _convertir_nativos(resultado)
                costo_standby = round(horas_extra * float(data.tarifa_standby), 2)
                total_viaje = float(resultado.get("total_viaje", 0))
                resultado.update({
                    "horas_logisticas_usuario": horas_usuario,
                    "horas_logisticas_base": horas_base,
                    "horas_standby_adicionales": horas_extra,
                    "tarifa_standby": float(data.tarifa_standby),
                    "costo_standby": costo_standby,
                    "total_viaje_ajustado": round(total_viaje + costo_standby, 2),
                })
        else:
            resultado = _normalizar_total(_ejecutar_modelo(data.horas_logisticas, ruta_row=fila_ruta))

    resultado = _normalizar_total(resultado)
    resultado_convertido = _convertir_nativos(resultado) if resultado is not None else None

    respuesta = {
        "SICETAC": resultado_convertido,
        "MODO_VIAJE": data.modo_viaje.upper(),
    }
    if len(ruta) > 1:
        variantes = []
        for _, r in ruta.iterrows():
            try:
                res_var = _normalizar_total(_ejecutar_modelo(data.horas_logisticas, ruta_row=r))
                variantes.append({
                    "NOMBRE_SICE": r.get("NOMBRE_SICE"),
                    "ID_SICE": r.get("ID_SICE"),
                    "RESULTADO": _convertir_nativos(res_var) if res_var is not None else None,
                })
            except Exception:
                continue
        if variantes:
            respuesta["SICETAC_VARIANTES"] = variantes
    if escenarios_tiempos is not None:
        respuesta["MODO_TIEMPOS_LOGISTICOS"] = True
        respuesta["ESCENARIOS_TIEMPOS_LOGISTICOS"] = escenarios_tiempos
    return respuesta
