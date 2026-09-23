"""Full-model arithmetic and matching traditional totals for direct detail requests."""
import unittest
from unittest.mock import patch
import pandas as pd
from fastapi.testclient import TestClient
from main import app
import sicetac_service as svc
from modelo_utils import costo_fijo_vigente
from commercial_api import PrequoteInput, _prequote_sicetac_input, _search_card
import commercial_mcp_server as mcp


class CostDetailTests(unittest.TestCase):
    def setUp(self):
        params = {"TIPO_VEHICULO": "C3S3", "MES": 202609,
                  "HORAS_HABILES_MES": 230, "VALOR COMBUSTIBLE GALÓN ACPM": 12000,
                  "COSTOS VARIABLES": 1000, "COSTOS VARIABLES VACIO": 800}
        for mode in ("cargado", "vacio"):
            for terreno, velocity, efficiency in [("plano",60,6), ("ondulado",30,3), ("montana",20,2), ("urbano",15,1.5), ("afirmado",10,1)]:
                params[f"vel_{terreno}_{mode}"] = velocity
                params[f"consumo_{terreno}_{mode}"] = efficiency
        self.fixed = pd.DataFrame([
            {"TIPO_VEHICULO":"C3S3", "MES":202608, "TIPO_CARROCERIA":"GENERAL", "COSTO FIJO":23000000},
            {"TIPO_VEHICULO":"C3S3", "MES":202610, "TIPO_CARROCERIA":"GENERAL", "COSTO FIJO":99000000},
            {"TIPO_VEHICULO":"C3S3", "MES":202609, "TIPO_CARROCERIA":"FURGON", "COSTO FIJO":88000000},
        ])
        route = {"CODIGO_DANE_ORIGEN":11001000, "CODIGO_DANE_DESTINO":8001000,
                 "ID_SICE":"93", "NOMBRE_SICE":"BOGOTA-BARRANQUILLA", "RUTA":"BOGOTA-BARRANQUILLA",
                 "KM_PLANO":60,"KM_ONDULADO":30,"KM_MONTAÑOSO":20,"KM_URBANO":15,"KM_DESPAVIMENTADO":10}
        self.routes=pd.DataFrame([route])
        municipalities=pd.DataFrame([{"codigo_dane":11001000,"nombre_oficial":"BOGOTA"},{"codigo_dane":8001000,"nombre_oficial":"BARRANQUILLA"}])
        self.frames=[municipalities,pd.DataFrame([{"TIPO_VEHICULO":"C3S3","EJES_CONFIGURACION":"6"}]),pd.DataFrame([params]),self.fixed,pd.DataFrame(),self.routes,pd.DataFrame(),pd.DataFrame()]
        for name,value in [("_refresh_cache",None),("_get_dataframes",self.frames),("get_peajes_detalle_df",pd.DataFrame()),("_attach_valor_plaza",None),("_lookup_sicetac_totales",[])]:
            patcher=patch.object(svc,name,return_value=value);patcher.start();self.addCleanup(patcher.stop)
        for name in ("_RUTAS_INDEX","_PEAJES_INDEX"):
            patcher=patch.object(svc,name,None);patcher.start();self.addCleanup(patcher.stop)
        self.client=TestClient(app)

    def request(self, **kwargs):
        payload={"origen":"BOGOTA","destino":"BARRANQUILLA","vehiculo":"C3S3","carroceria":"GENERAL","mes":202609,"detalle_costos":True,**kwargs}
        response=self.client.post('/consulta',json=payload)
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def test_full_model_reconciles_and_does_not_use_published_total(self):
        with patch.object(svc,'_lookup_sicetac_totales',return_value=[self.published()]):
            r=self.request(horas_logisticas=6)
        self.assertEqual(r['sicetac_tradicional']['total_viaje'],1600)
        self.assertNotEqual(r['detalle_costos']['total_viaje'],1600)
        c=r['detalle_costos']; terrains=r['detalle_consumo']['por_terreno']
        self.assertEqual(r['total_km'],135)
        self.assertEqual(c['total_galones'],50)
        self.assertEqual(c['combustible'],600000)
        self.assertEqual(c['horas_recorrido'],5)
        self.assertEqual(c['horas_logisticas'],6)
        self.assertEqual(c['rotaciones_calculadas'],round(230/11,4))
        self.assertEqual(c['mes_costo_fijo'],202608)
        self.assertEqual(c['peajes'],0)
        self.assertEqual(sum(v['costo_combustible'] for v in terrains.values()),600000)
        self.assertAlmostEqual(c['costos_variables'],sum(c[k] for k in ['combustible','peajes','mantenimiento','imprevistos']),places=2)
        self.assertAlmostEqual(c['total_viaje'],c['costo_fijo']+c['costos_variables']+c['otros_costos'],places=2)
        self.assertEqual(c['total_viaje'],r['totales']['H6'])

    @staticmethod
    def published(rutasid='93', base=1000):
        return {"rutasid":rutasid,"mes_codigo":202609,"totales":{"H2":base+200,"H4":base+400,"H8":base+800},"lookup_method":"lookup_consolidado","movilizacion":base,"valor_hora":100,"lookup_column":"GENERAL","lookup_label":"General"}

    def test_direct_details_include_traditional_total_with_selected_hours(self):
        for field in ('detalle_costos','detalle_consumo'):
            for hours, expected in [(None,1400),(0,1000),(6,1600),(2.5,1250)]:
                with self.subTest(field=field,hours=hours), patch.object(svc,'_lookup_sicetac_totales',return_value=[self.published()]):
                    r=self.request(**{'detalle_costos':False,field:True,'horas_logisticas':hours})
                    ref=r['sicetac_tradicional']
                    self.assertEqual(ref['total_viaje'],expected)
                    self.assertEqual(ref['horas_logisticas'],4 if hours is None else hours)
                    self.assertEqual(ref['rutasid'],'93')
                    self.assertEqual(ref['mes'],202609)
                    self.assertFalse(ref['estimado'])
                    self.assertEqual(_search_card(r,None,None,hours)['sicetac'],expected)
                    text=self.client.post('/consulta_texto',json={'origen':'BOGOTA','destino':'BARRANQUILLA','vehiculo':'C3S3','mes':202609,field:True,'horas_logisticas':hours}).json()['texto']
                    self.assertIn(f"Total SICETAC: ${expected:,}".replace(',','.'),text)
                    self.assertNotIn("Total modelo:",text)
                    self.assertEqual(text.count("Total SICETAC:"),1)

    def test_traditional_total_matches_each_variant_not_the_primary(self):
        self.frames[5]=pd.concat([self.routes,self.routes.assign(ID_SICE='94',KM_PLANO=120)],ignore_index=True)
        with patch.object(svc,'_lookup_sicetac_totales',return_value=[self.published('94',2000),self.published('93',1000)]):
            r=self.request()
            self.assertEqual(r['sicetac_tradicional']['total_viaje'],1400)
            self.assertEqual([v['sicetac_tradicional']['total_viaje'] for v in r['variantes']],[1400,2400])
            selected=self.request(rutasid='94')
            self.assertEqual(selected['sicetac_tradicional']['total_viaje'],2400)
            self.assertEqual(selected['sicetac_tradicional']['rutasid'],'94')

    def test_traditional_fallback_and_urban_remain_estimates(self):
        for kwargs in ({},{'destino':'BOGOTA'}):
            with self.subTest(kwargs=kwargs):
                r=self.request(horas_logisticas=6,**kwargs)
                ref=r['sicetac_tradicional']
                self.assertTrue(ref['estimado'])
                self.assertEqual(ref['total_viaje'],r['detalle_costos']['total_viaje'])
                self.assertEqual(ref['metodo'],'modelo_completo')

    def test_zero_logistic_hours_is_preserved(self):
        r=self.request(horas_logisticas=0)
        self.assertEqual(r['detalle_costos']['horas_logisticas'],0)
        self.assertEqual(r['detalle_costos']['total_viaje'],r['totales']['H0'])

    def test_urban_summary_uses_thirty_undulating_km_and_no_tolls(self):
        with patch.object(svc,'_lookup_sicetac_totales',side_effect=AssertionError('no urban lookup')):
            r=self.request(destino='BOGOTA',detalle_costos=False)
        self.assertTrue(r['estimado'])
        self.assertEqual(r['total_km'],30)
        c=r['detalle_costos'];t=r['detalle_consumo']['por_terreno']
        self.assertEqual(t['ondulado']['km'],30)
        self.assertEqual(t['urbano']['km'],0)
        self.assertEqual(c['total_galones'],10)
        self.assertEqual(c['horas_recorrido'],1)
        self.assertEqual(c['peajes'],0)
        self.assertAlmostEqual(c['costo_fijo'],500000,places=2)
        self.assertEqual(c['total_viaje'],798891.45)

    def test_empty_vehicle_has_no_logistic_hours(self):
        r=self.request(modo_viaje='VACIO',horas_logisticas=6)
        self.assertEqual(r['detalle_costos']['horas_logisticas'],0)
        self.assertEqual(r['totales']['H2'],r['totales']['H8'])

    def test_variant_selection_retains_correct_distance(self):
        self.frames[5]=pd.concat([self.routes,self.routes.assign(ID_SICE='94',KM_PLANO=120)],ignore_index=True)
        r=self.request(rutasid='94')
        self.assertEqual(r['rutasid'],'94')
        self.assertEqual(r['total_km'],195)
        r=self.request()
        self.assertEqual(r['rutasid'],'93')
        self.assertEqual(r['total_km'],135)
        self.assertEqual(r['variantes'][1]['total_km'],195)

    def test_summary_adds_km_without_changing_published_totals(self):
        row={"rutasid":"93","mes_codigo":202609,"totales":{"H2":1,"H4":2,"H8":3},"lookup_method":"lookup_oficial","movilizacion":0,"valor_hora":1,"lookup_column":"GENERAL","lookup_label":"General"}
        with patch.object(svc,'_lookup_sicetac_totales',return_value=[row]):
            r=self.request(detalle_costos=False)
        self.assertEqual(r['total_km'],135)
        self.assertEqual(r['totales'],row['totales'])
        self.assertNotIn('detalle_costos',r)

    def test_fixed_cost_applies_by_body_and_without_future_values(self):
        self.assertEqual(costo_fijo_vigente(self.fixed,'C3S3',202609,'GENERAL'),(23000000,202608))
        with self.assertRaises(ValueError):
            costo_fijo_vigente(self.fixed,'C3S3',202607,'GENERAL')

    def test_prequote_views_trigger_full_model_and_keep_context(self):
        for view,field in [('costs','detalle_costos'),('consumption','detalle_consumo')]:
            p=_prequote_sicetac_input(PrequoteInput(view=view,rutasid='93',horas_logisticas=6,mes=202609),'C3S3')
            self.assertTrue(getattr(p,field))
            self.assertEqual(p.rutasid,'93')
            self.assertEqual(p.horas_logisticas,6)
        card=_search_card(self.request(destino='BOGOTA'),None,None)
        self.assertEqual(card['kilometros'],30)
        self.assertTrue(card['estimado'])

    def test_mcp_actions_call_api_with_the_full_context(self):
        with patch.object(mcp.CommercialClient,'from_env') as client:
            for method,field in [(mcp.detalle_costos_sicetac,'detalle_costos'),(mcp.detalle_consumo_sicetac,'detalle_consumo')]:
                method('BOGOTA','BARRANQUILLA','C3S3',mes=202609,rutasid='93',horas_logisticas=6)
                payload=client.return_value.quote.call_args.args[0]
                self.assertTrue(payload[field]);self.assertFalse(payload['resumen'])
                self.assertEqual(payload['rutasid'],'93');self.assertEqual(payload['horas_logisticas'],6)

    def test_mcp_through_authenticated_api_executes_model(self):
        import hashlib, json, os, httpx
        from commercial_client import CommercialClient
        import commercial_api
        requests = []
        def transport(request):
            requests.append(request.url.path)
            response = self.client.request(request.method, request.url.path, headers=dict(request.headers), content=request.content)
            return httpx.Response(response.status_code, content=response.content, headers=response.headers)
        client=CommercialClient("https://example.test", "cost-detail-test", transport=httpx.MockTransport(transport))
        commercial_api._memory_usage.clear()
        with patch.dict(os.environ, {
            "SICETAC_API_ACCESS_MODE":"api_key", "SICETAC_API_CONSUMERS_DB":"false", "SICETAC_USAGE_PERSISTENCE":"false",
            "SICETAC_API_KEYS_JSON":json.dumps([{"consumer_id":"cost-detail-test", "key_hash":hashlib.sha256(b"cost-detail-test").hexdigest(),"active":True,"monthly_quota":10}])
        }), patch.object(mcp.CommercialClient, "from_env", return_value=client):
            result=mcp.detalle_costos_sicetac("BOGOTA","BOGOTA","C3S3",mes=202609)
        self.assertEqual(requests,["/v1/quotes"])
        self.assertEqual(result["data"]["detalle_costos"]["total_viaje"],798891.45)
        self.assertTrue(result["data"]["estimado"])
        self.assertEqual(result["meta"]["units"],1)

    def test_transient_table_error_does_not_poison_catalog_cache(self):
        import supabase_data
        supabase_data.get_table_df.cache_clear()
        self.addCleanup(supabase_data.get_table_df.cache_clear)
        with patch.object(supabase_data,'_fetch_table_all',side_effect=[RuntimeError('transient network error'),[{'tipo_vehiculo':'C3S3','mes_codigo':202608,'costo_fijo':23000000}]] ) as fetch:
            self.assertTrue(supabase_data.get_table_df('costos_fijos').empty)
            self.assertFalse(supabase_data.get_table_df('costos_fijos').empty)
            self.assertFalse(supabase_data.get_table_df('costos_fijos').empty)
        self.assertEqual(fetch.call_count,2)
