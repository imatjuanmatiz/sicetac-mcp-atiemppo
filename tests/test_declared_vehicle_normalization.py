import unittest

from cotizador_core import evaluate_quote, load_ruleset


RULESET = {
    "schema_version": 1,
    "scope_id": "mercado_colombia_tecnico",
    "ruleset_id": "declared-vehicle-normalization",
    "version": "test-1",
    "status": "published",
    "source_snapshot_id": "test-source",
    "emission_allowed": False,
    "container_tares_kg": {},
    "configuration_aliases": {"C2": "2", "C3": "3", "C2S2": "2S2", "C2S3": "2S3", "C3S2": "3S2", "C3S3": "3S3"},
    "body_type_aliases": {"FURGON": "General - Furgon", "FURGON SECO": "General - Furgon"},
    "location_aliases": {
        "ZF SANTANDER": {"municipality": "Floridablanca", "department": "Santander", "dane_code": "68276000"},
        "ZONA FRANCA SANTANDER": {"municipality": "Floridablanca", "department": "Santander", "dane_code": "68276000"},
        "ZONA FRANCA DE RIONEGRO": {"municipality": "Rionegro", "department": "Antioquia", "dane_code": "05615000"},
    },
    "vehicle_equivalences": [],
    "vehicle_rules": [
        {
            "rule_id": "general_3", "service_code": "carga_general",
            "sicetac_configuration": "3", "commercial_label": "Camión C3",
            "priority": 10, "min_operating_weight_kg": 0,
            "max_operating_weight_kg": 17000, "max_cargo_kg": 16000,
            "axle_count": 3, "provisional": True,
        },
        {
            "rule_id": "general_3s3", "service_code": "carga_general",
            "sicetac_configuration": "3S3", "commercial_label": "Tractocamión C3S3",
            "priority": 20, "min_operating_weight_kg": 32001,
            "max_operating_weight_kg": 34000, "max_cargo_kg": 34000,
            "axle_count": 6, "provisional": True,
        },
    ],
}


class DeclaredVehicleNormalizationTests(unittest.TestCase):
    def test_c3s3_resolves_to_3s3_even_when_three_axles_are_also_sent(self):
        result = evaluate_quote({
            "scope_id": "mercado_colombia_tecnico",
            "request_id": "declared-c3s3",
            "service_code": "carga_general",
            "requested_configuration": "C3S3",
            # Este valor puede describir sólo el tracto; no puede degradar el
            # equipo explícito a la regla C3/3.
            "axles": 3,
        }, load_ruleset(RULESET))
        self.assertEqual(result["recommendation"]["sicetac_configuration"], "3S3")
        self.assertEqual(result["recommendation"]["commercial_label"], "Tractocamión C3S3")
        self.assertEqual(result["normalized_input"]["configuration"]["canonical"], "3S3")

    def test_furgon_seco_uses_the_published_body_alias(self):
        ruleset = load_ruleset(RULESET)
        self.assertEqual(ruleset.normalize_body_type("furgón seco"), "General - Furgon")

    def test_zone_alias_resolves_to_the_published_canonical_municipality(self):
        resolved = load_ruleset(RULESET).normalize_location("Zona Franca Santander")
        self.assertEqual(resolved["municipality"], "Floridablanca")
        self.assertEqual(resolved["department"], "Santander")
        self.assertEqual(resolved["dane_code"], "68276000")
        self.assertEqual(resolved["source"], "published_ruleset_alias")

    def test_homonymous_municipality_alias_carries_its_published_dane_code(self):
        resolved = load_ruleset(RULESET).normalize_location("Zona Franca de Rionegro")
        self.assertEqual(resolved["municipality"], "Rionegro")
        self.assertEqual(resolved["department"], "Antioquia")
        self.assertEqual(resolved["dane_code"], "05615000")


if __name__ == "__main__":
    unittest.main()
