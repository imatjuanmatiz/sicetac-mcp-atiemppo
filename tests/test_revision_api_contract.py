"""Regresiones para los hallazgos de la revisión API del 16 de octubre."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

import commercial_api
import main
import sicetac_service as service
from cotizador_core import load_ruleset
import test_prequote_api


class RevisionApiContractTests(unittest.TestCase):
    def test_search_card_derives_zero_fractional_and_long_hours_from_lookup(self):
        reference = {
            "origen": "A",
            "destino": "B",
            "mes": 202610,
            "totales": {"H2": 1200, "H4": 1400, "H8": 1800},
            "detalle_lookup": {"rutasid": "93", "movilizacion": 1000, "valor_hora": 100},
            "toneladas_configuracion": 20,
        }
        for hours, expected in ((0, 1000), (2.5, 1250), (6, 1600), (48, 5800)):
            with self.subTest(hours=hours):
                search = commercial_api._search_card(reference, None, None, hours)
                self.assertEqual(search["sicetac"], expected)
                self.assertEqual(search["horas_logisticas"], hours)
                self.assertEqual(search["sicetac_h2"], 1200)
                self.assertEqual(search["sicetac_h4"], 1400)
                self.assertEqual(search["sicetac_h8"], 1800)
                self.assertEqual(search["sicetac_por_tonelada"], expected / 20)

        fixture = test_prequote_api.PrequoteApiTests(methodName="test_private_prequote_runs_core_then_sicetac")
        fixture.setUp()
        try:
            with patch.object(commercial_api, "load_published_market_ruleset", return_value=load_ruleset(test_prequote_api.RULESET)), patch.object(
                commercial_api, "calcular_sicetac_resumen", return_value=reference,
            ):
                for hours, expected in ((0, 1000), (2.5, 1250), (6, 1600), (48, 5800)):
                    response = fixture.client.post("/v1/prequotes", headers={"X-API-Key": fixture.api_key}, json={
                        "origen": "A", "destino": "B", "requested_configuration": "C3S3",
                        "view": "search", "horas_logisticas": hours,
                    })
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json()["data"]["search"]["sicetac"], expected)
        finally:
            fixture.doCleanups()

    def test_round_trip_selects_requested_secondary_route_on_both_legs(self):
        def promoted(rows):
            return service._promover_variante_principal({"variantes": rows})

        ida = promoted([
            {"RUTASID": "93", "NOMBRE_SICE": "A-B principal", "totales": {"H2": 80, "H4": 100, "H8": 140}},
            {"RUTASID": "94", "NOMBRE_SICE": "A-B alternativa", "totales": {"H2": 180, "H4": 200, "H8": 240}},
        ])
        regreso = promoted([
            {"RUTASID": "95", "NOMBRE_SICE": "B-A principal", "totales": {"H2": 280, "H4": 300, "H8": 340}},
            {"RUTASID": "96", "NOMBRE_SICE": "B-A alternativa", "totales": {"H2": 380, "H4": 400, "H8": 440}},
        ])
        data = service.ConsultaInput(
            origen="A", destino="B", origen_regreso="B", destino_regreso="A",
            carroceria="Portacontenedores", modo_viaje="CARGADO", viaje_redondo=True,
            tipo_contenedor="CARGADO", tipo_contenedor_regreso="VACIO",
            rutasid_ida="94", rutasid_regreso="96",
        )
        with patch.object(service, "calcular_sicetac_resumen", side_effect=[ida, regreso]):
            result = service._calcular_viaje_redondo_contenedor(data)

        self.assertEqual(result["ida"]["rutasid"], "94")
        self.assertEqual(result["regreso"]["rutasid"], "96")
        self.assertEqual(result["totales"]["H4"], 600)
        card = commercial_api._search_card(result, None, None, 4)
        self.assertEqual(card["rutasid_ida"], "94")
        self.assertEqual(card["rutasid_regreso"], "96")
        self.assertEqual(card["sicetac"], 600)

    def test_market_comparison_uses_the_sicetac_reference_shown_to_user(self):
        reference = {
            "mes": 202609,
            "totales": {"H4": 2000},
            "sicetac_tradicional": {"mes": 202609, "totales": {"H4": 1400}, "estimado": False},
            "valor_plaza": {"meses": [{"mes_codigo": 202609, "valor": 2000}]},
        }
        search = commercial_api._search_card(reference, None, None, 4)
        comparison = commercial_api._market_analysis(reference)["comparison_to_sicetac_h4"]
        self.assertEqual(search["sicetac"], 1400)
        self.assertEqual(comparison["sicetac_h4"], search["sicetac"])
        self.assertEqual(comparison["difference_cop"], 600)

    def test_estimated_fallback_provenance_is_preserved_in_search_card(self):
        reference = {
            "totales": {"H2": 1200, "H4": 1400, "H8": 1800},
            "sicetac_tradicional": {
                "estimado": True,
                "mes": 202609,
                "totales": {"H2": 1200, "H4": 1400, "H8": 1800, "H6": 1600},
            },
        }
        search = commercial_api._search_card(reference, None, None, 6)
        self.assertTrue(search["estimado"])
        self.assertEqual(search["sicetac"], 1600)

        summary_only = commercial_api._search_card(
            {"metodo": "modelo_completo", "estimado": False, "totales": {"H4": 1400}},
            None,
            None,
            4,
        )
        self.assertTrue(summary_only["estimado"])

    def test_round_trip_text_uses_each_leg_identity_and_combined_totals(self):
        result = {
            "tipo_consulta": "VIAJE_REDONDO_CONTENEDOR",
            "totales": {"H2": 500, "H4": 600, "H8": 800},
            "ida": {
                "origen": "A", "destino": "B", "rutasid": "93", "nombre_sice": "A-B",
                "totales": {"H2": 100, "H4": 200, "H8": 300},
            },
            "regreso": {
                "origen": "B", "destino": "A", "rutasid": "94", "nombre_sice": "B-A",
                "totales": {"H2": 400, "H4": 400, "H8": 500},
            },
        }
        client = TestClient(main.app)
        with patch.object(main, "calcular_sicetac_resumen", return_value=result):
            response = client.post("/consulta_texto", json={
                "origen": "A", "destino": "B", "vehiculo": "C3S3",
                "carroceria": "Portacontenedores", "viaje_redondo": True, "resumen": True,
            })
        self.assertEqual(response.status_code, 200, response.text)
        text = response.json()["texto"]
        self.assertIn("Ida A-B (ID 93)", text)
        self.assertIn("Regreso B-A (ID 94)", text)
        self.assertIn("Total viaje redondo: H2 $500, H4 $600, H8 $800", text)
        self.assertNotIn("None->None", text)

    def test_trip_mode_is_trimmed_and_invalid_modes_are_rejected(self):
        self.assertEqual(service.ConsultaInput(modo_viaje=" VACIO ").modo_viaje, "VACIO")
        self.assertEqual(commercial_api.PrequoteInput(modo_viaje=" cargado ").modo_viaje, "CARGADO")
        with self.assertRaises(ValidationError):
            service.ConsultaInput(modo_viaje="INVALIDO")
        with self.assertRaises(ValidationError):
            commercial_api.PrequoteInput(modo_viaje="INVALIDO")
        response = TestClient(main.app).post("/consulta", json={"modo_viaje": "INVALIDO"})
        self.assertEqual(response.status_code, 422)

    def test_non_finite_manual_amounts_are_rejected_before_calculation(self):
        for field in ("valor_peaje_manual", "valor_peajes_manual", "tarifa_standby"):
            for value in ("Infinity", "NaN", float("inf"), float("-inf")):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValidationError):
                        service.ConsultaInput(**{field: value})
        response = TestClient(main.app).post(
            "/consulta",
            json={"origen": "A", "destino": "B", "valor_peaje_manual": "Infinity"},
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
