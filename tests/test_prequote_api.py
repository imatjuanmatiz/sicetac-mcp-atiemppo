import hashlib
import json
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import commercial_api
from cotizador_core import load_ruleset
from main import app


RULESET = {
    "schema_version": 1,
    "scope_id": "mercado_colombia_tecnico",
    "ruleset_id": "market-test",
    "version": "test-1",
    "status": "published",
    "source_snapshot_id": "test-source",
    "emission_allowed": False,
    "container_tares_kg": {"40": 4100},
    "configuration_aliases": {"C2S2": "2S2"},
    "vehicle_equivalences": [],
    "vehicle_rules": [
        {
            "rule_id": "container_2s2", "service_code": "contenedor",
            "sicetac_configuration": "2S2", "commercial_label": "C2S2",
            "priority": 1, "min_operating_weight_kg": 17001,
            "max_operating_weight_kg": 28000, "max_cargo_kg": 22000,
            "axle_count": 4, "vehicle_model_code": "C2S2",
            "container_sizes_ft": [40], "provisional": True,
        }
    ],
}


class PrequoteApiTests(unittest.TestCase):
    def setUp(self):
        commercial_api._memory_usage.clear()
        self.client = TestClient(app)
        self.api_key = "prequote-test-key"
        key_hash = hashlib.sha256(self.api_key.encode()).hexdigest()
        self.env = {
            "SICETAC_API_ACCESS_MODE": "api_key",
            "SICETAC_API_KEYS_JSON": json.dumps([{
                "consumer_id": "test-consumer", "name": "Test", "plan": "sandbox",
                "key_hash": key_hash, "monthly_quota": 10, "active": True,
            }]),
            "SICETAC_API_CONSUMERS_DB": "false",
            "SICETAC_USAGE_PERSISTENCE": "false",
        }
        self.patch_env = patch.dict(os.environ, self.env, clear=False)
        self.patch_env.start()
        self.addCleanup(self.patch_env.stop)

    def test_private_prequote_runs_core_then_sicetac(self):
        with patch.object(commercial_api, "load_published_market_ruleset", return_value=load_ruleset(RULESET)), patch.object(
            commercial_api, "calcular_sicetac_resumen", return_value={"route": "test-route", "totales": {"H8": 123}}
        ) as sicetac:
            response = self.client.post(
                "/v1/prequotes", headers={"X-API-Key": self.api_key}, json={
                    "origen": "Bogotá", "destino": "Medellín", "cargo_weight_value": 18000,
                    "cargo_weight_unit": "kg", "service_code": "contenedor",
                    "container_size_ft": 40, "axles": 4, "peajes": False,
                },
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["data"]["technical_decision"]["recommendation"]["sicetac_configuration"], "2S2")
        self.assertEqual(body["data"]["sicetac_reference"]["totales"]["H8"], 123)
        self.assertFalse(body["data"]["commercial"]["emission_allowed"])
        self.assertEqual(sicetac.call_args.args[0].vehiculo, "C2S2")

    def test_empty_container_is_forwarded_as_loaded_container_series(self):
        with patch.object(commercial_api, "load_published_market_ruleset", return_value=load_ruleset(RULESET)), patch.object(
            commercial_api, "calcular_sicetac_resumen", return_value={
                "route": "test-route", "totales": {"H4": 123},
                "valor_plaza_no_aplica": "CONTENEDOR_VACIO",
            }
        ) as sicetac:
            response = self.client.post(
                "/v1/prequotes", headers={"X-API-Key": self.api_key}, json={
                    "origen": "Bogotá", "destino": "Buenaventura", "cargo_weight_value": 0,
                    "cargo_weight_unit": "kg", "service_code": "contenedor",
                    "container_size_ft": 40, "axles": 4, "peajes": False,
                    "carroceria": "Portacontenedores", "modo_viaje": "CARGADO",
                    "tipo_contenedor": "VACIO",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(sicetac.call_args.args[0].modo_viaje, "CARGADO")
        self.assertEqual(sicetac.call_args.args[0].tipo_contenedor, "VACIO")
        self.assertEqual(
            response.json()["data"]["market_analysis"]["reason"],
            "CONTAINER_EMPTY_NO_MARKET_PROXY",
        )

    def test_prequote_exposes_observed_market_as_a_separate_analysis_layer(self):
        sicetac_result = {
            "mes": 202609,
            "totales": {"H4": 3_000_000},
            "valor_plaza": {
                "route_code": "11001000-76109000",
                "configuracion_analisis": "2S2",
                "tipo_carga_label": "Carga normal",
                "promedio_ultimos_meses": 3_250_000,
                "meses": [{
                    "mes_codigo": 202607,
                    "mes_label": "2026-07",
                    "valor": 3_300_000,
                    "fuente": "rndc_proxy",
                    "tipo_carga_usado": "Carga normal",
                }],
            },
        }
        with patch.object(commercial_api, "load_published_market_ruleset", return_value=load_ruleset(RULESET)), patch.object(
            commercial_api, "calcular_sicetac_resumen", return_value=sicetac_result
        ):
            response = self.client.post(
                "/v1/prequotes", headers={"X-API-Key": self.api_key}, json={
                    "origen": "Bogotá", "destino": "Buenaventura", "cargo_weight_value": 18000,
                    "cargo_weight_unit": "kg", "service_code": "contenedor",
                    "container_size_ft": 40, "peajes": False,
                },
            )
        analysis = response.json()["data"]["market_analysis"]
        self.assertTrue(analysis["available"])
        self.assertEqual(analysis["latest_observation"]["mes_codigo"], 202607)
        self.assertEqual(analysis["comparison_to_sicetac_h4"]["difference_cop"], 300000)
        self.assertFalse(analysis["comparison_to_sicetac_h4"]["same_cutoff"])

    def test_term_feedback_is_pending_and_never_publishes_rules(self):
        with patch.object(commercial_api, "record_term_observation") as observation:
            response = self.client.post(
                "/v1/feedback/terms", headers={"X-API-Key": self.api_key},
                json={"raw_expression": "camión turbo", "entity_type": "vehicle_alias"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "pending_review")
        self.assertEqual(observation.call_args.kwargs["raw_expression"], "camión turbo")

    def test_public_consulta_never_invokes_market_core(self):
        with patch.object(commercial_api, "load_published_market_ruleset", side_effect=AssertionError("public route used core")), patch(
            "main.calcular_sicetac_resumen", return_value={"legacy": True}
        ):
            response = self.client.post("/consulta", json={"origen": "A", "destino": "B", "resumen": True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"legacy": True})


if __name__ == "__main__":
    unittest.main()
