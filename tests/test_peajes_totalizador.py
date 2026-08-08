from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from peajes_totalizador import TOLL_RULE_VERSION, select_effective_toll, source_manifest, totalize_toll_rows
from sicetac_service import SicetacError, obtener_peajes_detalle


GOLDEN_ROWS = [
    {"RUTA_ID": 12736, "ORDEN": 1, "ID_PEAJE": "143", "NOMBRE_PEAJE": "BETANIA", "VALOR1": 13400, "VALOR2": 17400, "VALOR3": 41000, "VALOR4": 56000, "VALOR5": 61800, "VALOR6": 0, "VALOR7": 0},
    {"RUTA_ID": 12736, "ORDEN": 2, "ID_PEAJE": "142", "NOMBRE_PEAJE": "LA URIBE", "VALOR1": 13400, "VALOR2": 17400, "VALOR3": 41000, "VALOR4": 56000, "VALOR5": 61800, "VALOR6": 0, "VALOR7": 0},
    {"RUTA_ID": 12736, "ORDEN": 3, "ID_PEAJE": "48", "NOMBRE_PEAJE": "COROZAL", "VALOR1": 16200, "VALOR2": 19300, "VALOR3": 19300, "VALOR4": 19300, "VALOR5": 47100, "VALOR6": 58900, "VALOR7": 68100},
    {"RUTA_ID": 12736, "ORDEN": 4, "ID_PEAJE": "213", "NOMBRE_PEAJE": "TUNEL DE LA LINEA QUINDIO", "VALOR1": 13000, "VALOR2": 14600, "VALOR3": 29800, "VALOR4": 37900, "VALOR5": 42900, "VALOR6": 0, "VALOR7": 0},
    {"RUTA_ID": 12736, "ORDEN": 5, "ID_PEAJE": "77", "NOMBRE_PEAJE": "GUALANDAY", "VALOR1": 15300, "VALOR2": 18000, "VALOR3": 42400, "VALOR4": 57000, "VALOR5": 62500, "VALOR6": 0, "VALOR7": 0},
    {"RUTA_ID": 12736, "ORDEN": 6, "ID_PEAJE": "76", "NOMBRE_PEAJE": "CHICORAL", "VALOR1": 16600, "VALOR2": 18300, "VALOR3": 16600, "VALOR4": 21500, "VALOR5": 43700, "VALOR6": 58000, "VALOR7": 64000},
    {"RUTA_ID": 12736, "ORDEN": 7, "ID_PEAJE": "125", "NOMBRE_PEAJE": "CHINAUTA", "VALOR1": 16100, "VALOR2": 17900, "VALOR3": 38000, "VALOR4": 61700, "VALOR5": 70700, "VALOR6": 0, "VALOR7": 0},
    {"RUTA_ID": 12736, "ORDEN": 8, "ID_PEAJE": "126", "NOMBRE_PEAJE": "CHUSACA", "VALOR1": 16100, "VALOR2": 17900, "VALOR3": 38000, "VALOR4": 61700, "VALOR5": 70700, "VALOR6": 0, "VALOR7": 0},
    {"RUTA_ID": 12736, "ORDEN": 9, "ID_PEAJE": "204", "NOMBRE_PEAJE": "RAMAL", "VALOR1": 18500, "VALOR2": 22100, "VALOR3": 22100, "VALOR4": 25400, "VALOR5": 73300, "VALOR6": 100800, "VALOR7": 115200},
    {"RUTA_ID": 12736, "ORDEN": 10, "ID_PEAJE": "169", "NOMBRE_PEAJE": "MONDOÑEDO", "VALOR1": 18500, "VALOR2": 22100, "VALOR3": 22100, "VALOR4": 25400, "VALOR5": 73300, "VALOR6": 100800, "VALOR7": 115200},
]


class TollTotalizerTests(unittest.TestCase):
    def test_golden_route_12736_matches_official_august_totals(self) -> None:
        expected = {
            "2": 194800,
            "3": 467600,
            "2S2": 467600,
            "2S3": 648800,
            "3S2": 648800,
            "3S3": 732900,
        }
        for configuration, total in expected.items():
            with self.subTest(configuration=configuration):
                result = totalize_toll_rows(GOLDEN_ROWS, configuration)
                self.assertEqual(result["total_peajes"], total)
                self.assertEqual(result["cantidad_casetas_unicas"], 10)

        c3s3 = totalize_toll_rows(GOLDEN_ROWS, "3S3")
        categories = [item["categoria_efectiva_label"] for item in c3s3["detalle"]]
        self.assertEqual(categories.count("V"), 6)
        self.assertEqual(categories.count("VII"), 4)

    def test_last_category_zero_falls_back_for_3s3(self) -> None:
        row = {"ID_PEAJE": "1", **{f"VALOR{i}": (i * 10 if i < 7 else 0) for i in range(1, 8)}}
        result = totalize_toll_rows([row], "3S3")
        self.assertEqual(result["detalle"][0]["categoria_efectiva"], 6)
        self.assertEqual(result["detalle"][0]["razon"], "ultima_categoria_disponible_por_caseta")

    def test_last_and_penultimate_zero_fall_back_to_fifth(self) -> None:
        row = {"ID_PEAJE": "1", **{f"VALOR{i}": (i * 10 if i < 6 else 0) for i in range(1, 8)}}
        result = totalize_toll_rows([row], "3S3")
        self.assertEqual(result["detalle"][0]["categoria_efectiva"], 5)

    def test_relative_target_out_of_range_returns_zero(self) -> None:
        row = {"ID_PEAJE": "1", "VALOR1": 10, "VALOR2": 20, "VALOR3": 0, "VALOR4": 0, "VALOR5": 0, "VALOR6": 0, "VALOR7": 0}
        result = totalize_toll_rows([row], "3")
        self.assertIsNone(result["detalle"][0]["categoria_efectiva"])
        self.assertEqual(result["detalle"][0]["valor_efectivo"], 0)
        self.assertEqual(result["detalle"][0]["razon"], "categoria_objetivo_fuera_de_rango")

    def test_only_higher_categories_uses_first_available(self) -> None:
        row = {"ID_PEAJE": "1", "VALOR1": 0, "VALOR2": 0, "VALOR3": 0, "VALOR4": 0, "VALOR5": 50, "VALOR6": 60, "VALOR7": 70}
        result = totalize_toll_rows([row], "3")
        self.assertEqual(result["detalle"][0]["categoria_efectiva"], 5)
        self.assertEqual(result["detalle"][0]["razon"], "categoria_relativa_disponible")

    def test_relative_category_moves_with_maximum_category(self) -> None:
        max_five = {"VALOR1": 10, "VALOR2": 20, "VALOR3": 30, "VALOR4": 40, "VALOR5": 50, "VALOR6": 0, "VALOR7": 0}
        max_six = {**max_five, "VALOR6": 60}
        max_seven = {**max_six, "VALOR7": 70}

        self.assertEqual(select_effective_toll(max_five, "2")["categoria_efectiva"], 2)
        self.assertEqual(select_effective_toll(max_six, "2")["categoria_efectiva"], 3)
        self.assertEqual(select_effective_toll(max_seven, "2")["categoria_efectiva"], 4)
        self.assertEqual(select_effective_toll(max_five, "3S3")["categoria_efectiva"], 5)
        self.assertEqual(select_effective_toll(max_six, "3S3")["categoria_efectiva"], 6)
        self.assertEqual(select_effective_toll(max_seven, "3S3")["categoria_efectiva"], 7)

    def test_missing_relative_target_does_not_fallback_to_another_category(self) -> None:
        row = {"VALOR1": 0, "VALOR2": 0, "VALOR3": 0, "VALOR4": 0, "VALOR5": 0, "VALOR6": 60, "VALOR7": 70}
        result = select_effective_toll(row, "2")
        self.assertEqual(result["categoria_nominal"], 4)
        self.assertIsNone(result["categoria_efectiva"])
        self.assertEqual(result["razon"], "categoria_objetivo_no_disponible")

    def test_all_zero_is_retained_as_zero(self) -> None:
        row = {"ID_PEAJE": "1", **{f"VALOR{i}": 0 for i in range(1, 8)}}
        result = totalize_toll_rows([row], "3S3")
        self.assertEqual(result["total_peajes"], 0)
        self.assertEqual(result["detalle"][0]["razon"], "todas_categorias_cero")

    def test_category_one_only_is_not_valid_for_load_configurations(self) -> None:
        row = {"ID_PEAJE": "196", "VALOR1": 14800, **{f"VALOR{i}": 0 for i in range(2, 8)}}
        result = totalize_toll_rows([row], "3S3")
        self.assertEqual(result["total_peajes"], 0)
        self.assertIsNone(result["detalle"][0]["categoria_efectiva"])
        self.assertEqual(result["detalle"][0]["razon"], "categoria_maxima_insuficiente")

    def test_duplicate_caseta_is_counted_once(self) -> None:
        result = totalize_toll_rows(GOLDEN_ROWS[:1] + GOLDEN_ROWS[:1], "2")
        self.assertEqual(result["cantidad_filas_fuente"], 2)
        self.assertEqual(result["cantidad_casetas_unicas"], 1)
        self.assertEqual(result["duplicados_ignorados"], 1)
        self.assertEqual(result["total_peajes"], 17400)

    def test_empty_route_is_distinct_from_route_with_zero_rows(self) -> None:
        empty = totalize_toll_rows([], "3")
        self.assertEqual(empty["cantidad_filas_fuente"], 0)
        self.assertEqual(empty["total_peajes"], 0)

        zero_row = {"ID_PEAJE": "zero", **{f"VALOR{i}": 0 for i in range(1, 8)}}
        with patch("sicetac_service.get_peajes_detalle_df", return_value=pd.DataFrame([zero_row])), patch(
            "sicetac_service.get_peajes_resumen_df", return_value=pd.DataFrame()
        ):
            response = obtener_peajes_detalle(999, "3")
            self.assertEqual(response["resumen"]["3"]["total_peajes"], 0)

        with patch("sicetac_service.get_peajes_detalle_df", return_value=pd.DataFrame()), patch(
            "sicetac_service.get_peajes_resumen_df", return_value=pd.DataFrame()
        ):
            with self.assertRaises(SicetacError) as context:
                obtener_peajes_detalle(999, "3")
            self.assertEqual(context.exception.status_code, 404)

    def test_repeated_response_is_identical(self) -> None:
        self.assertEqual(totalize_toll_rows(GOLDEN_ROWS, "3S3"), totalize_toll_rows(GOLDEN_ROWS, "3S3"))

    @patch("sicetac_service.get_peajes_resumen_df")
    @patch("sicetac_service.get_peajes_detalle_df")
    def test_api_uses_detail_and_marks_difference_from_old_summary(self, get_detail, get_summary) -> None:
        get_detail.return_value = pd.DataFrame(GOLDEN_ROWS)
        get_summary.return_value = pd.DataFrame([{"configuracion": "C3S3", "total_peajes": 607800}])
        response = obtener_peajes_detalle(12736, "3S3")
        self.assertEqual(response["resumen"]["C3S3"]["total_peajes"], 732900)
        self.assertTrue(response["auditoria"]["discrepante"])
        self.assertEqual(response["auditoria"]["diferencia_vs_anterior"], 125100)
        self.assertEqual(response["auditoria"]["version_regla"], TOLL_RULE_VERSION)

    @patch("sicetac_service.get_peajes_resumen_df")
    @patch("sicetac_service.get_peajes_detalle_df")
    def test_api_builds_each_configuration_when_view_is_unfiltered(self, get_detail, get_summary) -> None:
        rows = pd.DataFrame(
            [
                {"RUTA_ID": 12736, "ORDEN": 1, "ID_PEAJE": "1", "configuracion": "C2", "VALOR1": 10, "VALOR2": 20, "VALOR3": 30, "VALOR4": 40, "VALOR5": 50},
                {"RUTA_ID": 12736, "ORDEN": 1, "ID_PEAJE": "1", "configuracion": "C3S3", "VALOR1": 10, "VALOR2": 20, "VALOR3": 30, "VALOR7": 70},
            ]
        )
        get_detail.return_value = rows
        get_summary.return_value = pd.DataFrame()

        response = obtener_peajes_detalle(12736)

        self.assertEqual(response["resumen"]["C2"]["total_peajes"], 20)
        self.assertEqual(response["resumen"]["C3S3"]["total_peajes"], 70)
        self.assertEqual(response["detalle"][0]["valores"]["C2"], 20)
        self.assertEqual(response["detalle"][0]["valores"]["C3S3"], 70)

    @patch("sicetac_service.get_peajes_detalle_df")
    def test_calculation_path_prefers_deterministic_detail_over_legacy_index(self, get_detail) -> None:
        from sicetac_service import _peaje_total_deterministico

        get_detail.return_value = pd.DataFrame(
            [{"ID_SICE": 12736, "ORDEN": 1, "ID_PEAJE": "1", "VALOR1": 10, "VALOR2": 20, "VALOR3": 30, "VALOR4": 40, "VALOR5": 50}]
        )

        self.assertEqual(_peaje_total_deterministico(12736, "3", fallback=999), 30)

    @patch("sicetac_service.get_peajes_inventario_df")
    @patch("sicetac_service.get_peajes_detalle_df")
    def test_route_link_is_enriched_from_toll_inventory(self, get_detail, get_inventory) -> None:
        get_detail.return_value = pd.DataFrame(
            [{"ID_SICE": 12736, "ORDEN": 1, "ID_PEAJE": "196", "NOMBRE_PEAJE": "LOS SANTOS"}]
        )
        get_inventory.return_value = pd.DataFrame(
            [{"ID_PEAJE": "196", "VALOR1": 14800, "VALOR2": 20000, "VALOR3": 30000, "VALOR4": 40000, "VALOR5": 50000, "VALOR6": 0, "VALOR7": 0}]
        )

        from sicetac_service import _peaje_total_deterministico

        self.assertEqual(_peaje_total_deterministico(12736, "3", fallback=999), 30000)

    @patch("supabase_data._fetch_table_filtered")
    def test_route_detail_can_be_loaded_without_configuration_column(self, fetch_rows) -> None:
        from supabase_data import get_peajes_detalle_df

        fetch_rows.side_effect = [
            [],
            [{"id_sice": 9988, "id_peaje": "196", "orden": 1}],
        ]
        get_peajes_detalle_df.cache_clear()
        result = get_peajes_detalle_df(9988, "3")
        self.assertEqual(result.iloc[0]["id_peaje"], "196")
        self.assertEqual(fetch_rows.call_count, 2)
        get_peajes_detalle_df.cache_clear()

    @patch("sicetac_service.get_peajes_resumen_df")
    @patch("sicetac_service.get_peajes_detalle_df")
    def test_api_exposes_source_manifest_fields_when_loaded(self, get_detail, get_summary) -> None:
        get_detail.return_value = pd.DataFrame(
            [{
                "ID_SICE": 12736,
                "ORDEN": 1,
                "ID_PEAJE": "1",
                "VALOR1": 10,
                "VALOR2": 20,
                "fuente_corte": "2026-08-01",
                "fuente_archivo": "PeajesPorRutasConTarifas_SICETAC_2026-08-01.xlsx",
                "fuente_sha256": "abc123",
                "filas_fuente": 69957,
            }]
        )
        get_summary.return_value = pd.DataFrame()

        response = obtener_peajes_detalle(12736, "2")

        self.assertEqual(response["auditoria"]["fuente_sha256"], "abc123")
        self.assertEqual(response["auditoria"]["filas_fuente"], 69957)


if __name__ == "__main__":
    unittest.main()
