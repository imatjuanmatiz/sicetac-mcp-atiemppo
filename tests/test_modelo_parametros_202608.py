import unittest

import pandas as pd

from modelo_sicetac import (
    TASA_OTROS_COSTOS_CARGADO,
    calcular_modelo_sicetac_extendido,
)
from modelo_sicetac_vacio import (
    TASA_OTROS_COSTOS_VACIO,
    calcular_modelo_sicetac_extendido_vacio,
)
from modelo_utils import canonicalizar_carroceria_costos


class ModeloParametrosAgostoTest(unittest.TestCase):
    def test_tasa_otros_costos_cargado_vigente(self):
        self.assertEqual(TASA_OTROS_COSTOS_CARGADO, 0.224824)

    def test_vacio_usa_tasa_vigente_y_costo_variable_vacio(self):
        self.assertEqual(TASA_OTROS_COSTOS_VACIO, 0.221824)

        parametros = pd.DataFrame([{
            "TIPO_VEHICULO": "CA",
            "MES": 202608,
            "HORAS_HABILES_MES": 230,
            "VALOR COMBUSTIBLE GALÓN ACPM": 11576,
            "COSTOS VARIABLES": 633.528598005,
            "COSTOS VARIABLES VACIO": 621.928801852,
            **{f"vel_{terreno}_vacio": 50 for terreno in ("plano", "ondulado", "montana", "urbano", "afirmado")},
            **{f"consumo_{terreno}_vacio": 20 for terreno in ("plano", "ondulado", "montana", "urbano", "afirmado")},
        }])
        costos = pd.DataFrame([{
            "TIPO_VEHICULO": "CA",
            "MES": 202608,
            "TIPO_CARROCERIA": "GENERAL",
            "COSTO FIJO": 6934693.82,
        }])
        vehiculos = pd.DataFrame([{"TIPO_VEHICULO": "CA", "EJES_CONFIGURACION": "2"}])
        resultado = calcular_modelo_sicetac_extendido_vacio(
            origen="A",
            destino="B",
            configuracion="CA",
            serie=202608,
            distancias={"km_plano": 100, "km_ondulado": 0, "km_montanoso": 0, "km_urbano": 0, "km_despavimentado": 0},
            valor_peaje_manual=0,
            matriz_parametros=parametros,
            matriz_costos_fijos=costos,
            matriz_vehicular=vehiculos,
            rutas_df=pd.DataFrame(),
            peajes_df=pd.DataFrame(),
            carroceria_especial="General - Estacas",
            horas_logisticas=8,
        )
        self.assertEqual(resultado["horas_logisticas"], 0)
        self.assertEqual(resultado["mantenimiento"], round(100 * 621.928801852, 2))
        base = (
            resultado["costo_fijo"] + resultado["combustible"] + resultado["peajes"]
            + resultado["mantenimiento"] + resultado["imprevistos"]
        )
        self.assertEqual(resultado["otros_costos"], round(base * TASA_OTROS_COSTOS_VACIO, 2))

    def test_etiquetas_publicas_resuelven_costos_fijos(self):
        casos = {
            "General - Estacas": "GENERAL",
            "General - Estibas": "ESTIBA",
            "General - Furgon": "FURGON",
            "General - Plataforma": "PLATAFORMA",
            "Granel Sólido - Volco": "GRANEL SOLIDO - VOLCO",
        }
        for entrada, esperado in casos.items():
            with self.subTest(entrada=entrada):
                self.assertEqual(canonicalizar_carroceria_costos(entrada), esperado)

    def test_modelo_usa_tasa_y_carroceria_canonica(self):
        parametros = pd.DataFrame(
            [
                {
                    "TIPO_VEHICULO": "C257",
                    "MES": 202608,
                    "HORAS_HABILES_MES": 230,
                    "VALOR COMBUSTIBLE GALÓN ACPM": 11576,
                    "COSTOS VARIABLES": 633.528598005,
                    **{f"vel_{terreno}_cargado": 50 for terreno in ("plano", "ondulado", "montana", "urbano", "afirmado")},
                    **{f"consumo_{terreno}_cargado": 20 for terreno in ("plano", "ondulado", "montana", "urbano", "afirmado")},
                }
            ]
        )
        costos = pd.DataFrame(
            [
                {
                    "TIPO_VEHICULO": "C257",
                    "MES": 202608,
                    "TIPO_CARROCERIA": "GENERAL",
                    "COSTO FIJO": 7053081.82,
                }
            ]
        )
        vehiculos = pd.DataFrame(
            [{"TIPO_VEHICULO": "C257", "EJES_CONFIGURACION": "2"}]
        )
        resultado = calcular_modelo_sicetac_extendido(
            origen="A",
            destino="B",
            configuracion="C257",
            serie=202608,
            distancias={
                "km_plano": 100,
                "km_ondulado": 0,
                "km_montanoso": 0,
                "km_urbano": 0,
                "km_despavimentado": 0,
            },
            valor_peaje_manual=0,
            matriz_parametros=parametros,
            matriz_costos_fijos=costos,
            matriz_vehicular=vehiculos,
            rutas_df=pd.DataFrame(),
            peajes_df=pd.DataFrame(),
            carroceria_especial="General - Estacas",
            horas_logisticas=0,
        )
        base = (
            resultado["costo_fijo"]
            + resultado["combustible"]
            + resultado["peajes"]
            + resultado["mantenimiento"]
            + resultado["imprevistos"]
        )
        self.assertEqual(resultado["carroceria"], "GENERAL")
        self.assertAlmostEqual(
            resultado["otros_costos"],
            round(base * TASA_OTROS_COSTOS_CARGADO, 2),
            places=2,
        )


if __name__ == "__main__":
    unittest.main()
