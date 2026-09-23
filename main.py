import os
import math
import secrets
from io import BytesIO

from fastapi import Depends, FastAPI, Header, HTTPException
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
from commercial_api import router as commercial_router

app = FastAPI(title="API SICETAC", version="2.5.1")

# Orden de presentación para los rangos livianos vigentes desde agosto de 2026.
# El resto del catálogo conserva un orden alfabético estable.
VEHICULOS_LIVIANOS_VIGENTES_ORDEN = {
    "CA": 10,
    "C257": 20,
    "C279": 30,
    "C2910": 40,
}

cors_origins = os.getenv("CORS_ORIGINS", "*")
origins = [o.strip() for o in cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins else ["*"],
    allow_credentials=bool(origins and origins != ["*"]),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Contrato comercial versionado. Los endpoints legacy se mantienen abajo para
# no romper WhatsApp ni las integraciones actuales.
app.include_router(commercial_router)


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


def _require_admin_token(x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")):
    """Protege operaciones de escritura/refresco que nunca deben ser públicas."""
    expected = os.getenv("SICETAC_ADMIN_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Operación administrativa no configurada.")
    if not x_admin_token or not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=401, detail="Token administrativo inválido.")


def _valor_plaza_text(valor_plaza, format_cop) -> str:
    """Formatea el último valor en plaza ya resuelto para la ruta consultada."""
    if not isinstance(valor_plaza, dict):
        return ""
    meses = valor_plaza.get("meses") or []
    if not isinstance(meses, list) or not meses:
        return ""

    ultimo = meses[0]
    if not isinstance(ultimo, dict) or ultimo.get("valor") in (None, ""):
        return ""

    mes = ultimo.get("mes_label") or ultimo.get("mes_codigo")
    valor = format_cop(ultimo.get("valor"))
    tipo = ultimo.get("tipo_carga_usado")
    sufijo_tipo = f" ({tipo})" if tipo else ""
    return f", valor en plaza {mes} {valor}{sufijo_tipo}"

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
        records.sort(
            key=lambda row: (
                VEHICULOS_LIVIANOS_VIGENTES_ORDEN.get(
                    str(row.get("tipo_vehiculo") or "").upper(),
                    100,
                ),
                str(row.get("tipo_vehiculo") or ""),
            )
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
def refresh_cache(_: None = Depends(_require_admin_token)):
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

        if data.detalle_costos or data.detalle_consumo or not data.resumen:
            r = calcular_sicetac_service(data)
            c = r["detalle_costos"]
            lines = [f"{r['origen']} a {r['destino']} · {r['total_km']} km"]
            if r.get("estimado"):
                lines.append("VALOR ESTIMADO: 30 km en terreno ondulado.")
            if data.detalle_consumo:
                for terreno, item in r["detalle_consumo"]["por_terreno"].items():
                    lines.append(f"{terreno}: {item['km']:g} km, {item['gal']:.2f} gal, {_format_cop(item['costo_combustible'])}")
                lines.append(f"Total: {c['total_galones']:.2f} gal, {_format_cop(c['combustible'])}")
            else:
                lines.extend([f"Galones: {c['total_galones']:.2f}; recorrido: {c['horas_recorrido']} h; logística: {c['horas_logisticas']} h; rotaciones/mes: {c['rotaciones_calculadas']}",
                    f"Fijos: {_format_cop(c['costo_fijo'])}; variables: {_format_cop(c['costos_variables'])}; otros: {_format_cop(c['otros_costos'])}",
                    f"Total modelo: {_format_cop(c['total_viaje'])}"])
            return _json_response({"texto": "\n".join(lines)})

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
                    aumento = v.get("aumento") or {}
                    if aumento.get("activo"):
                        aumento_pct = aumento.get("aumento_pct") or {}
                        linea += (
                            f", aumento desde {aumento.get('periodo_base')}: "
                            f"H4 {aumento_pct.get('H4')}%, H8 {aumento_pct.get('H8')}%"
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
                aumento = r.get("aumento") or {}
                if aumento.get("activo"):
                    aumento_pct = aumento.get("aumento_pct") or {}
                    texto += (
                        f", aumento desde {aumento.get('periodo_base')}: "
                        f"H4 {aumento_pct.get('H4')}%, H8 {aumento_pct.get('H8')}%"
                    )
                resumen_peajes = r.get("peajes_resumen")
                if resumen_peajes:
                    texto += (
                        f", peajes {_format_cop(resumen_peajes.get('total_peajes'))}"
                        f" ({resumen_peajes.get('cantidad_peajes')} peajes)"
                    )
            texto += _valor_plaza_text(r.get("valor_plaza"), _format_cop)
            if (r.get("aumento") or {}).get("activo"):
                texto += " Modo aumento activo: conserva este modo en las próximas búsquedas hasta decir 'modo aumento off'."
            texto += f" · {r.get('total_km')} km" if r.get("total_km") is not None else ""
            if r.get("estimado"):
                texto = "VALOR ESTIMADO (30 km ondulados). " + texto
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
            texto += _valor_plaza_text(r.get("valor_plaza"), _format_cop)
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
def snapshot_generate(_: None = Depends(_require_admin_token)):
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
