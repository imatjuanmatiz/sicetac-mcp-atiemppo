from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from sicetac_service import (
    ConsultaInput,
    SicetacError,
    _attach_valor_plaza,
    _calcular_viaje_redondo_contenedor,
    _carroceria_option,
    _fila_vehiculo,
    _lookup_sicetac_totales,
    _verificar_parametros_modelo,
    _validar_contexto_tipo_contenedor,
    calcular_sicetac,
)
from sicetac_helper import SICETACHelper


class SicetacVacioLookupTests(unittest.TestCase):
    def test_vehicle_catalog_accepts_new_light_range_without_case_sensitivity(self) -> None:
        catalog = pd.DataFrame(
            [{"TIPO_VEHICULO": "C257", "CONFIGURACION_SICETAC_LOOKUP": "2_5_7"}]
        )
        row = _fila_vehiculo(catalog, "c257")
        self.assertEqual(row["TIPO_VEHICULO"], "C257")

    def test_detail_mode_rejects_new_range_without_normative_parameters(self) -> None:
        vehicle = pd.Series({"TIPO_VEHICULO": "C257"})
        params = pd.DataFrame([{"TIPO_VEHICULO": "C3S3", "MES": 202607}])
        costs = pd.DataFrame([{"TIPO_VEHICULO": "C3S3", "MES": 202607}])
        with self.assertRaises(SicetacError) as context:
            _verificar_parametros_modelo(params, costs, vehicle, 202607)
        self.assertEqual(context.exception.status_code, 503)

    def test_dane_code_resolution_accepts_leading_zero(self) -> None:
        helper = SICETACHelper(
            pd.DataFrame(
                [{"codigo_dane": 8560004, "nombre_oficial": "SANTA RITA"}]
            )
        )
        result = helper.buscar_municipio_por_codigo("08560004")
        self.assertEqual(result["codigo_dane"], "8560004")

    def test_all_service_options_map_to_a_vacio_body(self) -> None:
        expected = {
            "General - Estacas": "ESTACAS_VACIO",
            "General - Furgon": "FURGON_VACIO",
            "General - Estibas": "ESTIBAS_VACIO",
            "General - Plataforma": "PLATAFORMA_VACIO",
            "Portacontenedores": "PORTACONTENEDORES_VACIO",
            "Furgon Refrigerado": "FURGON_REFRIGERADO_VACIO",
            "Granel Solido - Estacas": "ESTACAS_VACIO",
            "Granel Solido - Furgon": "FURGON_VACIO",
            "Granel Solido - Volco": "VOLCO_VACIO",
            "Granel Solido - Estibas": "ESTIBAS_VACIO",
            "Granel Solido - Plataforma": "PLATAFORMA_VACIO",
            "Granel Liquido - Tanque": "TANQUE_VACIO",
        }
        for label, column in expected.items():
            with self.subTest(label=label):
                self.assertEqual(_carroceria_option(label)["vacio_column"], column)

    @patch("sicetac_service.get_sicetac_vacio_df")
    def test_vacio_uses_official_value_and_source_hourly_rate(self, get_vacio) -> None:
        get_vacio.return_value = pd.DataFrame(
            [
                {
                    "RUTASID": "154",
                    "PORTACONTENEDORES_VACIO": 2_114_019,
                    "VALORHORA_VACIO": 0,
                }
            ]
        )

        rows = _lookup_sicetac_totales(
            cod_origen_str="76109000",
            cod_destino_str="11001000",
            configuracion_lookup="2S2",
            carroceria="Portacontenedores",
            modo_viaje="VACIO",
            mes_codigo=202607,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["movilizacion"], 2_114_019)
        self.assertEqual(rows[0]["valor_hora"], 0)
        self.assertEqual(
            rows[0]["totales"],
            {"H2": 2_114_019, "H4": 2_114_019, "H8": 2_114_019},
        )
        self.assertEqual(rows[0]["lookup_method"], "lookup_vacio_oficial")
        self.assertEqual(rows[0]["lookup_column"], "portacontenedores_vacio")

    @patch("sicetac_service.get_sicetac_valorhora_df")
    @patch("sicetac_service.get_sicetac_movilizacion_df")
    def test_contenedor_vacio_uses_its_own_official_series(
        self, get_movilizacion, get_valorhora
    ) -> None:
        get_movilizacion.return_value = pd.DataFrame(
            [
                {
                    "RUTASID": "106",
                    "CONTENEDOR_PORTACONTENEDORES_CARGADO": 3_802_629,
                    "CONTENEDOR_PORTACONTENEDORES_VACIO": 3_111_306,
                }
            ]
        )
        get_valorhora.return_value = pd.DataFrame(
            [
                {
                    "CONTENEDOR_PORTACONTENEDORES_CARGADO": 90_704,
                    "CONTENEDOR_PORTACONTENEDORES_VACIO": 90_482,
                }
            ]
        )

        rows = _lookup_sicetac_totales(
            cod_origen_str="11001000",
            cod_destino_str="05001000",
            configuracion_lookup="3S3",
            carroceria="Portacontenedores",
            modo_viaje="CARGADO",
            tipo_contenedor="VACIO",
            mes_codigo=202607,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["movilizacion"], 3_111_306)
        self.assertEqual(rows[0]["valor_hora"], 90_482)
        self.assertEqual(
            rows[0]["totales"],
            {"H2": 3_292_270, "H4": 3_473_234, "H8": 3_835_162},
        )
        self.assertEqual(rows[0]["lookup_method"], "lookup_contenedor_vacio_oficial")
        self.assertEqual(
            rows[0]["lookup_column"], "contenedor_portacontenedores_vacio"
        )

    def test_contenedor_vacio_is_not_a_vehicle_vacio_lookup(self) -> None:
        with self.assertRaises(SicetacError) as context:
            _lookup_sicetac_totales(
                cod_origen_str="11001000",
                cod_destino_str="05001000",
                configuracion_lookup="3S3",
                carroceria="Portacontenedores",
                modo_viaje="VACIO",
                tipo_contenedor="VACIO",
                mes_codigo=202607,
            )
        self.assertIn("modo_viaje=CARGADO", context.exception.detail)

    def test_tipo_contenedor_requires_loaded_portacontenedores(self) -> None:
        with self.assertRaises(SicetacError) as context:
            _validar_contexto_tipo_contenedor(
                ConsultaInput(
                    carroceria="Portacontenedores",
                    modo_viaje="VACIO",
                    tipo_contenedor="VACIO",
                )
            )
        self.assertIn("modo_viaje=CARGADO", context.exception.detail)

    def test_contenedor_vacio_omits_valor_plaza(self) -> None:
        payload = _attach_valor_plaza(
            {},
            resolved_route={"route_code": "11001000-05001000"},
            configuracion_lookup="3S3",
            carroceria="Portacontenedores",
            tipo_contenedor="VACIO",
        )
        self.assertEqual(payload, {"valor_plaza_no_aplica": "CONTENEDOR_VACIO"})

    def test_detalle_no_uses_generic_model_for_tipo_contenedor(self) -> None:
        with self.assertRaises(SicetacError) as context:
            calcular_sicetac(
                ConsultaInput(
                    carroceria="Portacontenedores",
                    modo_viaje="CARGADO",
                    tipo_contenedor="VACIO",
                )
            )
        self.assertIn("resumen=true", context.exception.detail)

    def test_detalle_no_ignores_viaje_redondo(self) -> None:
        with self.assertRaises(SicetacError) as context:
            calcular_sicetac(ConsultaInput(viaje_redondo=True))
        self.assertIn("resumen=true", context.exception.detail)

    @patch("sicetac_service.calcular_sicetac_resumen")
    def test_viaje_redondo_uses_loaded_outbound_and_empty_container_return(
        self, resumen
    ) -> None:
        resumen.side_effect = [
            {
                "origen": "Bogotá",
                "destino": "Medellín",
                "totales": {"H2": 3_984_037, "H4": 4_165_445, "H8": 4_528_261},
            },
            {
                "origen": "Medellín",
                "destino": "Bogotá",
                "totales": {"H2": 3_292_270, "H4": 3_473_234, "H8": 3_835_162},
                "valor_plaza_no_aplica": "CONTENEDOR_VACIO",
            },
        ]

        result = _calcular_viaje_redondo_contenedor(
            ConsultaInput(
                origen="Bogotá",
                destino="Medellín",
                vehiculo="C3S3",
                carroceria="Portacontenedores",
                modo_viaje="CARGADO",
                viaje_redondo=True,
            )
        )

        ida_data, regreso_data = [call.args[0] for call in resumen.call_args_list]
        self.assertEqual(ida_data.tipo_contenedor, "CARGADO")
        self.assertEqual(ida_data.origen, "Bogotá")
        self.assertEqual(ida_data.destino, "Medellín")
        self.assertFalse(ida_data.viaje_redondo)
        self.assertEqual(regreso_data.tipo_contenedor, "VACIO")
        self.assertEqual(regreso_data.origen, "Medellín")
        self.assertEqual(regreso_data.destino, "Bogotá")
        self.assertEqual(regreso_data.modo_viaje, "CARGADO")
        self.assertEqual(
            result["totales"],
            {"H2": 7_276_307.0, "H4": 7_638_679.0, "H8": 8_363_423.0},
        )
        self.assertEqual(result["valor_plaza_regreso_no_aplica"], "CONTENEDOR_VACIO")

    @patch("sicetac_service.calcular_sicetac_resumen")
    def test_viaje_redondo_returns_variants_until_each_route_is_selected(
        self, resumen
    ) -> None:
        resumen.side_effect = [
            {"variantes": [{"RUTASID": "106", "totales": {"H2": 1, "H4": 2, "H8": 3}}]},
            {"variantes": [{"RUTASID": "107", "totales": {"H2": 4, "H4": 5, "H8": 6}}]},
        ]

        result = _calcular_viaje_redondo_contenedor(
            ConsultaInput(
                origen="Bogotá",
                destino="Medellín",
                carroceria="Portacontenedores",
                viaje_redondo=True,
            )
        )

        self.assertTrue(result["requiere_seleccion_ruta"])
        self.assertNotIn("totales", result)
        self.assertEqual(result["ida"]["variantes"][0]["RUTASID"], "106")
        self.assertEqual(result["regreso"]["variantes"][0]["RUTASID"], "107")


if __name__ == "__main__":
    unittest.main()
