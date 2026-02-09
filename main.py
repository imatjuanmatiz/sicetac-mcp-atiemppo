from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from sicetac_service import ConsultaInput, SicetacError, calcular_sicetac

app = FastAPI(title="API SICETAC", version="1.5")

@app.post("/consulta")
def calcular_sicetac(data: ConsultaInput):
    try:
        respuesta = calcular_sicetac(data)
        return JSONResponse(content=respuesta)

    except HTTPException as ex:
        raise ex
    except SicetacError as ex:
        raise HTTPException(status_code=ex.status_code, detail=ex.detail)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)
