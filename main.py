import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from sicetac_service import (
    ConsultaInput,
    SicetacError,
    calcular_sicetac as calcular_sicetac_service,
    calcular_sicetac_resumen,
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
