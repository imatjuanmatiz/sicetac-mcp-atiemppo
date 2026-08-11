"""Normalizaciones compartidas por los motores SICETAC."""

from __future__ import annotations

import re
import unicodedata


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
