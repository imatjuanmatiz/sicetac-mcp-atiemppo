from __future__ import annotations

from sicetac_service import (
    ConsultaInput,
    SicetacError,
    calcular_sicetac,
    calcular_sicetac_resumen,
)

try:
    from mcp.server.fastmcp import FastMCP
except Exception as e:
    raise RuntimeError(
        "No se pudo importar el SDK MCP. Instala el paquete 'mcp' en requirements.txt."
    ) from e


mcp = FastMCP("sicetac")


@mcp.tool()
def calcular_sicetac_tool(
    origen: str,
    destino: str,
    vehiculo: str = "C3S3",
    mes: int | None = None,
    carroceria: str = "GENERAL",
    valor_peaje_manual: float = 0.0,
    horas_logisticas: float | None = None,
    horas_logisticas_personalizadas: float | None = None,
    tarifa_standby: float = 150000.0,
    km_plano: float = 0,
    km_ondulado: float = 0,
    km_montañoso: float = 0,
    km_urbano: float = 0,
    km_despavimentado: float = 0,
    modo_viaje: str = "CARGADO",
    modo_tiempos_logisticos: bool = False,
    resumen: bool = True,
):
    """
    Calcula el modelo SICETAC usando datos de Supabase.
    Si no se pasa MES, se usa el más reciente en parametros_vigentes.
    """
    try:
        payload = ConsultaInput(
            origen=origen,
            destino=destino,
            vehiculo=vehiculo,
            mes=mes,
            carroceria=carroceria,
            valor_peaje_manual=valor_peaje_manual,
            horas_logisticas=horas_logisticas,
            horas_logisticas_personalizadas=horas_logisticas_personalizadas,
            tarifa_standby=tarifa_standby,
            km_plano=km_plano,
            km_ondulado=km_ondulado,
            km_montañoso=km_montañoso,
            km_urbano=km_urbano,
            km_despavimentado=km_despavimentado,
            modo_viaje=modo_viaje,
            modo_tiempos_logisticos=modo_tiempos_logisticos,
            resumen=resumen,
        )
        if resumen:
            return calcular_sicetac_resumen(payload)
        return calcular_sicetac(payload)
    except SicetacError as ex:
        return {"error": ex.detail, "status_code": ex.status_code}


if __name__ == "__main__":
    mcp.run()
