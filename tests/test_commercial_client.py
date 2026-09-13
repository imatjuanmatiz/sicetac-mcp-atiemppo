import asyncio
import hashlib
import json
import os
import unittest
from unittest.mock import Mock, patch

import httpx
from fastapi.testclient import TestClient
import pandas as pd

import commercial_api
import commercial_mcp_server
from commercial_client import CommercialClient, CommercialClientError
from cotizador_core import load_ruleset
from main import app


class ClientTests(unittest.TestCase):
    def test_explicit_vehicle_and_body_type_required_before_network(self):
        client = CommercialClient("https://example.test", "test-only")
        for payload in ({"origen": "A", "destino": "B"}, {"origen": "A", "destino": "B", "vehiculo": "C3"}):
            with self.assertRaises(ValueError):
                client.quote(payload)

    def test_key_requires_encrypted_remote_transport(self):
        for url in ("http://example.test", "https://user:pass@example.test", "https://example.test?key=x"):
            with self.assertRaises(ValueError):
                CommercialClient(url, "test-only")
        CommercialClient("http://localhost:8000", "test-only")

    def test_no_redirect_retry_or_key_in_error(self):
        for status in (302, 401, 429, 503):
            requests = []
            def handler(request):
                requests.append(request)
                return httpx.Response(status, headers={"Location": "https://other.test"}, json={"detail": "test-only-secret"})
            client = CommercialClient("https://example.test", "test-only-secret", transport=httpx.MockTransport(handler))
            with self.assertRaises(CommercialClientError) as ctx:
                client.quote({"origen": "A", "destino": "B", "vehiculo": "C3", "carroceria": "General - Furgon"})
            self.assertEqual(len(requests), 1)
            self.assertEqual(ctx.exception.status_code, status)
            self.assertNotIn("test-only-secret", str(ctx.exception))

    def test_timeout_is_not_retried(self):
        calls = []
        def handler(request):
            calls.append(request)
            raise httpx.ReadTimeout("timeout", request=request)
        client = CommercialClient("https://example.test", "test-only", transport=httpx.MockTransport(handler))
        with self.assertRaises(CommercialClientError):
            client.vehicles()
        self.assertEqual(len(calls), 1)

    def test_successful_transport_with_invalid_json_contract_is_rejected(self):
        for result in ([], {"totales": {"H4": 1}}):
            client = CommercialClient("https://example.test", "test-only", transport=httpx.MockTransport(lambda req: httpx.Response(200, json=result)))
            with self.assertRaises(CommercialClientError):
                client.quote({"origen": "A", "destino": "B", "vehiculo": "C3", "carroceria": "General - Furgon"})

    def test_mcp_to_commercial_api_flow(self):
        # Ejercita catálogo -> herramienta -> cliente HTTP -> FastAPI -> respuesta,
        # con cálculo y fuente de datos simulados y sin acceder a Supabase.
        api = TestClient(app)
        requests = []
        def handler(request):
            requests.append(request.url.path)
            response = api.request(request.method, request.url.path, headers=dict(request.headers), content=request.content)
            return httpx.Response(response.status_code, headers=response.headers, content=response.content)
        client = CommercialClient("https://example.test", "test-only", transport=httpx.MockTransport(handler))
        result = {
            "mes": 202609, "configuracion": "C3",
            "resolved_route": {"route_code": "11001000-5001000"},
            "totales": {"H2": 10, "H4": 20, "H8": 30},
        }
        commercial_api._memory_usage.clear()
        with patch.dict(os.environ, {
            "SICETAC_API_ACCESS_MODE": "api_key", "SICETAC_USAGE_PERSISTENCE": "false",
            "SICETAC_API_CONSUMERS_DB": "false",
            "SICETAC_API_KEYS_JSON": json.dumps([{
                "consumer_id": "test-integration", "key_hash": hashlib.sha256(b"test-only").hexdigest(),
                "active": True, "monthly_quota": 3,
            }]),
        }), patch.object(
            CommercialClient, "from_env", return_value=client
        ), patch.object(commercial_api, "get_table_df", return_value=pd.DataFrame([{"tipo_vehiculo": "C3"}])) , patch.object(
            commercial_api, "calcular_sicetac_resumen", return_value=result
        ) as calculator, patch.object(commercial_api, "get_client", side_effect=AssertionError("No usar base real")):
            self.assertEqual(commercial_mcp_server.listar_vehiculos()["items"][0]["tipo_vehiculo"], "C3")
            quote = commercial_mcp_server.cotizar_sicetac("Bogotá", "Medellín", "C3", "General - Furgon", mes=202609)
            self.assertEqual(quote["data"], result)
            self.assertEqual(quote["meta"]["units"], 1)
            self.assertEqual(calculator.call_args.args[0].vehiculo, "C3")
            self.assertEqual(commercial_mcp_server.consultar_consumo()["used"], 1)
        self.assertEqual(requests, ["/v1/catalog/vehicles", "/v1/quotes", "/v1/usage"])

    def test_mcp_schema_exposes_required_selections_and_quota_effect(self):
        tools = {tool.name: tool for tool in asyncio.run(commercial_mcp_server.mcp.list_tools())}
        self.assertEqual(set(tools), {"listar_vehiculos", "listar_carrocerias", "listar_municipios", "consultar_consumo", "consultar_instrucciones_vigentes", "cotizar_sicetac", "precotizar_transporte", "registrar_termino_para_revision"})
        quote = tools["cotizar_sicetac"]
        self.assertIn("vehiculo", quote.inputSchema["required"])
        self.assertIn("carroceria", quote.inputSchema["required"])
        self.assertFalse(quote.annotations.idempotentHint)
        self.assertFalse(quote.annotations.readOnlyHint)
        prequote = tools["precotizar_transporte"]
        self.assertIn("cargo_weight_value", prequote.inputSchema["required"])
        self.assertIn("cargo_weight_unit", prequote.inputSchema["required"])
        self.assertFalse(prequote.annotations.idempotentHint)
        self.assertTrue(tools["consultar_instrucciones_vigentes"].annotations.readOnlyHint)

    def test_mcp_agent_profile_delegates_without_prequote(self):
        client = Mock()
        client.agent_profile.return_value = {"agent_policy_version": "test"}
        with patch.object(CommercialClient, "from_env", return_value=client):
            result = commercial_mcp_server.consultar_instrucciones_vigentes()
        self.assertEqual(result["agent_policy_version"], "test")
        self.assertEqual(result["client_bridge_version"], commercial_mcp_server.BRIDGE_VERSION)
        client.agent_profile.assert_called_once_with()

    def test_mcp_prequote_to_api_to_core_to_sicetac_flow(self):
        api = TestClient(app)
        paths = []

        def handler(request):
            paths.append(request.url.path)
            response = api.request(request.method, request.url.path, headers=dict(request.headers), content=request.content)
            return httpx.Response(response.status_code, headers=response.headers, content=response.content)

        client = CommercialClient("https://example.test", "test-only", transport=httpx.MockTransport(handler))
        ruleset = load_ruleset({
            "schema_version": 1, "scope_id": "mercado_colombia_tecnico", "ruleset_id": "e2e",
            "version": "1", "status": "published", "source_snapshot_id": "test", "emission_allowed": False,
            "container_tares_kg": {"40": 4100}, "configuration_aliases": {}, "vehicle_equivalences": [],
            "vehicle_rules": [{"rule_id": "c2s2", "service_code": "contenedor", "sicetac_configuration": "2S2", "commercial_label": "C2S2", "priority": 1, "min_operating_weight_kg": 17001, "max_operating_weight_kg": 28000, "max_cargo_kg": 22000, "axle_count": 4, "container_sizes_ft": [40], "provisional": True}],
        })
        commercial_api._memory_usage.clear()
        with patch.dict(os.environ, {
            "SICETAC_API_ACCESS_MODE": "api_key", "SICETAC_USAGE_PERSISTENCE": "false",
            "SICETAC_API_CONSUMERS_DB": "false", "SICETAC_API_KEYS_JSON": json.dumps([{
                "consumer_id": "test-integration", "key_hash": hashlib.sha256(b"test-only").hexdigest(),
                "active": True, "monthly_quota": 3,
            }]),
        }), patch.object(CommercialClient, "from_env", return_value=client), patch.object(
            commercial_api, "load_published_market_ruleset", return_value=ruleset
        ), patch.object(commercial_api, "calcular_sicetac_resumen", return_value={"totales": {"H8": 30}}) as calculator:
            result = commercial_mcp_server.precotizar_transporte(
                "Bogotá", "Medellín", 18, "t", service_code="contenedor", container_size_ft=40, axles=4,
                peajes=False, carroceria="Portacontenedores", modo_viaje="CARGADO", tipo_contenedor="VACIO"
            )
        self.assertEqual(paths, ["/v1/prequotes"])
        self.assertEqual(result["data"]["technical_decision"]["recommendation"]["sicetac_configuration"], "2S2")
        self.assertEqual(calculator.call_args.args[0].vehiculo, "2S2")
        self.assertEqual(calculator.call_args.args[0].tipo_contenedor, "VACIO")

    def test_mcp_prequote_delegates_to_private_client_contract(self):
        client = Mock()
        client.prequote.return_value = {"data": {"technical_decision": {}}, "meta": {}}
        with patch.object(CommercialClient, "from_env", return_value=client):
            result = commercial_mcp_server.precotizar_transporte(
                "Bogotá", "Medellín", 18, "t", service_code="contenedor", container_size_ft=40, axles=4
            )
        self.assertIn("data", result)
        self.assertEqual(client.prequote.call_args.args[0]["cargo_weight_value"], 18)
        self.assertEqual(client.prequote.call_args.args[0]["container_size_ft"], 40)


if __name__ == "__main__":
    unittest.main()
