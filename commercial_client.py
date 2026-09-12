"""Cliente de terceros: consume SICETAC por HTTP sin acceso a la base de datos."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import httpx


class CommercialClientError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class CommercialClient:
    def __init__(self, base_url: str, api_key: str, *, transport=None):
        parsed = urlsplit(base_url)
        local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if (not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment
                or not (parsed.scheme == "https" or (parsed.scheme == "http" and local))):
            raise ValueError("Configura una URL HTTPS sin credenciales; HTTP solo se admite en localhost.")
        if not api_key.strip():
            raise ValueError("Falta SICETAC_API_KEY: configura la clave comercial como secreto.")
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key.strip()
        self._transport = transport

    @classmethod
    def from_env(cls):
        return cls(os.getenv("SICETAC_BASE_URL", ""), os.getenv("SICETAC_API_KEY", ""))

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        try:
            with httpx.Client(timeout=30.0, follow_redirects=False, transport=self._transport) as client:
                response = client.request(
                    method, self.base_url + path,
                    headers={"X-API-Key": self._api_key, "Accept": "application/json"},
                    json=payload,
                )
        except httpx.RequestError:
            raise CommercialClientError(
                "No se pudo confirmar la respuesta de SICETAC. Revisa conectividad y consumo antes de repetir una cotización."
            ) from None
        if response.status_code >= 300:
            messages = {
                401: "Clave comercial inválida, ausente o inactiva.",
                403: "El acceso comercial no permite esta operación.",
                404: "Recurso o combinación no encontrados; comprueba URL, municipios y cobertura.",
                422: "Entrada inválida; revisa los campos según el contrato API.",
                429: "Cuota comercial agotada; consulta con el administrador.",
                503: "Servicio o datos temporalmente no disponibles.",
            }
            raise CommercialClientError(
                messages.get(response.status_code, f"SICETAC respondió HTTP {response.status_code}; revisa el servicio."),
                response.status_code,
            )
        try:
            result = response.json()
        except ValueError:
            raise CommercialClientError("SICETAC devolvió una respuesta que no es JSON.") from None
        if not isinstance(result, dict):
            raise CommercialClientError("La respuesta no cumple el contrato de objeto JSON.")
        return result

    def health(self) -> dict:
        return self._request("GET", "/v1/health")

    def vehicles(self) -> dict:
        return self._request("GET", "/v1/catalog/vehicles")

    def body_types(self) -> dict:
        return self._request("GET", "/v1/catalog/body-types")

    def municipalities(self) -> dict:
        return self._request("GET", "/v1/catalog/municipalities")

    def usage(self) -> dict:
        return self._request("GET", "/v1/usage")

    def quote(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("La consulta debe ser un objeto JSON.")
        for field in ("vehiculo", "carroceria"):
            if not isinstance(payload.get(field), str) or not payload[field].strip():
                raise ValueError(f"Selecciona {field} explícitamente desde el catálogo.")
        for name, code in (("origen", "codigo_dane_origen"), ("destino", "codigo_dane_destino")):
            if not any(isinstance(payload.get(key), str) and payload[key].strip() for key in (name, code)):
                raise ValueError(f"Falta {name} o {code} como texto.")
        result = self._request("POST", "/v1/quotes", payload)
        if not isinstance(result.get("data"), dict) or not isinstance(result.get("meta"), dict):
            raise CommercialClientError("La cotización no contiene data y meta del contrato comercial v1.")
        return result

    def prequote(self, payload: dict) -> dict:
        """Solicita decisión técnica y referencia SICETAC en una sola unidad."""
        if not isinstance(payload, dict):
            raise ValueError("La pre-cotización debe ser un objeto JSON.")
        for name, code in (("origen", "codigo_dane_origen"), ("destino", "codigo_dane_destino")):
            if not any(isinstance(payload.get(key), str) and payload[key].strip() for key in (name, code)):
                raise ValueError(f"Falta {name} o {code} como texto.")
        for field in ("cargo_weight_value", "cargo_weight_unit"):
            if payload.get(field) in (None, ""):
                raise ValueError(f"Falta {field} para aplicar el motor técnico.")
        result = self._request("POST", "/v1/prequotes", payload)
        if not isinstance(result.get("data"), dict) or not isinstance(result.get("meta"), dict):
            raise CommercialClientError("La pre-cotización no contiene data y meta del contrato comercial v1.")
        return result

    def record_term_observation(self, payload: dict) -> dict:
        """Envía una observación pendiente; no altera reglas publicadas."""
        if not isinstance(payload, dict) or not str(payload.get("raw_expression") or "").strip():
            raise ValueError("raw_expression es obligatorio para registrar una observación.")
        return self._request("POST", "/v1/feedback/terms", payload)


def main():
    parser = argparse.ArgumentParser(description="Consultar la API comercial SICETAC.")
    parser.add_argument("action", choices=["health", "vehicles", "body-types", "municipalities", "usage", "quote", "prequote", "feedback-terms"])
    parser.add_argument("--payload", type=Path, help="JSON de entrada; requerido para quote, prequote y feedback-terms.")
    args = parser.parse_args()
    try:
        client = CommercialClient.from_env()
        if args.action in {"quote", "prequote", "feedback-terms"}:
            if not args.payload:
                parser.error(f"{args.action} requiere --payload archivo.json")
            payload = json.loads(args.payload.read_text(encoding="utf-8"))
            result = {"quote": client.quote, "prequote": client.prequote, "feedback-terms": client.record_term_observation}[args.action](payload)
        else:
            result = getattr(client, args.action.replace("-", "_"))()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, CommercialClientError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
