import unittest
import json
from pathlib import Path

from cotizador_core import evaluate_quote, load_ruleset


RULESET = {
    "schema_version": 1,
    "scope_id": "mercado_colombia_tecnico",
    "ruleset_id": "container-defaults-test",
    "version": "test-1",
    "status": "published",
    "source_snapshot_id": "test-source",
    "emission_allowed": False,
    "container_tares_kg": {"20": 2300, "40": 4100},
    "configuration_aliases": {"C2": "2", "C2S2": "2S2"},
    "vehicle_equivalences": [],
    "vehicle_rules": [
        {
            "rule_id": "container_2", "service_code": "contenedor",
            "sicetac_configuration": "2", "commercial_label": "C2M10",
            "priority": 1, "min_operating_weight_kg": 0,
            "max_operating_weight_kg": 10500, "max_cargo_kg": 9000,
            "axle_count": 2, "container_sizes_ft": [20],
            "requires_explicit_request": True, "provisional": True,
        },
        {
            "rule_id": "container_2s2", "service_code": "contenedor",
            "sicetac_configuration": "2S2", "commercial_label": "C2S2",
            "priority": 10, "min_operating_weight_kg": None,
            "max_operating_weight_kg": None, "max_cargo_kg": 22000,
            "axle_count": 4, "container_sizes_ft": [20, 40], "provisional": True,
        },
    ],
}


class ContainerDefaultTests(unittest.TestCase):
    def setUp(self):
        self.ruleset = load_ruleset(RULESET)

    def quote(self, **updates):
        request = {
            "scope_id": "mercado_colombia_tecnico", "request_id": "test-request",
            "cargo_weight_value": 8, "cargo_weight_unit": "t",
            "service_code": "contenedor", "container_size_ft": 20,
        }
        request.update(updates)
        return evaluate_quote(request, self.ruleset)

    def test_container_20_defaults_to_c2s2_even_when_c2_is_lighter(self):
        result = self.quote()
        recommendation = result["recommendation"]
        self.assertEqual(recommendation["sicetac_configuration"], "2S2")
        self.assertEqual(recommendation["selection"], "automatic_operational_default")
        self.assertIsNone(recommendation["pbv_compatible"])
        self.assertEqual(recommendation["pbv_assessment"], "requires_vehicle_tare")
        self.assertEqual(result["normalized_input"]["load_and_container_weight_kg"], 10300)
        self.assertIn("C2S2 es el mínimo técnico operativo", result["warnings"][-1])

    def test_smaller_container_vehicle_requires_explicit_request(self):
        result = self.quote(requested_configuration="C2")
        self.assertEqual(result["recommendation"]["sicetac_configuration"], "2")
        self.assertEqual(result["recommendation"]["selection"], "explicit")
        self.assertTrue(result["recommendation"]["requires_explicit_request"])

    def test_general_and_suelta_are_normalized_without_container_tare(self):
        general_ruleset = load_ruleset({
            **RULESET,
            "vehicle_rules": [{
                "rule_id": "general_2", "service_code": "carga_general",
                "sicetac_configuration": "2", "commercial_label": "C2",
                "priority": 1, "min_operating_weight_kg": 0,
                "max_operating_weight_kg": None, "max_cargo_kg": 9000,
                "axle_count": 2, "provisional": True,
            }],
        })
        result = evaluate_quote({
            "scope_id": "mercado_colombia_tecnico", "request_id": "general-request",
            "cargo_weight_value": 4, "cargo_weight_unit": "t", "service_code": "suelta",
        }, general_ruleset)
        self.assertEqual(result["normalized_input"]["service_code"], "carga_general")
        self.assertEqual(result["normalized_input"]["tare_kg"], 0)

    def test_external_schema_defaults_service_to_general(self):
        schema_path = Path(__file__).resolve().parents[1] / "docs/agent-api-package/tool-schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertNotIn("service_code", schema["required"])
        self.assertEqual(schema["properties"]["service_code"]["default"], "carga_general")


if __name__ == "__main__":
    unittest.main()
