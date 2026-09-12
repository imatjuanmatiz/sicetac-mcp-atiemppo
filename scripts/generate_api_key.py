#!/usr/bin/env python3
"""Genera una API key y el registro hash que se puede guardar fuera del repo."""

import argparse
import hashlib
import json
import secrets


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera credenciales para un consumidor SICETAC")
    parser.add_argument("consumer_id")
    parser.add_argument("name")
    parser.add_argument("--plan", default="sandbox")
    parser.add_argument("--monthly-quota", type=int, default=1000)
    args = parser.parse_args()

    key = "sk_sicetac_" + secrets.token_urlsafe(32)
    record = {
        "consumer_id": args.consumer_id,
        "name": args.name,
        "plan": args.plan,
        "key_prefix": key[:16],
        "key_hash": hashlib.sha256(key.encode()).hexdigest(),
        "monthly_quota": args.monthly_quota,
        "active": True,
    }
    print("API_KEY (guardar una sola vez):")
    print(key)
    print("\nRegistro sin la clave secreta:")
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
