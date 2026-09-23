"""Normalizaciones compartidas por los motores SICETAC."""

from __future__ import annotations

import re
import unicodedata
import math

import pandas as pd


# 13.6824 % comisiones + factor prestacional, 5 % administrativo y
# 3.8 % retefuente + ICA. La tasa aplica sobre costos fijos + variables.
TASA_OTROS_COSTOS_CARGADO_SICETAC = 0.224824
TASA_OTROS_COSTOS_VACIO_SICETAC = 0.221824


_CARROCERIAS_COSTO_FIJO = {
    "GENERAL": "GENERAL",
    "GENERAL ESTACAS": "GENERAL",
    "GENERAL ESTACA": "GENERAL",
    "GENERAL ESTIBAS": "ESTIBA",
    "GENERAL ESTIBA": "ESTIBA",
    "ESTIBAS": "ESTIBA",
    "GENERAL FURGON": "FURGON",
    "GENERAL PLATAFORMA": "PLATAFORMA",
    "FURGON REFRIGERADO": "FURGON REFRIGERADO",
    "PORTACONTENEDORES": "PORTACONTENEDORES",
    "GRANEL SOLIDO ESTACAS": "GRANEL SOLIDO - ESTACAS",
    "GRANEL SOLIDO ESTIBAS": "GRANEL SOLIDO - ESTIBAS",
    "GRANEL SOLIDO FURGON": "GRANEL SOLIDO - FURGON",
    "GRANEL SOLIDO PLATAFORMA": "GRANEL SOLIDO - PLATAFORMA",
    "GRANEL SOLIDO VOLCO": "GRANEL SOLIDO - VOLCO",
    "GRANEL LIQUIDO TANQUE": "GRANEL LIQUIDO - TANQUE",
}


def canonicalizar_carroceria_costos(value: str | None) -> str:
    """Convierte las etiquetas públicas del API a la clave de costos fijos."""
    text = str(value or "GENERAL").strip().upper()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"\s*-\s*", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return _CARROCERIAS_COSTO_FIJO.get(text, text)


def costo_fijo_vigente(matriz, configuracion, serie, carroceria):
    """Último costo aplicable por clave; conserva su período de origen."""
    meses = pd.to_numeric(matriz['MES'], errors='coerce')
    rows = matriz[
        (matriz['TIPO_VEHICULO'].astype(str).str.upper() == configuracion.upper())
        & (meses <= int(serie))
        & (matriz['TIPO_CARROCERIA'].astype(str).str.upper().str.strip() == carroceria)
    ]
    if rows.empty:
        raise ValueError(f'No se encontró costo fijo vigente para {configuracion} - {serie} - {carroceria}')
    mes = int(pd.to_numeric(rows['MES']).max())
    rows = rows[pd.to_numeric(rows['MES']) == mes]
    values = pd.to_numeric(rows['COSTO FIJO'], errors='coerce').unique()
    if len(values) != 1 or not math.isfinite(float(values[0])) or values[0] <= 0:
        raise ValueError(f'Costo fijo inválido o ambiguo para {configuracion} - {mes} - {carroceria}')
    return float(values[0]), mes


def detalle_terrenos(distancias, parametros, columnas):
    """Consumos y tiempos a partir de distancias, con unidades explícitas."""
    precio = float(parametros['VALOR COMBUSTIBLE GALÓN ACPM'])
    if not math.isfinite(precio) or precio <= 0:
        raise ValueError('Precio de combustible inválido')
    detalle = {}
    for terreno, raw_km in distancias.items():
        km = float(raw_km)
        velocidad = float(parametros[columnas[terreno]['velocidad']])
        rendimiento = float(parametros[columnas[terreno]['consumo']])
        if not math.isfinite(km) or km < 0:
            raise ValueError(f'Distancia inválida: {terreno}')
        if not all(math.isfinite(x) and x > 0 for x in (velocidad, rendimiento)):
            raise ValueError(f'Velocidad o rendimiento inválido: {terreno}')
        galones = km / rendimiento
        detalle[terreno] = {'km': km, 'horas': km / velocidad, 'gal': galones,
            'velocidad_km_h': velocidad, 'rendimiento_km_galon': rendimiento,
            'costo_combustible': round(galones * precio, 2)}
    if sum(d['km'] for d in detalle.values()) <= 0:
        raise ValueError('La distancia total debe ser mayor que cero')
    return detalle
