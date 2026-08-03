import unittest
from unittest.mock import patch

from sicetac_service import (
    ConsultaInput,
    SicetacError,
    _variacion_total_sicetac,
    calcular_sicetac,
    calcular_sicetac_resumen,
)


class ModoAumentoTests(unittest.TestCase):
    def test_variacion_calcula_diferencia_y_porcentaje(self):
        resultado = _variacion_total_sicetac(112.34, 100, hora="H4")
        self.assertEqual(resultado["aumento_cop"], 12.34)
        self.assertEqual(resultado["aumento_pct"], 12.34)
        self.assertTrue(resultado["disponible"])

    @patch("sicetac_service._calcular_sicetac_resumen_base")
    def test_modo_aumento_compara_respuesta_actual_con_diciembre(self, base):
        base.side_effect = [
            {
                "configuracion": "C3S3",
                "configuracion_analisis": "C3S3",
                "mes": 202608,
                "metodo": "lookup_consolidado",
                "totales": {"H2": 110, "H4": 130, "H8": 170},
            },
            {
                "configuracion": "C3S3",
                "configuracion_analisis": "C3S3",
                "mes": 202512,
                "metodo": "lookup_consolidado",
                "totales": {"H2": 100, "H4": 100, "H8": 150},
            },
        ]
        respuesta = calcular_sicetac_resumen(
            ConsultaInput(vehiculo="C3S3", modo_aumento=True)
        )
        self.assertEqual(respuesta["aumento"]["periodo_base"], 202512)
        self.assertEqual(respuesta["aumento"]["aumento_pct"]["H4"], 30.0)
        self.assertEqual(respuesta["aumento"]["aumento_pct"]["H8"], 13.33)
        self.assertEqual(base.call_args_list[1].args[0].mes, 202512)
        self.assertFalse(base.call_args_list[1].args[0].modo_aumento)

    @patch("sicetac_service._calcular_sicetac_resumen_base")
    def test_modo_aumento_asocia_variantes_por_rutasid(self, base):
        base.side_effect = [
            {
                "configuracion_analisis": "C2S2",
                "mes": 202608,
                "metodo": "lookup_consolidado",
                "variantes": [
                    {"RUTASID": "20", "totales": {"H4": 220, "H8": 320}},
                    {"RUTASID": "10", "totales": {"H4": 110, "H8": 160}},
                ],
            },
            {
                "configuracion_analisis": "C2S2",
                "mes": 202512,
                "metodo": "lookup_consolidado",
                "variantes": [
                    {"RUTASID": "10", "totales": {"H4": 100, "H8": 150}},
                    {"RUTASID": "20", "totales": {"H4": 200, "H8": 300}},
                ],
            },
        ]
        respuesta = calcular_sicetac_resumen(
            ConsultaInput(vehiculo="C2S2", modo_aumento=True)
        )
        por_id = {v["RUTASID"]: v["aumento"] for v in respuesta["variantes"]}
        self.assertEqual(por_id["10"]["aumento_pct"]["H4"], 10.0)
        self.assertEqual(por_id["20"]["aumento_pct"]["H8"], 6.67)

    @patch("sicetac_service._calcular_sicetac_resumen_base")
    def test_configuracion_nueva_informa_que_no_hay_base_historica(self, base):
        base.return_value = {
            "configuracion_analisis": "2_5_7",
            "mes": 202608,
            "totales": {"H4": 100, "H8": 150},
        }
        respuesta = calcular_sicetac_resumen(
            ConsultaInput(vehiculo="C257", modo_aumento=True)
        )
        self.assertFalse(respuesta["aumento"]["disponible"])
        base.assert_called_once()

    def test_modo_aumento_no_se_mezcla_con_detalle(self):
        with self.assertRaises(SicetacError):
            calcular_sicetac(ConsultaInput(resumen=False, modo_aumento=True))


if __name__ == "__main__":
    unittest.main()
