"""Puente MCP stdio hacia la API comercial remota; solo necesita la clave del cliente."""
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from commercial_client import CommercialClient

mcp = FastMCP("sicetac-comercial")
read_only = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)
BRIDGE_VERSION = "1.2.1"


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


@mcp.tool(annotations=read_only)
def consultar_instrucciones_vigentes() -> dict:
    """Lee el perfil vigente sin consumir cuota. Úsalo una vez al inicio de cada sesión."""
    profile = CommercialClient.from_env().agent_profile()
    profile["client_bridge_version"] = BRIDGE_VERSION
    return profile


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
    detalle_costos: bool = False, detalle_consumo: bool = False, rutasid: str | None = None,
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
    origen: str, destino: str, cargo_weight_value: float | None = None,
    cargo_weight_unit: str | None = None,
    weight_includes_tare: bool = False,
    service_code: str = "carga_general", container_size_ft: int | None = None,
    axles: int | None = None, requested_configuration: str | None = None,
    carroceria: str = "General - Estacas", mes: int | None = None,
    peajes: bool = False, modo_viaje: str = "CARGADO",
    tipo_contenedor: str | None = None, viaje_redondo: bool = False,
    origen_regreso: str | None = None, destino_regreso: str | None = None,
    tipo_contenedor_regreso: str | None = None,
    rutasid_ida: str | None = None, rutasid_regreso: str | None = None,
    codigo_dane_origen: str | None = None, codigo_dane_destino: str | None = None,
    codigo_dane_origen_regreso: str | None = None,
    codigo_dane_destino_regreso: str | None = None,
    view: str = "search", horas_logisticas: float | None = None, rutasid: str | None = None,
) -> dict:
    """Aplica el Core técnico y luego SICETAC. Consume una unidad y no emite precio comercial.

    Para carga general sin vehículo, solicite el peso. Para contenedor, si hay
    tamaño pero no peso, cotice con el default por tamaño y marque la capacidad
    como no validada; si hay peso, selecciónelo con la tara publicada.
    Con requested_configuration búsquelo directo y calcule; el peso es
    opcional para validar capacidad, no para poder cotizar.
    Envíe weight_includes_tare cuando el peso informado ya incluya la tara del
    contenedor. El resultado search presenta referencia, plaza y capacidad neta
    de mercancía para apoyar una precotización de ventas.
    Para un contenedor vacío transportado use modo_viaje=CARGADO y
    tipo_contenedor=VACIO; para ida cargada y regreso vacío use viaje_redondo,
    tipo_contenedor=CARGADO y tipo_contenedor_regreso=VACIO. VACIO en
    modo_viaje solo significa vehículo sin carga ni contenedor.
    Nunca afirme cumplimiento de PBV legal: falta la tara real del vehículo.
    No inventa disponibilidad, margen, tarifa propia ni condiciones de negocio.
    """
    payload = {key: value for key, value in locals().items() if value is not None}
    return CommercialClient.from_env().prequote(payload)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False))
def detalle_costos_sicetac(
    origen: str, destino: str, vehiculo: str, carroceria: str = "GENERAL",
    mes: int | None = None, rutasid: str | None = None,
    horas_logisticas: float = 4, modo_viaje: str = "CARGADO",
) -> dict:
    """Ejecuta el modelo completo: galones, tiempos, rotaciones, fijos, variables y otros.

    Conserve ruta, variante, vehículo, carrocería, mes y horas de la consulta.
    Muestre como único total del viaje sicetac_tradicional.total_viaje;
    no presente el total interno del modelo. Consume una unidad.
    Origen=destino usa 30 km ondulados y devuelve estimado=true.
    """
    payload = {key: value for key, value in locals().items() if value is not None}
    payload.update(resumen=False, detalle_costos=True)
    return CommercialClient.from_env().quote(payload)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False))
def detalle_consumo_sicetac(
    origen: str, destino: str, vehiculo: str, carroceria: str = "GENERAL",
    mes: int | None = None, rutasid: str | None = None,
    horas_logisticas: float = 4, modo_viaje: str = "CARGADO",
) -> dict:
    """Devuelve galones y costo de combustible por terreno y total desde el modelo.

    Muestre como único total del viaje sicetac_tradicional.total_viaje.
    Conserve el contexto de la ruta. Consume una unidad; no reintente automáticamente.
    """
    payload = {key: value for key, value in locals().items() if value is not None}
    payload.update(resumen=False, detalle_consumo=True)
    return CommercialClient.from_env().quote(payload)


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
