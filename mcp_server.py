from __future__ import annotations

from sicetac_service import (
    ConsultaInput,
    SicetacError,
    adjuntar_peajes_a_respuesta,
    calcular_sicetac,
    calcular_sicetac_resumen,
    consulta_solicita_peajes,
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
    tipo_contenedor: str | None = None,
    viaje_redondo: bool = False,
    tipo_contenedor_regreso: str | None = None,
    rutasid_ida: str | None = None,
    rutasid_regreso: str | None = None,
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
    modo_aumento: bool = False,
    resumen: bool = True,
    peajes: bool = False,
    incluir_peajes: bool = False,
    detalle_peajes: bool = False,
):
    """
    Calcula el modelo SICETAC usando datos de Supabase.
    Si no se pasa MES, se usa el más reciente en parametros_vigentes.
    Con modo_aumento=true agrega el porcentaje de variación de H4 y H8 frente
    a diciembre de 2025; el cliente debe reenviar el indicador mientras esté
    activo y usar false cuando el usuario indique "modo aumento off".
    """
    try:
        payload = ConsultaInput(
            origen=origen,
            destino=destino,
            vehiculo=vehiculo,
            mes=mes,
            carroceria=carroceria,
            tipo_contenedor=tipo_contenedor,
            viaje_redondo=viaje_redondo,
            tipo_contenedor_regreso=tipo_contenedor_regreso,
            rutasid_ida=rutasid_ida,
            rutasid_regreso=rutasid_regreso,
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
            modo_aumento=modo_aumento,
            resumen=resumen,
            peajes=peajes,
            incluir_peajes=incluir_peajes,
            detalle_peajes=detalle_peajes,
        )
        if resumen:
            respuesta = calcular_sicetac_resumen(payload)
        else:
            respuesta = calcular_sicetac(payload)
        if consulta_solicita_peajes(payload):
            respuesta = adjuntar_peajes_a_respuesta(respuesta, vehiculo)
        return respuesta
    except SicetacError as ex:
        return {"error": ex.detail, "status_code": ex.status_code}


if __name__ == "__main__":
    mcp.run()
