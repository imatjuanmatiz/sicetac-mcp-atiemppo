"""Puente MCP stdio hacia la API comercial remota; solo necesita la clave del cliente."""
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from commercial_client import CommercialClient

mcp = FastMCP("sicetac-comercial")
read_only = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)


@mcp.tool(annotations=read_only)
def listar_vehiculos() -> dict:
    """Obtiene códigos, descripciones y ejes. No certifica capacidad útil ni disponibilidad de flota."""
    return CommercialClient.from_env().vehicles()


@mcp.tool(annotations=read_only)
def listar_carrocerias() -> dict:
    """Obtiene etiquetas exactas de carrocería y sus relaciones con series de costo."""
    return CommercialClient.from_env().body_types()


@mcp.tool(annotations=read_only)
def listar_municipios() -> dict:
    """Obtiene municipios, departamentos, aliases y códigos para aclarar origen y destino."""
    return CommercialClient.from_env().municipalities()


@mcp.tool(annotations=read_only)
def consultar_consumo() -> dict:
    """Consulta uso y cuota del consumidor. No consume una cotización."""
    return CommercialClient.from_env().usage()


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False))
def cotizar_sicetac(
    origen: str, destino: str, vehiculo: str, carroceria: str,
    mes: int | None = None, resumen: bool = True,
    codigo_dane_origen: str | None = None, codigo_dane_destino: str | None = None,
    modo_viaje: str = "CARGADO", tipo_contenedor: str | None = None,
    viaje_redondo: bool = False, tipo_contenedor_regreso: str | None = None,
    rutasid_ida: str | None = None, rutasid_regreso: str | None = None,
    horas_logisticas: float | None = None, peajes: bool = False,
    detalle_peajes: bool = False, modo_aumento: bool = False,
) -> dict:
    """Consulta SICETAC por API. Consume una unidad; no reintentar automáticamente.

    Elige vehiculo y carroceria del catálogo. No presupone capacidad útil.
    Comprueba data.resolved_route, periodo y variantes antes de recomendar.
    Devuelve data y meta sin modificar los cálculos ni su trazabilidad.
    Para códigos DANE, envía los códigos como texto y los nombres vacíos.
    """
    payload = {key: value for key, value in locals().items() if value is not None}
    return CommercialClient.from_env().quote(payload)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False))
def precotizar_transporte(
    origen: str, destino: str, cargo_weight_value: float, cargo_weight_unit: str,
    service_code: str = "carga_general", container_size_ft: int | None = None,
    axles: int | None = None, requested_configuration: str | None = None,
    carroceria: str = "General - Estacas", mes: int | None = None,
    peajes: bool = True,
) -> dict:
    """Aplica el Core técnico y luego SICETAC. Consume una unidad y no emite precio comercial.

    El agente debe explicar PBV, SICE y advertencias como referencia técnica.
    No inventa disponibilidad, margen, tarifa propia ni condiciones de negocio.
    """
    payload = {key: value for key, value in locals().items() if value is not None}
    return CommercialClient.from_env().prequote(payload)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False))
def registrar_termino_para_revision(
    raw_expression: str, entity_type: str, normalized_expression: str | None = None,
    suggested_value: str | None = None,
) -> dict:
    """Registra un término como candidato. No modifica automáticamente reglas ni equivalencias."""
    payload = {key: value for key, value in locals().items() if value is not None}
    return CommercialClient.from_env().record_term_observation(payload)


if __name__ == "__main__":
    mcp.run(transport="stdio")
