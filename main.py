import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from sicetac_service import (
    ConsultaInput,
    SicetacError,
    calcular_sicetac as calcular_sicetac_service,
    calcular_sicetac_resumen,
    _refresh_cache,
)

app = FastAPI(title="API SICETAC", version="1.5")

cors_origins = os.getenv("CORS_ORIGINS", "*")
origins = [o.strip() for o in cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/consulta")
def calcular_sicetac_endpoint(data: ConsultaInput):
    try:
        if data.resumen:
            respuesta = calcular_sicetac_resumen(data)
        else:
            respuesta = calcular_sicetac_service(data)
        return JSONResponse(content=respuesta)

    except HTTPException as ex:
        raise ex
    except SicetacError as ex:
        raise HTTPException(status_code=ex.status_code, detail=ex.detail)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/consulta_resumen")
def calcular_sicetac_resumen_endpoint(data: ConsultaInput):
    try:
        respuesta = calcular_sicetac_resumen(data)
        return JSONResponse(content=respuesta)

    except HTTPException as ex:
        raise ex
    except SicetacError as ex:
        raise HTTPException(status_code=ex.status_code, detail=ex.detail)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/refresh")
def refresh_cache():
    _refresh_cache(force=True)
    return {"status": "ok", "refreshed": True}


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
            if "variantes" in r:
                partes = []
                for v in r["variantes"]:
                    tot = v.get("totales", {})
                    partes.append(
                        f"{v.get('NOMBRE_SICE','RUTA')} (ID {v.get('ID_SICE')}): "
                        f"H2 {_format_cop(tot.get('H2'))}, H4 {_format_cop(tot.get('H4'))}, H8 {_format_cop(tot.get('H8'))}"
                    )
                texto = " | ".join(partes)
            else:
                tot = r.get("totales", {})
                texto = (
                    f"{r.get('origen')}->{r.get('destino')} {r.get('configuracion')} "
                    f"H2 {_format_cop(tot.get('H2'))}, H4 {_format_cop(tot.get('H4'))}, H8 {_format_cop(tot.get('H8'))}"
                )
            return {"texto": texto}
        else:
            r = calcular_sicetac_service(data)
            s = r.get("SICETAC", {})
            texto = (
                f"{s.get('origen')}->{s.get('destino')} {s.get('configuracion')} "
                f"total {_format_cop(s.get('total_viaje'))}"
            )
            return {"texto": texto}
    except HTTPException as ex:
        raise ex
    except SicetacError as ex:
        raise HTTPException(status_code=ex.status_code, detail=ex.detail)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)
