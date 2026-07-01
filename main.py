import os
import math
from io import BytesIO

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from sicetac_service import (
    ConsultaInput,
    SicetacError,
    adjuntar_peajes_a_respuesta,
    calcular_sicetac as calcular_sicetac_service,
    calcular_sicetac_resumen,
    consulta_solicita_peajes,
    _refresh_cache,
    generar_snapshot,
    get_sice_column_options,
    obtener_peajes_detalle,
)
from supabase_data import get_client, get_table_df

app = FastAPI(title="API SICETAC", version="2.0.1")

cors_origins = os.getenv("CORS_ORIGINS", "*")
origins = [o.strip() for o in cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _json_safe(value):
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if value is None or isinstance(value, (str, int, bool)):
        return value
    try:
        if value != value:
            return None
    except Exception:
        pass
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except Exception:
            pass
    return value


def _json_response(content, status_code: int = 200):
    return JSONResponse(content=_json_safe(content), status_code=status_code)

@app.post("/consulta")
def calcular_sicetac_endpoint(data: ConsultaInput):
    try:
        if data.resumen:
            respuesta = calcular_sicetac_resumen(data)
        else:
            respuesta = calcular_sicetac_service(data)
        if consulta_solicita_peajes(data):
            respuesta = adjuntar_peajes_a_respuesta(respuesta, data.vehiculo)
        return _json_response(respuesta)

    except HTTPException as ex:
        raise ex
    except SicetacError as ex:
        raise HTTPException(status_code=ex.status_code, detail=ex.detail)
    except Exception as e:
        return _json_response({"error": str(e)}, status_code=500)


@app.post("/consulta_resumen")
def calcular_sicetac_resumen_endpoint(data: ConsultaInput):
    try:
        respuesta = calcular_sicetac_resumen(data)
        if consulta_solicita_peajes(data):
            respuesta = adjuntar_peajes_a_respuesta(respuesta, data.vehiculo)
        return _json_response(respuesta)

    except HTTPException as ex:
        raise ex
    except SicetacError as ex:
        raise HTTPException(status_code=ex.status_code, detail=ex.detail)
    except Exception as e:
        return _json_response({"error": str(e)}, status_code=500)


@app.get("/health")
def health():
    return _json_response({"status": "ok", "version": app.version})


@app.get("/opciones/carrocerias")
def opciones_carrocerias():
    return _json_response({"carrocerias": get_sice_column_options()})


@app.get("/opciones/vehiculos")
def opciones_vehiculos():
    try:
        df_vehiculos = get_table_df("vehiculos")
        if df_vehiculos.empty:
            return _json_response({"vehiculos": []})

        columnas = [
            col
            for col in ["tipo_vehiculo", "configuracion_analisis", "detalle_tipo_vehiculo", "ejes_configuracion"]
            if col in df_vehiculos.columns
        ]
        records = (
            df_vehiculos[columnas]
            .fillna("")
            .drop_duplicates()
            .to_dict(orient="records")
        )
        return _json_response({"vehiculos": records})
    except Exception as e:
        return _json_response({"error": str(e)}, status_code=500)


@app.get("/peajes/detalle")
def peajes_detalle(id_sice: int, configuracion: str | None = None):
    try:
        return _json_response(obtener_peajes_detalle(id_sice=id_sice, configuracion=configuracion))
    except SicetacError as ex:
        raise HTTPException(status_code=ex.status_code, detail=ex.detail)
    except Exception as e:
        return _json_response({"error": str(e)}, status_code=500)


@app.get("/municipios")
def listar_municipios():
    try:
        df_municipios = get_table_df("municipios")
        if df_municipios.empty:
            return _json_response({"municipios": []})

        columnas = [
            col
            for col in ["codigo_dane", "nombre_oficial", "variacion_1", "variacion_2", "variacion_3", "departamento"]
            if col in df_municipios.columns
        ]
        records = (
            df_municipios[columnas]
            .fillna("")
            .to_dict(orient="records")
        )
        return _json_response({"municipios": records})
    except Exception as e:
        return _json_response({"error": str(e)}, status_code=500)


@app.post("/refresh")
def refresh_cache():
    _refresh_cache(force=True)
    return _json_response({"status": "ok", "refreshed": True})


@app.post("/consulta_texto")
def calcular_sicetac_texto(data: ConsultaInput):
    try:
        def _format_cop(value):
            try:
                v = float(value)
            except Exception:
                return str(value)
            # Formato COP sin decimales, con separadores
            return f"${v:,.0f}".replace(",", ".")

        if data.resumen:
            r = calcular_sicetac_resumen(data)
            if consulta_solicita_peajes(data):
                r = adjuntar_peajes_a_respuesta(r, data.vehiculo)
            if "variantes" in r:
                partes = []
                for v in r["variantes"]:
                    tot = v.get("totales", {})
                    linea = (
                        f"{v.get('NOMBRE_SICE','RUTA')} (ID {v.get('ID_SICE')}): "
                        f"H2 {_format_cop(tot.get('H2'))}, H4 {_format_cop(tot.get('H4'))}, H8 {_format_cop(tot.get('H8'))}"
                    )
                    resumen_peajes = v.get("peajes_resumen")
                    if resumen_peajes:
                        linea += (
                            f", peajes {_format_cop(resumen_peajes.get('total_peajes'))}"
                            f" ({resumen_peajes.get('cantidad_peajes')} peajes)"
                        )
                    partes.append(linea)
                texto = " | ".join(partes)
            else:
                tot = r.get("totales", {})
                texto = (
                    f"{r.get('origen')}->{r.get('destino')} {r.get('configuracion')} "
                    f"H2 {_format_cop(tot.get('H2'))}, H4 {_format_cop(tot.get('H4'))}, H8 {_format_cop(tot.get('H8'))}"
                )
                resumen_peajes = r.get("peajes_resumen")
                if resumen_peajes:
                    texto += (
                        f", peajes {_format_cop(resumen_peajes.get('total_peajes'))}"
                        f" ({resumen_peajes.get('cantidad_peajes')} peajes)"
                    )
            return _json_response({"texto": texto})
        else:
            r = calcular_sicetac_service(data)
            if consulta_solicita_peajes(data):
                r = adjuntar_peajes_a_respuesta(r, data.vehiculo)
            s = r.get("SICETAC", {})
            texto = (
                f"{s.get('origen')}->{s.get('destino')} {s.get('configuracion')} "
                f"total {_format_cop(s.get('total_viaje'))}"
            )
            resumen_peajes = r.get("peajes_resumen")
            if resumen_peajes:
                texto += (
                    f", peajes {_format_cop(resumen_peajes.get('total_peajes'))}"
                    f" ({resumen_peajes.get('cantidad_peajes')} peajes)"
                )
            return _json_response({"texto": texto})
    except HTTPException as ex:
        raise ex
    except SicetacError as ex:
        raise HTTPException(status_code=ex.status_code, detail=ex.detail)
    except Exception as e:
        return _json_response({"error": str(e)}, status_code=500)


@app.post("/snapshot/generate")
def snapshot_generate():
    try:
        df = generar_snapshot(horas=[0, 2, 4, 8])
        if df.empty:
            return _json_response({"error": "Snapshot vacío"}, status_code=500)

        # Nombre del archivo
        mes = int(df["mes"].iloc[0]) if "mes" in df.columns else "latest"
        filename = f"sicetac_snapshot_{mes}_all.xlsx"

        # Exportar a Excel en memoria
        buf = BytesIO()
        df.to_excel(buf, index=False)
        buf.seek(0)

        client = get_client()
        bucket = client.storage.from_("snapshots")

        # Upload (upsert)
        bucket.upload(
            filename,
            buf.getvalue(),
            {"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "upsert": True},
        )

        public_url = bucket.get_public_url(filename)

        return _json_response({"ok": True, "file": filename, "url": public_url})
    except SicetacError as ex:
        raise HTTPException(status_code=ex.status_code, detail=ex.detail)
    except Exception as e:
        return _json_response({"error": str(e)}, status_code=500)
