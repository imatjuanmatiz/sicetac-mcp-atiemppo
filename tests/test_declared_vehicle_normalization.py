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
    "configuration_aliases": {
        "C2": "2", "C3": "3", "C2S2": "2S2", "C2S3": "2S3", "C3S2": "3S2", "C3S3": "3S3",
        "2S2": "2S2", "2S3": "2S3", "3S2": "3S2", "3S3": "3S3", "2": "2", "3": "3",
        "PATINETA": "2S2", "PATINETA 2S2": "2S2", "PATINETA C2S2": "2S2",
        "TURBO": "2_7_9", "C279": "2_7_9",
        "TRACTOMULA": "3S3", "TRACTO MULA": "3S3",
    },
    "body_type_aliases": {"FURGON": "General - Furgon", "FURGON SECO": "General - Furgon"},
    "location_aliases": {
        "ZF SANTANDER": {"municipality": "Floridablanca", "department": "Santander"},
        "ZONA FRANCA SANTANDER": {"municipality": "Floridablanca", "department": "Santander"},
        "ZONA FRANCA DE RIONEGRO": {"municipality": "Rionegro", "department": "Antioquia"},
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
            "rule_id": "general_2_7_9", "service_code": "carga_general",
            "sicetac_configuration": "2_7_9", "commercial_label": "Turbo C279",
            "priority": 15, "min_operating_weight_kg": 7001,
            "max_operating_weight_kg": 9000, "max_cargo_kg": 4000,
            "axle_count": 2, "vehicle_model_code": "C279", "provisional": True,
        },
        {
            "rule_id": "general_2s2", "service_code": "carga_general",
            "sicetac_configuration": "2S2", "commercial_label": "Patineta C2S2",
            "priority": 18, "min_operating_weight_kg": 17001,
            "max_operating_weight_kg": 28000, "max_cargo_kg": 22000,
            "axle_count": 4, "vehicle_model_code": "C2S2", "provisional": True,
        },
        {
            "rule_id": "general_3s3", "service_code": "carga_general",
            "sicetac_configuration": "3S3", "commercial_label": "Tractocamión C3S3",
            "priority": 20, "min_operating_weight_kg": 32001,
            "max_operating_weight_kg": 34000, "max_cargo_kg": 34000,
            "axle_count": 6, "vehicle_model_code": "C3S3", "provisional": True,
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

    def test_commercial_names_resolve_to_published_sicetac_codes(self):
        ruleset = load_ruleset(RULESET)
        self.assertEqual(ruleset.normalize_configuration("patineta"), "2S2")
        self.assertEqual(ruleset.normalize_configuration("Patineta 2S2"), "2S2")
        self.assertEqual(ruleset.normalize_configuration("C2S2"), "2S2")
        self.assertEqual(ruleset.normalize_configuration("turbo"), "2_7_9")
        self.assertEqual(ruleset.normalize_configuration("C279"), "2_7_9")
        self.assertEqual(ruleset.normalize_configuration("tractomula"), "3S3")
        self.assertEqual(ruleset.normalize_configuration("C3S3"), "3S3")

    def test_patineta_quotes_as_c2s2_without_net_weight(self):
        result = evaluate_quote({
            "scope_id": "mercado_colombia_tecnico",
            "request_id": "patineta-c2s2",
            "service_code": "carga_general",
            "requested_configuration": "Patineta",
        }, load_ruleset(RULESET))
        self.assertEqual(result["recommendation"]["sicetac_configuration"], "2S2")
        self.assertEqual(result["recommendation"]["vehicle_model_code"], "C2S2")
        self.assertEqual(result["normalized_input"]["configuration"]["canonical"], "2S2")

    def test_furgon_seco_uses_the_published_body_alias(self):
        ruleset = load_ruleset(RULESET)
        self.assertEqual(ruleset.normalize_body_type("furgón seco"), "General - Furgon")

    def test_zone_alias_resolves_to_the_published_canonical_municipality(self):
        resolved = load_ruleset(RULESET).normalize_location("Zona Franca Santander")
        self.assertEqual(resolved["municipality"], "Floridablanca")
        self.assertEqual(resolved["department"], "Santander")
        self.assertEqual(resolved["source"], "published_ruleset_alias")

    def test_homonymous_municipality_alias_carries_its_published_department(self):
        resolved = load_ruleset(RULESET).normalize_location("Zona Franca de Rionegro")
        self.assertEqual(resolved["municipality"], "Rionegro")
        self.assertEqual(resolved["department"], "Antioquia")


if __name__ == "__main__":
    unittest.main()
