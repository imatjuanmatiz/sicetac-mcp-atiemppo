import hashlib
import json
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import commercial_api
from cotizador_core import load_ruleset
from main import app
from sicetac_service import SicetacError


RULESET = {
    "schema_version": 1,
    "scope_id": "mercado_colombia_tecnico",
    "ruleset_id": "market-test",
    "version": "test-1",
    "status": "published",
    "source_snapshot_id": "test-source",
    "emission_allowed": False,
    "container_tares_kg": {"40": 4100},
    "configuration_aliases": {"C2S2": "2S2", "C3S3": "3S3"},
    "body_type_aliases": {"FURGON SECO": "General - Furgon"},
    "location_aliases": {
        "ZF SANTANDER": {"municipality": "Floridablanca", "department": "Santander"},
        "ZONA FRANCA SANTANDER": {"municipality": "Floridablanca", "department": "Santander"},
        "ZONA FRANCA DE RIONEGRO": {"municipality": "Rionegro", "department": "Antioquia"},
    },
    "vehicle_equivalences": [],
    "vehicle_rules": [
        {
            "rule_id": "container_2s2", "service_code": "contenedor",
            "sicetac_configuration": "2S2", "commercial_label": "C2S2",
            "priority": 1, "min_operating_weight_kg": 17001,
            "max_operating_weight_kg": 28000, "max_cargo_kg": 22000,
            "axle_count": 4, "vehicle_model_code": "C2S2",
            "container_sizes_ft": [40], "provisional": True,
        },
        {
            "rule_id": "general_2s2", "service_code": "carga_general",
            "sicetac_configuration": "2S2", "commercial_label": "C2S2",
            "priority": 1, "min_operating_weight_kg": None,
            "max_operating_weight_kg": None, "max_cargo_kg": 22000,
            "axle_count": 4, "vehicle_model_code": "C2S2", "provisional": True,
        },
        {
            "rule_id": "general_3s3", "service_code": "carga_general",
            "sicetac_configuration": "3S3", "commercial_label": "C3S3",
            "priority": 2, "min_operating_weight_kg": None,
            "max_operating_weight_kg": None, "max_cargo_kg": 34000,
            "axle_count": 6, "vehicle_model_code": "C3S3", "provisional": True,
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

    def test_declared_vehicle_and_body_are_enough_to_request_a_reference(self):
        with patch.object(commercial_api, "load_published_market_ruleset", return_value=load_ruleset(RULESET)), patch.object(
            commercial_api, "calcular_sicetac_resumen", return_value={
                "route": "test-route", "totales": {"H4": 123},
                "resolved_route": {"codigo_dane_origen": "11001000", "codigo_dane_destino": "68276000"},
            }
        ) as sicetac:
            response = self.client.post(
                "/v1/prequotes", headers={"X-API-Key": self.api_key}, json={
                    "origen": "Bogotá", "destino": "Buenaventura",
                    "service_code": "contenedor", "container_size_ft": 40,
                    "requested_configuration": "C2S2", "peajes": False,
                    "carroceria": "Portacontenedores",
                },
            )
        self.assertEqual(response.status_code, 200)
        decision = response.json()["data"]["technical_decision"]
        self.assertEqual(decision["recommendation"]["selection_basis"], "declared_configuration")
        self.assertIsNone(decision["normalized_input"]["cargo_kg"])
        self.assertEqual(decision["normalized_input"]["weight_validation"], "not_provided")
        self.assertEqual(sicetac.call_args.args[0].vehiculo, "C2S2")
        self.assertEqual(sicetac.call_args.args[0].carroceria, "Portacontenedores")
        search = response.json()["data"]["search"]
        self.assertEqual(search["configuracion"], "C2S2")
        self.assertEqual(search["sicetac_h4"], 123)

    def test_view_search_returns_only_the_route_card(self):
        with patch.object(commercial_api, "load_published_market_ruleset", return_value=load_ruleset(RULESET)), patch.object(
            commercial_api, "calcular_sicetac_resumen", return_value={
                "nombre_sice": "BOGOTA-BUENAVENTURA",
                "mes": 202609,
                "totales": {"H2": 1, "H4": 4500000, "H8": 3},
                "valor_plaza": {"meses": [{"valor": 4100000, "mes_codigo": 202608, "mes_label": "2026-08"}]},
            }
        ):
            response = self.client.post(
                "/v1/prequotes", headers={"X-API-Key": self.api_key}, json={
                    "origen": "Bogotá", "destino": "Buenaventura",
                    "service_code": "carga_general",
                    "requested_configuration": "C2S2", "peajes": False,
                    "view": "search",
                },
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()["data"]
        self.assertEqual(set(body), {"search"})
        self.assertEqual(body["search"], {
            "ruta": "BOGOTA-BUENAVENTURA",
            "configuracion": "C2S2",
            "sicetac_corte": 202609,
            "valor_plaza": 4100000,
            "valor_plaza_corte": "2026-08",
            "horas_logisticas": 4,
            "horas_etiqueta": "H4, 4 horas logísticas",
            "sicetac": 4500000,
            "sicetac_h2": 1,
            "sicetac_h4": 4500000,
            "sicetac_h8": 3,
        })

    def test_declared_c2s2_general_cargo_quotes_without_net_weight(self):
        with patch.object(commercial_api, "load_published_market_ruleset", return_value=load_ruleset(RULESET)), patch.object(
            commercial_api, "calcular_sicetac_resumen", return_value={
                "route": "test-route", "totales": {"H2": 1, "H4": 2, "H8": 3},
            }
        ) as sicetac:
            response = self.client.post(
                "/v1/prequotes", headers={"X-API-Key": self.api_key}, json={
                    "origen": "Buenaventura", "destino": "Valledupar",
                    "service_code": "carga_general",
                    "requested_configuration": "C2S2", "peajes": False,
                },
            )
        self.assertEqual(response.status_code, 200)
        decision = response.json()["data"]["technical_decision"]
        self.assertEqual(decision["recommendation"]["sicetac_configuration"], "2S2")
        self.assertEqual(decision["recommendation"]["selection_basis"], "declared_configuration")
        self.assertIsNone(decision["normalized_input"]["cargo_kg"])
        self.assertEqual(decision["normalized_input"]["weight_validation"], "not_provided")
        self.assertEqual(sicetac.call_args.args[0].vehiculo, "C2S2")

    def test_prequote_uses_published_aliases_before_calling_sicetac(self):
        with patch.object(commercial_api, "load_published_market_ruleset", return_value=load_ruleset(RULESET)), patch.object(
            commercial_api, "calcular_sicetac_resumen", return_value={"route": "test-route", "totales": {"H4": 123}}
        ) as sicetac:
            response = self.client.post(
                "/v1/prequotes", headers={"X-API-Key": self.api_key}, json={
                    "origen": "Guadalajara de Buga", "destino": "Ibagué",
                    "service_code": "carga_general", "requested_configuration": "C3S3",
                    "axles": 3, "carroceria": "furgón seco", "peajes": False,
                },
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()["data"]
        self.assertEqual(body["technical_decision"]["recommendation"]["sicetac_configuration"], "3S3")
        self.assertEqual(body["input_resolution"]["configuration"]["sicetac_vehicle"], "C3S3")
        self.assertEqual(body["input_resolution"]["body_type"]["sicetac"], "General - Furgon")
        self.assertEqual(sicetac.call_args.args[0].vehiculo, "C3S3")
        self.assertEqual(sicetac.call_args.args[0].carroceria, "General - Furgon")

    def test_prequote_resolves_operational_destination_before_the_municipality_helper(self):
        with patch.object(commercial_api, "load_published_market_ruleset", return_value=load_ruleset(RULESET)), patch.object(
            commercial_api, "calcular_sicetac_resumen", return_value={
                "route": "test-route", "totales": {"H4": 123},
                "resolved_route": {"codigo_dane_origen": "11001000", "codigo_dane_destino": "68276000"},
            }
        ) as sicetac:
            response = self.client.post(
                "/v1/prequotes", headers={"X-API-Key": self.api_key}, json={
                    "origen": "Bogotá", "destino": "Zona Franca Santander",
                    "service_code": "carga_general", "requested_configuration": "C3S3",
                    "carroceria": "furgón seco", "peajes": False,
                },
            )
        self.assertEqual(response.status_code, 200)
        destination = response.json()["data"]["input_resolution"]["locations"]["destination"]
        self.assertEqual(destination["municipality"], "Floridablanca")
        self.assertEqual(destination["department"], "Santander")
        self.assertEqual(destination["source"], "published_ruleset_alias")
        self.assertEqual(destination["dane_code"], "68276000")
        self.assertEqual(destination["dane_source"], "catalog")
        self.assertEqual(sicetac.call_args.args[0].destino, "Floridablanca, Santander")
        self.assertIsNone(sicetac.call_args.args[0].codigo_dane_destino)

    def test_missing_route_returns_resolved_dane_and_does_not_ask_for_km(self):
        with patch.object(commercial_api, "load_published_market_ruleset", return_value=load_ruleset(RULESET)), patch.object(
            commercial_api,
            "calcular_sicetac_resumen",
            side_effect=SicetacError(
                404,
                "Ruta no registrada y no se proporcionaron distancias manuales",
                payload={
                    "reason": "OD_PAIR_NOT_IN_SICETAC_CATALOG",
                    "resolved_route": {
                        "codigo_dane_origen": "11001000",
                        "codigo_dane_destino": "68276000",
                    },
                },
            ),
        ):
            response = self.client.post(
                "/v1/prequotes", headers={"X-API-Key": self.api_key}, json={
                    "origen": "Bogotá", "destino": "Zona Franca Santander",
                    "service_code": "carga_general", "requested_configuration": "C3S3",
                    "carroceria": "furgón seco", "peajes": False,
                },
            )
        self.assertEqual(response.status_code, 404)
        detail = response.json()["detail"]
        self.assertEqual(detail["reason"], "OD_PAIR_NOT_IN_SICETAC_CATALOG")
        self.assertFalse(detail["ask_for_manual_distance"])
        self.assertEqual(detail["input_resolution"]["locations"]["destination"]["municipality"], "Floridablanca")
        self.assertEqual(detail["input_resolution"]["locations"]["destination"]["dane_code"], "68276000")
        self.assertEqual(detail["input_resolution"]["locations"]["destination"]["dane_source"], "catalog")
        self.assertEqual(detail["resolved_route"]["codigo_dane_destino"], "68276000")

    def test_missing_return_route_maps_catalog_dane_to_return_locations(self):
        with patch.object(commercial_api, "load_published_market_ruleset", return_value=load_ruleset(RULESET)), patch.object(
            commercial_api,
            "calcular_sicetac_resumen",
            side_effect=SicetacError(
                404,
                "Ruta no registrada y no se proporcionaron distancias manuales",
                payload={
                    "reason": "OD_PAIR_NOT_IN_SICETAC_CATALOG",
                    "resolved_route": {
                        "input_origen": "Floridablanca, Santander",
                        "input_destino": "Buenaventura",
                        "codigo_dane_origen": "68276000",
                        "codigo_dane_destino": "76109000",
                    },
                },
            ),
        ):
            response = self.client.post(
                "/v1/prequotes", headers={"X-API-Key": self.api_key}, json={
                    "origen": "Bogotá", "destino": "Zona Franca Santander",
                    "origen_regreso": "Zona Franca Santander", "destino_regreso": "Buenaventura",
                    "cargo_weight_value": 0, "cargo_weight_unit": "kg", "service_code": "contenedor",
                    "container_size_ft": 40, "requested_configuration": "C2S2",
                    "carroceria": "Portacontenedores", "viaje_redondo": True,
                    "tipo_contenedor": "CARGADO", "tipo_contenedor_regreso": "VACIO", "peajes": False,
                },
            )
        self.assertEqual(response.status_code, 404)
        detail = response.json()["detail"]
        self.assertFalse(detail["ask_for_manual_distance"])
        locations = detail["input_resolution"]["locations"]
        self.assertIsNone(locations["origin"]["dane_code"])
        self.assertIsNone(locations["destination"]["dane_code"])
        self.assertEqual(locations["return_origin"]["dane_code"], "68276000")
        self.assertEqual(locations["return_origin"]["dane_source"], "catalog")
        self.assertEqual(locations["return_destination"]["dane_code"], "76109000")
        self.assertEqual(locations["return_destination"]["dane_source"], "catalog")

    def test_consumer_dane_does_not_replace_the_municipality_from_equivalences(self):
        with patch.object(commercial_api, "load_published_market_ruleset", return_value=load_ruleset(RULESET)), patch.object(
            commercial_api, "calcular_sicetac_resumen", return_value={
                "route": "test-route", "totales": {"H4": 123},
                "resolved_route": {
                    "codigo_dane_origen": "11001000", "codigo_dane_destino": "68276000",
                    "destino_dane_mismatch": True,
                },
            }
        ) as sicetac:
            response = self.client.post(
                "/v1/prequotes", headers={"X-API-Key": self.api_key}, json={
                    "origen": "Bogotá", "destino": "Zona Franca Santander",
                    "codigo_dane_destino": "13001000", "service_code": "carga_general",
                    "requested_configuration": "C3S3", "carroceria": "furgón seco", "peajes": False,
                },
            )
        self.assertEqual(response.status_code, 200)
        destination = response.json()["data"]["input_resolution"]["locations"]["destination"]
        self.assertEqual(destination["municipality"], "Floridablanca")
        self.assertEqual(destination["provided_dane_code"], "13001000")
        self.assertEqual(destination["dane_code"], "68276000")
        self.assertEqual(destination["dane_source"], "catalog")
        self.assertTrue(destination["dane_mismatch"])
        self.assertEqual(sicetac.call_args.args[0].destino, "Floridablanca, Santander")
        self.assertEqual(sicetac.call_args.args[0].codigo_dane_destino, "13001000")

    def test_homonymous_location_alias_sends_municipality_and_department_to_the_helper(self):
        with patch.object(commercial_api, "load_published_market_ruleset", return_value=load_ruleset(RULESET)), patch.object(
            commercial_api, "calcular_sicetac_resumen", return_value={
                "route": "test-route", "totales": {"H4": 123},
                "resolved_route": {"codigo_dane_origen": "11001000", "codigo_dane_destino": "05615000"},
            }
        ) as sicetac:
            response = self.client.post(
                "/v1/prequotes", headers={"X-API-Key": self.api_key}, json={
                    "origen": "Bogotá", "destino": "Zona Franca de Rionegro",
                    "service_code": "carga_general", "requested_configuration": "C3S3",
                    "carroceria": "furgón seco", "peajes": False,
                },
            )
        self.assertEqual(response.status_code, 200)
        destination = response.json()["data"]["input_resolution"]["locations"]["destination"]
        self.assertEqual(destination["municipality"], "Rionegro")
        self.assertEqual(destination["department"], "Antioquia")
        self.assertEqual(destination["dane_code"], "05615000")
        self.assertEqual(destination["dane_source"], "catalog")
        self.assertEqual(sicetac.call_args.args[0].destino, "Rionegro, Antioquia")
        self.assertIsNone(sicetac.call_args.args[0].codigo_dane_destino)

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

    def test_prequote_passes_explicit_empty_return_route_as_one_combined_request(self):
        with patch.object(commercial_api, "load_published_market_ruleset", return_value=load_ruleset(RULESET)), patch.object(
            commercial_api,
            "calcular_sicetac_resumen",
            return_value={"tipo_consulta": "VIAJE_REDONDO_CONTENEDOR", "totales": {"H4": 456}},
        ) as sicetac:
            response = self.client.post(
                "/v1/prequotes", headers={"X-API-Key": self.api_key}, json={
                    "origen": "Buenaventura", "destino": "Sincelejo",
                    "origen_regreso": "Sincelejo", "destino_regreso": "Cartagena",
                    "cargo_weight_value": 23900, "cargo_weight_unit": "kg",
                    "service_code": "contenedor", "container_size_ft": 40,
                    "requested_configuration": "C2S2", "peajes": False,
                    "carroceria": "Portacontenedores", "modo_viaje": "CARGADO",
                    "viaje_redondo": True, "tipo_contenedor": "CARGADO",
                    "tipo_contenedor_regreso": "VACIO",
                },
            )
        self.assertEqual(response.status_code, 200)
        consulta = sicetac.call_args.args[0]
        self.assertTrue(consulta.viaje_redondo)
        self.assertEqual(consulta.origen_regreso, "Sincelejo")
        self.assertEqual(consulta.destino_regreso, "Cartagena")
        self.assertEqual(consulta.tipo_contenedor_regreso, "VACIO")
        self.assertEqual(response.json()["data"]["market_analysis"]["available"], False)

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
