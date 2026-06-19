#!/usr/bin/env python
"""
Seed a *running* instance with the bundled example documents.

Unlike scripts/smoke_test.py (which boots the app in-process), this talks to a
live server over HTTP — useful for populating a deployment you can then explore
in the dashboard.

    # start the server in one terminal:
    uvicorn app.main:app --port 8000
    # then, in another:
    python scripts/seed_examples.py --base-url http://localhost:8000 --api-key dev-local-key

Environment variables EKA_BASE_URL and EKA_API_KEY are used as defaults.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest example documents into a running instance.")
    parser.add_argument("--base-url", default=os.environ.get("EKA_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--api-key", default=os.environ.get("EKA_API_KEY", "dev-local-key"))
    parser.add_argument("--namespace", default="demo")
    args = parser.parse_args()

    headers = {"X-API-Key": args.api_key}

    try:
        health = httpx.get(f"{args.base_url}/health", timeout=5.0)
        health.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"Could not reach {args.base_url} — is the server running? ({exc})")
        return 1

    print(f"Seeding namespace '{args.namespace}' at {args.base_url}")
    ok = 0
    for path in sorted(EXAMPLES.iterdir()):
        try:
            resp = httpx.post(
                f"{args.base_url}/v1/documents",
                params={"namespace": args.namespace},
                files={"file": (path.name, path.read_bytes())},
                headers=headers,
                timeout=120.0,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  [FAIL] {path.name}: {exc}")
            continue
        if resp.status_code == 201:
            body = resp.json()
            flag = " (deduplicated)" if body.get("deduplicated") else ""
            print(f"  [ok ] {path.name}: {body['chunk_count']} chunks{flag}")
            ok += 1
        else:
            print(f"  [FAIL] {path.name}: {resp.status_code} {resp.text}")

    print(f"\nDone — {ok}/{len(list(EXAMPLES.iterdir()))} documents ingested.")
    print(f"Open the dashboard at {args.base_url}/dashboard to explore.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
