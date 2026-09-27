"""Paridad de resolución: Instant (/consulta) y Core (/v1/prequotes).

Catálogo reducido del SELECT verificado el 2026-09-27 UTC; Puerto Antioquia
en variacion_2 es la actualización propuesta, aún no publicada.
"""
import hashlib
import json
import os
import unittest
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

import commercial_api
import sicetac_service
from cotizador_core import load_ruleset
from main import app
from sicetac_helper import SICETACHelper, format_dane_municipality

CATALOG = [
    {"codigo_dane": 5837000, "nombre_oficial": "TURBO", "variacion_1": "TURBO", "variacion_2": "TURBO", "departamento": "ANTIOQUIA"},
    {"codigo_dane": 5837002, "nombre_oficial": "NUEVA COLONIA", "variacion_1": "NUEVA COLONIA TURBO", "variacion_2": "PUERTO ANTIOQUIA", "departamento": "ANTIOQUIA"},
    {"codigo_dane": 8573000, "nombre_oficial": "PUERTO COLOMBIA", "variacion_1": "PUERTO COLOMBIA", "variacion_2": "PUERTO COLOMBIA", "departamento": "ATLÁNTICO"},
]
RULESET = {
    "schema_version": 1, "scope_id": "mercado_colombia_tecnico", "ruleset_id": "helper-test",
    "version": "test-only", "status": "published", "source_snapshot_id": "synthetic",
    "emission_allowed": False, "container_tares_kg": {"40": 4100},
    "configuration_aliases": {"C2S2": "2S2"}, "location_aliases": {}, "vehicle_equivalences": [],
    "vehicle_rules": [{"rule_id": "container_2s2", "service_code": "contenedor",
        "sicetac_configuration": "2S2", "commercial_label": "C2S2", "vehicle_model_code": "C2S2",
        "priority": 1, "min_operating_weight_kg": None, "max_operating_weight_kg": None,
        "max_cargo_kg": 22000, "axle_count": 4, "container_sizes_ft": [40], "provisional": True}],
}


class SharedMunicipalityHelperTests(unittest.TestCase):
    def test_full_alias_precedes_department_suffix_parsing(self):
        helper = SICETACHelper(pd.DataFrame(CATALOG))
        for text in ["Puerto Antioquia", " puerto antioquia ", "Puerto Antioquia, Antioquia", "Nueva Colonia, Turbo, Antioquia"]:
            with self.subTest(text=text):
                result = helper.resolver_municipio_input(text)
                self.assertIsNotNone(result)
                self.assertEqual(format_dane_municipality(result["codigo_dane"]), "05837002")
                self.assertEqual(result["nombre_oficial"], "NUEVA COLONIA")

    def test_helper_never_invents_the_port_alias_if_catalog_lacks_it(self):
        published = [dict(row) for row in CATALOG]
        published[1]["variacion_2"] = None
        self.assertIsNone(SICETACHelper(pd.DataFrame(published)).resolver_municipio_input("Puerto Antioquia"))

    def test_puerto_colombia_and_turbo_remain_distinct(self):
        helper = SICETACHelper(pd.DataFrame(CATALOG))
        for text, expected in [("Puerto Colombia", "08573000"), ("Turbo", "05837000"), ("Nueva Colonia", "05837002")]:
            with self.subTest(text=text):
                self.assertEqual(format_dane_municipality(helper.resolver_municipio_input(text)["codigo_dane"]), expected)

    def test_mismatched_parent_code_cannot_replace_port_center(self):
        result = SICETACHelper(pd.DataFrame(CATALOG)).resolver_municipio_input("Puerto Antioquia", "05837000")
        self.assertEqual(format_dane_municipality(result["codigo_dane"]), "05837002")
        self.assertTrue(result["codigo_hint_mismatch"])

    def test_official_name_still_beats_an_alias_on_another_row(self):
        rows = [*CATALOG, {"codigo_dane": 10000001, "nombre_oficial": "OTRO CENTRO", "variacion_1": "PUERTO COLOMBIA", "departamento": "ATLÁNTICO"}]
        result = SICETACHelper(pd.DataFrame(rows)).resolver_municipio_input("Puerto Colombia")
        self.assertEqual(format_dane_municipality(result["codigo_dane"]), "08573000")

    def test_both_endpoints_invoke_same_helper_without_motor_alias(self):
        client = TestClient(app)
        token = "synthetic-helper-test"
        env = {"SICETAC_API_ACCESS_MODE": "api_key", "SICETAC_API_CONSUMERS_DB": "false", "SICETAC_USAGE_PERSISTENCE": "false",
            "SICETAC_API_KEYS_JSON": json.dumps([{"consumer_id": "helper-test", "name": "Test", "plan": "sandbox",
                "key_hash": hashlib.sha256(token.encode()).hexdigest(), "monthly_quota": 10, "active": True}])}
        frames = (pd.DataFrame(CATALOG), pd.DataFrame([{"TIPO_VEHICULO": "C2S2"}]), pd.DataFrame([{"MES": 202609}]),
                  pd.DataFrame([{"MES": 202609}]), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
        real_resolve = SICETACHelper.resolver_municipio_input
        calls = []

        def observed(helper, name=None, code=None):
            result = real_resolve(helper, name, code)
            calls.append((name, format_dane_municipality(result["codigo_dane"]) if result else None))
            return result

        commercial_api._memory_usage.clear()
        with patch.dict(os.environ, env), patch.object(sicetac_service, "_refresh_cache"), \
             patch.object(sicetac_service, "_get_dataframes", return_value=frames), \
             patch.object(sicetac_service, "_RUTAS_INDEX", None), \
             patch.object(commercial_api, "load_published_market_ruleset", return_value=load_ruleset(RULESET)), \
             patch.object(SICETACHelper, "resolver_municipio_input", new=observed):
            base = {"origen": "Puerto Antioquia", "destino": "Puerto Colombia", "carroceria": "Portacontenedores"}
            legacy = client.post("/consulta", json={**base, "vehiculo": "C2S2", "resumen": True, "peajes": False})
            self.assertEqual(legacy.status_code, 404)
            self.assertIn("Ruta no registrada", legacy.json()["detail"])
            legacy_calls = list(calls)
            calls.clear()
            motor = client.post("/v1/prequotes", headers={"X-API-Key": token}, json={**base,
                "cargo_weight_value": 8, "cargo_weight_unit": "t", "service_code": "contenedor",
                "container_size_ft": 40, "requested_configuration": "C2S2", "peajes": False})
            self.assertEqual(motor.status_code, 404)
            detail = motor.json()["detail"]
            self.assertEqual(detail["reason"], "OD_PAIR_NOT_IN_SICETAC_CATALOG")
            self.assertEqual(detail["resolved_route"]["codigo_dane_origen"], "05837002")
            self.assertEqual(detail["input_resolution"]["locations"]["origin"]["dane_source"], "catalog")
            self.assertFalse(detail["ask_for_manual_distance"])
            self.assertEqual(legacy_calls, calls)
            self.assertEqual(calls, [("Puerto Antioquia", "05837002"), ("Puerto Colombia", "08573000")])


if __name__ == "__main__":
    unittest.main()
