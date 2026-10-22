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
    "configuration_aliases": {
        "C2": "2", "C2S2": "2S2", "C2S3": "2S3",
        "C3S2": "3S2", "C3S3": "3S3",
        "PATINETA": "2S2", "PATINETA 20": "2S2", "PATINETA 40": "2S3",
        "MINIMULA": "3S2", "MULA": "3S3", "TRACTOMULA": "3S3",
        "TRACTOCAMION 3 EJES": "3S3", "TRACTOCAMION DE 3 EJES": "3S3",
    },
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
            "rule_id": "container_2s2_20", "service_code": "contenedor",
            "sicetac_configuration": "2S2", "commercial_label": "C2S2 Patineta 20 pies",
            "priority": 10, "min_operating_weight_kg": None,
            "max_operating_weight_kg": None, "max_cargo_kg": 19700,
            "max_configuration_load_kg": 22000,
            "axle_count": 4, "container_sizes_ft": [20], "provisional": True,
        },
        {
            "rule_id": "container_2s3_20", "service_code": "contenedor",
            "sicetac_configuration": "2S3", "commercial_label": "C2S3 Patineta 20 pies",
            "priority": 20, "min_operating_weight_kg": None,
            "max_operating_weight_kg": None, "max_cargo_kg": 24700,
            "max_configuration_load_kg": 27000,
            "axle_count": 5, "container_sizes_ft": [20], "provisional": True,
        },
        {
            "rule_id": "container_3s2_20", "service_code": "contenedor",
            "sicetac_configuration": "3S2", "commercial_label": "C3S2 Minimula 20 pies",
            "priority": 30, "min_operating_weight_kg": None,
            "max_operating_weight_kg": None, "max_cargo_kg": 28700,
            "max_configuration_load_kg": 31000,
            "axle_count": 5, "container_sizes_ft": [20], "provisional": True,
        },
        {
            "rule_id": "container_3s3_20", "service_code": "contenedor",
            "sicetac_configuration": "3S3", "commercial_label": "C3S3 Mula / Tractomula / Tractocamión 3 ejes 20 pies",
            "priority": 40, "min_operating_weight_kg": None,
            "max_operating_weight_kg": None, "max_cargo_kg": 31700,
            "max_configuration_load_kg": 34000,
            "axle_count": 6, "container_sizes_ft": [20], "provisional": True,
        },
        {
            "rule_id": "container_2s3_40", "service_code": "contenedor",
            "sicetac_configuration": "2S3", "commercial_label": "C2S3 Patineta 40 pies",
            "priority": 10, "min_operating_weight_kg": None,
            "max_operating_weight_kg": None, "max_cargo_kg": 22900,
            "max_configuration_load_kg": 27000,
            "axle_count": 5, "container_sizes_ft": [40], "provisional": True,
        },
        {
            "rule_id": "container_3s2_40", "service_code": "contenedor",
            "sicetac_configuration": "3S2", "commercial_label": "C3S2 Minimula 40 pies",
            "priority": 20, "min_operating_weight_kg": None,
            "max_operating_weight_kg": None, "max_cargo_kg": 26900,
            "max_configuration_load_kg": 31000,
            "axle_count": 5, "container_sizes_ft": [40], "provisional": True,
        },
        {
            "rule_id": "container_3s3_40", "service_code": "contenedor",
            "sicetac_configuration": "3S3", "commercial_label": "C3S3 Mula / Tractomula / Tractocamión 3 ejes 40 pies",
            "priority": 30, "min_operating_weight_kg": None,
            "max_operating_weight_kg": None, "max_cargo_kg": 29900,
            "max_configuration_load_kg": 34000,
            "axle_count": 6, "container_sizes_ft": [40], "provisional": True,
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
        self.assertEqual(result["engine_version"], "1.3.0")
        self.assertEqual(recommendation["sicetac_configuration"], "2S2")
        self.assertEqual(recommendation["selection"], "automatic_operational_default")
        self.assertIsNone(recommendation["pbv_compatible"])
        self.assertEqual(recommendation["pbv_assessment"], "requires_vehicle_tare")
        self.assertEqual(result["normalized_input"]["load_and_container_weight_kg"], 10300)
        self.assertIn("C2S2 para contenedor de 20 pies", result["warnings"][-1])

    def test_container_capacity_20_uses_sicetac_configuration_tonnage_including_tare(self):
        at_limit = self.quote(cargo_weight_value=19.7)
        over_limit = self.quote(cargo_weight_value=19.701)
        self.assertEqual(at_limit["recommendation"]["sicetac_configuration"], "2S2")
        self.assertEqual(at_limit["recommendation"]["max_cargo_kg"], 19700)
        self.assertEqual(at_limit["recommendation"]["max_configuration_load_kg"], 22000)
        self.assertEqual(over_limit["recommendation"]["sicetac_configuration"], "2S3")

    def test_container_capacity_40_prefers_c2s3_and_scales_by_configuration_tonnage(self):
        at_limit = self.quote(container_size_ft=40, cargo_weight_value=22.9)
        over_limit = self.quote(container_size_ft=40, cargo_weight_value=22.901)
        self.assertEqual(at_limit["recommendation"]["sicetac_configuration"], "2S3")
        self.assertEqual(at_limit["recommendation"]["max_configuration_load_kg"], 27000)
        self.assertEqual(over_limit["recommendation"]["sicetac_configuration"], "3S2")

    def test_40_foot_sales_quote_defaults_to_c2s3_and_resolves_generic_patineta(self):
        no_weight = self.quote(container_size_ft=40, cargo_weight_value=None, cargo_weight_unit=None)
        patineta = self.quote(container_size_ft=40, requested_configuration="Patineta")
        self.assertEqual(no_weight["recommendation"]["sicetac_configuration"], "2S3")
        self.assertEqual(no_weight["recommendation"]["max_cargo_kg"], 22900)
        self.assertEqual(patineta["recommendation"]["sicetac_configuration"], "2S3")

    def test_weight_including_40_foot_container_tare_uses_net_cargo_capacity(self):
        result = self.quote(container_size_ft=40, cargo_weight_value=27, weight_includes_tare=True)
        self.assertEqual(result["normalized_input"]["cargo_kg"], 22900)
        self.assertEqual(result["recommendation"]["sicetac_configuration"], "2S3")
        self.assertEqual(result["recommendation"]["max_cargo_kg"], 22900)

    def test_patinetas_resolve_by_container_size_and_commercial_aliases(self):
        self.assertEqual(self.ruleset.normalize_configuration("Patineta", 20), "2S2")
        self.assertEqual(self.ruleset.normalize_configuration("Patineta", 40), "2S3")
        self.assertEqual(self.ruleset.normalize_configuration("Minimula"), "3S2")
        self.assertEqual(self.ruleset.normalize_configuration("Tractocamión de 3 ejes"), "3S3")

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

    def test_general_automatic_selection_includes_the_upper_range_limit(self):
        general_ruleset = load_ruleset({
            **RULESET,
            "vehicle_rules": [
                {
                    "rule_id": "general_2", "service_code": "carga_general",
                    "sicetac_configuration": "2", "commercial_label": "C2",
                    "priority": 1, "min_operating_weight_kg": 0,
                    "max_operating_weight_kg": 10000, "max_cargo_kg": 10000,
                    "axle_count": 2, "provisional": True,
                },
                {
                    "rule_id": "general_3", "service_code": "carga_general",
                    "sicetac_configuration": "3", "commercial_label": "C3",
                    "priority": 2, "min_operating_weight_kg": 10001,
                    "max_operating_weight_kg": 16000, "max_cargo_kg": 16000,
                    "axle_count": 3, "provisional": True,
                },
            ],
        })
        result = evaluate_quote({
            "scope_id": "mercado_colombia_tecnico", "request_id": "limit-10t",
            "cargo_weight_value": 10, "cargo_weight_unit": "t",
        }, general_ruleset)
        self.assertEqual(result["normalized_input"]["service_code"], "carga_general")
        self.assertEqual(result["recommendation"]["sicetac_configuration"], "2")
        self.assertEqual(result["recommendation"]["selection"], "automatic")

    def test_general_load_uses_sice_capacity_not_a_published_pbv_band(self):
        general_ruleset = load_ruleset({
            **RULESET,
            "vehicle_rules": [{
                "rule_id": "general_3s3", "service_code": "carga_general",
                "sicetac_configuration": "3S3", "commercial_label": "C3S3",
                "priority": 1, "min_operating_weight_kg": 32001,
                "max_operating_weight_kg": 34000, "max_cargo_kg": 34000,
                "axle_count": 6, "provisional": True,
            }],
        })
        result = evaluate_quote({
            "scope_id": "mercado_colombia_tecnico", "request_id": "c3s3-32t",
            "cargo_weight_value": 32, "cargo_weight_unit": "t",
            "service_code": "carga_general",
        }, general_ruleset)
        recommendation = result["recommendation"]
        self.assertEqual(recommendation["sicetac_configuration"], "3S3")
        self.assertEqual(recommendation["selection"], "nearest_available_sice_candidate")
        self.assertTrue(recommendation["sice_cargo_compatible"])
        self.assertIsNone(recommendation["pbv_compatible"])
        self.assertEqual(recommendation["pbv_assessment"], "requires_vehicle_tare")
        self.assertNotIn("no encaja", " ".join(result["warnings"]).lower())

    def test_explicit_larger_vehicle_is_valid_and_smaller_weight_option_is_only_a_hint(self):
        general_ruleset = load_ruleset({
            **RULESET,
            "configuration_aliases": {"C3S2": "3S2", "C3S3": "3S3"},
            "vehicle_rules": [
                {
                    "rule_id": "general_3s2", "service_code": "carga_general",
                    "sicetac_configuration": "3S2", "commercial_label": "C3S2",
                    "priority": 1, "min_operating_weight_kg": 0,
                    "max_operating_weight_kg": 30000, "max_cargo_kg": 30000,
                    "axle_count": 5, "provisional": True,
                },
                {
                    "rule_id": "general_3s3", "service_code": "carga_general",
                    "sicetac_configuration": "3S3", "commercial_label": "C3S3",
                    "priority": 2, "min_operating_weight_kg": 32001,
                    "max_operating_weight_kg": 34000, "max_cargo_kg": 34000,
                    "axle_count": 6, "provisional": True,
                },
            ],
        })
        result = evaluate_quote({
            "scope_id": "mercado_colombia_tecnico", "request_id": "c3s3-25t",
            "cargo_weight_value": 25, "cargo_weight_unit": "t",
            "service_code": "carga_general", "requested_configuration": "C3S3",
        }, general_ruleset)
        recommendation = result["recommendation"]
        self.assertEqual(recommendation["selection"], "explicit")
        self.assertTrue(recommendation["sice_cargo_compatible"])
        self.assertEqual(
            recommendation["capacity_only_alternatives"][0]["sicetac_configuration"], "3S2"
        )
        self.assertNotIn("no encaja", " ".join(result["warnings"]).lower())

    def test_declared_vehicle_can_be_quoted_without_inventing_a_cargo_weight(self):
        general_ruleset = load_ruleset({
            **RULESET,
            "configuration_aliases": {"C3S3": "3S3"},
            "vehicle_rules": [{
                "rule_id": "general_3s3", "service_code": "carga_general",
                "sicetac_configuration": "3S3", "commercial_label": "C3S3",
                "priority": 1, "min_operating_weight_kg": 32001,
                "max_operating_weight_kg": 34000, "max_cargo_kg": 34000,
                "axle_count": 6, "provisional": True,
            }],
        })
        result = evaluate_quote({
            "scope_id": "mercado_colombia_tecnico", "request_id": "declared-3s3",
            "service_code": "carga_general", "requested_configuration": "C3S3",
        }, general_ruleset)
        recommendation = result["recommendation"]
        self.assertEqual(recommendation["sicetac_configuration"], "3S3")
        self.assertEqual(recommendation["selection"], "explicit")
        self.assertEqual(recommendation["selection_basis"], "declared_configuration")
        self.assertIsNone(recommendation["sice_cargo_compatible"])
        self.assertIsNone(result["normalized_input"]["cargo_kg"])
        self.assertEqual(result["normalized_input"]["weight_validation"], "not_provided")
        self.assertIn("sin validar", " ".join(result["warnings"]).lower())

    def test_external_schema_defaults_service_to_general(self):
        schema_path = Path(__file__).resolve().parents[1] / "docs/agent-api-package/tool-schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertNotIn("service_code", schema["required"])
        self.assertEqual(schema["properties"]["service_code"]["default"], "carga_general")


if __name__ == "__main__":
    unittest.main()
