from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from sicetac_service import _carroceria_option, _lookup_sicetac_totales


class SicetacVacioLookupTests(unittest.TestCase):
    def test_all_service_options_map_to_a_vacio_body(self) -> None:
        expected = {
            "General - Estacas": "ESTACAS_VACIO",
            "General - Furgon": "FURGON_VACIO",
            "General - Estibas": "ESTIBAS_VACIO",
            "General - Plataforma": "PLATAFORMA_VACIO",
            "Portacontenedores": "PORTACONTENEDORES_VACIO",
            "Furgon Refrigerado": "FURGON_REFRIGERADO_VACIO",
            "Granel Solido - Estacas": "ESTACAS_VACIO",
            "Granel Solido - Furgon": "FURGON_VACIO",
            "Granel Solido - Volco": "VOLCO_VACIO",
            "Granel Solido - Estibas": "ESTIBAS_VACIO",
            "Granel Solido - Plataforma": "PLATAFORMA_VACIO",
            "Granel Liquido - Tanque": "TANQUE_VACIO",
        }
        for label, column in expected.items():
            with self.subTest(label=label):
                self.assertEqual(_carroceria_option(label)["vacio_column"], column)

    @patch("sicetac_service.get_sicetac_vacio_df")
    def test_vacio_uses_official_value_and_source_hourly_rate(self, get_vacio) -> None:
        get_vacio.return_value = pd.DataFrame(
            [
                {
                    "RUTASID": "154",
                    "PORTACONTENEDORES_VACIO": 2_114_019,
                    "VALORHORA_VACIO": 0,
                }
            ]
        )

        rows = _lookup_sicetac_totales(
            cod_origen_str="76109000",
            cod_destino_str="11001000",
            configuracion_lookup="2S2",
            carroceria="Portacontenedores",
            modo_viaje="VACIO",
            mes_codigo=202607,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["movilizacion"], 2_114_019)
        self.assertEqual(rows[0]["valor_hora"], 0)
        self.assertEqual(
            rows[0]["totales"],
            {"H2": 2_114_019, "H4": 2_114_019, "H8": 2_114_019},
        )
        self.assertEqual(rows[0]["lookup_method"], "lookup_vacio_oficial")
        self.assertEqual(rows[0]["lookup_column"], "portacontenedores_vacio")


if __name__ == "__main__":
    unittest.main()
