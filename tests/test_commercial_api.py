import hashlib
import json
import os
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import pandas as pd

from fastapi.testclient import TestClient

import commercial_api
from cotizador_core import load_ruleset
from main import app


class CommercialApiTests(unittest.TestCase):
    def setUp(self):
        commercial_api._memory_usage.clear()
        self.client = TestClient(app)
        self.api_key = "test-commercial-key"
        self.key_hash = hashlib.sha256(self.api_key.encode()).hexdigest()
        self.consumer_config = json.dumps(
            [
                {
                    "consumer_id": "test-consumer",
                    "name": "Test consumer",
                    "plan": "sandbox",
                    "key_hash": self.key_hash,
                    "monthly_quota": 1,
                    "active": True,
                }
            ]
        )
        self.env_patch = patch.dict(os.environ, {
            "SICETAC_API_ACCESS_MODE": "api_key",
            "SICETAC_API_KEYS_JSON": self.consumer_config,
            "SICETAC_API_CONSUMERS_DB": "false",
            "SICETAC_USAGE_PERSISTENCE": "false",
        })
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.network_guard = patch.object(commercial_api, "get_client", side_effect=AssertionError("Acceso real a datos no permitido en tests"))
        self.network_guard.start()
        self.addCleanup(self.network_guard.stop)

    def test_health_is_public(self):
        with patch.dict(os.environ, {"SICETAC_API_ACCESS_MODE": "api_key"}, clear=False):
            response = self.client.get("/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["version"], "v1")

    def test_agent_profile_is_authenticated_and_does_not_charge(self):
        ruleset = load_ruleset({
            "schema_version": 1, "scope_id": "mercado_colombia_tecnico",
            "ruleset_id": "profile-test", "version": "test-1", "status": "published",
            "source_snapshot_id": "test-source", "emission_allowed": False,
            "container_tares_kg": {"20": 2300}, "configuration_aliases": {},
            "vehicle_equivalences": [], "vehicle_rules": [{
                "rule_id": "container_2s2", "service_code": "contenedor",
                "sicetac_configuration": "2S2", "commercial_label": "C2S2", "priority": 1,
                "min_operating_weight_kg": None, "max_operating_weight_kg": None,
                "max_cargo_kg": 22000, "axle_count": 4, "container_sizes_ft": [20],
                "provisional": True,
            }],
        })
        with patch.object(commercial_api, "load_published_market_ruleset", return_value=ruleset):
            missing = self.client.get("/v1/agent-profile")
            response = self.client.get("/v1/agent-profile", headers={"X-API-Key": self.api_key})
            usage = self.client.get("/v1/usage", headers={"X-API-Key": self.api_key})
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["ruleset"]["version"], "test-1")
        self.assertEqual(response.json()["input_policy"]["container"]["automatic_configuration_by_size_ft"]["20"], "2S2")
        self.assertEqual(response.json()["output_policy"]["view"], "search")
        self.assertIn("data.search", response.json()["output_policy"]["present"])
        self.assertFalse(response.json()["quota"]["consumes_units"])
        self.assertEqual(usage.json()["used"], 0)

    def test_quote_requires_valid_key_and_reports_usage(self):
        env = {
            "SICETAC_API_ACCESS_MODE": "api_key",
            "SICETAC_API_KEYS_JSON": self.consumer_config,
            "SICETAC_USAGE_PERSISTENCE": "false",
        }
        with patch.dict(os.environ, env, clear=False):
            unauthorized = self.client.post("/v1/quotes", json={"origen": "A", "destino": "B"})
            self.assertEqual(unauthorized.status_code, 401)

            with patch.object(
                commercial_api,
                "calcular_sicetac_resumen",
                return_value={"totales": {"H2": 10, "H4": 20, "H8": 30}},
            ):
                response = self.client.post(
                    "/v1/quotes",
                    headers={"X-API-Key": self.api_key},
                    json={"origen": "A", "destino": "B", "vehiculo": "C3S3"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["totales"]["H8"], 30)
        self.assertEqual(response.json()["meta"]["consumer_id"], "test-consumer")
        self.assertEqual(response.json()["meta"]["monthly_usage"], 1)

    def test_quota_is_enforced(self):
        env = {
            "SICETAC_API_ACCESS_MODE": "api_key",
            "SICETAC_API_KEYS_JSON": self.consumer_config,
            "SICETAC_USAGE_PERSISTENCE": "false",
        }
        with patch.dict(os.environ, env, clear=False), patch.object(
            commercial_api,
            "calcular_sicetac_resumen",
            return_value={"totales": {"H2": 1, "H4": 2, "H8": 3}},
        ):
            payload = {"origen": "A", "destino": "B"}
            first = self.client.post("/v1/quotes", headers={"X-API-Key": self.api_key}, json=payload)
            second = self.client.post("/v1/quotes", headers={"X-API-Key": self.api_key}, json=payload)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)

    def test_expired_key_is_rejected_before_calculation(self):
        expired = json.dumps([{
            "consumer_id": "expired", "name": "Expired", "plan": "sandbox",
            "key_hash": self.key_hash, "monthly_quota": 1, "active": True,
            "expires_at": "2020-01-01T00:00:00Z",
        }])
        with patch.dict(os.environ, {"SICETAC_API_KEYS_JSON": expired}, clear=False), patch.object(
            commercial_api, "calcular_sicetac_resumen", side_effect=AssertionError("expired key calculated")
        ):
            response = self.client.post(
                "/v1/quotes", headers={"X-API-Key": self.api_key},
                json={"origen": "A", "destino": "B", "vehiculo": "C3S3"},
            )
        self.assertEqual(response.status_code, 401)

    def test_persistent_reservation_uses_atomic_rpc(self):
        calls = []

        class Database:
            def rpc(self, name, params):
                calls.append(("rpc", name, params))
                self.rpc_name = name
                return self
            def table(self, name):
                calls.append(("table", name))
                return self
            def update(self, values):
                calls.append(("update", values))
                return self
            def eq(self, *args):
                return self
            def execute(self):
                if getattr(self, "rpc_name", None) == "reserve_api_usage":
                    self.rpc_name = None
                    return SimpleNamespace(data=[{"month_key": "2026-09", "monthly_usage": 1, "monthly_quota": 3}])
                return SimpleNamespace(data=[])

        with patch.dict(os.environ, {"SICETAC_USAGE_PERSISTENCE": "true"}, clear=False), patch.object(
            commercial_api, "get_client", return_value=Database()
        ), patch.object(
            commercial_api, "calcular_sicetac_resumen", return_value={"totales": {"H8": 3}}
        ):
            response = self.client.post(
                "/v1/quotes", headers={"X-API-Key": self.api_key},
                json={"origen": "A", "destino": "B", "vehiculo": "C3S3"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls[0][1], "reserve_api_usage")
        self.assertTrue(any(call[0] == "update" for call in calls))

    def test_admin_operations_are_closed_without_token(self):
        with patch.dict(os.environ, {"SICETAC_ADMIN_TOKEN": "admin-secret"}, clear=False), patch("main._refresh_cache"):
            missing = self.client.post("/refresh")
            valid = self.client.post("/refresh", headers={"X-Admin-Token": "admin-secret"})
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(valid.status_code, 200)

    def test_consumer_from_database_accepts_valid_key(self):
        record = json.loads(self.consumer_config)[0]

        class Query:
            def table(self, name):
                return self
            def select(self, columns):
                self.columns = columns.split(",")
                return self
            def eq(self, *args):
                return self
            def limit(self, value):
                return self
            def execute(self):
                # Simula la proyección de SELECT, no devuelve columnas omitidas.
                return SimpleNamespace(data=[{key: record[key] for key in self.columns if key in record}])

        with patch.dict(os.environ, {"SICETAC_API_KEYS_JSON": "[]", "SICETAC_API_CONSUMERS_DB": "true"}), patch.object(
            commercial_api, "get_client", return_value=Query()
        ):
            response = self.client.get("/v1/usage", headers={"Authorization": f"Bearer {self.api_key}"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["consumer_id"], "test-consumer")
        self.assertNotIn("key_hash", response.text)

    def test_municipality_catalog_is_authenticated_and_does_not_charge(self):
        catalog = pd.DataFrame([{
            "codigo_dane": 5001000.0, "nombre_oficial": "MEDELLIN",
            "departamento": "ANTIOQUIA", "variacion_1": "Medellín",
            "private_column": "must-not-leak",
        }])
        with patch.object(commercial_api, "get_table_df", return_value=catalog):
            missing = self.client.get("/v1/catalog/municipalities")
            response = self.client.get("/v1/catalog/municipalities", headers={"X-API-Key": self.api_key})
            usage = self.client.get("/v1/usage", headers={"X-API-Key": self.api_key})
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["codigo_dane"], "05001000")
        self.assertNotIn("private_column", response.text)
        self.assertEqual(usage.json()["used"], 0)

    def test_empty_municipality_catalog(self):
        with patch.object(commercial_api, "get_table_df", return_value=pd.DataFrame()):
            response = self.client.get("/v1/catalog/municipalities", headers={"X-API-Key": self.api_key})
        self.assertEqual(response.json(), {"items": []})


if __name__ == "__main__":
    unittest.main()
